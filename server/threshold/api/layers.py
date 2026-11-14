"""Map layer routes for the world explorer: the catalogue, each layer's GeoJSON (a whole city, or one tile of the
layer's own grid), the weather now, and Vexcel's orthophoto and 3D city mesh for the map. Owned by the explorer
workstream."""
from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, Response

from ..aerial.vexcel import VexcelError
from ..layers import aerial, catalog
from ..sources import matterport as mp

router = APIRouter(prefix="/api/layers")
DAY = {"Cache-Control": "max-age=86400"}
HOUR = {"Cache-Control": "max-age=3600"}


def _call(fn, *a, **k):
    try:
        return fn(*a, **k)
    except VexcelError as e:
        raise HTTPException(404 if e.status == 404 else 502, str(e)) from None
    except LookupError as e:
        raise HTTPException(404, str(e)) from None
    except (httpx.HTTPError, ValueError) as e:  # the source is down, or answered with something that is not JSON
        raise HTTPException(502, f"The source did not answer ({type(e).__name__}). Nothing was cached; try again.") from None
    except KeyError as e:
        raise HTTPException(503, f"setting missing: {e}") from None


@router.get("")
def layers(city: str = "hou") -> dict:
    """Every layer: what it is, who publishes it, how far to trust it, and the day our copy was fetched."""
    if city not in catalog.CITIES:
        raise HTTPException(404, "city is hou or la")
    return {"city": city, "layers": catalog.catalogue(city)}


@router.get("/weather")
def weather(city: str = "hou") -> dict:
    return _call(catalog.weather, city)


@router.get("/ortho/{z}/{x}/{y}.jpg")
def ortho(z: int, x: int, y: int) -> Response:
    data = _call(aerial.ortho_tile, z, x, y)
    if data is None:
        return Response(status_code=204, headers=HOUR)  # no picture here: the map keeps what is under it
    return Response(data, media_type="image/jpeg", headers=DAY)


@router.get("/city3d")
def city3d(lat: float | None = None, lon: float | None = None, sid: str | None = None) -> dict:
    """The 3D city mesh tiles round a point, or round a scan (then the near tiles are the building scene's own)."""
    if sid:
        g = _call(mp.plan, sid).get("geo") or {}
        if g.get("lat") is None:
            raise HTTPException(404, "this scan has no geocoordinates")
        return _call(aerial.patch, g["lat"], g["lon"], sid)
    if lat is None or lon is None:
        raise HTTPException(400, "give lat and lon, or sid")
    return _call(aerial.patch, lat, lon)


@router.get("/{layer}/geojson")
def city_geojson(layer: str, city: str = "hou") -> Response:
    return Response(_call(catalog.city_geojson, layer, city), media_type="application/geo+json", headers=HOUR)


@router.get("/{layer}/tile/{z}/{x}/{y}")
def tile_geojson(layer: str, z: int, x: int, y: int) -> Response:
    return Response(_call(catalog.tile_geojson, layer, z, x, y), media_type="application/geo+json", headers=DAY)
