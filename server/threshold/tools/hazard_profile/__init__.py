"""Hazard profile: every hazard map at one address in one result.

Both cities: FEMA flood zone, modelled transportation noise (US DOT), urban heat severity (Trust for Public Land),
sea level rise at 3 and 6 feet (NOAA), weather alerts now, earthquakes and wildfires nearby. Houston adds hurricane
evacuation zones, airport noise contours, the category 3 storm surge (NOAA NHC) and Hurricane Harvey's high-water
marks. Los Angeles adds the state's earthquake fault, liquefaction and landslide zones and CAL FIRE's fire hazard
severity. Each map says what its publisher drew; a blank map is "not mapped here", not "no risk".
"""
from __future__ import annotations

import json

from pydantic import BaseModel

from ...layers import catalog, lookup
from ...layers.sources import california, houston, imagery
from .. import (
    Check,
    Finding,
    GeoAnchor,
    Metric,
    NotApplicable,
    Place,
    Source,
    ToolResult,
    Verdict,
    field,
    tool,
)

NOISE = "https://geo.dot.gov/server/rest/services/Hosted/NTAD_Noise_2020_CONUS_Aviation_Road_Rail/MapServer"
HEAT = "https://server4.tplgis.org/arcgis4/rest/services/NATIONAL/uhi_city_severity_2023/ImageServer"
SURGE = "https://tiles.arcgis.com/tiles/C8EMgrsFcRFL6LrL/arcgis/rest/services/Storm_Surge_HazardMaps_Category3_v3/MapServer"
SLR = "https://tiles.arcgis.com/tiles/C8EMgrsFcRFL6LrL/arcgis/rest/services/slr_{}ft/MapServer"
HUD = "HUD 24 CFR 51.103: above 65 dB DNL is normally unacceptable for housing"
SFHA = {"A", "AE", "AH", "AO", "AR", "A99", "V", "VE"}


class Inputs(BaseModel):
    place: Place = field(source="selection.place")


def source(note: str, confidence: str = "high", method: str = "lookup") -> Source:
    return Source(layer="model", method=method, confidence=confidence, note=note)


class Profile:
    """Collects one check and one finding per hazard; a source that does not answer becomes an 'unknown' row."""

    def __init__(self, ctx, site):
        self.ctx, self.site, self.checks, self.findings, self.metrics = ctx, site, [], [], []
        self.anchor = GeoAnchor(geo=(site.lon, site.lat))

    def add(self, key: str, rule: str, status: str, detail: str, src: Source, measured=None, threshold=None, unit="",
            standard=None, title: str | None = None):
        fid = f"hazard_profile:{self.site.key}:{key}"
        self.checks.append(Check(id=key, rule=rule, measured=measured, threshold=threshold, unit=unit, status=status,
                                 standard=standard, findings=[fid]))
        self.findings.append(Finding(id=fid, title=title or rule, status=status, detail=detail, anchor=self.anchor, source=src))

    def run(self, key: str, rule: str, src: Source, fn):
        try:
            fn()
        except Exception as e:  # noqa: BLE001  one map down must not sink the profile
            self.add(key, rule, "unknown", f"The source did not answer ({type(e).__name__}); try again later.", src)


def flood(p: Profile, lon, lat):
    src = source("FEMA National Flood Hazard Layer (special flood hazard areas), Esri's hosted copy", "medium")
    rows = lookup.arcgis_at(catalog.ESRI_FEMA.removesuffix("/query"), lon, lat, "FLD_ZONE,ZONE_SUBTY,SFHA_TF")
    zones = [r["properties"] for r in rows if (r["properties"].get("FLD_ZONE") or "") in SFHA]
    if zones:
        z = zones[0]
        way = "FLOODWAY" in (z.get("ZONE_SUBTY") or "").upper()
        p.add("flood", "FEMA flood zone", "fail", f"Zone {z['FLD_ZONE']}{', floodway' if way else ''}: the 1% annual chance "
              "floodplain, where federally backed mortgages require flood insurance.", src, title=f"In FEMA flood zone {z['FLD_ZONE']}")
    else:
        p.add("flood", "FEMA flood zone", "pass", "Outside FEMA's mapped 1% annual chance floodplain. Outside the line is not "
              "safe: in Houston many homes that flooded in Harvey were outside it.", src, title="Outside FEMA's mapped floodplain")


