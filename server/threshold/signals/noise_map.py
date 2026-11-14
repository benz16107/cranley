"""US DOT / BTS National Transportation Noise Map (2020 data, released 2022) at a point.

The map models 24-hour A-weighted equivalent sound level (LAeq, 24h) on a 30 m grid for road, aviation and rail
noise across the lower 48 states. It is served only as cached colour tiles (identify and export fail), down to zoom
12 (about 33 m a pixel at Houston), so the level comes back as the legend class whose colour the pixel has:
45-50, 50-55, 55-60, 60-70, 70-80, 80-90, 90+ dBA. A transparent pixel is below 45 dBA, the map's lowest class.
Tiles and the legend are cached on disk under $THRESHOLD_DATA_DIR/cache/noise_map/; requests are 1 s apart.
https://www.bts.gov/geospatial/national-transportation-noise-map
"""
from __future__ import annotations

import base64
import io
import json
import math
import threading
import time

import httpx
from PIL import Image

from ..config import CACHE

BASE = "https://geo.dot.gov/server/rest/services/Hosted/NTAD_Noise_2020_CONUS_{}/MapServer"
LAYERS = {"road": "Road", "aviation": "Aviation", "rail": "Rail"}
ZOOM = 12
FLOOR_DBA = 45.0
NOTE = "US DOT BTS National Transportation Noise Map, 2020 data (LAeq 24 h, 30 m grid, read from map tiles)"
AGENT = "threshold-hackprinceton/0.1 (noise lookup)"
GAP_S = 1.0
_lock = threading.Lock()
_last = [0.0]


def _get(url: str, path) -> bytes:
    if path.exists():
        return path.read_bytes()
    with _lock:
        wait = _last[0] + GAP_S - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.monotonic()
        r = httpx.get(url, headers={"User-Agent": AGENT}, timeout=30)
    if r.status_code == 404:
        body = b""  # no tile: nothing modelled there
    else:
        r.raise_for_status()
        body = r.content
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return body


def _legend(layer: str) -> list[tuple[float, float, tuple[int, int, int]]]:
    raw = _get(BASE.format(LAYERS[layer]) + "/legend?f=json", CACHE / "noise_map" / f"{layer}_legend.json")
    out = []
    for lyr in json.loads(raw)["layers"]:
        if lyr["layerName"] != "Image":
            continue
        for item in lyr["legend"]:
            im = Image.open(io.BytesIO(base64.b64decode(item["imageData"]))).convert("RGB")
            out.append((*parse_class(item["label"]), im.getpixel((im.width // 2, im.height // 2))))
    return out


def parse_class(label: str) -> tuple[float, float]:
    """"60.0 - 69.9" -> (60, 70); "> 90.0" -> (90, 100)."""
    label = label.strip()
    if label.startswith(">"):
        lo = float(label[1:])
        return lo, lo + 10
    lo, hi = (float(x) for x in label.split("-"))
    return lo, math.ceil(hi)


def classify(rgba: tuple[int, int, int, int], legend) -> tuple[float, float] | None:
    """The legend class nearest the pixel's colour; None for a transparent pixel (below the map's floor)."""
    if rgba[3] < 128:
        return None
    lo, hi, _ = min(legend, key=lambda c: sum((a - b) ** 2 for a, b in zip(c[2], rgba[:3])))
    return lo, hi


def tile_px(lat: float, lon: float, z: int = ZOOM) -> tuple[int, int, int, int]:
    n = 2 ** z
    x = (lon + 180) / 360 * n
    y = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n
    return int(x), int(y), int((x % 1) * 256), int((y % 1) * 256)


def level(lat: float, lon: float, layer: str) -> dict:
    """{layer, low, high, below_floor} for one layer at a point; low/high None when below 45 dBA."""
    tx, ty, px, py = tile_px(lat, lon)
    body = _get(f"{BASE.format(LAYERS[layer])}/tile/{ZOOM}/{ty}/{tx}", CACHE / "noise_map" / layer / f"{ZOOM}_{ty}_{tx}.png")
    if not body:
        return {"layer": layer, "low": None, "high": None, "below_floor": True}
    im = Image.open(io.BytesIO(body)).convert("RGBA")
    c = classify(im.getpixel((px, py)), _legend(layer))
    return {"layer": layer, "low": c[0] if c else None, "high": c[1] if c else None, "below_floor": c is None}


def levels(lat: float, lon: float) -> dict[str, dict]:
    """Road, aviation and rail levels at a point. Raises RuntimeError when the map cannot be reached."""
    try:
        return {k: level(lat, lon, k) for k in LAYERS}
    except (httpx.HTTPError, OSError, ValueError, KeyError) as e:
        raise RuntimeError(f"Noise map unavailable: {e}") from None
