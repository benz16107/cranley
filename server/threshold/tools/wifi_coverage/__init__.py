"""Wi-Fi coverage: expected signal per room from a router, through the walls and floors of the scan.

A grid of points in every room gets a received signal from the COST 231 multi-wall model (`model.py`): free-space
loss over the 3D distance, plus a loss for each wall piece and window the straight line crosses (wall type assumed
from its thickness) and for each floor. A room's value is the median of its points. With no router given, the tool
tries a point every metre in the house and keeps the one whose worst bedroom or office is strongest; then it looks
for the one mesh node spot, still in good reach of the router, that brings the most of the house up to good.
It is an estimate: furniture, doors, appliances, neighbours' networks and the router's antennas are not modelled.
"""
from __future__ import annotations

from typing import Literal

import numpy as np
from pydantic import BaseModel

from .. import (
    Assumption,
    Check,
    Finding,
    Legend,
    LensOverlay,
    Metric,
    Pin,
    PinsOverlay,
    PointAnchor,
    RoomAnchor,
    ScanScope,
    Source,
    ToolResult,
    Verdict,
    field,
    tool,
)
from ...signals.plan2d import grid, room_names, room_polys
from .model import (BANDS, COST231, FAIR, GOOD, HEAVY_WALL_M, MATERIALS, ROUTER_H_M, ROUTERS, WEAK, House, grade,
                    outbuilding)

TARGET_WORDS = ("bedroom", "office", "den", "study", "loft")  # labels from vision come in lower case
NO_ROUTER = {"Garage", "Patio", "Porch", "Balcony", "Deck", "Closet", "Staircase", "Utility", "Void", "Pool",
             "Yard", "Exterior", "Bathroom", "Laundry", "Pantry"}  # wet rooms and cupboards are no place for a router
NODE_MIN_M = 5.0  # a mesh node next to the router adds nothing
LIVING_SKIP = {"Garage", "Patio", "Porch", "Balcony", "Deck", "Closet", "Staircase", "Pool", "Yard", "Exterior"}
SAMPLE_M, CANDIDATE_M, MAX_SPOTS = 0.75, 1.0, 160
MODEL = Source(layer="matterport", method="simulation", confidence="low",
               note=f"{COST231} over the scan's walls; wall materials assumed from thickness; furniture, doors and "
                    "interference not modelled")
STATUS = {"good": "pass", "fair": "warn", "weak": "fail", "dead": "fail"}


class Inputs(BaseModel):
    scan: str = field(source="selection.scan", description="Scan id")
    router_room: str | None = field(None, description="Room id where the router is; empty to let the tool find the best spot")
    router_point: tuple[float, float] | None = field(None, description="Router position [x, y] in the scan frame (metres)")
    router_floor: str | None = field(None, description="Floor id of router_point, when the scan has several floors")
    router: Literal["typical", "long_range"] = field("typical", pref="wifi.router_class",
                                                     description="typical: 20 dBm at 2.4 GHz, 23 dBm at 5 GHz. long_range: 4 dB more")
    targets: list[str] | None = field(None, description="Room ids that must have good signal; default the bedrooms and office")
    wall_materials: dict[str, Literal[tuple(MATERIALS)]] = field(
        {}, description="Walls the scan cannot tell apart by thickness: wall id or room id (all its walls) to a "
                        "material (metal ductwork, coated glass, clear glass, masonry, drywall)")
    outbuilding_m: float | None = field(None, gt=0, le=200, unit="m", pref="wifi.outbuilding_m",
                                        description="A detached garage or studio this far from the house; estimates "
                                                    "the signal inside it")
    outbuilding_wall: Literal[tuple(MATERIALS)] = field("masonry", pref="wifi.outbuilding_wall",
                                                        description="What the detached building's wall facing the "
                                                                    "house is (a metal garage door: metal ductwork)")


