"""Storm plan: an ordered plan for the hours before a flood, fitted to the people and time the household has.

The planner ranks work, then fits it into the crew-minutes available: shutoffs first and last (always), the
envelope (a store run, window boards, door dams) only when there are enough hours and the dams would hold, then
belongings by value saved per crew-minute, weighted by how sure the loss is. What does not fit is dropped with
its reason. Each run is kept per scan, so the next run says what changed and why."""
from __future__ import annotations

import json
import math
from typing import Literal

from pydantic import Field

from ...config import CACHE
from ...geometry._plan import floor_z, polygons, room_floor_z
from .. import (
    Action,
    Assumption,
    Check,
    Finding,
    Metric,
    OpeningAnchor,
    Pin,
    PinsOverlay,
    PointAnchor,
    RoomAnchor,
    RuleOverlay,
    ScanScope,
    SelectOpenings,
    Source,
    ToolResult,
    Verdict,
    field,
    tool,
)
from ..flood_rehearsal.scenario import FloodInputs, check_plan, room_depth_at
from ..flood_rehearsal.scenario import run as flood_run
from ..types import GeoAnchor, Media, PanoAnchor, SelectRooms, WaterOverlay
from ..valuables_height import inventory
from . import prep

MEMO = CACHE / "tools" / "storm_plan"
WORK_SHARE = 0.5            # share of the hours left a household can work: sleep, food, shopping, the news
ENVELOPE_MIN_HOURS = 8.0    # below this, no store run: shelves empty and the boarding will not finish
ENVELOPE_SHARE = 0.5        # boards and bags get at least this share of the crew-minutes, or all carrying leaves
COUNTER_M = 0.9             # counter and table height: lifting things there helps only below this
PLAN_SRC = Source(layer="model", method="simulation", confidence="medium",
                  note="Planner over the scan's geometry and the vision inventory; times are rules of thumb")
GEO = Source(layer="matterport", method="geometry", confidence="high", note="Window and door sizes from the wall graph")
CDC = ("CDC: never run a generator inside or less than 20 feet from an open window, door or vent; CPSC (2024, after "
       "Tropical Storm Beryl): 20 feet from the house with the exhaust pointed away")
FEMA_BOARD = "FEMA, Protect Your Property from High Winds: exterior plywood 5/8 in or thicker, 4 in past each edge"


class Inputs(FloodInputs):
    hours_left: float = field(ask="How many hours until the storm reaches you?", pref="storm.hours_left", unit="h",
                              gt=0, le=168, description="Hours until the storm")
    adults: int = field(ask="How many adults can lift and carry?", pref="storm.adults", ge=1, le=12,
                        description="Adults who can lift and carry")
    upper_floor: Literal["auto", "yes", "no"] = field("auto", pref="storm.upper_floor",
                                                      description="Is there an upper floor? auto reads the scan")
    attic: bool = field(False, pref="storm.attic", description="There is an attic you can reach and get out of")
    board_windows: bool = field(True, pref="storm.board_windows", description="Board the windows against wind")
    max_rooms: int = Field(8, ge=1, le=12, description="Most rooms to read with the vision model")


def _lowest_floor(plan: dict) -> str | None:
    fz = floor_z(plan)
    return min(fz, key=fz.get) if fz else None


