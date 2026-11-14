"""City of Los Angeles: zoning and the General Plan's land use from ZIMAS (the planning department's map service),
building permits from LADBS on data.lacity.org (Socrata), and LADOT's bikeways. No keys."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ..catalog import AGENT, Layer, send
from ._arcgis import collect, join, layer

ZIMAS = "https://zimas.lacity.org/arcgis/rest/services/zma/zimas/MapServer/"
# each in two layers: the 1946 code (Chapter 1) and the new code (Chapter 1A, Downtown so far)
ZONING, GENPLAN = [ZIMAS + "1102", ZIMAS + "1101"], [ZIMAS + "1202", ZIMAS + "1201"]
BIKEWAYS = "https://services1.arcgis.com/tp9wqSVX1AitKgjd/arcgis/rest/services/LA_City_Bikeways/FeatureServer/0"
PERMITS = "https://data.lacity.org/resource/pi9x-tg5x.json"  # LADBS building permits issued from 2020 to present
CITY = {"cities": ("la",), "licence": "City of Los Angeles open data (public)"}
ZONE_GROUP = {"R": "Residential", "C": "Commercial", "M": "Industrial", "P": "Parking", "O": "Open space", "A": "Agricultural"}


def zone_group(zone: str) -> str:
    z = (zone or "").upper().lstrip("()[]QT")  # [Q], (T) and the like are conditions written before the zone
    if z.startswith("[") or "][" in (zone or ""):  # Chapter 1A strings: [form-frontage-standards][use-density][district]
        return "Chapter 1A (new code)"
    if z.startswith(("OS", "PF")):
        return "Open space" if z.startswith("OS") else "Public facilities"
    if z.startswith(("RE", "RS", "RA", "RD", "RW", "R1", "R2", "R3", "R4", "R5", "RU", "RZ", "RMP")):
        return "Residential"
    if z.startswith(("CR", "C1", "C2", "C4", "C5", "CM", "CW")):
        return "Commercial"
    if z.startswith(("MR", "M1", "M2", "M3")):
        return "Industrial"
    return "Other or specific plan"


LEGEND = [[0, "Open space"], [1, "Residential"], [2, "Public facilities"], [3, "Other or specific plan"],
          [4, "Commercial, or the new Chapter 1A code"], [5, "Industrial"]]  # one stop per level: the list keys on it
GROUP_LEVEL = {"Open space": 0, "Residential": 1, "Public facilities": 2, "Other or specific plan": 3, "Commercial": 4,
               "Chapter 1A (new code)": 4, "Industrial": 5}


def permits(box, city):
    """Permits LADBS issued in the last two years inside one map tile."""
    w, s, e, n = box
    since = (datetime.now(UTC) - timedelta(days=730)).strftime("%Y-%m-%dT00:00:00")
    rows = send("GET", PERMITS, headers=AGENT, timeout=90, params={
        "$select": "permit_nbr,primary_address,permit_type,permit_sub_type,work_desc,issue_date,valuation,lat,lon",
        "$where": f"within_box(geolocation, {n}, {w}, {s}, {e}) AND issue_date > '{since}'",
        "$order": "issue_date DESC", "$limit": 3000}).json()
    out = []
    for r in rows:
        try:
            lon, lat = float(r["lon"]), float(r["lat"])
        except (KeyError, TypeError, ValueError):
            continue
        kind = r.get("permit_type") or "Permit"
        out.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]},
                    "properties": {"name": f"{kind}, {(r.get('primary_address') or '').title()}".strip(", "),
                                   "detail": join((r.get("issue_date") or "")[:10], r.get("permit_sub_type"),
                                                  (r.get("work_desc") or "")[:120]),
                                   "fast": kind.startswith("Bldg-New")}})
    return out, len(rows) >= 3000


_pairs = (
    layer("la_zoning", "Zoning", "Rules", "area", ZONING, grid_z=15, minzoom=13.5, fields="ZONE_CMPLT,ZONE_CLASS",
          offset=0.000005, name="ZONE_CMPLT", detail=lambda a: zone_group(a.get("ZONE_CMPLT") or ""),
          props=lambda a: {"level": GROUP_LEVEL[zone_group(a.get("ZONE_CMPLT") or "")]},
          source="Los Angeles City Planning, ZIMAS", source_url="https://zimas.lacity.org/", confidence="high",
          note="The zone string on each lot, such as C2-1VL or R1-1: class, then height district. Q and T conditions, "
          "D limits, specific plans and overlays can change what it allows; ZIMAS's parcel report lists them.",
          extra={"hue": "--tool-7", "legend": {"title": "Zone class", "unit": "", "stops": LEGEND}},
          **CITY),
    layer("la_general_plan", "General Plan land use", "Rules", "area", GENPLAN, grid_z=14, minzoom=12.5,
          fields="*", offset=0.00001,
          name=lambda a: a.get("POLYS.DESCRIPTION") or a.get("GPLU_LUT.DESCRIPTION") or "General Plan land use",
          source="Los Angeles City Planning, ZIMAS", source_url="https://zimas.lacity.org/", confidence="high",
          note="The land use each community plan intends for an area. Zoning is meant to follow it but does not always yet.",
          extra={"hue": "--tool-6"}, **CITY),
    layer("la_bikeways", "Bikeways", "Getting around", "line", BIKEWAYS, scope="city", fields="ST_NAME,Class,Bikeway,Year_",
          where="Retire IS NULL OR Retire <> 'Y'", name=lambda a: (a.get("ST_NAME") or "Bikeway").title(),
          detail=lambda a: join(a.get("Bikeway") or a.get("Class"), f"installed {a['Year_']}" if a.get("Year_") else ""),
          source="LADOT, City of Los Angeles bikeways", source_url="https://geohub.lacity.org/", confidence="medium",
          note="Bike paths (class I), lanes (II), routes (III) and protected lanes (IV) in the City of Los Angeles. "
          "Other cities in the county are not included.", extra={"hue": "--tool-1"}, **CITY),
)
LAYERS, FETCH = collect(*_pairs)
LAYERS += (Layer("la_permits", "Building permits (last 2 years)", "Rules", "point", "grid",
                 "Los Angeles Department of Building and Safety (data.lacity.org)",
                 "https://data.lacity.org/d/pi9x-tg5x",
                 "high", "Permits LADBS issued in the last two years, at the permit's address. New buildings draw larger. "
                 "Work done without a permit is not here.", grid_z=15, minzoom=14, extra={"hue": "--tool-8", "ttl_s": 86400},
                 **CITY),)
FETCH["la_permits"] = permits