def _is(room: dict, words) -> bool:
    label = (room.get("label") or "").lower()
    return any(w in label.split() or label.startswith(w) for w in words)


def _median(x: np.ndarray) -> float:
    return float(np.median(x)) if len(x) else float("nan")


@tool(id="wifi_coverage", title="Wi-Fi coverage", icon="wifi",
      summary="Estimates Wi-Fi strength in every room from a router spot, finds dead zones, the best router spot for "
              "the bedrooms and office, and where a mesh node helps most.",
      model_description="Wi-Fi signal estimate per room through the scan's wall graph (COST 231 multi-wall model, wall "
                        "materials assumed from thickness), for 2.4 and 5 GHz. Give router_room or router_point, or "
                        "leave both empty to find the best spot for the bedrooms and office. Returns a per-room lens "
                        "(5 GHz dBm), checks per room, dead zones, router and mesh node pins. Low confidence estimate.",
      personas=["remote_worker"],
      requires=[{"layer": "matterport.walls"}, {"layer": "matterport.openings"},
                {"layer": "matterport.room_labels", "need": "optional"}],
      blocks=["VerdictHeader", "MetricRow", "MiniChart", "CheckList", "FloorPlanMini", "AssumptionChips", "StepLog"],
      overlays=["lens", "pins"],
      examples=["Where should the router go?", "Will Wi-Fi reach the back bedroom?", "Do I need a mesh node?"])
