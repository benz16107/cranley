"""What is happening now: earthquakes (USGS), weather alerts (National Weather Service), wildfire perimeters (NIFC)
and river and bayou levels at USGS stream gauges. Each is fetched again once its `ttl_s` has passed."""
from __future__ import annotations

from datetime import UTC, datetime

from ..catalog import AGENT, Layer, send
from ._arcgis import join, layer

QUAKES = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_month.geojson"
ALERTS = "https://api.weather.gov/alerts/active"
FIRES = "https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/WFIGS_Interagency_Perimeters_Current/FeatureServer/0"
GAUGES = "https://waterservices.usgs.gov/nwis/iv/"
STATE = {"hou": "TX", "la": "CA"}


def inside(box, lon, lat) -> bool:
    w, s, e, n = box
    return w <= lon <= e and s <= lat <= n


def quakes(box, city):
    body = send("GET", QUAKES, headers=AGENT, timeout=60).json()
    out = []
    for f in body.get("features") or []:
        lon, lat, depth = (f.get("geometry") or {}).get("coordinates") or (None, None, None)
        p = f.get("properties") or {}
        if lon is None or not inside(box, lon, lat) or p.get("type") != "earthquake":
            continue
        when = datetime.fromtimestamp(p["time"] / 1000, UTC).strftime("%Y-%m-%d %H:%M UTC") if p.get("time") else ""
        out.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]},
                    "properties": {"name": f"Magnitude {p['mag']:.1f}" if p.get("mag") is not None else "Earthquake",
                                   "detail": join(p.get("place"), when, f"{depth:.0f} km deep" if depth is not None else ""),
                                   "mag": p.get("mag"), "fast": (p.get("mag") or 0) >= 3}})
    return out, False


def alerts(box, city):
    # the service asks automated clients for a User-Agent; a generic one names the software, not a person
    body = send("GET", ALERTS, params={"area": STATE[city]}, timeout=60,
                headers={**AGENT, "Accept": "application/geo+json"}).json()
    w, s, e, n = box
    out = []
    for f in body.get("features") or []:
        g, p = f.get("geometry"), f.get("properties") or {}
        if not g:  # zone-based alerts carry no shape of their own; the outline would need one more request per zone
            continue
        ring = [c for poly in ([g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]) for c in poly[0]]
        if not any(w <= x <= e and s <= y <= n for x, y in ring):
            continue
        out.append({"type": "Feature", "geometry": g, "properties": {
            "name": p.get("event") or "Weather alert", "detail": join(p.get("severity"), f"until {(p.get('ends') or p.get('expires') or '')[:16]}",
                                                                      (p.get("headline") or "")[:140])}})
    return out, False


def gauges(box, city):
    w, s, e, n = box
    # gauge height (00065) and flow (00060) now; the service limits a box to 25 square degrees, the city boxes are smaller
    body = send("GET", GAUGES, headers=AGENT, timeout=90, params={
        "format": "json", "bBox": f"{w:.4f},{s:.4f},{e:.4f},{n:.4f}", "parameterCd": "00065,00060", "siteStatus": "active"}).json()
    sites: dict[str, dict] = {}
    for ts in (body.get("value") or {}).get("timeSeries") or []:
        info, var = ts["sourceInfo"], ts["variable"]
        vals = (ts.get("values") or [{}])[0].get("value") or []
        if not vals:
            continue
        code = info["siteCode"][0]["value"]
        loc = info["geoLocation"]["geogLocation"]
        site = sites.setdefault(code, {"name": info["siteName"].title(), "lon": loc["longitude"], "lat": loc["latitude"], "read": {}})
        site["read"][var["variableCode"][0]["value"]] = (vals[-1]["value"], vals[-1]["dateTime"][:16].replace("T", " "))
    out = []
    for code, st in sites.items():
        h, q = st["read"].get("00065"), st["read"].get("00060")
        out.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [st["lon"], st["lat"]]},
                    "properties": {"name": st["name"], "detail": join(f"water level {h[0]} ft (gauge datum)" if h else "",
                                                                      f"flow {q[0]} ft³/s" if q else "", (h or q)[1]),
                                   "site": code}})
    return out, False


LIVE = {"group": "Live", "confidence": "medium"}
LAYERS = (
    Layer("quakes", "Earthquakes, last 30 days", shape="point", scope="city", source="USGS Earthquake Hazards Program",
          source_url="https://earthquake.usgs.gov/earthquakes/map/", licence="Public domain (USGS)",
          note="Every earthquake USGS located in the last 30 days, of any size; magnitude 3 and up draws larger. Recent "
          "events are automatic solutions and can be revised.", extra={"hue": "--tool-3", "ttl_s": 900}, **LIVE),
    Layer("weather_alerts", "Weather alerts now", shape="area", scope="city", source="National Weather Service",
          source_url="https://www.weather.gov/", licence="Public domain (NOAA)",
          note="Active warnings, watches and advisories that the Weather Service drew as a shape. Alerts issued for whole "
          "counties or zones are not drawn; check weather.gov for those.", extra={"hue": "--tool-3", "ttl_s": 600}, **LIVE),
    Layer("stream_gauges", "River and bayou levels now", shape="point", scope="city", source="USGS Water Data (instantaneous values)",
          source_url="https://waterdata.usgs.gov/", licence="Public domain (USGS)",
          note="The latest reading at each active USGS stream gauge. Levels are on each gauge's own datum, so compare a "
          "gauge with its own history, not with another gauge. Provisional data.", extra={"hue": "--tool-2", "ttl_s": 900}, **LIVE),
)
_fires = layer("wildfires", "Wildfire perimeters now", "Live", "area", FIRES, scope="city",
               fields="poly_IncidentName,poly_GISAcres,poly_DateCurrent,attr_PercentContained",
               name=lambda a: f"{a.get('poly_IncidentName') or 'Wildfire'} fire",
               detail=lambda a: join(f"{a['poly_GISAcres']:,.0f} acres" if a.get("poly_GISAcres") else "",
                                     f"{a['attr_PercentContained']:.0f}% contained" if a.get("attr_PercentContained") is not None else ""),
               source="National Interagency Fire Center, current perimeters", source_url="https://data-nifc.opendata.arcgis.com/",
               licence="Public (NIFC)", confidence="medium",
               note="Perimeters of wildfires burning now, as the incident teams last mapped them (often once a day).",
               extra={"hue": "--tool-3", "ttl_s": 1800})
LAYERS += (_fires[0],)
FETCH = {"quakes": quakes, "weather_alerts": alerts, "stream_gauges": gauges, "wildfires": _fires[1]}