def noise(p: Profile, lon, lat):
    src = source("US DOT BTS National Transportation Noise Map 2020 (road, rail, aviation; modelled 24-hour LAeq)", "medium", "simulation")
    label = lookup.nearest_colour(lookup.pixel(imagery.LAYERS_BY_ID["noise"].tiles, lon, lat, 12), lookup.legend(NOISE))
    if not label:
        p.add("noise", "Transportation noise", "pass", "Below 45 dB, the lowest level the national noise map draws.", src,
              measured=None, threshold=65, unit="dB", standard=HUD, title="Quiet on the transportation noise map")
        return
    low = float(label.lstrip("> ").split(" ")[0])
    st = "fail" if low >= 65 else "warn" if low >= 55 else "pass"
    p.add("noise", "Transportation noise", st, f"{label} dB modelled from road, rail and air traffic (24-hour average, 30 m "
          "cells). A model of traffic, not a measurement, and it leaves out every other noise.", src, measured=low,
          threshold=65, unit="dB", standard=HUD, title="Transportation noise level")
    p.metrics.append(Metric(id="noise_db", label="Transportation noise, lower bound of the class", value=low, unit="dB", source=src))


def heat(p: Profile, lon, lat):
    src = source("Trust for Public Land heat severity 2023, from Landsat 8 surface temperature", "medium")
    body = lookup.cached(f"tpl-heat|{lon:.5f},{lat:.5f}", lambda: lookup.send(
        "GET", HEAT + "/identify", headers=lookup.AGENT, timeout=60, params={
            "geometry": json.dumps({"x": lon, "y": lat, "spatialReference": {"wkid": 4326}}), "geometryType": "esriGeometryPoint",
            "returnGeometry": "false", "returnCatalogItems": "false", "f": "json"}).json(), 30 * 86400)
    v = body.get("value")
    if v in (None, "NoData", ""):
        p.add("heat", "Urban heat", "pass", "Not among the hotter areas of the city on the heat severity map, which shades "
              "only places hotter than the city's average summer surface.", src, title="Not a mapped heat spot")
        return
    sev = float(v)
    p.add("heat", "Urban heat", "warn" if sev >= 4 else "pass", f"Heat severity {sev:g} on a 1 to 5 scale: how much hotter "
          "the summer ground surface is than the city average. Surface, not air, temperature.", src, measured=sev, threshold=4,
          unit="of 5", title="Urban heat severity")
    p.metrics.append(Metric(id="heat", label="Heat severity", value=sev, unit="of 5", source=src))


def sea(p: Profile, lon, lat):
    src = source("NOAA Office for Coastal Management sea level rise inundation (above mean higher high water)")
    wet = {ft: (lookup.pixel(imagery.LAYERS_BY_ID[f"sea_level_{ft}ft"].tiles, lon, lat, 14) or (0, 0, 0, 0))[3] > 32 for ft in (3, 6)}
    if wet[3]:
        p.add("sea", "Sea level rise", "fail", "Under water at high tide with 3 feet more sea, if nothing protected it.", src,
              title="Under water with 3 ft of sea level rise")
    elif wet[6]:
        p.add("sea", "Sea level rise", "warn", "Dry with 3 feet more sea, under water at high tide with 6 feet.", src,
              title="Under water with 6 ft of sea level rise")
    else:
        p.add("sea", "Sea level rise", "pass", "Dry at high tide even with 6 feet more sea on NOAA's map.", src,
              title="Above 6 ft of sea level rise")