def destination(plan: dict, flood: dict, inputs: Inputs) -> dict:
    """Where things go: the highest dry floor, an attic, high surfaces, or out of the house."""
    fz, rz, polys = floor_z(plan), room_floor_z(plan), polygons(plan)
    low = _lowest_floor(plan)
    hi_level = flood["levels"]["hi"]
    labels = {r["id"]: r.get("label") for r in plan["rooms"]}
    dry_floors = [f for f, z in fz.items() if f != low and z > hi_level + 0.05]
    stair = next((r for r in plan["rooms"] if r["floor"] == low and r.get("label") == "Staircase"
                  and polys.get(r["id"]) is not None), None)
    entry = flood.get("entry_door")
    stair_xy = ((polys[stair["id"]].centroid.x, polys[stair["id"]].centroid.y) if stair else
                tuple(entry["center"]) if entry else None)
    if dry_floors and inputs.upper_floor != "no":
        best = max(dry_floors, key=fz.get)
        rooms = [r for r in plan["rooms"] if r["floor"] == best and labels.get(r["id"]) not in ("Void", "Closet")
                 and room_depth_at(flood, r["id"], "hi") == 0]
        area = sum(r.get("area") or 0 for r in rooms)
        room = max(rooms, key=lambda r: r.get("area") or 0, default=None)
        return {"kind": "upstairs", "floor": best, "room": room["id"] if room else None, "area_m2": round(area, 1),
                "flights": 1, "stair_xy": stair_xy, "stair_room": stair["id"] if stair else None,
                "text": f"upstairs to the {labels.get(room['id']) or 'largest room'}" if room else "upstairs",
                "dry_by_m": round(fz[best] - hi_level, 2)}
    if inputs.upper_floor == "yes":
        return {"kind": "upstairs_unscanned", "floor": None, "room": None, "area_m2": None, "flights": 1,
                "stair_xy": stair_xy, "stair_room": None, "text": "upstairs (that floor is not in the scan)"}
    same = [r for r in plan["rooms"] if labels.get(r["id"]) not in ("Void", None) and room_depth_at(flood, r["id"], "hi") == 0
            and rz.get(r["id"], 0) >= rz.get(entry["rooms"][0], 0) if entry]
    if same:
        room = max(same, key=lambda r: r.get("area") or 0)
        return {"kind": "dry_room", "floor": room["floor"], "room": room["id"], "area_m2": round(sum(r.get("area") or 0 for r in same), 1),
                "flights": 0, "stair_xy": (polys[room["id"]].centroid.x, polys[room["id"]].centroid.y)
                if polys.get(room["id"]) is not None else stair_xy, "stair_room": None,
                "text": f"to the {labels.get(room['id'])}, which stays dry"}
    if inputs.attic:
        return {"kind": "attic", "floor": None, "room": None, "area_m2": None, "flights": 1, "stair_xy": stair_xy,
                "stair_room": None, "text": "into the attic (you said you can reach it and get out of it)"}
    deep = max((r.get("depth_hi", 0) for r in flood["rooms"].values()), default=0)
    if deep + 0.1 < COUNTER_M:
        return {"kind": "high_surfaces", "floor": low, "room": None, "area_m2": None, "flights": 0, "stair_xy": None,
                "stair_room": None, "text": "onto counters, beds and tables in the same room", "dry_by_m": round(COUNTER_M - deep, 2)}
    return {"kind": "car", "floor": None, "room": None, "area_m2": None, "flights": 0, "stair_xy": stair_xy,
            "stair_room": None, "text": "out of the house by car: nothing inside stays dry"}


def item_xy(plan: dict, x: dict) -> tuple[float, float] | None:
    if "point" in x["anchor"]:
        return tuple(x["anchor"]["point"][:2])
    p = next((p for p in plan["panos"] if p["id"] == x.get("pano")), None)
    return tuple(p["position"][:2]) if p else None


CERTAINTY = {"lo": 1.0, "mid": 0.75, "hi": 0.4}


def carry_tasks(plan: dict, items: list[dict], dest: dict) -> list[dict]:
    out = []
    for x in items:
        if x["fixture"] or not x["carry_people"] or not x["wet_hi"]:
            continue
        sure = "lo" if x["wet_lo"] else "mid" if x["wet_mid"] else "hi"
        xy = item_xy(plan, x)
        if dest["kind"] == "high_surfaces":
            dist = 2.0
        elif dest.get("stair_xy") and xy:
            dist = math.dist(xy, dest["stair_xy"])
        else:
            dist = 8.0
        mins = prep.carry_minutes(x["size_class"], dist, dest["flights"], x["carry_people"]) * x["count"]
        if dest["kind"] == "car":
            mins += 2 * x["carry_people"] * x["count"]
        value = (x["cost"][0] + x["cost"][1]) / 2 * CERTAINTY[sure]
        out.append({"id": f"carry:{x['id']}", "kind": "carry", "label": f"Carry the {x['name'].lower()}"
                    + (f" (x{x['count']})" if x["count"] > 1 else ""), "minutes": round(mins, 1), "people": x["carry_people"],
                    "value": value, "density": value / max(mins, 0.5), "sure": sure, "item": x, "distance_m": round(dist, 1)})
    return sorted(out, key=lambda t: -t["density"])


