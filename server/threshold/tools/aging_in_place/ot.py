"""What an occupational therapist measures on a home assessment, as far as the scan can measure it: doorway widths,
pinch points on the routes to the bathroom and bedroom, threshold heights, the bath's width and the floor beside the
bed. The rest of their list (seat heights, threshold depth, step treads, clearance under the bed, bath ledges) is
listed to confirm on site."""
from __future__ import annotations

import math

import shapely
from shapely.geometry import Polygon

from ...geometry._plan import VERDICT_STATUS, clear_width, judge
from .. import Check
from .._access import (GEO, IN, SILL_NOISE_M, STD, STEP_M, cannot, face_polygon, floor_objects, has_objects,
                       implausible, label, links_of, sill_step, step_kind)

BESIDE_BED = 30 * IN      # ADA 2010 806.2.3: a 30 x 48 in clear floor space beside the bed, parallel to it
ROUTE_M = 36 * IN         # ADA 2010 403.5.1: 36 in route
OT_STD = "What an occupational therapist measures on a home assessment"
CONFIRM = [("seats", "seat heights: the preferred chair, the bed and the toilet"),
           ("threshold_depth", "how deep each threshold is, and whether it is bevelled"),
           ("treads", "step widths and tread depths on stairs and outside steps"),
           ("under_bed", "clearance under the bed for a hoist's legs"),
           ("bath_ledges", "the bath's inside width and the ledges at its ends")]


def _strip(o, along, out, length, width):
    """A rectangle `length` along `along` from o, `width` out along `out`."""
    return Polygon([(o[0], o[1]), (o[0] + along[0] * length, o[1] + along[1] * length),
                    (o[0] + along[0] * length + out[0] * width, o[1] + along[1] * length + out[1] * width),
                    (o[0] + out[0] * width, o[1] + out[1] * width)])


def beside_bed(plan: dict, bed: dict, room_id: str) -> float | None:
    """Clear width beside the bed on its roomier long side, between the bed and the walls or other objects."""
    face = face_polygon(plan, room_id)
    if face is None:
        return None
    others = [o["footprint"] for o in floor_objects(plan, room_id, face) if o["id"] != bed["id"]]
    clear = face.difference(shapely.union_all(others)) if others else face
    (cx, cy), (w, d) = bed["center"][:2], bed["size"][:2]
    a = math.radians(bed["yaw_deg"])
    u = (math.cos(a), math.sin(a))               # along the object's width
    v = (-u[1], u[0])
    along, out, length, half = (u, v, w, d / 2) if w >= d else (v, u, d, w / 2)
    best = 0.0
    for s in (1, -1):
        o = (cx - along[0] * length / 2 + s * out[0] * half, cy - along[1] * length / 2 + s * out[1] * half)
        dirn = (s * out[0], s * out[1])
        x = 0.02
        while x <= 2.5 and clear.buffer(1e-6).contains(_strip(o, along, dirn, length, x)):
            x += 0.02
        best = max(best, x - 0.02)
    return best


def ot_checks(ctx, plan: dict) -> list[Check]:
    from ..step_free_route import Inputs as RouteInputs
    from ..step_free_route import run_routes
    out = []
    links = [x for x in links_of(plan).values() if x.get("kind") != "invisible" and x.get("width")]
    widths = [clear_width(x) for x in links if not implausible(x) and clear_width(x) is not None]
    if widths:
        n = sum(w < 0.815 for w in widths)
        out.append(Check(id="ot.doorways", rule=f"Doorway clear widths: narrowest of {len(widths)} measured, "
                         f"{n} under 32 in", measured=round(min(widths), 3), threshold=0.815, unit="m",
                         status=VERDICT_STATUS[judge(min(widths), 0.815)], standard=f"{OT_STD}; {STD['door']}"))
    res = run_routes(ctx, plan, RouteInputs(scan=plan["sid"], destinations=["Bathroom", "Bedroom"],
                                            read_panoramas=False))
    routed = [it for it in res["routes"] if it["route"]]
    chokes = [c for it in routed for c in it["chokes"]]
    if routed:
        w = min((c["width"] for c in chokes), default=None)
        out.append(Check(id="ot.pinch", rule="Pinch points between walls on the routes to the bathroom and bedroom: "
                         + (f"{len(chokes)}, the narrowest {w:.2f} m" if chokes else "none narrower than the doorways"),
                         measured=round(w, 3) if w is not None else None, threshold=round(ROUTE_M, 3), unit="m",
                         status=VERDICT_STATUS[judge(w, ROUTE_M)] if w is not None else "pass",
                         standard=f"{OT_STD}; {STD['route']}"))
    steps = [(sill_step(plan, x), x) for x in links]
    steps = [(s, x) for s, x in steps if s is not None]
    if steps:
        top, _ = max(steps, key=lambda t: t[0])
        k = step_kind(top)
        n = sum(step_kind(s) != "none" for s, _ in steps)
        out.append(Check(id="ot.thresholds", rule=f"Threshold heights: the highest of {len(steps)} doorway sills is "
                         f"{top * 100:.0f} cm off the floor, {n} over the "
                         f"{(STEP_M + SILL_NOISE_M) * 100:.0f} cm the scan can resolve",
                         measured=round(top, 3), threshold=STEP_M, unit="m",
                         status={"none": "pass", "possible": "warn"}.get(k, "fail"),
                         standard=f"{OT_STD}; {STD['level']}; sills scatter about 4 cm on flat floors"))
    things = plan.get("objects") or []
    for t in (x for x in things if "bath" in (x.get("label") or x.get("category") or "").lower()):
        out.append(Check(id=f"ot.bath.{t['id']}", rule=f"Bath outside width {min(t['size'][:2]):.2f} m, measured by "
                         "the scan; the inside is narrower, confirm it on site", measured=round(min(t["size"][:2]), 3),
                         threshold=None, unit="m", status="unknown", standard=OT_STD))
    beds = [x for x in things if "bed" in (x.get("label") or x.get("category") or "").lower() and x.get("room")]
    for b in beds:
        room = next((r for r in plan["rooms"] if r["id"] == b["room"]), None)
        w = beside_bed(plan, b, b["room"])
        if w is None:
            continue
        out.append(Check(id=f"ot.beside_bed.{b['id']}", rule=f"Clear floor beside the bed, {label(room).lower()}, on "
                         "its roomier long side", measured=round(w, 2), threshold=round(BESIDE_BED, 3), unit="m",
                         status=VERDICT_STATUS[judge(w, BESIDE_BED)],
                         standard=f"{OT_STD}; ADA 2010 806.2.3: 30 x 48 in beside the bed, parallel to it"))
    if not beds:
        out.append(cannot("ot.beside_bed", "the floor beside the bed: " + (
            "this phone scan found no bed" if has_objects(plan) else "this scan records walls only, not the bed")))
    out += [cannot(f"ot.{cid}", f"{what} (confirm on site)") for cid, what in CONFIRM]
    return out