def alerts(p: Profile, lon, lat):
    src = source("National Weather Service active alerts for this point", "high")
    body = lookup.cached(f"nws|{lat:.3f},{lon:.3f}", lambda: lookup.send(
        "GET", "https://api.weather.gov/alerts/active", params={"point": f"{lat:.4f},{lon:.4f}"}, timeout=60,
        headers={**lookup.AGENT, "Accept": "application/geo+json"}).json(), 600)
    events = [f["properties"] for f in body.get("features") or []]
    if events:
        p.add("alerts", "Weather alerts now", "warn", "; ".join(f"{e.get('event')} until {(e.get('ends') or e.get('expires') or '')[:16]}"
                                                                   for e in events[:4]), src, title="Weather alert in force")
    else:
        p.add("alerts", "Weather alerts now", "pass", "No watch, warning or advisory in force here now.", src, title="No weather alerts now")


def points(g: dict) -> list:
    """The vertices of a point, or of a polygon's outer rings, to measure a distance to."""
    t, c = g.get("type"), g.get("coordinates") or []
    return [c] if t == "Point" else c[0] if t == "Polygon" and c else [v for poly in c for v in poly[0]] if t == "MultiPolygon" else []


def nearby(lon, lat, city, layer, km):
    """Features of a cached city layer within `km` of a point, nearest first, as (metres, properties)."""
    near = []
    for f in json.loads(catalog.city_geojson(layer, city))["features"]:
        d = min((lookup.metres(lat, lon, y, x) for x, y, *_ in points(f.get("geometry") or {})), default=None)
        if d is not None and d <= km * 1000:
            near.append((d, f["properties"]))
    return sorted(near, key=lambda t: t[0])


def quakes(p: Profile, lon, lat, city):
    src = source("USGS earthquake catalogue, last 30 days", "high")
    near = nearby(lon, lat, city, "quakes", 50)
    big = [q for _, q in near if (q.get("mag") or 0) >= 3]
    p.add("quakes", "Earthquakes within 50 km, last 30 days", "warn" if big else "pass",
          f"{len(near)} located within 50 km in the last 30 days, {len(big)} of magnitude 3 or more"
          + (f"; largest {max(big, key=lambda q: q['mag'])['name'].lower()}" if big else "") + ".", src,
          measured=len(near), unit="earthquakes", title="Recent earthquakes nearby")


def fires(p: Profile, lon, lat, city):
    src = source("National Interagency Fire Center, current wildfire perimeters", "medium")
    near = nearby(lon, lat, city, "wildfires", 25)
    p.add("wildfires", "Wildfires burning within 25 km", "fail" if near and near[0][0] < 5000 else "warn" if near else "pass",
          "; ".join(f"{q['name']} {d / 1000:.0f} km away ({q.get('detail') or 'size not given'})" for d, q in near[:3])
          or "No mapped wildfire perimeter within 25 km now.", src, title="Wildfires now")


def in_layer(p: Profile, key, rule, url, lon, lat, src, status, yes, no, fields="*", name=None):
    rows = [r["properties"] for r in lookup.arcgis_at(url, lon, lat, fields)]
    if rows:
        p.add(key, rule, status(rows[0]) if callable(status) else status, yes(rows[0]) if callable(yes) else yes, src,
              title=name(rows[0]) if callable(name) else name or rule)
    else:
        p.add(key, rule, "pass", no, src, title=f"Not in {rule[0].lower() + rule[1:]}")