def exterior(plan: dict, kind: str, floor: str | None = None) -> list[dict]:
    return [o for o in plan.get("openings") or [] if o["type"] == kind and len(o.get("rooms") or []) == 1
            and (floor is None or o["floor"] == floor) and o.get("width") and o.get("height")]


def envelope_tasks(plan: dict, flood: dict, inputs: Inputs, capacity: float, reserved: float = 0.0) -> tuple[list[dict], dict, dict]:
    """Store run, window boards, door dams; with the reasons for anything left out."""
    skipped: dict[str, str] = {}
    labels = {r["id"]: r.get("label") or "unlabelled room" for r in plan["rooms"]}
    low = _lowest_floor(plan)
    windows = sorted(exterior(plan, "window"), key=lambda o: -(o["width"] * o["height"]))
    cut = prep.cut_list([{"id": o["id"], "width": o["width"], "height": o["height"], "label": labels.get(o["rooms"][0])}
                         for o in windows])
    hi = flood["levels"]["hi"]
    dams, dam_rows = [], []
    for o in exterior(plan, "doorway", low):
        at_door = hi - o["sill"]
        if at_door <= 0:
            continue
        d = prep.door_dam(o["width"], at_door)
        dam_rows.append({**d, "opening": o["id"], "room": labels.get(o["rooms"][0]), "water_m": round(at_door, 2),
                         "width": o["width"]})
        if d["holds"]:
            dams.append({"id": f"dam:{o['id']}", "kind": "dam", "label": f"Sandbag the doorway, {labels.get(o['rooms'][0])}",
                         "minutes": d["minutes"], "people": 2, "opening": o["id"], "needs": ["materials"], "dam": d})
        else:
            skipped[f"dam:{o['id']}"] = (f"water {at_door:.2f} m deep against this door is more than a door dam holds "
                                         f"({prep.DAM_MAX_M:.1f} m)")
    boards = [{"id": f"board:{w['opening']}", "kind": "board", "label": f"Board the window, {w['room'] or 'room'}",
               "minutes": prep.BOARD_MINUTES * w["boards"], "people": 2, "opening": w["opening"], "needs": ["materials"],
               "cut": w} for w in cut["windows"]] if inputs.board_windows else []
    if not inputs.board_windows:
        skipped["boards"] = "you chose not to board windows"
    out: list[dict] = []
    if inputs.hours_left < ENVELOPE_MIN_HOURS and (boards or dams):
        for t in boards + dams:
            skipped[t["id"]] = (f"only {inputs.hours_left:g} h left: a store run and boarding need about "
                                f"{ENVELOPE_MIN_HOURS:g} h, and shelves empty first")
        return out, cut, {"rows": dam_rows, "skipped": skipped}
    budget = max(ENVELOPE_SHARE * capacity, capacity - reserved)  # half the time, or all that carrying leaves
    picked, used = [], prep.MATERIALS_MINUTES
    for t in dams + boards:  # dams first: water is the hazard this tool plans for
        if used + t["minutes"] <= budget:
            picked.append(t)
            used += t["minutes"]
        else:
            skipped[t["id"]] = "there is not time for it as well as carrying the belongings up"
    if picked:
        n_sheets = prep.cut_list([t["cut"] | {"id": t["opening"]} for t in picked if t["kind"] == "board"])["sheets"]
        n_bags = sum(t["dam"]["bags"] for t in picked if t["kind"] == "dam")
        out.append({"id": "materials", "kind": "materials", "minutes": prep.MATERIALS_MINUTES, "people": 1,
                    "label": "Buy " + " and ".join(x for x in (f"{n_sheets} sheets of 5/8 in plywood" if n_sheets else "",
                                                                f"{n_bags} sandbags (and sand)" if n_bags else "") if x),
                    "sheets": n_sheets, "bags": n_bags})
    return out + picked, cut, {"rows": dam_rows, "skipped": skipped}


def memo_read(sid: str) -> dict | None:
    f = MEMO / f"{sid}.json"
    try:
        return json.loads(f.read_text()) if f.exists() else None
    except (OSError, ValueError):
        return None


def memo_write(sid: str, data: dict) -> None:
    try:
        MEMO.mkdir(parents=True, exist_ok=True)
        (MEMO / f"{sid}.json").write_text(json.dumps(data))
    except OSError:
        pass