def run(ctx, inputs: Inputs) -> ToolResult:
    plan = ctx.plan(inputs.scan)
    scope = ScanScope(sid=inputs.scan)
    polys = room_polys(plan)
    if not plan.get("walls") or not polys:
        return ToolResult(scope=scope, verdict=Verdict(status="unknown", text=(
            "This scan has no wall graph with room outlines, so signal through walls cannot be estimated.")))
    rooms = {r["id"]: r for r in plan["rooms"]}
    names = room_names(plan, polys)
    living = [k for k in polys if rooms[k].get("label") not in LIVING_SKIP]
    mats = {}
    for key, m in inputs.wall_materials.items():
        for w in ([key] if any(w["id"] == key for w in plan["walls"]) else rooms.get(key, {}).get("walls") or []):
            mats[w] = m
    house = House(plan, materials=mats)
    eirp = ROUTERS[inputs.router]
    samples = {k: grid(polys[k], SAMPLE_M) for k in living}
    ctx.step(f"Cut {sum(len(s) for s in house.segs.values())} wall pieces at their doors and windows; "
             f"{sum(len(s) for s in samples.values())} sample points in {len(living)} rooms")

    targets = [t for t in (inputs.targets or []) if t in samples] or \
        [k for k in living if _is(rooms[k], TARGET_WORDS)]
    no_office = not inputs.targets and not any(_is(rooms[k], ("office", "study", "den")) for k in living)
    noun = "chosen rooms" if inputs.targets else "bedrooms" if no_office else "bedrooms and offices"

    by_floor: dict[str, tuple[np.ndarray, list[tuple[str, int, int]]]] = {}
    for fl in {rooms[k]["floor"] for k in samples}:
        ks = [k for k in samples if rooms[k]["floor"] == fl]
        cuts = np.cumsum([0] + [len(samples[k]) for k in ks])
        by_floor[fl] = (np.vstack([samples[k] for k in ks]), [(k, cuts[i], cuts[i + 1]) for i, k in enumerate(ks)])

    def field_of(src, band="5"):
        """dBm at every sample point, one wall-crossing pass per floor."""
        out = {}
        for fl, (pts, spans) in by_floor.items():
            sig = house.signal(src, pts, fl, band, eirp[band])
            out.update({k: sig[i:j] for k, i, j in spans})
        return out

    def spots(exclude=None):
        """Candidate router or node spots on a grid, coarsened so a big floor stays near MAX_SPOTS."""
        ok = {k: p for k, p in polys.items() if rooms[k].get("label") not in NO_ROUTER and k != exclude}
        step = max(CANDIDATE_M, (sum(p.area for p in ok.values()) / MAX_SPOTS) ** 0.5)
        return [(float(x), float(y), rooms[k]["floor"], k) for k, p in ok.items() for x, y in grid(p, step)]

    # ---- the router spot ----
    src, router_room, chosen = None, None, False
    if inputs.router_point is not None:
        fl = inputs.router_floor or (plan["floors"][0]["id"] if len(plan["floors"]) == 1 else None)
        if fl is None or fl not in house.z:
            return ToolResult(scope=scope, verdict=Verdict(status="unknown",
                              text="The scan has several floors; give router_floor with router_point."))
        src = (float(inputs.router_point[0]), float(inputs.router_point[1]), fl)
        router_room = next((k for k, p in polys.items() if rooms[k]["floor"] == fl and p.covers(_pt(src))), None)
    elif inputs.router_room:
        if inputs.router_room not in polys:
            return ToolResult(scope=scope, verdict=Verdict(status="unknown",
                              text="That router room has no outline in the scan; pick another room or a point."))
        rp = polys[inputs.router_room].representative_point()
        c = polys[inputs.router_room].centroid
        xy = (c.x, c.y) if polys[inputs.router_room].contains(c) else (rp.x, rp.y)  # an L-shaped room's centroid can fall outside
        src, router_room = (*xy, rooms[inputs.router_room]["floor"]), inputs.router_room
    else:
        cands = spots()
        goal = targets or living
        ctx.step(f"Trying {len(cands)} router spots against {len(goal)} rooms "
                 f"({noun if targets else 'every room'})")
        best = None
        for x, y, fl, k in cands:
            f = field_of((x, y, fl))
            meds = [_median(f[t]) for t in goal]
            score = (min(meds), sum(meds) / len(meds))
            if best is None or score > best[0]:
                best = (score, (x, y, fl), k)
        _, src, router_room = best
        chosen = True
    f5, f24 = field_of(src, "5"), field_of(src, "2.4")
    med5 = {k: _median(v) for k, v in f5.items()}
    med24 = {k: _median(v) for k, v in f24.items()}
    where = names.get(router_room, "the given point") if router_room else "the given point"
    ctx.step(f"Router {'placed' if chosen else 'set'} in {where}")

    # ---- the mesh node ----
    weak = [k for k in living if med5[k] < (GOOD if k in targets else FAIR)]
    node, node_room, node_gain = None, None, []
    if weak:
        cands = [c for c in spots(router_room) if np.hypot(c[0] - src[0], c[1] - src[1]) >= NODE_MIN_M or c[2] != src[2]]
        backhaul = [c for c in cands if house.signal(src, np.array([c[:2]]), c[2], "5", eirp["5"])[0] >= GOOD] or \
            [c for c in cands if house.signal(src, np.array([c[:2]]), c[2], "5", eirp["5"])[0] >= FAIR]
        ctx.step(f"{len(weak)} rooms need a better 5 GHz signal; trying {len(backhaul)} mesh node spots in good reach of the router")
        best = None
        for x, y, fl, k in backhaul:
            f = field_of((x, y, fl))
            fixed = [t for t in weak if _median(np.maximum(f5[t], f[t])) >= GOOD]
            score = (len([t for t in fixed if t in targets]), len(fixed))
            if fixed and (best is None or score > best[0]):
                best = (score, (x, y, fl), k, fixed)
        if best:
            _, node, node_room, node_gain = best

    # ---- result ----
    def z_of(p):
        return round(house.z[p[2]] + ROUTER_H_M, 2)

    checks, findings, metrics = [], [], []
    for k in sorted(living, key=lambda k: -med5[k]):
        g5, g24 = grade(med5[k]), grade(med24[k])
        fid = f"wifi_coverage:{inputs.scan}:{k}"
        checks.append(Check(id=k, rule=f"5 GHz signal, {names[k]}", measured=round(med5[k], 1), threshold=GOOD,
                            unit="dBm", status=STATUS[g5], findings=[fid] if g5 != "good" else []))
        if g5 != "good":
            low = float(np.mean(f5[k] < WEAK))
            findings.append(Finding(
                id=fid, title=f"{'Dead zone' if g5 == 'dead' else g5.capitalize() + ' Wi-Fi'}: {names[k]}",
                status="fail" if g5 in ("weak", "dead") else "warn", source=MODEL, anchor=RoomAnchor(sid=inputs.scan, room=k),
                detail=f"5 GHz about {med5[k]:.0f} dBm ({g5}), 2.4 GHz about {med24[k]:.0f} dBm ({g24}); "
                       f"{low:.0%} of the room is below {WEAK:.0f} dBm. Good for video calls is {GOOD:.0f} dBm or more."))
        metrics.append(Metric(id=f"ghz5.{names[k]}", label=names[k], value=round(med5[k], 1), unit="dBm", source=MODEL))
    good = [k for k in living if med5[k] >= GOOD]
    dead = [k for k in living if med5[k] < WEAK]
    tgood = [k for k in targets if med5[k] >= GOOD]
    worst_t = min(targets, key=lambda k: med5[k]) if targets else None
    metrics = [Metric(id="good_rooms", label="Rooms with good 5 GHz", value=len(good), unit=f"of {len(living)}", source=MODEL),
               Metric(id="dead_zones", label="Dead zones (5 GHz)", value=len(dead), unit="rooms", source=MODEL),
               *([Metric(id="worst_target", label=f"Weakest target: {names[worst_t]}", value=round(med5[worst_t], 1),
                         unit="dBm", source=MODEL)] if worst_t else []),
               Metric(id="dead_24", label="Dead zones (2.4 GHz)", value=len([k for k in living if med24[k] < WEAK]),
                      unit="rooms", source=MODEL), *metrics]
    findings.insert(0, Finding(
        id=f"wifi_coverage:{inputs.scan}:router", title=f"Router {'spot' if chosen else 'position'}: {where}",
        status="pass" if len(tgood) == len(targets) else "warn", source=MODEL,
        anchor=PointAnchor(sid=inputs.scan, point=(src[0], src[1], z_of(src))),
        detail=(f"{'Best spot found' if chosen else 'Router'} at x {src[0]:.1f}, y {src[1]:.1f} m, {ROUTER_H_M} m above the floor. "
                f"{len(tgood)} of {len(targets)} {noun} get good 5 GHz signal."
                if targets else f"{len(good)} of {len(living)} rooms get good 5 GHz signal.")))
    pins = [Pin(id="router", anchor=PointAnchor(sid=inputs.scan, point=(src[0], src[1], z_of(src))),
                label="Router", status="pass")]
    if node:
        findings.insert(1, Finding(
            id=f"wifi_coverage:{inputs.scan}:mesh", title=f"Mesh node: {names[node_room]}", status="pass", source=MODEL,
            anchor=PointAnchor(sid=inputs.scan, point=(node[0], node[1], z_of(node))),
            detail=f"A node at x {node[0]:.1f}, y {node[1]:.1f} m hears the router at about "
                   f"{house.signal(src, np.array([node[:2]]), node[2], '5', eirp['5'])[0]:.0f} dBm and brings "
                   f"{len(node_gain)} room{'s' if len(node_gain) != 1 else ''} up to good: "
                   + ", ".join(names[k] for k in node_gain) + "."))
        pins.append(Pin(id="mesh", anchor=PointAnchor(sid=inputs.scan, point=(node[0], node[1], z_of(node))),
                        label="Mesh node", status="warn"))

    if targets:
        text = f"With the router in {where}, {len(tgood)} of {len(targets)} {noun} get good 5 GHz signal"
    else:
        text = f"With the router in {where}, {len(good)} of {len(living)} rooms get good 5 GHz signal"
    text += f", and {len(dead)} room{'s are' if len(dead) != 1 else ' is'} a dead zone." if dead else "."
    if node:
        text += f" A mesh node in the {names[node_room]} fixes {len(node_gain)} more."
    elif weak:
        text += " No single mesh node spot fixes the weak rooms."
    if no_office:
        text += " The scan labels no office, so only bedrooms were targeted."
    if inputs.outbuilding_m:
        from shapely.ops import unary_union
        edge = unary_union([p for k, p in polys.items() if rooms[k]["floor"] == src[2]]).exterior.distance(_pt(src))
        ob = {b: outbuilding(eirp[b], b, edge, inputs.outbuilding_m, inputs.outbuilding_wall) for b in ("5", "2.4")}
        g = grade(ob["2.4"])  # the check grades 5 GHz like every room; the sentence says whether 2.4 GHz reaches
        checks.insert(0, Check(id="outbuilding", rule=f"Detached building {inputs.outbuilding_m:.0f} m from the house: "
                               f"2.4 GHz about {ob['2.4']:.0f} dBm, 5 GHz about {ob['5']:.0f} dBm", measured=round(
                                   ob["5"], 1), threshold=GOOD, unit="dBm", status=STATUS[grade(ob["5"])],
                               standard=f"{COST231}; two outside walls, {edge:.1f} m from the router to the house wall"))
        text += (f" The detached building gets about {ob['2.4']:.0f} dBm on 2.4 GHz ({g})"
                 + (": it needs a mesh node or an outdoor access point." if g in ("weak", "dead") else "."))
    text += " Estimate from the walls alone."
    status = "pass" if not weak else "warn" if not dead and len(tgood) == len(targets) else "fail" if dead else "warn"
    vals = {k: round(v, 1) for k, v in med5.items()}
    return ToolResult(
        scope=scope, verdict=Verdict(status=status, text=text), metrics=metrics, checks=checks, findings=findings,
        overlays=[LensOverlay(values=vals, ramp="sequential", legend=Legend(
            title="Wi-Fi signal, 5 GHz (estimate)", unit="dBm", min=min(vals.values()), max=max(vals.values()))),
            PinsOverlay(pins=pins)],
        assumptions=[
            Assumption(id="wifi.router_class", label=f"Router class ({inputs.router}), 5 GHz EIRP", value=eirp["5"], unit="dBm", editable=True),
            Assumption(id="eirp_24", label="2.4 GHz EIRP", value=eirp["2.4"], unit="dBm"),
            Assumption(id="model", label="Path loss model", value=COST231),
            *[Assumption(id=f"{k}_{b}", label=f"{BANDS[b]['label']} loss per {lbl}", value=BANDS[b][k], unit="dB")
              for b in ("2.4", "5") for k, lbl in (("light", f"wall under {HEAVY_WALL_M * 100:.0f} cm (stud, drywall)"),
                                                  ("heavy", f"wall {HEAVY_WALL_M * 100:.0f} cm or thicker (masonry)"),
                                                  ("window", "window (clear glass)"), ("floor", "floor"))],
            *[Assumption(id=f"material.{m}", label=f"Loss through {m}, 2.4 / 5 GHz (assumed)",
                         value=f"{MATERIALS[m]['2.4']:g} / {MATERIALS[m]['5']:g}", unit="dB")
              for m in sorted(set(inputs.wall_materials.values()))],
            Assumption(id="doors", label="Doorways are open (a closed wooden door adds about 3 dB)", value=True),
            Assumption(id="good", label="Good signal for video calls", value=GOOD, unit="dBm"),
            Assumption(id="dead", label="Dead zone below", value=WEAK, unit="dBm"),
            Assumption(id="heights", label="Router height above the floor", value=ROUTER_H_M, unit="m")])


def _pt(src):
    from shapely.geometry import Point
    return Point(src[0], src[1])