def _houston(p: Profile, lon, lat):
    coh = source("City of Houston GIS")
    p.run("evacuation", "A hurricane evacuation zone", coh, lambda: in_layer(
        p, "evacuation", "A hurricane evacuation zone", houston.FH + "8", lon, lat, coh, "warn",
        lambda r: f"{(r.get('Zone') or '').replace('Zip-Zone', 'Zone').strip()}: told to leave when officials call this zone before a hurricane.",
        "Outside the zip-code zones called to leave before a hurricane: officials expect people here to shelter in place unless told otherwise.",
        "Zone", "In a hurricane evacuation zone"))
    p.run("airport_noise", "An airport noise contour", coh, lambda: in_layer(
        p, "airport_noise", "An airport noise contour", houston.TR + "18", lon, lat, coh, "warn",
        "Inside the 65 dB day-night average contour of an airport.", "Outside the airports' 65 dB DNL contours.",
        "OBJECTID", "Inside an airport's 65 dB noise contour"))
    nhc = source("NOAA National Hurricane Center storm surge risk map, category 3 at high tide", "medium", "simulation")

    def surge():
        label = lookup.nearest_colour(lookup.pixel(imagery.LAYERS_BY_ID["storm_surge"].tiles, lon, lat, 14), lookup.legend(SURGE))
        if not label:
            p.add("surge", "Storm surge, category 3", "pass", "Outside the worst case surge of a category 3 hurricane at high tide.",
                  nhc, title="Outside category 3 storm surge")
        else:
            p.add("surge", "Storm surge, category 3", "warn" if label.startswith("Less") else "fail", f"{label} in a worst case "
                  "category 3 hurricane at high tide (many modelled storms).", nhc, title="In category 3 storm surge")
    p.run("surge", "Storm surge, category 3", nhc, surge)
    usgs = source("USGS Short-Term Network, Hurricane Harvey high-water marks (2017)", "medium")

    def harvey():
        near = nearby(lon, lat, "hou", "harvey", 0.5)
        depths = [q["depth_m"] for _, q in near if (q.get("depth_m") or 0) > 0]
        if near:
            p.add("harvey", "Harvey high-water marks within 500 m", "warn", f"{len(near)} surveyed marks within 500 m, nearest "
                  f"{near[0][0]:.0f} m away" + (f"; up to {max(depths):.2f} m above ground" if depths else "") + ".", usgs,
                  measured=max(depths) if depths else None, unit="m", title="Harvey flooded nearby")
        else:
            p.add("harvey", "Harvey high-water marks within 500 m", "pass", "No surveyed Harvey high-water mark within 500 m. "
                  "Surveyors marked a sample of places, not every flooded street.", usgs, title="No Harvey marks nearby")
    p.run("harvey", "Harvey high-water marks within 500 m", usgs, harvey)


def _la(p: Profile, lon, lat):
    cgs = source("California Geological Survey regulatory zone maps")
    for key, rule, url, status, yes in (
        ("fault", "An earthquake fault zone", california.AP, "fail", ("Inside an Alquist-Priolo earthquake fault zone: most new "
         "buildings need a geologic study showing no active fault under them, and a sale must disclose it.")),
        ("liquefaction", "A liquefaction zone", california.LIQUEFACTION, "warn", ("Inside a state liquefaction zone: the ground "
         "could lose strength in strong shaking; new building needs a site study, and a sale must disclose it.")),
        ("landslide", "A landslide zone", california.LANDSLIDE, "warn", ("Inside a state earthquake-induced landslide zone: new "
         "building needs a site study, and a sale must disclose it.")),
    ):
        p.run(key, rule, cgs, lambda key=key, rule=rule, url=url, status=status, yes=yes: in_layer(
            p, key, rule, url, lon, lat, cgs, status, yes, f"Outside the state's mapped {rule.split(' ', 1)[1]}. Areas the "
            "survey has not mapped look the same.", "QUAD_NAME", f"Inside {rule[0].lower() + rule[1:]}"))
    fire_src = source("CAL FIRE Fire Hazard Severity Zones (state 2024, local 2025 maps)")

    def fire():
        rows = [r["properties"] for u in (california.FHSZ_SRA, california.FHSZ_LRA)
                for r in lookup.arcgis_at(u, lon, lat, "FHSZ_Description,FHSZ")]
        rows = [r for r in rows if r.get("FHSZ_Description") in california.SEVERITY]
        if not rows:
            p.add("fire", "Fire hazard severity", "pass", "Not in a CAL FIRE fire hazard severity zone.", fire_src,
                  title="Not in a fire hazard severity zone")
            return
        worst = max(rows, key=lambda r: california.SEVERITY[r["FHSZ_Description"]])["FHSZ_Description"]
        p.add("fire", "Fire hazard severity", "fail" if worst == "Very High" else "warn", f"{worst} fire hazard severity zone: "
              "building and defensible space rules apply, and a sale must disclose it.", fire_src, title=f"{worst} fire hazard zone")
    p.run("fire", "Fire hazard severity", fire_src, fire)


