"""Vexcel imagery for the map itself: orthophoto tiles, and the 3D city mesh tiles round any point.

Both pass through the Vexcel client, which keeps every answer on disk and holds the whole process to about three
requests a second. Nothing is asked for outside the two cities, and a tile Vexcel has no picture for is remembered
as missing so it is not asked for twice.
"""
from __future__ import annotations

import json
import math

from ..aerial import vexcel
from ..sources.upstream import cache_path, write_atomic
from ..world import tiles3d
from .catalog import city_of, tile_box

ORTHO_Z = (14, 21)          # below 14 a free national mosaic is sharp enough; 21 is Vexcel's finest
ORTHO_LAYER = "urban"
# (zoom, metres): the finest tiles within this distance. The first three are the building scene's own rings
# (world/tiles3d.RINGS), so the map and the scene draw the same tiles round a building; the outer two carry the
# city on to the edge of a tilted view.
RINGS = (*tiles3d.RINGS, (17, 800.0), (16, 1600.0))
GRID_DEG = 0.002            # patches for a roaming map are centred on a grid this fine (about 200 m)
PATCH_VERSION = 1


def ortho_tile(z: int, x: int, y: int) -> bytes | None:
    """One 256 px orthophoto tile as JPEG, or None where Vexcel has no picture."""
    if not ORTHO_Z[0] <= z <= ORTHO_Z[1] or city_of(tile_box(z, x, y)) is None:
        return None
    miss = cache_path("layers", "ortho_miss", f"{z}_{x}_{y}")
    if miss.exists():
        return None
    try:
        data, _ = vexcel.call("GET", "ortho/tile", params={"layer": ORTHO_LAYER, "zoom": z, "tile-x": x, "tile-y": y})
    except vexcel.VexcelError as e:
        if e.status in (400, 404, 422):
            write_atomic(miss, b"")
            return None
        raise
    return data


def patch(lat: float, lon: float, key: str | None = None) -> dict:
    """The city mesh tiles round a point, fine near it and coarser further out, each area once, nearest first:
    {anchor, tiles: [{url, zoom, dist_m}], capture, copyright}. `key` names the cache file (a scan id); without it
    the point is snapped to the grid, so a roaming map asks for few distinct patches."""
    if key is None:
        lat, lon = round(lat / GRID_DEG) * GRID_DEG, round(lon / GRID_DEG) * GRID_DEG
        key = f"g_{lat:.3f}_{lon:.3f}"
    f = cache_path("layers", "city3d", f"{key}.json")
    if f.exists():
        hit = json.loads(f.read_text())
        if hit.get("version") == PATCH_VERSION:
            return hit
    out: dict = {"version": PATCH_VERSION, "anchor": {"lat": lat, "lon": lon}, "tiles": [], "capture": [], "copyright": None}
    cover = tiles3d.coverage(lat, lon) if city_of((lon, lat, lon, lat)) else None
    if cover is None:
        return out  # not cached: coverage is one small answer, and a miss here may be Vexcel being down
    kx, ky = 111320.0 * math.cos(math.radians(lat)), 110574.0

    def dist(region: list[float]) -> float:
        w, s, e, n = (math.degrees(v) for v in region[:4])
        return math.hypot(max(w - lon, 0.0, lon - e) * kx, max(s - lat, 0.0, lat - n) * ky)

    def walk(node: dict) -> None:
        d = dist(node["boundingVolume"]["region"])
        want = next((z for z, r in RINGS if d <= r), None)
        if want is None:
            return
        uri = (node.get("content") or {}).get("uri") or ""
        name, _, query = uri.removeprefix("./").partition("?")
        params = dict(p.split("=", 1) for p in query.split("&")) if query else {}
        if name == "tileset.json":  # the same tile again, in a file of its own with its children
            walk(json.loads(tiles3d.fetch("tileset.json", params))["root"])
            return
        kids = node.get("children") or []
        if name == "tile.glb" and (int(params.get("zoom", 0)) >= want or not kids):
            out["tiles"].append({"url": f"/api/world/3d/tile.glb?{query}", "zoom": int(params.get("zoom", 0)), "dist_m": round(d, 1)})
            return
        for ch in kids:
            walk(ch)

    walk(json.loads(tiles3d.fetch("tileset.json", {"collection": cover["collection"], "layer": cover["layer"]}))["root"])
    out["tiles"].sort(key=lambda t: t["dist_m"])
    out["capture"], out["copyright"] = cover["capture"], cover["copyright"]
    write_atomic(f, json.dumps(out).encode())
    return out
