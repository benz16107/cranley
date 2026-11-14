"""Shared lookups over a ScanPlan dict (Contract 1). Pure functions, no I/O."""
from __future__ import annotations

import math
import statistics

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import polygonize, unary_union
from shapely.validation import make_valid

CAMERA_HEIGHT_M = 1.4   # typical Matterport tripod height; only used when a floor has no doorway sills
DOOR_PROBE_M = 0.25     # how far either side of a wall we look for a room


def unavailable(reason: str, **extra) -> dict:
    """The one shape for 'this scan cannot answer that'. Callers check `available`."""
    return {"available": False, "reason": reason, **extra}


def geo_source(note: str, confidence: str = "high") -> dict:
    return {"layer": "matterport", "method": "geometry", "confidence": confidence, "note": note}


def rooms_by_id(plan: dict) -> dict[str, dict]:
    return {r["id"]: r for r in plan.get("rooms") or []}


def walls_by_id(plan: dict) -> dict[str, dict]:
    return {w["id"]: w for w in plan.get("walls") or []}


def openings_by_id(plan: dict) -> dict[str, dict]:
    return {o["id"]: o for o in plan.get("openings") or []}


def _clean(poly) -> Polygon | None:
    if poly is None or poly.is_empty:
        return None
    if not poly.is_valid:
        poly = make_valid(poly)
    polys = [g for g in getattr(poly, "geoms", [poly]) if isinstance(g, Polygon)]
    best = max(polys, key=lambda g: g.area, default=None)
    return best if best is not None and best.area > 0 else None


def _faces(wall_ids: list[str], walls: dict[str, dict]) -> Polygon | None:
    segs = [LineString([walls[w]["a"], walls[w]["b"]]) for w in wall_ids if w in walls]
    return _clean(max(polygonize(unary_union(segs)), key=lambda g: g.area, default=None)) if segs else None


def _build_polygons(plan: dict) -> dict[str, tuple[Polygon | None, str | None]]:
    walls = walls_by_id(plan)
    out = {}
    for r in plan.get("rooms") or []:
        pts = r.get("polygon") or []
        poly, src = (_clean(Polygon(pts)), "scan") if len(pts) >= 3 else (None, None)
        if poly is None:  # the normalizer could not chain the edges (a stub wall, a T): rebuild from faces
            poly, src = _faces(r.get("walls") or [], walls), "rebuilt"
        if poly is not None:
            for hole in r.get("holes") or []:
                h = _faces(hole, walls)
                if h is not None:
                    poly = _clean(poly.difference(h)) or poly
        out[r["id"]] = (poly, src if poly is not None else None)
    # a rebuilt outline encloses the rooms inside it (offices in an open floor); cut them out
    floor_of = {r["id"]: r["floor"] for r in plan.get("rooms") or []}
    for rid, (poly, src) in list(out.items()):
        if src != "rebuilt":
            continue
        inner = [q for k, (q, _) in out.items() if k != rid and q is not None and floor_of[k] == floor_of[rid]
                 and q.intersection(poly).area > 0.5 * q.area]
        if inner:
            out[rid] = (_clean(poly.difference(unary_union(inner))) or poly, src)
    return out


def polygons(plan: dict) -> dict[str, Polygon | None]:
    """Floor polygon per room at the wall centre lines, holes (columns) removed. Rooms whose edges the
    normalizer could not chain are rebuilt from their walls; rooms with no walls map to None."""
    return {k: v[0] for k, v in cached(plan, "polygons", lambda: _build_polygons(plan)).items()}


def polygon_source(plan: dict, room_id: str) -> str | None:
    return cached(plan, "polygons", lambda: _build_polygons(plan))[room_id][1]


_CACHE: dict[tuple, object] = {}


def cached(plan: dict, key: str, build):
    # shortcut: keyed on object identity and sizes, so a plan edited in place keeps stale results; key on a
    # content hash if plans start being mutated
    k = (id(plan), plan.get("sid"), len(plan.get("walls") or []), len(plan.get("rooms") or []),
         len(plan.get("openings") or []), key)
    if k not in _CACHE:
        if len(_CACHE) > 256:
            _CACHE.clear()
        _CACHE[k] = build()
    return _CACHE[k]


def room_label(room: dict) -> str:
    return room.get("label") or "Unlabelled room"


def floor_z(plan: dict) -> dict[str, float]:
    """Floor elevation per floor in scan z. Opening sills are absolute scan z, so the median doorway sill on a
    floor is its floor level. Floors without doorways fall back to pano height minus a tripod height."""
    out: dict[str, float] = {}
    for fl in plan.get("floors") or []:
        sills = [o["sill"] for o in plan.get("openings") or []
                 if o["floor"] == fl["id"] and o["type"] != "window" and o.get("sill") is not None]
        if sills:
            out[fl["id"]] = statistics.median(sills)
            continue
        pz = [p["position"][2] for p in plan.get("panos") or [] if p.get("floor") == fl["id"]]
        out[fl["id"]] = statistics.median(pz) - CAMERA_HEIGHT_M if pz else 0.0
    return out


def default_ceiling(plan: dict) -> float | None:
    hs = [r["height"] for r in plan.get("rooms") or [] if r.get("height")]
    return statistics.median(hs) if hs else None


def wall_normal(wall: dict) -> tuple[float, float]:
    (ax, ay), (bx, by) = wall["a"], wall["b"]
    length = math.hypot(bx - ax, by - ay) or 1.0
    return (-(by - ay) / length, (bx - ax) / length)


def rooms_beside(plan: dict, opening: dict, wall: dict | None) -> list[str]:
    """Rooms on either side of an opening found by probing the room polygons, for openings whose wall is on no
    room boundary (or on only one). Returns room ids in probe order, same floor only."""
    if wall is None:
        return []
    nx, ny = wall_normal(wall)
    cx, cy = opening["center"]
    found: list[str] = []
    polys = polygons(plan)
    for s in (1, -1):
        p = Point(cx + s * nx * DOOR_PROBE_M, cy + s * ny * DOOR_PROBE_M)
        for r in plan.get("rooms") or []:
            if r["floor"] != opening["floor"] or r["id"] in found:
                continue
            poly = polys.get(r["id"])
            if poly is not None and poly.contains(p):
                found.append(r["id"])
                break
    return found


# A hinged door open at 90 degrees takes its leaf (1 3/8 to 1 3/4 in) and its stop out of the wall opening.
HUNG_DOOR_ALLOWANCE_M = 0.05
SCAN_TOLERANCE_M = 0.025  # about 1 in: Matterport's ~1% error on a door, plus wall-graph snapping
VERDICT_STATUS = {"likely pass": "pass", "measure on site": "warn", "likely fail": "fail", "not available": "unknown"}


def clear_width(link: dict) -> float | None:
    """Estimated clear width of a doorway, opening or invisible wall. Doorways lose the hung-door allowance."""
    w = link.get("width")
    if w is None:
        return None
    return max(0.0, w - HUNG_DOOR_ALLOWANCE_M) if link.get("kind", link.get("type")) == "doorway" else w


def judge(measured: float | None, threshold: float, tol: float = SCAN_TOLERANCE_M, at_least: bool = True) -> str:
    """'likely pass', 'likely fail' or 'measure on site' when the value is within the tolerance of the limit."""
    if measured is None:
        return "not available"
    margin = (measured - threshold) if at_least else (threshold - measured)
    return "likely pass" if margin >= tol else "likely fail" if margin < -tol else "measure on site"