@tool(id="hazard_profile", title="Hazard profile", icon="shield-alert",
      summary="Every hazard map at an address in one place: FEMA flood zone, hurricane evacuation zone, storm surge, "
              "Hurricane Harvey's high-water marks nearby, sea level rise, earthquake faults, liquefaction and landslide "
              "zones, fire hazard zones, urban heat, traffic noise, and weather alerts, earthquakes and wildfires now.",
      model_description="All public hazard layers at one place in Houston or Los Angeles: FEMA flood zone, transportation "
                        "noise, urban heat, sea level rise 3 and 6 ft, weather alerts now, earthquakes and wildfires nearby; "
                        "Houston also hurricane evacuation zone, airport noise, category 3 storm surge and Harvey high-water "
                        "marks; Los Angeles also Alquist-Priolo fault, liquefaction and landslide zones and CAL FIRE fire "
                        "hazard severity. Each row says its source; a blank map means not mapped, not no risk.",
      requires=[{"layer": "public.hazards"}], blocks=["VerdictHeader", "MetricRow", "CheckList", "StepLog"],
      examples=["Is this house in a flood zone?", "What hazards should a family know about here?", "Is this on a fault?"])
def run(ctx, inputs: Inputs) -> ToolResult:
    site = lookup.locate(ctx, inputs.place)
    if site.lat is None:
        raise NotApplicable("This place has no location, so no hazard map can be read.")
    ctx.step(f"Found {site.address or site.key} ({site.located_by})")
    city = lookup.city_at(site.lon, site.lat)
    if city not in ("hou", "la"):
        raise NotApplicable("Hazards are read for Houston and Los Angeles only.")
    lon, lat, p = site.lon, site.lat, Profile(ctx, site)
    for key, rule, fn in (("flood", "FEMA flood zone", flood), ("noise", "Transportation noise", noise), ("heat", "Urban heat", heat),
                          ("sea", "Sea level rise", sea), ("alerts", "Weather alerts now", alerts)):
        p.run(key, rule, source(rule), lambda fn=fn: fn(p, lon, lat))
    ctx.step("Read the flood, noise, heat, sea level and weather maps")
    (_houston if city == "hou" else _la)(p, lon, lat)
    p.run("quakes", "Earthquakes within 50 km, last 30 days", source("USGS"), lambda: quakes(p, lon, lat, city))
    p.run("wildfires", "Wildfires burning within 25 km", source("NIFC"), lambda: fires(p, lon, lat, city))
    ctx.step(f"Read the {'Houston' if city == 'hou' else 'California'} hazard maps and the live earthquake and wildfire feeds")
    bad = [c for c in p.checks if c.status == "fail"]
    watch = [c for c in p.checks if c.status == "warn"]
    unknown = [c for c in p.checks if c.status == "unknown"]
    text = (f"{len(bad)} mapped hazard{'s' if len(bad) != 1 else ''} at the address"
            + (f" ({', '.join(f.title.lower() for f in p.findings if f.status == 'fail')})" if bad else "")
            + f", {len(watch)} to watch, {len(p.checks) - len(bad) - len(watch) - len(unknown)} clear"
            + (f", {len(unknown)} not read" if unknown else "") + ".")
    p.metrics[:0] = [Metric(id="hazards", label="Mapped hazards", value=len(bad), unit="", source=source("This profile")),
                     Metric(id="watch", label="To watch", value=len(watch), unit="", source=source("This profile"))]
    order = {"fail": 0, "warn": 1, "unknown": 2, "pass": 3}
    return ToolResult(scope=site.scope(), verdict=Verdict(status="fail" if bad else "warn" if watch else "pass", text=text),
                      metrics=p.metrics, checks=sorted(p.checks, key=lambda c: order[c.status]), findings=p.findings)