def changes(prev: dict | None, now: dict, why: dict[str, str]) -> list[str]:
    """What changed since the last plan for this scan, each with its reason."""
    if not prev:
        return []
    out = []
    names = {"depth_m": ("Water above the ground", "m"), "hours_left": ("Hours left", "h"), "adults": ("Adults", ""),
             "floor_height_m": ("Floor height", "m"), "scenario": ("Scenario", "")}
    for k, (label, unit) in names.items():
        a, b = prev["inputs"].get(k), now["inputs"].get(k)
        if a != b:
            out.append(f"{label}: {a}{' ' + unit if unit and a is not None else ''} to {b}{' ' + unit if unit and b is not None else ''}.")
    if prev.get("dest") != now["dest"]:
        out.append(f"Things now go {now['dest']} (before: {prev.get('dest')}).")
    lab = {**prev.get("labels", {}), **now["labels"]}
    gone = [t for t in prev["kept"] if t not in now["kept"]]
    new = [t for t in now["kept"] if t not in prev["kept"]]
    env_why = next((v for k, v in why.items() if k.startswith(("board:", "dam:"))), None)
    for t in gone[:12]:
        default = ("it is no longer under water" if t.startswith("carry:") else
                   env_why or "no boards or dams are planned" if t == "materials" else "it is no longer needed")
        out.append(f"Dropped: {lab.get(t, t)}, because {why.get(t, default)}.")
    for t in new[:12]:
        reason = ("it is now under water" if t.startswith("carry:") and t not in prev.get("considered", [])
                  else "there is now time for it")
        out.append(f"Added: {lab.get(t, t)}, because {reason}.")
    if len(gone) > 12 or len(new) > 12:
        out.append(f"And {max(0, len(gone) - 12) + max(0, len(new) - 12)} more changes of the same kind.")
    return out


def hours_before(t: dict, adults: int, hours_left: float) -> float:
    return max(0.0, hours_left - t["end"] / (adults * 60 * WORK_SHARE))


@tool(id="storm_plan", title="Storm plan", icon="list-checks",
      summary="An ordered plan for the hours before the storm: what to carry up first, where it goes, plywood cut "
              "from your real window sizes, sandbags per door, which shutoffs to turn off, and where a generator can "
              "safely stand. It changes when the storm or the household changes.",
      model_description="Plan the hours before a flood for one scanned house. Inputs: hours left, able adults, upper "
                        "floor or attic, the flood scenario. Ranks and schedules work into the crew-minutes available "
                        "(carry belongings by value per minute and loss certainty; plywood cut list from ScanPlan window "
                        "sizes; sandbag lengths per exterior door; shutoffs; a generator spot 20 ft from the house on "
                        "the aerial photo). Says what it dropped and why, and what changed since the last plan.",
      personas=["houston_homeowner_storm"],
      requires=[{"layer": "matterport.openings"}, {"layer": "matterport.panoramas"},
                {"layer": "vexcel.footprint", "need": "optional", "fallback": "no generator spot"}],
      blocks=["VerdictHeader", "MetricRow", "Controls", "CheckList", "FloorPlanMini", "EvidenceStrip", "AssumptionChips",
              "StepLog", "ActionBar"],
      overlays=["pins", "rule", "water"], annotations={"cost": "slow"},
      examples=["The storm is 72 hours out and there are two of us. What do we do first?",
                "We only have 6 hours now. What changes?"])
def run(ctx, inputs: Inputs) -> ToolResult:
    sid = inputs.scan
    plan = ctx.plan(sid)
    check_plan(plan)
    flood = flood_run(plan, inputs, ctx.step)
    inv = inventory(plan, flood, inputs.max_rooms, ctx.step) if plan.get("panos") else {"items": [], "utilities": []}
    return build(sid, plan, inputs, flood, inv, ctx.step)


