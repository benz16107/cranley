"""Pure pieces of the storm plan: plywood cut list, door dams, carry times, the generator zone, the schedule.

Rules of thumb used here are assumptions, named in the result:
- Plywood: 4 x 8 ft sheets (1.22 x 2.44 m), each board overlapping the opening by 4 in (0.10 m) on every side
  (FEMA, "Protect Your Property from High Winds", 2010: exterior plywood at least 5/8 in, extending 4 in past
  the opening).
- Generator: at least 20 ft (6.1 m) from every door, window and vent (CDC carbon monoxide guidance; CPSC 2024
  release on Tropical Storm Beryl). Without verified positions for every opening, the zone is 20 ft from every
  wall of the house, which covers them all.
"""
from __future__ import annotations

import math

import shapely
from shapely import wkt as shapely_wkt
from shapely.geometry import Point, mapping, shape
from shapely.ops import nearest_points

SHEET_W, SHEET_H = 1.22, 2.44
OVERLAP_M = 0.10
GENERATOR_M = 6.1
BAG_LEN_M, BAG_H_M = 0.45, 0.13        # a half-filled sandbag laid lengthwise
BAG_MINUTES = 4.0                      # crew-minutes to fill and place one bag (a two-person team: about 30 an hour)
DAM_SIDE_M = 0.30                      # dam runs past each side of the doorway
DAM_MAX_M = 0.60                       # deeper than this at the door, a door dam does not hold; not worth the hours
BOARD_MINUTES = 40.0                   # crew-minutes to cut, carry and fix one window board (two people, 20 minutes)
MATERIALS_MINUTES = 120.0              # one adult, a store run in the days before a storm
HANDLE_MIN = {"hand-held": 0.5, "one person carries": 1.5, "two people carry": 3.0}
WALK_M_S = 0.7                         # carrying speed indoors
DETOUR = 1.4                           # walking distance over straight-line distance
STAIR_S = 45.0                         # one flight up with a load, per trip


def ft_in(m: float) -> str:
    inches = round(m / 0.0254)
    return f"{inches // 12}' {inches % 12}\""


def boards_for(width: float, height: float) -> list[tuple[float, float]]:
    """Pieces that cover one window with the overlap, each no bigger than a sheet."""
    w, h = width + 2 * OVERLAP_M, height + 2 * OVERLAP_M
    opts = []
    for sw, sh in ((SHEET_W, SHEET_H), (SHEET_H, SHEET_W)):
        nx, ny = math.ceil(w / sw - 1e-9), math.ceil(h / sh - 1e-9)
        opts.append((nx * ny, nx, ny))
    n, nx, ny = min(opts)
    return [(w / nx, h / ny)] * n


def pack(pieces: list[tuple[float, float]]) -> list[list[tuple[float, float]]]:
    """Shelf first-fit decreasing onto 4 x 8 sheets. Each piece is (w, h); returns the pieces on each sheet."""
    sheets: list[dict] = []
    for w, h in sorted(((min(p), max(p)) for p in pieces), key=lambda p: -p[1]):
        if h > SHEET_H + 1e-6:          # long side across the sheet instead
            w, h = h, w
        placed = False
        for s in sheets:
            for shelf in s["shelves"]:
                for pw, ph in ((w, h), (h, w)):
                    if ph <= shelf["h"] + 1e-6 and shelf["used"] + pw <= SHEET_W + 1e-6:
                        shelf["used"] += pw
                        s["pieces"].append((pw, ph))
                        placed = True
                        break
                if placed:
                    break
            if not placed:
                for pw, ph in ((w, h), (h, w)):
                    if pw <= SHEET_W + 1e-6 and s["y"] + ph <= SHEET_H + 1e-6:
                        s["shelves"].append({"h": ph, "used": pw})
                        s["y"] += ph
                        s["pieces"].append((pw, ph))
                        placed = True
                        break
            if placed:
                break
        if not placed:
            pw, ph = (w, h) if w <= SHEET_W + 1e-6 else (h, w)
            sheets.append({"y": ph, "shelves": [{"h": ph, "used": pw}], "pieces": [(pw, ph)]})
    return [s["pieces"] for s in sheets]


