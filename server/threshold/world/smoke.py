"""The smoke clock's CFAST run as a timeline the scene can play: per room, the smoke layer's height, its
temperature and thickness every five seconds, when the room becomes untenable, and the walking routes out with the
time each stretch is lost.

Every number is CFAST's own output for the run the Smoke clock tool made (found again by writing the same input
file, which is its cache key). A run that does not exist yet is not started from here: it takes minutes.
"""
from __future__ import annotations

import csv
import hashlib
import math
import re

from ..geometry._plan import floor_z, polygons
from ..tools import smoke_clock as sc
from ..tools.fire_preplan.common import BEDROOM, live_rooms, name, walls_ok

STEP_M = 0.4   # route points are resampled this close, so a route changes colour where it crosses into a room


def _layers(run_dir: str) -> tuple[list[float], dict[str, dict[str, list[float]]]]:
    """time, and per CFAST compartment id its layer height (m above its floor), upper layer temperature (C) and
    upper layer optical density (1/m), from case_compartments.csv."""
    rows = list(csv.reader(open(f"{run_dir}/case_compartments.csv")))
    ids, comps, data = rows[0], rows[2], [[float(v) for v in r] for r in rows[4:] if r]
    out: dict[str, dict[str, list[float]]] = {}
    want = {"HGT": "layer_m", "ULT": "upper_c", "ULOD": "od"}
    for i, (col, comp) in enumerate(zip(ids, comps)):
        key = want.get(col.rsplit("_", 1)[0].strip())
        if key:
            out.setdefault(comp.strip(), {})[key] = [row[i] for row in data]
    return [row[0] for row in data], out


def _first(t: list[float], ok: list[bool]) -> float | None:
    return next((ti for ti, x in zip(t, ok) if x), None)


def _densify(points: list) -> list[list[float]]:
    out = [list(points[0])]
    for a, b in zip(points, points[1:]):
        n = max(1, math.ceil(math.hypot(b[0] - a[0], b[1] - a[1]) / STEP_M))
        out += [[a[k] + (b[k] - a[k]) * i / n for k in range(3)] for i in range(1, n + 1)]
    return out


