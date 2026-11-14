"""World routes: a scan's surroundings (Vexcel 3D city mesh, surface model, orthophoto), Matterport's own scanned
mesh with colour baked from the panoramas, and the drone splat's placement. Owned by the views workstream."""
from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, Request, Response

from ..aerial.vexcel import VexcelError
from ..sources import matterport as mp
from ..sources.upstream import cache_path
from ..world import mesh, site, splatfit, terrain, tiles3d

router = APIRouter(prefix="/api/world")
DAY = {"Cache-Control": "max-age=86400"}


def _call(fn, *a, **k):
    try:
        return fn(*a, **k)
    except VexcelError as e:
        raise HTTPException(404 if e.status == 404 else 502, str(e)) from None
    except LookupError as e:
        raise HTTPException(404, str(e)) from None
    except httpx.HTTPError as e:
        raise HTTPException(502, f"upstream failed: {type(e).__name__}") from None
    except KeyError as e:
        raise HTTPException(503, f"setting missing: {e}") from None


@router.get("/3d/{name}")
def tiles(name: str, request: Request) -> Response:
    """Vexcel's 3D Tiles, passed through with our key: `tileset.json`, or `tile.glb` (Draco geometry, KTX2 texture)."""
    data = _call(tiles3d.fetch, name, dict(request.query_params))
    return Response(data, media_type="application/json" if name == "tileset.json" else "model/gltf-binary", headers=DAY)


@router.get("/{sid}/site")
def scan_site(sid: str) -> dict:
    return _call(site.describe, sid)


@router.get("/{sid}/tiles")
def scan_tiles(sid: str) -> dict:
    """The 3D city mesh tiles round the scan, nearest first: fine near the building, coarser further out."""
    g = _geo(sid)
    return {"tiles": _call(tiles3d.patch, sid, g["lat"], g["lon"])}


@router.get("/{sid}/terrain")
def scan_terrain(sid: str, size_m: float = 360, n: int = 256) -> dict:
    """The surface model round the scan as a height grid, and where the two orthophotos that texture it sit."""
    if not (60 <= size_m <= 600 and 32 <= n <= 512):
        raise HTTPException(400, "size_m is 60 to 600 and n is 32 to 512")
    g = _geo(sid)
    out = terrain.encode(_call(terrain.grid, g["lat"], g["lon"], size_m, n))
    out["ortho"] = [{"url": f"/api/aerial/ortho?lat={g['lat']}&lon={g['lon']}&size_m={s}&px={px}",
                     "bounds_enu": [round(v, 3) for v in _call(terrain.ortho_bounds_enu, g["lat"], g["lon"], s, px)]}
                    for s, px in site.ORTHO]
    return out


@router.get("/{sid}/mesh")
def scan_mesh(sid: str) -> Response:
    """Matterport's scanned mesh as one binary block (see world/mesh.py `pack`)."""
    return Response(_call(mesh.geometry, sid), media_type="application/octet-stream", headers=DAY)


@router.get("/{sid}/mesh/status")
def scan_mesh_status(sid: str, start: bool = True) -> dict:
    """Whether the colour atlas is baked; asking starts the bake (minutes the first time for a scan)."""
    return _call(mesh.status, sid, start)


@router.get("/{sid}/mesh/atlas.jpg")
def scan_mesh_atlas(sid: str) -> Response:
    if _call(mesh.status, sid, False)["state"] != "ready":
        raise HTTPException(404, "the atlas is not baked yet")
    return Response(cache_path("mesh", sid, "atlas.jpg").read_bytes(), media_type="image/jpeg", headers=DAY)


@router.get("/{sid}/splat-fit")
def scan_splat_fit(sid: str) -> dict:
    g = _geo(sid)
    return _call(splatfit.fit, sid, g["lat"], g["lon"])


def _geo(sid: str) -> dict:
    g = (_call(mp.plan, sid).get("geo") or {})
    if g.get("lat") is None:
        raise HTTPException(404, "this scan has no geocoordinates")
    return g
