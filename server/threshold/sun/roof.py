"""A roof read from the surface model: facets by slope and the way they face, setbacks, and how much of a clear-sky
year of sun each part of the roof gets after trees and neighbours.

Vexcel's property extract gives a roof shape and height but no facets, so the facets come from the DSM's slope:
each roof cell faces downhill. Cells are grouped by the compass sector they face (45 degrees wide) or as flat
(under 10 degrees). The energy of a cell is a clear-sky year of beam and diffuse light on the plane it would
carry panels in (flush with a pitched facet; tilted 10 degrees south on a flat one), relative to the same year on
an unshaded south-facing 20 degree plane, so a PVWatts yield for that reference plane scales it to kWh.
"""
from __future__ import annotations

import numpy as np
import shapely
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from . import horizon as hz
from .path import cos_incidence, year_path

FLAT_DEG, STEEP_DEG = 10.0, 60.0   # under FLAT is a flat roof; over STEEP is a wall, a parapet or a chimney side
FLAT_TILT = 10.0                    # racking on a flat roof
REF = (180.0, 20.0)                 # the plane a PVWatts yield is quoted for: south, 20 degrees
SECTORS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def cells(g: dict, outline: Polygon) -> dict:
    """Every grid cell whose centre is inside `outline` (east/north metres in the grid's frame): position, surface
    height, pitch and the compass direction it faces."""
    H = g["heights"]
    west, south, east, north = g["bounds_enu"]
    rows, cols = H.shape
    cell = (east - west) / cols
    dzde = np.gradient(H, axis=1) / cell
    dzdn = -np.gradient(H, axis=0) / cell
    ys, xs = np.mgrid[0:rows, 0:cols]
    ce, cn = west + (xs + 0.5) * cell, north - (ys + 0.5) * (north - south) / rows
    inside = shapely.contains_xy(outline, ce, cn) & np.isfinite(H)
    pitch = np.degrees(np.arctan(np.hypot(dzde, dzdn)))
    aspect = np.degrees(np.arctan2(-dzde, -dzdn)) % 360
    label = np.where(pitch < FLAT_DEG, 8, ((aspect + 22.5) // 45).astype(int) % 8)
    label = np.where(pitch > STEEP_DEG, -1, label)
    return {"e": ce, "n": cn, "z": H, "pitch": pitch, "aspect": aspect, "label": np.where(inside, label, -2),
            "inside": inside, "cell": cell}


def _edge(label: np.ndarray) -> np.ndarray:
    """Cells next to a cell of another facet: ridges, hips and valleys."""
    p = np.pad(label, 1, mode="edge")
    c = p[1:-1, 1:-1]
    return (p[:-2, 1:-1] != c) | (p[2:, 1:-1] != c) | (p[1:-1, :-2] != c) | (p[1:-1, 2:] != c)


def analyse(g: dict, outline: Polygon, lat: float, lon: float, year: int, setback_m: float = 0.9,
            min_access: float = 0.8) -> dict:
    """{facets: [...], ref_poa_kwh_m2, cell_m}. Each facet: id, faces, pitch_deg, azimuth_deg, roof_m2 (sloped area),
    usable_m2, access (shaded over unshaded sun, mean over its usable cells), orientation (unshaded sun on its plane
    over the reference plane), yield_ratio (shaded sun on its plane over the reference), polygons (usable area,
    east/north) and centroid. A cell is usable when it is `setback_m` inside the outline, not on a ridge or hip,
    and keeps at least `min_access` of its unshaded sun."""
    c = cells(g, outline)
    cell = c["cell"]
    inner = shapely.contains_xy(outline.buffer(-setback_m), c["e"], c["n"]) if setback_m > 0 else c["inside"]
    cand = inner & (c["label"] >= 0) & ~_edge(c["label"])
    sky = year_path(lat, lon, year)
    ref = _poa(sky, *REF, None)
    out = []
    for lab in range(9):
        roof = (c["label"] == lab)
        if roof.sum() < 4:
            continue
        flat = lab == 8
        pitch = float(np.median(c["pitch"][roof]))
        a = np.radians(c["aspect"][roof])
        az = 180.0 if flat else float(np.degrees(np.arctan2(np.sin(a).mean(), np.cos(a).mean())) % 360)
        tilt = FLAT_TILT if flat else pitch
        free = _poa(sky, az, tilt, None)
        idx = np.argwhere(cand & roof)
        acc = np.array([_poa(sky, az, tilt, hz.horizon(g, c["e"][i, j], c["n"][i, j], c["z"][i, j] + 0.3, start_m=1.0,
                                                       max_m=min(60.0, (g["bounds_enu"][2] - g["bounds_enu"][0]) / 2)))
                        for i, j in idx]) / free if len(idx) else np.array([])
        good = idx[acc >= min_access] if len(idx) else idx
        slope = 1 / np.cos(np.radians(0 if flat else pitch))
        polys = unary_union([box(c["e"][i, j] - cell / 2, c["n"][i, j] - cell / 2, c["e"][i, j] + cell / 2,
                                 c["n"][i, j] + cell / 2) for i, j in good]) if len(good) else Polygon()
        out.append({"id": "flat" if flat else SECTORS[lab], "faces": "flat" if flat else SECTORS[lab],
                    "pitch_deg": round(pitch, 1), "azimuth_deg": round(az, 1), "panel_tilt_deg": round(tilt, 1),
                    "roof_m2": round(roof.sum() * cell * cell * slope, 1),
                    "usable_m2": round(len(good) * cell * cell * (1 if flat else slope), 1),
                    "candidate_m2": round(len(idx) * cell * cell * (1 if flat else slope), 1),
                    "access": round(float(acc[acc >= min_access].mean()), 3) if (acc >= min_access).any() else
                    (round(float(acc.mean()), 3) if len(acc) else None),
                    "orientation": round(free / ref, 3),
                    "yield_ratio": round(free / ref * float(acc[acc >= min_access].mean()), 3) if (acc >= min_access).any() else 0.0,
                    "polygons": [p for p in getattr(polys, "geoms", [polys]) if not p.is_empty],
                    "centroid": (float(c["e"][roof].mean()), float(c["n"][roof].mean()))})
    return {"facets": sorted(out, key=lambda f: -f["usable_m2"]), "ref_poa_kwh_m2": round(ref, 1), "cell_m": round(cell, 3)}


def _poa(sky: dict, az: float, tilt: float, hzn: np.ndarray | None) -> float:
    """kWh/m2 in the clear-sky year on a plane facing `az` tilted `tilt`; the beam is dropped where `hzn` blocks it.
    Diffuse is isotropic and never blocked (a skyline of trees takes some of it; not counted)."""
    cosi = np.maximum(cos_incidence(sky["az"], sky["el"], az, tilt), 0)
    beam = sky["dni"] * cosi
    if hzn is not None:
        beam = np.where(hz.blocked(hzn, sky["az"], sky["el"]), 0, beam)
    diffuse = sky["dhi"] * (1 + np.cos(np.radians(tilt))) / 2
    return float((beam + diffuse).sum() * sky["hours"] / 1000)
