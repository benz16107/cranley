"""Is a point in a CAL FIRE Fire Hazard Severity Zone? The two public layers CAL FIRE's own lookup map reads: the State
Responsibility Area zones in effect from 2024-04-01 and the Local Responsibility Area zones the State Fire Marshal
recommended in 2025 (which cities then adopt). One query per layer per point, cached on disk for good, at least a
second apart.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time

import httpx

from ...config import CACHE

BASE = "https://services1.arcgis.com/jUJYIo9tSA7EHvfZ/arcgis/rest/services"
LAYERS = (("SRA", "FHSZSRA_23_3", "State Responsibility Area zones, effective 2024-04-01"),
          ("LRA", "FHSALRA25_v1_All", "Local Responsibility Area zones recommended by the State Fire Marshal, 2025"))
VIEWER = "https://experience.arcgis.com/experience/5065c998b4b0462f9ec3c6c226c610a9"
GAP_S = 1.0
_lock, _last = threading.Lock(), [0.0]


def _query(layer: str, lat: float, lon: float) -> list[dict]:
    params = {"geometry": f"{lon:.6f},{lat:.6f}", "geometryType": "esriGeometryPoint", "inSR": "4326",
              "spatialRel": "esriSpatialRelIntersects", "outFields": "SRA,FHSZ,FHSZ_Description",
              "returnGeometry": "false", "f": "json"}
    f = CACHE / "calfire" / f"{hashlib.sha256(json.dumps([layer, params], sort_keys=True).encode()).hexdigest()[:24]}.json"
    if f.exists():
        return json.loads(f.read_text())
    with _lock:
        wait = _last[0] + GAP_S - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.monotonic()
    r = httpx.get(f"{BASE}/{layer}/FeatureServer/0/query", params=params, timeout=30,
                  headers={"User-Agent": "threshold-site-tools/0.1"})
    r.raise_for_status()
    body = r.json()
    if "error" in body:
        raise RuntimeError(f"CAL FIRE layer {layer}: {body['error'].get('message')}")
    out = [x["attributes"] for x in body.get("features") or []]
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(out))
    return out


def zone(lat: float, lon: float) -> dict:
    """{available, zone: "Very High"|"High"|"Moderate"|None, responsibility: "SRA"|"LRA"|None, layer, note}.
    `zone` None with available True means the point is in neither layer's zones."""
    try:
        for resp, layer, note in LAYERS:
            hits = _query(layer, lat, lon)
            best = max(hits, key=lambda a: a.get("FHSZ") or 0, default=None)
            if best and best.get("FHSZ_Description"):
                return {"available": True, "zone": best["FHSZ_Description"], "responsibility": resp, "layer": layer,
                        "note": f"CAL FIRE {note}; check the parcel on {VIEWER}"}
    except (httpx.HTTPError, RuntimeError, ValueError) as e:
        return {"available": False, "zone": None, "responsibility": None, "layer": None,
                "note": f"CAL FIRE's hazard layer did not answer ({str(e)[:80]})"}
    return {"available": True, "zone": None, "responsibility": None, "layer": None,
            "note": "Outside every mapped Fire Hazard Severity Zone in CAL FIRE's 2024 SRA and 2025 LRA layers"}