def build(sid: str, plan: dict, inputs: Inputs, flood: dict, inv: dict, steps, memo: bool = True) -> ToolResult:
    labels = {r["id"]: r.get("label") or "unlabelled room" for r in plan["rooms"]}
    capacity = inputs.adults * inputs.hours_left * 60 * WORK_SHARE
    dest = destination(plan, flood, inputs)
    steps(f"{inputs.adults} adults x {inputs.hours_left:g} h x {WORK_SHARE:.0%} working = {capacity / 60:.1f} crew-hours; "
          f"belongings go {dest['text']}")
    utils = inv.get("utilities") or []
    panel = next((u for u in utils if u["label"] == "electrical panel"), None)
    heater = next((u for u in utils if u["label"] == "water heater"), None)
    wet_power = [u for u in utils if u["wet_hi"] and u["label"] in ("outlet near the floor", "electrical panel")]
    first = {"id": "find_shutoffs", "kind": "shutoff", "minutes": 10, "people": 1, "must": True,
             "label": "Find and label the main breaker, the water main and the gas meter"}
    carry = carry_tasks(plan, inv.get("items") or [], dest)
    last = []
    if wet_power or any(r.get("depth_hi", 0) > 0 for r in flood["rooms"].values()):
        last.append({"id": "power_off", "kind": "shutoff", "minutes": 5, "people": 1, "must": True,
                     "label": "Turn off the main breaker" + (f" at the panel in the {labels.get(panel['room'], 'house').lower()}"
                                                             if panel else "") + ", standing on dry ground", "util": panel})
    if heater and heater["wet_hi"]:
        last.append({"id": "gas_off", "kind": "shutoff", "minutes": 5, "people": 1, "must": True,
                     "label": f"Turn off the gas to the water heater in the {labels.get(heater['room'], 'house').lower()}",
                     "util": heater})
    env, cut, dams = envelope_tasks(plan, flood, inputs, capacity,
                                    reserved=sum(t["minutes"] for t in [first] + carry + last))
    tasks = [first] + env + carry + last
    kept, dropped = prep.schedule(tasks, capacity)
    why = {**dams["skipped"], **{t["id"]: t["why"] for t in dropped}}
    steps(f"Planned {len(kept)} tasks, dropped {len(dropped)}; {sum(t['minutes'] for t in kept) / 60:.1f} crew-hours used")

    prev = memo_read(sid) if memo else None
    now = {"inputs": {k: getattr(inputs, k) for k in ("depth_m", "hours_left", "adults", "floor_height_m", "scenario")},
           "kept": [t["id"] for t in kept], "dest": dest["text"],
           "considered": [t["id"] for t in carry], "labels": {t["id"]: t["label"] for t in tasks}}
    diff = changes(prev, now, why)
    if memo:
        memo_write(sid, now)

    saved = [t for t in kept if t["kind"] == "carry"]
    lost_carry = [t for t in dropped if t["kind"] == "carry"]
    s_lo = sum(t["item"]["cost"][0] for t in saved if t["item"]["wet_lo"])
    s_hi = sum(t["item"]["cost"][1] for t in saved)
    need = sum(t["minutes"] for t in tasks)
    mat = next((t for t in kept if t["kind"] == "materials"), None)
    n_boards = sum(1 for t in kept if t["kind"] == "board")
    n_dams = sum(1 for t in kept if t["kind"] == "dam")
    parts = []
    if mat:
        parts.append(mat["label"].lower())
    if n_boards:
        parts.append(f"board {n_boards} windows")
    if n_dams:
        parts.append(f"sandbag {n_dams} doors")
    if saved:
        parts.append(f"carry {len(saved)} things {dest['text']}")
    if last:
        parts.append("turn the power" + (" and gas" if any(t["id"] == "gas_off" for t in last) else "") + " off last")
    head = f"With {inputs.adults} adult{'s' if inputs.adults > 1 else ''} and {inputs.hours_left:g} h: " + ", ".join(parts) + "."
    fits = not dropped
    tail = (f" Everything fits, with {(capacity - need) / 60:.1f} crew-hours to spare." if fits else
            f" Not everything fits: {len(dropped) + len([k for k in dams['skipped'] if k.startswith(('board', 'dam'))])} "
            f"tasks left out ({len(lost_carry)} belongings).")
    text = head + tail + (" Changed since the last plan: " + " ".join(diff[:3]) if diff else "")
    status = "pass" if fits and not dams["skipped"] else "warn"

    checks, findings, pins, board_ids, dam_ids = [], [], [], [], []
    order = 0
    for t in kept + dropped:
        is_kept = t in kept
        fid = f"storm_plan:{sid}:{t['id']}"
        if is_kept:
            order += 1
        when = ("last, in the final hour before you leave or the water comes" if t["id"] in ("power_off", "gas_off")
                else f"done by {hours_before(t, inputs.adults, inputs.hours_left):.0f} h before the storm") if is_kept \
            else f"left out: {t['why']}"
        anchor, media, detail = None, [], ""
        if t["kind"] == "carry":
            x = t["item"]
            anchor = PointAnchor(**x["anchor"]) if "point" in x["anchor"] else PanoAnchor(**x["anchor"])
            media = [Media(**m) for m in x["media"]]
            sure = {"lo": "under water even at the low end", "mid": "under water at the middle estimate",
                    "hi": "under water only at the high end"}[t["sure"]]
            detail = (f"{x['cost_class']} each; {sure}; {t['people']} {'person' if t['people'] == 1 else 'people'}, "
                      f"about {t['minutes']:.0f} crew-minutes ({t['distance_m']:.0f} m to {dest['text']}).")
            if is_kept:
                pins.append(Pin(id=f"carry:{x['id']}", anchor=anchor, label=str(order), status="warn"))
        elif t["kind"] == "board":
            c = t["cut"]
            anchor = OpeningAnchor(sid=sid, opening=t["opening"])
            detail = (f"Window {c['width']:.2f} x {c['height']:.2f} m: {c['boards']} board(s) "
                      f"{c['board_w']:.2f} x {c['board_h']:.2f} m ({prep.ft_in(c['board_w'])} x {prep.ft_in(c['board_h'])}).")
            (board_ids if is_kept else []).append(t["opening"])
        elif t["kind"] == "dam":
            d = t["dam"]
            anchor = OpeningAnchor(sid=sid, opening=t["opening"])
            detail = (f"Dam {d['length_m']:.2f} m long ({prep.ft_in(d['length_m'])}), {d['layers']} layers, about "
                      f"{d['bags']} bags, for water up to {flood['levels']['hi'] - next(o['sill'] for o in plan['openings'] if o['id'] == t['opening']):.2f} m against the sill.")
            (dam_ids if is_kept else []).append(t["opening"])
        elif t["kind"] == "shutoff" and t.get("util"):
            u = t["util"]
            anchor = PointAnchor(**u["anchor"]) if "point" in u["anchor"] else PanoAnchor(**u["anchor"])
            media = [Media(**m) for m in u["media"]]
            detail = "Seen in the panorama. Never touch a panel or switch while standing in water; if water has come " \
                     "in, call CenterPoint to cut power at the meter."
            pins.append(Pin(id=t["id"], anchor=anchor, label=t["label"].split(",")[0], status="warn"))
        elif t["kind"] == "materials":
            detail = "Do this first: stores sell out once a watch is issued. Plywood list: " + "; ".join(
                f"{w['boards']} x {prep.ft_in(w['board_w'])} by {prep.ft_in(w['board_h'])}" for w in cut["windows"][:12])
        elif t["id"] == "find_shutoffs":
            detail = ("Breaker panel: " + (f"seen in the {labels.get(panel['room'], '?').lower()}" if panel else "not seen in "
                      "the panoramas; usually in the garage or a utility closet") + ". The water main and gas meter are "
                      "outside, usually at the front of the lot near the street; they are not in the scan.")
        findings.append(Finding(id=fid, title=t["label"], status="pass" if is_kept else "fail", anchor=anchor,
                                detail=f"{when}. {detail}".strip(), source=PLAN_SRC, media=media))
        checks.append(Check(id=t["id"], rule=f"{order}. {t['label']}" if is_kept else t["label"],
                            measured=round(t["minutes"], 1), threshold=None, unit="crew-min",
                            status="pass" if is_kept else "fail", findings=[fid]))
    for tid, reason in dams["skipped"].items():
        if tid.startswith("dam:"):
            oid = tid[4:]
            findings.append(Finding(id=f"storm_plan:{sid}:{tid}", title=f"No door dam, {labels.get(next((o['rooms'][0] for o in plan['openings'] if o['id'] == oid), ''), 'door')}",
                                    status="warn", anchor=OpeningAnchor(sid=sid, opening=oid), source=PLAN_SRC,
                                    detail=reason[0].upper() + reason[1:] + ". Spend the time carrying things up."))
    if any(k.startswith("board:") for k in dams["skipped"]) and inputs.hours_left < ENVELOPE_MIN_HOURS:
        findings.append(Finding(id=f"storm_plan:{sid}:no_boards", title="No window boards this time", status="warn",
                                anchor=None, source=PLAN_SRC, detail=next(v for k, v in dams["skipped"].items()
                                                                          if k.startswith("board:")) + "."))

    # Highest dry floor area
    dest_anchor = RoomAnchor(sid=sid, room=dest["room"]) if dest.get("room") else None
    dest_detail = {"upstairs": f"{dest.get('area_m2')} m2 of floor upstairs stays dry, {dest.get('dry_by_m', 0):.2f} m "
                               "above the high-end water level.",
                   "dry_room": f"{dest.get('area_m2')} m2 of rooms on this floor stay dry at the high end.",
                   "high_surfaces": f"No dry floor inside at the high end. Counters and tables ({COUNTER_M} m) stay "
                                    f"{dest.get('dry_by_m', 0):.2f} m above the water.",
                   "attic": "No dry floor inside at the high end. Do not shelter in a closed attic: rising water can "
                            "trap you there (Ready.gov). Go only where you can get out onto the roof.",
                   "car": "No dry floor and nothing high enough inside at the high end: take what matters in the car "
                          "when you leave.",
                   "upstairs_unscanned": "You said there is an upper floor; the scan does not include it, so its "
                                         "area and the stair position are not measured."}[dest["kind"]]
    findings.append(Finding(id=f"storm_plan:{sid}:dry_area", title="Highest dry place inside",
                            status="pass" if dest["kind"] in ("upstairs", "dry_room") else "warn", anchor=dest_anchor,
                            detail=dest_detail, source=PLAN_SRC))
    # Generator
    gen = generator(sid, flood)
    if gen["finding"]:
        findings.append(gen["finding"])
    if gen["pin"]:
        pins.append(gen["pin"])
    if diff:
        findings.append(Finding(id=f"storm_plan:{sid}:changes", title="What changed since the last plan", status="unknown",
                                anchor=None, source=PLAN_SRC, detail=" ".join(diff)))

    overlays = [WaterOverlay(level_m=round(flood["levels"]["mid"], 3))]
    if board_ids:
        overlays.append(RuleOverlay(select=SelectOpenings(openings=board_ids), style="highlight"))
    if dam_ids:
        overlays.append(RuleOverlay(select=SelectOpenings(openings=dam_ids), style="warn"))
    if dest.get("room"):
        overlays.append(RuleOverlay(select=SelectRooms(rooms=[dest["room"]]), style="pass"))
    if pins:
        overlays.append(PinsOverlay(pins=pins))
    metrics = [
        Metric(id="crew_hours_needed", label="Crew-hours the whole list needs", value=round(need / 60, 1), unit="h", source=PLAN_SRC),
        Metric(id="crew_hours_available", label="Crew-hours you have", value=round(capacity / 60, 1), unit="h", source=PLAN_SRC),
        Metric(id="saved_high", label="Belongings saved, up to", value=s_hi, unit="USD",
               source=Source(layer="model", method="vision", confidence="low", note="Sum of cost-class maximums of the items carried")),
        Metric(id="dropped", label="Tasks left out", value=len(dropped), unit="", source=PLAN_SRC),
        Metric(id="saved_low", label="Belongings saved, at least", value=s_lo, unit="USD",
               source=Source(layer="model", method="vision", confidence="low",
                             note="Cost-class minimums of carried items that are under water even at the low end")),
        Metric(id="plywood_sheets", label="Plywood sheets (all windows)", value=cut["sheets"], unit="sheets", source=GEO),
        Metric(id="window_boards", label="Window boards (all windows)", value=cut["boards"], unit="", source=GEO),
        Metric(id="sandbags", label="Sandbags (doors that a dam can hold)", value=sum(r["bags"] for r in dams["rows"] if r["holds"]),
               unit="", source=GEO),
        Metric(id="items_carried", label="Things carried", value=len(saved), unit="", source=PLAN_SRC)]
    assumptions = [
        Assumption(id="storm.hours_left", label="Hours until the storm", value=inputs.hours_left, unit="h", editable=True),
        Assumption(id="storm.adults", label="Adults who can carry", value=inputs.adults, unit=None, editable=True),
        Assumption(id="flood.depth_m", label="Water above the ground outside", value=inputs.depth_m, unit="m", editable=True),
        Assumption(id="work_share", label="Share of the hours spent working", value=WORK_SHARE, unit=None),
        Assumption(id="board_minutes", label="Crew-minutes per window board", value=prep.BOARD_MINUTES, unit="min"),
        Assumption(id="bag_minutes", label="Crew-minutes per sandbag filled and placed", value=prep.BAG_MINUTES, unit="min"),
        Assumption(id="dam_max_m", label="Deepest water a door dam is worth building for", value=prep.DAM_MAX_M, unit="m"),
        Assumption(id="board_rule", label=FEMA_BOARD, value=prep.OVERLAP_M, unit="m"),
        Assumption(id="generator_rule", label=CDC, value=prep.GENERATOR_M, unit="m")]
    actions = [Action(id="short", label="Re-plan with 6 hours left", tool="storm_plan",
                      inputs={"scan": sid, "depth_m": inputs.depth_m, "hours_left": 6, "adults": inputs.adults,
                              "scenario": inputs.scenario}),
               Action(id="deeper", label="Re-plan for 0.5 m more water", tool="storm_plan",
                      inputs={"scan": sid, "depth_m": round(min(3.0, inputs.depth_m + 0.5), 2), "hours_left": inputs.hours_left,
                              "adults": inputs.adults, "scenario": inputs.scenario}),
               Action(id="flood", label="See the water room by room", tool="flood_rehearsal",
                      inputs={"scan": sid, "depth_m": inputs.depth_m, "scenario": inputs.scenario})]
    return ToolResult(scope=ScanScope(sid=sid), verdict=Verdict(status=status, text=text), metrics=metrics,
                      checks=checks, findings=findings, overlays=overlays, assumptions=assumptions, actions=actions)


