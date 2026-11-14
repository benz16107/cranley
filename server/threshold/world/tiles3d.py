"""Vexcel's 3D city mesh (3D Tiles 1.1: a quadtree of Draco and KTX2 glb tiles in earth-centred coordinates).

The browser cannot hold the key, so tilesets and tiles pass through this server and are cached by the Vexcel
client. Relative links inside a tileset (`./tileset?zoom=...`, `./tile?zoom=...`) resolve under our own route; they
are given the file endings (`tileset.json`, `tile.glb`) that 3D Tiles loaders read a tile's type from.
Measured 2026-11-14: two collections (Houston 2023, Los Angeles 2020-21), zoom 13 (4 km tiles) to zoom 20 (33 m
tiles, geometric error 0.75 m, about 70 kB each).
"""
from __future__ import annotations

import json
import math
import re

from ..aerial import site, vexcel
from ..sources.upstream import cache_path, write_atomic

ALLOWED = {"collection": r"[a-z0-9-]{3,80}", "layer": r"[a-z0-9-]{2,40}", "zoom": r"\d{1,2}", "tile-x": r"\d{1,9}",
           "tile-y": r"\d{1,9}", "childAOI": r"[a-z0-9-]{3,80}", "latest": r"true|false"}


def clean(params: dict[str, str]) -> dict[str, str]:
    """Only the query keys Vexcel's own tilesets use, each with a harmless value. This route carries our key."""
    out = {k: v for k, v in params.items() if k in ALLOWED and re.fullmatch(ALLOWED[k], v)}
    if len(out) != len(params) or not out:
        raise LookupError("unknown tile parameters")
    return out


NAMES = {"tileset.json": "tileset", "tile.glb": "tile"}
_LINK = re.compile(rb'"\./(tileset|tile)\?')


def fetch(name: str, params: dict[str, str]) -> bytes:
    """`tileset.json` or `tile.glb` for these parameters, a tileset's own links renamed the same way."""
    if name not in NAMES:
        raise LookupError("tileset.json or tile.glb")
    data, _ = vexcel.call("GET", f"3d/{NAMES[name]}", params=clean(params))
    return _LINK.sub(lambda m: b'"./tileset.json?' if m.group(1) == b"tileset" else b'"./tile.glb?', data) if name == "tileset.json" else data


def regions(lat: float, lon: float) -> list[dict]:
    """Every 3D collection and its bounding region, in degrees. Vexcel answers with all of them whatever the point,
    so the first answer is kept."""
    f = cache_path("world", "3d_regions.json")
    if f.exists():
        return json.loads(f.read_text())
    root = vexcel.get_json("3d/tileset", wkt=site.point(lat, lon), srid=4326)
    out = []
    for ch in root["root"].get("children") or []:
        q = dict(p.split("=", 1) for p in ch["content"]["uri"].split("?", 1)[1].split("&"))
        w, s, e, n = (math.degrees(v) for v in ch["boundingVolume"]["region"][:4])
        out.append({"collection": q["collection"], "layer": q.get("layer", "3d-cities"), "bounds": [w, s, e, n]})
    write_atomic(f, json.dumps(out).encode())
    return out


def coverage(lat: float, lon: float) -> dict | None:
    """The collection whose mesh holds this point, or None. A collection's region is a box round an irregular
    area, so the point must also fall inside one of its top tiles."""
    for reg in regions(lat, lon):
        w, s, e, n = reg["bounds"]
        if not (w <= lon <= e and s <= lat <= n):
            continue
        params = {"collection": reg["collection"], "layer": reg["layer"]}
        top = json.loads(fetch("tileset.json", params))
        la, lo = math.radians(lat), math.radians(lon)
        for ch in top["root"].get("children") or []:
            cw, cs, ce, cn = ch["boundingVolume"]["region"][:4]
            if cw <= lo <= ce and cs <= la <= cn:
                extras = (top.get("asset") or {}).get("extras") or {}
                return {**params, "capture": [extras.get("minCaptureDate"), extras.get("maxCaptureDate")],
                        "copyright": extras.get("copyrightText")}
    return None


RINGS = ((20, 60.0), (19, 150.0), (18, 340.0))  # (zoom, metres): the finest tiles within this distance of the building
PATCH_VERSION = 1


def _want(dist_m: float) -> int | None:
    return next((z for z, r in RINGS if dist_m <= r), None)


def patch(sid: str, lat: float, lon: float) -> list[dict]:
    """The tiles that cover the building's surroundings: fine near it and coarser further out, each area once.
    [{url, zoom, dist_m}], nearest first. A general 3D Tiles renderer picks tiles per frame; a building page looks at
    one spot, so the choice is made once here, which also keeps the requests to Vexcel few (about a hundred)."""
    f = cache_path("world", "tiles", f"{sid}.json")
    if f.exists():
        hit = json.loads(f.read_text())
        if hit.get("version") == PATCH_VERSION:
            return hit["tiles"]
    cover = coverage(lat, lon)
    if cover is None:
        return []
    kx, ky = 111320.0 * math.cos(math.radians(lat)), 110574.0
    out: list[dict] = []

    def dist(region: list[float]) -> float:
        w, s, e, n = (math.degrees(v) for v in region[:4])
        dx = max(w - lon, 0.0, lon - e) * kx
        dy = max(s - lat, 0.0, lat - n) * ky
        return math.hypot(dx, dy)

    def walk(node: dict) -> None:
        d = dist(node["boundingVolume"]["region"])
        want = _want(d)
        if want is None:
            return
        uri = (node.get("content") or {}).get("uri") or ""
        name, _, query = uri.removeprefix("./").partition("?")
        params = dict(p.split("=", 1) for p in query.split("&")) if query else {}
        if name == "tileset.json":  # the same tile again, in a file of its own with its children
            walk(json.loads(fetch("tileset.json", params))["root"])
            return
        kids = node.get("children") or []
        if name == "tile.glb" and (int(params.get("zoom", 0)) >= want or not kids):
            out.append({"url": f"/api/world/3d/tile.glb?{query}", "zoom": int(params.get("zoom", 0)), "dist_m": round(d, 1)})
            return
        for ch in kids:
            walk(ch)

    walk(json.loads(fetch("tileset.json", {"collection": cover["collection"], "layer": cover["layer"]}))["root"])
    out.sort(key=lambda t: t["dist_m"])
    write_atomic(f, json.dumps({"version": PATCH_VERSION, "tiles": out}).encode())
    return out