def timeline(plan: dict, closed: bool = False, fire_room: str | None = None, growth: str = "fast",
             peak_kw: float = 2000.0) -> dict:
    sid = plan["sid"]
    no = lambda why: {"sid": sid, "available": False, "reason": why}  # noqa: E731
    if not walls_ok(plan):
        return no("This scan has no wall graph, so the fire model has no doorways to move smoke through.")
    if not sc.cfast_bin():
        return no("NIST CFAST is not installed on this server.")
    comp0, info = sc.compartments(plan)
    beds = [r for r in live_rooms(plan) if r.get("label") == BEDROOM and r["id"] in comp0]
    if not beds:
        return no("No room in this scan is typed as a bedroom, so the Smoke clock has nothing to time.")
    bed_comps = {comp0[r["id"]] for r in beds}
    fire = sc._pick_fire(plan, fire_room,
                         lambda r: len(sc.reachable(plan, comp0, comp0[r["id"]]) & bed_comps) if r["id"] in comp0 else 0)
    text, comp = sc.write_input(plan, fire, closed, sc.GROWTH[growth], peak_kw)
    d = sc.RUNS / hashlib.sha1(text.encode()).hexdigest()[:16]
    if not (d / "ok").exists() and not (d / "stalled").exists():
        return no("The Smoke clock has not been run on this scan with these settings. Run it first; the fire model "
                  "takes a few minutes.")
    res = sc.run_cfast(text)   # cached: returns the finished run
    t, layers = _layers(res["dir"])
    heights = {m.group(1): float(m.group(2)) for m in re.finditer(r"&COMP ID = '(\w+)'.*? HEIGHT = ([0-9.]+)", text)}
    z, polys = floor_z(plan), polygons(plan)
    rooms_by = {r["id"]: r for r in live_rooms(plan)}
    lost: dict[str, tuple[float | None, str | None]] = {}   # compartment -> (seconds, cause)
    for cid, L in layers.items():
        dev = sc.untenable(res, cid) if cid in bed_comps else None
        if dev and (dev["time_s"] is not None or any(k.endswith("|T_" + cid) for k in res["cols"])):
            lost[cid] = (dev["time_s"], dev["cause"])     # the tool's own sensor at head height in a bedroom
        else:                                             # no sensor here: the tool's limits applied to the layer
            at = _first(t, [h <= sc.TARGET_Z and od >= sc.OD_LIMIT for h, od in zip(L["layer_m"], L["od"])])
            lost[cid] = (at, "smoke layer below head height, too thick to see" if at is not None else None)
    rooms = []
    for rid, cid in comp.items():
        if cid not in layers or polys.get(rid) is None:
            continue
        r, L = rooms_by[rid], layers[cid]
        rooms.append({"id": rid, "label": name(r), "floor": r["floor"], "comp": cid, "floor_z": round(z.get(r["floor"], 0.0), 3),
                      "ceiling_m": heights.get(cid), "bedroom": r.get("label") == BEDROOM, "fire": rid == fire["id"],
                      "layer_m": [round(v, 2) for v in L["layer_m"]], "upper_c": [round(v) for v in L["upper_c"]],
                      "od": [round(v, 2) for v in L["od"]],
                      "untenable_s": lost[cid][0], "cause": lost[cid][1],
                      "timed_by": "sensor" if cid in bed_comps else "layer"})
    return {"sid": sid, "available": True, "doors": "closed" if closed else "open", "time": t,
            "end_s": t[-1] if t else 0, "stopped_early": res["stopped_s"] is not None,
            "fire_room": {"id": fire["id"], "label": name(fire)}, "growth": growth, "peak_kw": peak_kw,
            "rooms": rooms, "routes": _routes(plan, comp, lost),
            "limits": {"head_m": sc.TARGET_Z, "od_per_m": sc.OD_LIMIT, "fed": sc.FED_LIMIT},
            "source": {"confidence": sc.SIM.confidence, "text": sc.SIM.note + ". Bedrooms are timed by the tool's "
                       f"sensor at {sc.TARGET_Z} m; other rooms are lost when the smoke layer is below {sc.TARGET_Z} m "
                       f"and its optical density passes {sc.OD_LIMIT} per metre, the tool's visibility limit."}}


def _routes(plan: dict, comp: dict[str, str], lost: dict) -> list[dict]:
    """Each bedroom's walking route out (the egress tool's), resampled, with the second at which each point is lost."""
    from shapely.geometry import Point

    from ..tools import egress_routes as er
    polys = polygons(plan)
    a = er.analyse(plan, er.Inputs.model_fields["min_width_m"].default)
    by_floor: dict[str, list[tuple[str, object]]] = {}
    for r in live_rooms(plan):
        if polys.get(r["id"]) is not None:
            by_floor.setdefault(r["floor"], []).append((r["id"], polys[r["id"]]))
    out = []
    for rid, w in a["routes"].items():
        room = next((r for r in live_rooms(plan) if r["id"] == rid), None)
        if not w["available"] or room is None or room.get("label") != BEDROOM:
            continue
        for leg in w["legs"]:
            if leg.get("stairs") or len(leg["overlay"]["points"]) < 2:
                continue
            pts = _densify(leg["overlay"]["points"])
            floor = leg["overlay"]["floor"]
            red = []
            for p in pts:
                inside = next((k for k, poly in by_floor.get(floor, []) if poly.buffer(0.15).contains(Point(p[0], p[1]))), None)
                red.append(lost.get(comp.get(inside or ""), (None, None))[0])
            out.append({"room": rid, "label": name(room), "floor": floor,
                        "points": [[round(v, 3) for v in p] for p in pts], "red_s": red})
    return out
