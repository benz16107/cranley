"""Aerial routes (Contract 2): ortho, property facts, elevation, detection. Owned by perception."""
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from ..aerial import detect as det
from ..aerial import site
from ..aerial.vexcel import VexcelError

router = APIRouter(prefix="/api/aerial")


def _guard(fn, *a, **k):
    try:
        return fn(*a, **k)
    except VexcelError as e:
        raise HTTPException(502 if e.status >= 500 else 404 if e.status == 404 else 400, str(e)) from None


@router.get("/ortho")
def ortho(lat: float, lon: float, size_m: float = 60, px: int = 1024) -> Response:
    """JPEG, north up. Headers carry the pixel transform: bounds (west,south,east,north) in Web Mercator, linear."""
    if not (5 <= size_m <= 1000 and 64 <= px <= 2048):
        raise HTTPException(400, "size_m must be 5-1000 and px 64-2048")
    o = _guard(site.ortho, lat, lon, size_m, px)
    return Response(o.image, media_type="image/jpeg", headers={
        "X-Bounds": ",".join(f"{b:.8f}" for b in o.bounds), "X-Projection": "EPSG:3857",
        "X-Metres-Per-Px": f"{o.metres_per_px:.4f}", "X-Capture": o.meta.get("first-capture-date") or "",
        "Access-Control-Expose-Headers": "X-Bounds, X-Projection, X-Metres-Per-Px, X-Capture",
        "Cache-Control": "max-age=86400"})


@router.get("/property")
def property_facts(lat: float, lon: float) -> dict:
    return _guard(site.site_facts, lat, lon)


@router.get("/elevation")
def elevation(lat: float, lon: float, to_lat: float | None = None, to_lon: float | None = None, n: int = 50) -> dict:
    """Ground and surface at a point; with to_lat and to_lon, a profile along the line."""
    if to_lat is not None and to_lon is not None:
        return _guard(site.elevation_profile, (lat, lon), (to_lat, to_lon), n)
    return _guard(site.ground_and_surface, lat, lon)


class DetectIn(BaseModel):
    lat: float
    lon: float
    size_m: float = Field(80, ge=10, le=300)
    labels: list[str] = Field(default_factory=lambda: ["car"], min_length=1, max_length=8)
    obliques: bool = False
    threshold: float = Field(0.4, ge=0.05, le=0.95)
    method: str = Field("auto", pattern="^(auto|vexcel|vision)$")


@router.post("/detect")
def detect(body: DetectIn) -> dict:
    return _guard(det.detect, body.lat, body.lon, body.size_m, body.labels,
                  obliques=body.obliques, threshold=body.threshold, method=body.method)