def cut_list(windows: list[dict]) -> dict:
    """windows: [{id, width, height, label}]. Boards per window, total sheets."""
    rows, pieces = [], []
    for w in windows:
        b = boards_for(w["width"], w["height"])
        pieces += b
        rows.append({"opening": w["id"], "room": w.get("label"), "width": w["width"], "height": w["height"],
                     "boards": len(b), "board_w": round(b[0][0], 3), "board_h": round(b[0][1], 3)})
    sheets = pack(pieces)
    return {"windows": rows, "boards": len(pieces), "sheets": len(sheets),
            "board_area": round(sum(w * h for w, h in pieces), 2), "sheet_area": round(len(sheets) * SHEET_W * SHEET_H, 2)}


def door_dam(width: float, water_at_door: float) -> dict:
    """Sandbags across one doorway for water this deep against the sill. Stacked as a pyramid above two layers."""
    length = width + 2 * DAM_SIDE_M
    layers = max(1, math.ceil((water_at_door + 0.10) / BAG_H_M))
    per = math.ceil(length / BAG_LEN_M)
    bags = per * (layers if layers <= 2 else layers * (layers + 1) // 2)
    return {"length_m": round(length, 2), "layers": layers, "bags": bags, "holds": water_at_door <= DAM_MAX_M,
            "minutes": bags * BAG_MINUTES}


def carry_minutes(size_class: str, distance_m: float, flights: int, people: int) -> float:
    """Crew-minutes to move one item: handling, there and back, stairs."""
    walk = 2 * distance_m * DETOUR / WALK_M_S / 60
    return people * (HANDLE_MIN.get(size_class, 2.0) + walk + flights * STAIR_S / 60)


def schedule(tasks: list[dict], capacity: float) -> tuple[list[dict], list[dict]]:
    """Fit tasks into `capacity` crew-minutes in the order given (the planner already ranked them). A task whose
    prerequisite was dropped is dropped too. Returns (kept with start and end crew-minutes, dropped with reasons)."""
    kept, dropped, used, have = [], [], 0.0, set()
    for t in tasks:
        need = [d for d in t.get("needs", []) if d not in have]
        if need:
            dropped.append({**t, "why": "its materials trip did not fit"})
            continue
        if used + t["minutes"] > capacity + 1e-6 and not t.get("must"):
            dropped.append({**t, "why": "no time left"})
            continue
        kept.append({**t, "start": used, "end": used + t["minutes"]})
        used += t["minutes"]
        have.add(t["id"])
    return kept, dropped


def _local(lat0: float, lon0: float):
    kx, ky = 111320.0 * math.cos(math.radians(lat0)), 110574.0
    return (lambda x, y: ((x - lon0) * kx, (y - lat0) * ky)), (lambda x, y: (lon0 + x / kx, lat0 + y / ky))


def transform(f, geom):
    """Apply a point function (x, y) -> (x, y) to every coordinate of a shape."""
    return shapely.transform(geom, lambda xy: [f(x, y) for x, y in xy])


def largest(geom):
    """The biggest polygon of a shape that may be a MultiPolygon (a footprint with a detached shed)."""
    return max(getattr(geom, "geoms", [geom]), key=lambda g: g.area)


def generator_zone(footprint_wkt: str | None, parcel: dict | None, lat0: float, lon0: float) -> dict:
    """Where on the lot a generator stands at least 20 ft from every wall: the parcel minus a 6.1 m band round the
    house. The spot offered is the nearest point of that zone to the house (shortest cord run)."""
    if not footprint_wkt:
        return {"available": False, "reason": "No building footprint from Vexcel, so distances from the walls are unknown."}
    fwd, back = _local(lat0, lon0)
    fp = transform(fwd, largest(shapely_wkt.loads(footprint_wkt)))
    lot = transform(fwd, shape(parcel)) if parcel else None
    lot_known = lot is not None and lot.area > fp.area
    if not lot_known:
        lot = fp.buffer(12.0)
    zone = lot.difference(fp.buffer(GENERATOR_M))
    out = {"available": True, "lot_known": lot_known, "zone_area_m2": round(zone.area, 1),
           "house": mapping(transform(back, fp)), "lot": mapping(transform(back, lot))}
    if zone.is_empty or zone.area < 1.0:
        far = max(fp.distance(Point(c)) for c in shapely.get_coordinates(lot))
        out.update(empty=True, zone=None, spot=None, farthest_m=round(far, 1))
        return out
    _, spot = nearest_points(fp.buffer(GENERATOR_M + 0.3), zone)
    out.update(empty=False, zone=mapping(transform(back, zone)), spot=back(spot.x, spot.y),
               spot_distance_m=round(fp.distance(spot), 2))
    return out

