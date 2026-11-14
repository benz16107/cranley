"""Who lives here, by census tract: population density, median household income, median age, people 65 and over,
renters. American Community Survey 5-year estimates, read from Esri's hosted copy of the Census Bureau's tables (the
Census API itself now asks for a key). One upstream fetch per city serves all five layers.
"""
from __future__ import annotations

from ..catalog import CITIES, Layer, arcgis
from ..lookup import cached

ACS = ("https://P3ePLMYs2RVChkJx.svcs.arcgis.com/P3ePLMYs2RVChkJx/arcgis/rest/services/"
       "ACS_Population_and_Housing_Basics_View_Boundaries/FeatureServer/{}")
TRACT, COUNTY = ACS.format(2), ACS.format(1)
FIELDS = ("GEOID,NAME,County,ALAND,B01001_001E,B01001_calc_pctLT18E,B01001_calc_pctGE65E,B01002_001E,B19049_001E,"
          "B25002_001E,B25003_001E,B25003_002E,B25003_003E,B25058_001E,B25077_001E")
SRC = "US Census Bureau, American Community Survey 5-year estimates (Esri's hosted copy)"
URL = ACS.format("").rstrip("/")
COMMON = dict(source=SRC, source_url=URL, licence="Public domain (US Census Bureau); Esri hosting terms apply",
              attribution="US Census Bureau ACS; Esri", scope="city", shape="area", group="People", minzoom=8)
NOTE = (" ACS figures are survey estimates with a margin of error, largest in small tracts. Each tract is one colour: "
        "it says nothing about a single street.")


def bands(edges: list[float], fmt) -> list[list]:
    labels = [f"under {fmt(edges[0])}"] + [f"{fmt(a)} to {fmt(b)}" for a, b in zip(edges, edges[1:])] + [f"{fmt(edges[-1])} or more"]
    return [[i, t] for i, t in enumerate(labels)]


def level(v: float | None, edges: list[float]) -> int | None:
    return None if v is None else sum(v >= e for e in edges)


def density(a: dict) -> float | None:
    pop, land = a.get("B01001_001E"), a.get("ALAND")
    return round(pop / (land / 1e6)) if pop is not None and land else None


def renters(a: dict) -> float | None:
    occ, rent = a.get("B25003_001E"), a.get("B25003_003E")
    return round(100 * rent / occ, 1) if occ and rent is not None else None


money = lambda v: f"${v / 1000:.0f}k"  # noqa: E731
pct = lambda v: f"{v:g}%"  # noqa: E731
num = lambda v: f"{v:,.0f}"  # noqa: E731

# layer id -> (title, value of a tract, edges, how a value reads, legend title, unit, hue)
SPEC = {
    "acs_density": ("Population density", density, [1000, 2500, 5000, 10000, 20000], num, "People per km²", "per km²"),
    "acs_income": ("Median household income", lambda a: a.get("B19049_001E"), [35000, 60000, 90000, 130000, 180000], money,
                   "Median household income", "USD"),
    "acs_age": ("Median age", lambda a: a.get("B01002_001E"), [30, 35, 40, 45, 50], lambda v: f"{v:g}", "Median age", "years"),
    "acs_seniors": ("People 65 and over", lambda a: a.get("B01001_calc_pctGE65E"), [8, 12, 16, 20, 25], pct, "Share 65 and over", "%"),
    "acs_renters": ("Renter households", renters, [20, 35, 50, 65, 80], pct, "Share of households renting", "%"),
}


def tracts(city: str) -> list[dict]:
    """Every tract touching a city's box with the fields above, generalised to about 30 m. One fetch, kept a month."""
    def make():
        feats, _ = arcgis(TRACT + "/query", CITIES[city], FIELDS, 0.0003)
        return feats
    return cached(f"acs-tracts|{city}|{FIELDS}", make, 30 * 86400)


def describe(a: dict) -> str:
    parts = []
    if a.get("B01001_001E") is not None:
        d = density(a)
        parts.append(f"{a['B01001_001E']:,} people" + (f", {d:,} per km²" if d else ""))
    if a.get("B19049_001E"):
        parts.append(f"median household income ${a['B19049_001E']:,}")
    if a.get("B01002_001E"):
        parts.append(f"median age {a['B01002_001E']:g}")
    return "; ".join(parts)


def _fetcher(layer: str):
    _, value, edges, *_ = SPEC[layer]

    def fetch(box, city):
        out = []
        for f in tracts(city):
            a = f.get("properties") or {}
            v = value(a)
            if not f.get("geometry"):
                continue
            p = {"name": a.get("NAME") or "Census tract", "detail": describe(a)}
            if v is not None:
                p["level"], p["value"] = level(v, edges), v
            out.append({"type": "Feature", "geometry": f["geometry"], "properties": p})
        return out, False
    return fetch


LAYERS = tuple(
    Layer(lid, title, note=f"{title} by census tract." + NOTE, confidence="medium",
          extra={"hue": "--tool-5", "legend": {"title": legend, "unit": unit, "stops": bands(edges, fmt)}}, **COMMON)
    for lid, (title, _, edges, fmt, legend, unit) in SPEC.items())
FETCH = {lid: _fetcher(lid) for lid in SPEC}
