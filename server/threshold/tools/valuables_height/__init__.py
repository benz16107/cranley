"""Valuables height: what sits below the water line, from the panoramas, with heights off the floor and a loss range."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from pydantic import Field
from shapely.geometry import Point

from ...geometry._plan import floor_z, polygons, room_floor_z
from .. import (
    Action,
    Assumption,
    Check,
    Finding,
    Metric,
    Pin,
    PinsOverlay,
    PointAnchor,
    ScanScope,
    Source,
    ToolResult,
    Verdict,
    tool,
)
from ..flood_rehearsal.scenario import FloodInputs, check_plan, room_depth_at
from ..flood_rehearsal.scenario import run as flood_run
from ..types import Media, PanoAnchor, WaterOverlay

UTILITIES = ["electrical panel", "water heater", "furnace or air handler", "washer", "dryer", "outlet near the floor",
             "refrigerator"]
UTILITY_NAME = {"electrical panel": "Electrical panel", "water heater": "Water heater",
                "furnace or air handler": "Furnace or air handler", "washer": "Washer", "dryer": "Dryer",
                "outlet near the floor": "Low outlet", "refrigerator": "Refrigerator"}
COST = {"under $100": (20, 100), "$100 to $500": (100, 500), "$500 to $2,000": (500, 2000),
        "$2,000 to $10,000": (2000, 10000), "over $10,000": (10000, 30000)}
CARRY = {"hand-held": 1, "one person carries": 1, "two people carry": 2, "needs a mover or is built in": 0}
WICK_M = 0.02    # water this far above an item's base reaches it
ROOM_ORDER = ["Living Room", "Family Room", "Kitchen", "Garage", "Laundry", "Utility Room", "Office", "Bedroom",
              "Dining Room", "Game Room", "Entrance", "Hallway"]
VISION = Source(layer="model", method="vision", confidence="low",
                note="Vision model inventory of the furnished panorama; cost and carry are classes it chose")
HEIGHT = Source(layer="matterport", method="geometry", confidence="medium",
                note="Height where the ray through the bottom of the item's box meets the room's walls or floor")


class Inputs(FloodInputs):
    max_rooms: int = Field(8, ge=1, le=12, description="Most rooms to read with the vision model")


def rooms_to_read(plan: dict, flood: dict, n: int) -> list[dict]:
    """Rooms that can take water (lowest floor first, deepest first) that have a panorama to read."""
    from ...vision.reader import room_panos
    rz = room_floor_z(plan)
    low = min(rz.values(), default=0.0)
    cand = [r for r in plan["rooms"] if r.get("label") != "Void" and room_panos(plan, r)
            and (room_depth_at(flood, r["id"], "hi") > 0 or rz[r["id"]] < low + 0.5)]

    def rank(r):
        lab = r.get("label") or ""
        return (-room_depth_at(flood, r["id"], "hi"), ROOM_ORDER.index(lab) if lab in ROOM_ORDER else len(ROOM_ORDER))
    return sorted(cand, key=rank)[:n]


def _room_of(plan: dict, point, fallback: str | None, polys) -> str | None:
    if point is None:
        return fallback
    pt = Point(point[:2])
    for r in plan["rooms"]:
        p = polys.get(r["id"])
        if p is not None and p.buffer(0.1).contains(pt) and r.get("label") != "Void":
            return r["id"]
    return fallback


def _height(plan, rz, polys, anchor: dict, room: str | None) -> tuple[float | None, str | None]:
    if "point" not in anchor:
        return None, room
    rid = _room_of(plan, anchor["point"], room, polys)
    floor = next((r["floor"] for r in plan["rooms"] if r["id"] == rid), None)
    if abs(anchor["point"][2] - floor_z(plan).get(floor, 0.0)) < 0.02:
        return 0.0, rid  # the ray met the floor plane; in a sunken room the item still stands on that room's floor
    return max(0.0, anchor["point"][2] - rz.get(rid, 0.0)), rid


def inventory(plan: dict, flood: dict, max_rooms: int, steps, *, contents=None, find_objects=None) -> dict:
    """Belongings and utilities in the rooms that can flood, each with height, value class, carry class, and whether
    the water reaches it at the low, middle and high water level."""
    if contents is None:
        from ...vision.reader import contents, find_objects, room_panos
    else:
        from ...vision.reader import room_panos
    rooms = rooms_to_read(plan, flood, max_rooms)
    if not rooms:
        return {"items": [], "utilities": [], "rooms_read": [], "reason": "No room that can take water has a panorama."}
    steps(f"Reading {len(rooms)} rooms with the vision model: " + ", ".join(r.get("label") or "unlabelled" for r in rooms))
    rz, polys = room_floor_z(plan), polygons(plan)
    with ThreadPoolExecutor(3) as ex:
        inv = list(ex.map(lambda r: contents(plan, r["id"]), rooms))
    panos = [room_panos(plan, r)[0]["id"] for r in rooms]
    found = find_objects(plan, labels=UTILITIES, panos=panos, max_panos=len(panos))
    items, utils = [], []
    for r, c in zip(rooms, inv):
        for i, it in enumerate(c["items"]):
            h, rid = _height(plan, rz, polys, it["anchor"], r["id"])
            lo, hi = COST[it["cost_class"]]
            items.append({"id": f"{r['id']}:{i}", "name": it["name"], "category": it["category"], "count": it["count"],
                          "fixture": it["fixture"], "size_class": it["size_class"], "cost_class": it["cost_class"],
                          "cost": (lo * it["count"], hi * it["count"]), "carry_people": CARRY[it["size_class"]],
                          "confidence": it["confidence"], "room": rid, "height_m": h, "anchor": it["anchor"],
                          "media": it["media"], "pano": c["pano"]})
    for j, o in enumerate(found):
        f = o["finding"]
        h, rid = _height(plan, rz, polys, f["anchor"], o["room"])
        utils.append({"id": f"u{j}", "label": o["label"], "name": UTILITY_NAME[o["label"]], "room": rid, "height_m": h,
                      "anchor": f["anchor"], "pano_anchor": o["pano_anchor"], "media": f["media"],
                      "confidence": f["source"]["confidence"]})
    for x in items + utils:
        for k in ("lo", "mid", "hi"):
            d = room_depth_at(flood, x["room"], k)
            x[f"wet_{k}"] = d > 0 and (x["height_m"] is None or d > x["height_m"] + WICK_M)
        if x["height_m"] is None:                                   # an unknown height counts only at the high end
            x["wet_lo"] = x["wet_mid"] = False
    steps(f"Found {len(items)} belongings and fixtures and {len(utils)} utilities; "
          f"{sum(1 for x in items if x['height_m'] is not None)} items placed in 3D")
    return {"items": items, "utilities": utils, "rooms_read": [r["id"] for r in rooms],
            "defurnished": bool(plan.get("has", {}).get("defurnished"))}


def losses(items: list[dict]) -> dict:
    out = {}
    for kind, sel in (("belongings", lambda x: not x["fixture"]), ("fixtures", lambda x: x["fixture"])):
        xs = [x for x in items if sel(x)]
        out[kind] = (sum(x["cost"][0] for x in xs if x["wet_lo"]), sum(x["cost"][1] for x in xs if x["wet_hi"]))
    return out


def money(x: float) -> str:
    return f"${x:,.0f}"


@tool(id="valuables_height", title="What sits below the water", icon="sofa",
      summary="Finds the belongings, appliances, outlets and utilities in the rooms that flood, how high each sits off "
              "the floor, and what the water would cost, as a range.",
      model_description="Inventory the rooms that can flood in one scanned house from its panoramas (vision model, "
                        "cached), with each item's height off the floor, replacement-cost class and whether a person can "
                        "carry it; electrical panel, water heater, furnace, washer, dryer and low outlets with heights. "
                        "Totals the loss at the flood scenario as a low-high range. Pins every item.",
      personas=["houston_homeowner_storm", "insurance_underwriter"],
      requires=[{"layer": "matterport.panoramas"}, {"layer": "matterport.rooms"},
                {"layer": "matterport.defurnished", "need": "optional"}],
      blocks=["VerdictHeader", "MetricRow", "Controls", "CheckList", "EvidenceStrip", "FloorPlanMini", "AssumptionChips",
              "StepLog", "ActionBar"],
      overlays=["pins", "water"], annotations={"cost": "slow"},
      examples=["What would I lose at two feet of water?", "Is the water heater high enough?"])
def run(ctx, inputs: Inputs) -> ToolResult:
    sid = inputs.scan
    plan = ctx.plan(sid)
    check_plan(plan)
    flood = flood_run(plan, inputs, ctx.step)
    inv = inventory(plan, flood, inputs.max_rooms, ctx.step)
    return result(sid, plan, inputs, flood, inv)


def result(sid: str, plan: dict, inputs: Inputs, flood: dict, inv: dict) -> ToolResult:
    items, utils = inv["items"], inv["utilities"]
    labels = {r["id"]: r.get("label") or "unlabelled room" for r in plan["rooms"]}
    lv = flood["levels"]
    if not items and not utils:
        return ToolResult(scope=ScanScope(sid=sid), verdict=Verdict(
            status="unknown", text=inv.get("reason") or "The panoramas showed nothing to list in the rooms that flood."),
            overlays=[WaterOverlay(level_m=round(lv["mid"], 3))])
    loss = losses(items)
    under = [x for x in items if x["wet_mid"] and not x["fixture"]]
    maybe = [x for x in items if x["wet_hi"] and not x["wet_mid"] and not x["fixture"]]
    carry = [x for x in under + maybe if x["carry_people"]]
    b_lo, b_hi = loss["belongings"]
    f_lo, f_hi = loss["fixtures"]
    status = "fail" if under else "warn" if maybe else "pass"
    text = (f"Between {money(b_lo)} and {money(b_hi)} of belongings sit below the water line "
            f"({len(under)} items at the middle estimate, {len(maybe)} more at the high end); {len(carry)} of them can be "
            "carried up." if b_hi else f"No belongings in the {len(inv['rooms_read'])} rooms read sit below the water line.")
    if f_hi:
        text += f" Built-in fixtures below it: {money(f_lo)} to {money(f_hi)}."
    low_util = [u for u in utils if u["wet_hi"] and u["label"] != "outlet near the floor"]
    if low_util:
        text += " Under water at the high end: " + ", ".join(sorted({u["name"].lower() for u in low_util})) + "."

    def src_cost(kind):
        return Source(layer="model", method="vision", confidence="low",
                      note=f"Sum of the model's replacement-cost classes for {kind} the water reaches: low end counts "
                           "class minimums at the low water level, high end class maximums at the high level")
    metrics = [Metric(id="loss_low", label="Belongings lost, low end", value=b_lo, unit="USD", source=src_cost("belongings")),
               Metric(id="loss_high", label="Belongings lost, high end", value=b_hi, unit="USD", source=src_cost("belongings")),
               Metric(id="items_under", label="Belongings under water (middle)", value=len(under), unit="", source=VISION),
               Metric(id="can_carry", label="Of those, can be carried", value=len(carry), unit="", source=VISION),
               Metric(id="fixtures_low", label="Fixtures lost, low end", value=f_lo, unit="USD", source=src_cost("fixtures")),
               Metric(id="fixtures_high", label="Fixtures lost, high end", value=f_hi, unit="USD", source=src_cost("fixtures")),
               Metric(id="items_seen", label="Items listed", value=len(items), unit="", source=VISION),
               Metric(id="rooms_read", label="Rooms read", value=len(inv["rooms_read"]), unit="", source=VISION)]
    per_room: dict[str, int] = {}
    for x in under:
        per_room[x["room"]] = per_room.get(x["room"], 0) + 1
    metrics += [Metric(id=f"under.{r}", label=labels.get(r, "?"), value=n, unit="items", source=VISION)
                for r, n in sorted(per_room.items(), key=lambda kv: -kv[1])]

    findings, pins, checks = [], [], []

    def state(x):
        return "fail" if x["wet_mid"] else "warn" if x["wet_hi"] else "pass"

    def where(x):
        d = room_depth_at(flood, x["room"], "mid")
        h = "height unknown (the ray met no wall or floor)" if x["height_m"] is None else (
            "on the floor" if x["height_m"] < 0.03 else f"{x['height_m']:.2f} m above the floor")
        return h, d

    for x in sorted(items, key=lambda x: (not x["wet_mid"], not x["wet_hi"], -x["cost"][1])):
        h, d = where(x)
        st = state(x)
        fid = f"valuables_height:{sid}:{x['id']}"
        carry = {0: "built in or needs a mover", 1: "one person can carry it", 2: "two people carry it"}[x["carry_people"]]
        water = ("under water at the middle estimate" if st == "fail" else "under water only at the high end"
                 if st == "warn" else "above the water")
        anchor = PointAnchor(**x["anchor"]) if "point" in x["anchor"] else PanoAnchor(**x["anchor"])
        findings.append(Finding(
            id=fid, title=x["name"] + (f" (x{x['count']})" if x["count"] > 1 else ""), status=st, anchor=anchor,
            detail=f"{labels.get(x['room'], '?')}: {h}; water {d:.2f} m there, {water}. {x['cost_class']} each, "
                   f"{carry}{', a fixture of the house' if x['fixture'] else ''}.",
            source=Source(layer="model", method="vision", confidence=x["confidence"],
                          note="Item and classes from the vision model; height from the scan geometry"),
            media=[Media(**m) for m in x["media"]]))
        pins.append(Pin(id=f"item:{x['id']}", anchor=anchor, label=x["name"], status=st))
        if "point" in x["anchor"]:
            pa = x.get("media")[0]["ref"].split("/") if x.get("media") else None
            if pa:
                pins.append(Pin(id=f"item:{x['id']}:pano", label=x["name"], status=st, anchor=PanoAnchor(
                    sid=sid, pano=pa[1], **_pano_dir(plan, pa[1], x["anchor"]["point"]))))
    for u in sorted(utils, key=lambda u: (u["height_m"] is None, u["height_m"] or 0)):
        h, d = where(u)
        st = state(u) if u["height_m"] is not None or u["wet_hi"] else "unknown"
        fid = f"valuables_height:{sid}:{u['id']}"
        anchor = PointAnchor(**u["anchor"]) if "point" in u["anchor"] else PanoAnchor(**u["anchor"])
        findings.append(Finding(id=fid, title=f"{u['name']}, {labels.get(u['room'], '?')}", status=st, anchor=anchor,
                                detail=f"{h}; water {d:.2f} m in this room "
                                       f"({room_depth_at(flood, u['room'], 'lo'):.2f} to {room_depth_at(flood, u['room'], 'hi'):.2f}).",
                                source=Source(layer="model", method="vision", confidence=u["confidence"],
                                              note="Found by the vision model; height from the scan geometry"),
                                media=[Media(**m) for m in u["media"]]))
        checks.append(Check(id=u["id"], rule=f"{u['name']} above the water, {labels.get(u['room'], '?')}",
                            measured=round(u["height_m"], 2) if u["height_m"] is not None else None,
                            threshold=round(d, 2), unit="m", status=st, findings=[fid]))
        pins.append(Pin(id=f"util:{u['id']}", anchor=anchor, label=u["name"], status=st))
        pins.append(Pin(id=f"util:{u['id']}:pano", anchor=PanoAnchor(**u["pano_anchor"]), label=u["name"], status=st))
    missing = [UTILITY_NAME[k] for k in ("electrical panel", "water heater", "furnace or air handler")
               if not any(u["label"] == k for u in utils)]
    if missing:
        findings.append(Finding(id=f"valuables_height:{sid}:not_seen", title="Utilities not seen", status="unknown",
                                anchor=None, source=VISION,
                                detail=", ".join(missing) + " did not show in the panoramas read. They may be in a "
                                       "closet, the attic, the garage or outside; look before the storm."))
    findings.append(Finding(id=f"valuables_height:{sid}:staging", title="These are the listing's furnishings",
                            status="unknown", anchor=None, source=VISION,
                            detail="The scans were taken for a sale or rental listing, so the furniture may be the "
                                   "seller's or a stager's. Treat the totals as what a furnished home like this one "
                                   "holds at these heights, and re-run after a new scan for your own things."))
    return ToolResult(
        scope=ScanScope(sid=sid), verdict=Verdict(status=status, text=text), metrics=metrics, checks=checks,
        findings=findings, overlays=[WaterOverlay(level_m=round(lv["mid"], 3)), PinsOverlay(pins=pins)],
        assumptions=[
            Assumption(id="flood.depth_m", label="Water above the ground outside", value=inputs.depth_m, unit="m",
                       editable=True),
            Assumption(id="flood.floor_height_m", label="Floor above the ground", value=flood["floor"]["value_m"],
                       unit="m", editable=True),
            Assumption(id="wick_m", label="Water reaches an item once this far above its base", value=WICK_M, unit="m"),
            Assumption(id="cost_classes", label="Cost classes in dollars: under $100 = 20-100, ..., over $10,000 = "
                                                "10,000-30,000", value="model classes"),
            Assumption(id="defurnished_used", label="Empty panoramas used to tell fixtures from belongings",
                       value=inv.get("defurnished", False))],
        actions=[Action(id="plan", label="Plan what to carry up first", tool="storm_plan",
                        inputs={"scan": sid, "depth_m": inputs.depth_m, "scenario": inputs.scenario}),
                 Action(id="flood", label="See the water room by room", tool="flood_rehearsal",
                        inputs={"scan": sid, "depth_m": inputs.depth_m, "scenario": inputs.scenario})])


def _pano_dir(plan: dict, pano_id: str, point) -> dict:
    import math
    p = next(x for x in plan["panos"] if x["id"] == pano_id)
    dx, dy, dz = (point[i] - p["position"][i] for i in range(3))
    return {"yaw_deg": round(math.degrees(math.atan2(dy, dx)), 2),
            "pitch_deg": round(math.degrees(math.atan2(dz, math.hypot(dx, dy))), 2)}