def generator(sid: str, flood: dict) -> dict:
    site = flood.get("site") or {}
    if not site.get("footprint"):
        return {"finding": Finding(id=f"storm_plan:{sid}:generator", title="Where a generator can run", status="unknown",
                                   anchor=None, source=PLAN_SRC, detail="No Vexcel footprint for this house, so the "
                                   "20 ft distance cannot be drawn. " + CDC + "."), "pin": None, "zone": None}
    z = prep.generator_zone(site["footprint"], site.get("parcel"), site["lat"], site["lon"])
    src = Source(layer="vexcel", method="geometry", confidence="medium" if z.get("lot_known") else "low",
                 note="Vexcel footprint and parcel; 6.1 m from every wall covers every door, window and vent")
    if z.get("empty"):
        f = Finding(id=f"storm_plan:{sid}:generator", title="No safe generator spot on this lot", status="fail",
                    anchor=GeoAnchor(geo=(site["lon"], site["lat"])), source=src,
                    detail=f"No point of the lot is 20 ft (6.1 m) from every wall; the farthest is {z['farthest_m']} m. "
                           "Run it at the far end of the driveway only if that is 20 ft clear, or not at all. " + CDC + ".")
        return {"finding": f, "pin": None, "zone": z}
    lon, lat = z["spot"]
    media = [Media(kind="ortho", ref=f"/api/aerial/ortho?lat={site['lat']:.6f}&lon={site['lon']:.6f}&size_m=60&px=1024")]
    f = Finding(id=f"storm_plan:{sid}:generator", title="Where a generator can run", status="pass",
                anchor=GeoAnchor(geo=(lon, lat)), source=src, media=media,
                detail=f"{z['zone_area_m2']:.0f} m2 of the {'lot' if z['lot_known'] else 'ground around the house (lot line unknown)'} "
                       f"is at least 20 ft (6.1 m) from every wall. The nearest spot is {z['spot_distance_m']:.1f} m out; "
                       "point the exhaust away from the house. The zone does not know where the neighbours' doors and "
                       "windows are: keep 20 ft from theirs too. " + CDC + ".")
    return {"finding": f, "pin": Pin(id="generator", anchor=GeoAnchor(geo=(lon, lat)), label="Generator", status="pass"),
            "zone": z}

