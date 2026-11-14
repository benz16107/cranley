"""Connectivity: how well a place is connected, by wire and on foot.

Broadband from the FCC National Broadband Map for the block group (the share of homes and businesses some provider
says it can serve at 100/20 Mbps, and how many providers offer fiber or cable), transit stops within a walk (the
federal transit map), the nearest bikeway (each city's own map), and the traffic counted on the nearest state count
station. Broadband figures are what providers say they offer, not measured speeds; Ookla's measured speed tiles are
licensed for non-commercial use only and are not used here.
"""
from __future__ import annotations

import math

from pydantic import BaseModel
from shapely.geometry import Point, shape
from shapely.ops import transform

from ...layers import catalog, lookup
from ...layers.sources import federal, houston, los_angeles
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

STOPS = catalog.ARCGIS["transit"]["urls"][0].removesuffix("/query")
BIKEWAYS = {"hou": (houston.TR + "7", "Full_Name,HC_Class,HC_Status", "HC_Status='Existing'"),
            "la": (los_angeles.BIKEWAYS, "ST_NAME,Bikeway,Class", "1=1")}
AADT = {"hou": (federal.TXDOT, "AADT_RPT_QTY,AADT_RPT_YEAR,ON_ROAD"), "la": (federal.CALTRANS, "AHEAD_AADT,BACK_AADT,RTE,DESCRIPTION")}


class Inputs(BaseModel):
    place: Place = field(source="selection.place")
    walk_m: float = field(800, ge=200, le=2000, description="How far the person is willing to walk to a stop, in metres",
                          pref="getting_around.walk_m", unit="m")


def source(note: str, confidence: str = "high") -> Source:
    return Source(layer="model", method="lookup", confidence=confidence, note=note)


def metres_to(geom: dict, lon: float, lat: float) -> float:
    """Distance from a point to a shape, in metres, on a flat plane centred on the point (good over a few kilometres)."""
    k = 111320 * math.cos(math.radians(lat))
    return transform(lambda x, y, z=None: ((x - lon) * k, (y - lat) * 111320), shape(geom)).distance(Point(0, 0))


def broadband(p, site) -> None:
    src = source("FCC National Broadband Map, Broadband Data Collection, block group summary (Esri's hosted copy)", "medium")
    rows = lookup.arcgis_at(federal.FCC_BLOCK_GROUP, site.lon, site.lat, federal.FCC_FIELDS)
    if not rows:
        p["checks"].append(Check(id="broadband", rule="Broadband at 100/20 Mbps", measured=None, threshold=None, unit="%", status="unknown"))
        return
    a = rows[0]["properties"]
    served = round(100 * (a.get("ServedBSLs") or 0) / a["TotalBSLs"], 1) if a.get("TotalBSLs") else None
    fiber, cable = a.get("UniqueProvidersFiber") or 0, a.get("UniqueProvidersCable") or 0
    st = "unknown" if served is None else "pass" if served >= 90 and (fiber or cable) else "warn" if served >= 50 else "fail"
    fid = f"connectivity:{p['key']}:broadband"
    p["metrics"] += [Metric(id="served_pct", label="Locations offered 100/20 Mbps", value=served, unit="%", source=src),
                     Metric(id="providers", label="Providers", value=a.get("UniqueProviders"), unit="", source=src),
                     Metric(id="fiber_providers", label="Fiber providers", value=fiber, unit="", source=src),
                     Metric(id="cable_providers", label="Cable providers", value=cable, unit="", source=src)]
    p["checks"].append(Check(id="broadband", rule="Broadband offered at 100/20 Mbps", measured=served, threshold=90, unit="%",
                             status=st, standard="FCC definition of served: 100 Mbps down, 20 up", findings=[fid]))
    p["findings"].append(Finding(id=fid, title="Home broadband on offer", status=st, anchor=p["anchor"], source=src, detail=(
        f"In this block group {served:g}% of the {a['TotalBSLs']:,} homes and businesses have a provider offering at least "
        f"100/20 Mbps by wire or licensed fixed wireless; {a.get('UniqueProviders') or 0} providers in all, {fiber} with fiber, "
        f"{cable} with cable. Providers report what they offer; ask for the exact address." if served is not None else
        "The FCC summary for this block group has no locations.")))


def transit(p, site, walk_m) -> None:
    src = source("US DOT National Transit Map stops (agencies' GTFS)", "medium")
    rows = lookup.arcgis_at(STOPS, site.lon, site.lat, "stop_name,stop_type_text", radius_m=walk_m, geometry=True, limit=500)
    stops = sorted(((lookup.metres(site.lat, site.lon, r["geometry"]["coordinates"][1], r["geometry"]["coordinates"][0]),
                     r["properties"]) for r in rows if r.get("geometry")), key=lambda t: t[0])
    rail = [(d, s) for d, s in stops if (s.get("stop_type_text") or "").strip('"').lower() not in ("bus", "")]
    near = sum(d <= 400 for d, _ in stops)
    st = "pass" if near else "warn" if stops else "fail"
    fid = f"connectivity:{p['key']}:transit"
    p["metrics"] += [Metric(id="stops_400m", label="Transit stops within 400 m", value=near, unit="", source=src),
                     Metric(id="stops_walk", label=f"Transit stops within {walk_m:.0f} m", value=len(stops), unit="", source=src),
                     Metric(id="nearest_stop_m", label="Nearest stop", value=round(stops[0][0]) if stops else None, unit="m", source=src)]
    p["checks"].append(Check(id="transit", rule="A transit stop within 400 m", measured=round(stops[0][0]) if stops else None,
                             threshold=400, unit="m", status=st, findings=[fid]))
    detail = (f"Nearest: {stops[0][1].get('stop_name')} ({(stops[0][1].get('stop_type_text') or 'stop').strip(chr(34))}), "
              f"{stops[0][0]:.0f} m in a straight line; {len(stops)} stops within {walk_m:.0f} m" if stops else
              f"No stop within {walk_m:.0f} m in the federal transit map")
    if rail:
        detail += f"; nearest rail stop {rail[0][1].get('stop_name')}, {rail[0][0]:.0f} m"
    p["findings"].append(Finding(id=fid, title="Transit within a walk", status=st, anchor=p["anchor"], source=src,
                                 detail=detail + ". Distances are straight lines; the walk is longer."))


def bikes(p, site, city) -> None:
    url, fields, where = BIKEWAYS[city]
    src = source(f"{'City of Houston' if city == 'hou' else 'LADOT'} bikeways", "medium")
    rows = lookup.arcgis_at(url, site.lon, site.lat, fields, radius_m=800, geometry=True, where=where)
    best = min(((metres_to(r["geometry"], site.lon, site.lat), r["properties"]) for r in rows if r.get("geometry")),
               default=None, key=lambda t: t[0])
    st = "pass" if best and best[0] <= 400 else "warn" if best else "unknown"
    fid = f"connectivity:{p['key']}:bike"
    name = best and ((best[1].get("Full_Name") or best[1].get("ST_NAME") or "a bikeway").title())
    kind = best and (best[1].get("HC_Class") or best[1].get("Bikeway") or best[1].get("Class") or "")
    p["metrics"].append(Metric(id="bikeway_m", label="Nearest bikeway", value=round(best[0]) if best else None, unit="m", source=src))
    p["checks"].append(Check(id="bike", rule="A bikeway within 400 m", measured=round(best[0]) if best else None, threshold=400,
                             unit="m", status=st, findings=[fid]))
    p["findings"].append(Finding(id=fid, title="Nearest bikeway", status=st, anchor=p["anchor"], source=src, detail=(
        f"{name}{f' ({kind})' if kind else ''}, {best[0]:.0f} m away." if best else "No mapped bikeway within 800 m.")))


def traffic(p, site, city) -> None:
    url, fields = AADT[city]
    src = source("TxDOT annual average daily traffic" if city == "hou" else "Caltrans annual average daily traffic (state highways)")
    rows = lookup.arcgis_at(url, site.lon, site.lat, fields, radius_m=300, geometry=True)
    if not rows:
        p["findings"].append(Finding(id=f"connectivity:{p['key']}:traffic", title="No state traffic count nearby", status="unknown",
                                     anchor=p["anchor"], source=src, detail="No state count station within 300 m; local streets "
                                     "are rarely counted by the state."))
        return
    near = min(rows, key=lambda r: metres_to(r["geometry"], site.lon, site.lat))
    a, d = near["properties"], metres_to(near["geometry"], site.lon, site.lat)
    v = a.get("AADT_RPT_QTY") if city == "hou" else max((int(x) for x in (a.get("AHEAD_AADT"), a.get("BACK_AADT")) if str(x or "").isdigit()), default=None)
    road = next((r for r in (a.get("ON_ROAD"), f"Route {a['RTE']}" if a.get("RTE") else "") if r and r.strip("- ")), "the counted road")
    st = "warn" if (v or 0) >= 50000 else "pass"
    p["metrics"].append(Metric(id="aadt", label="Vehicles a day at the nearest count", value=v, unit="vehicles", source=src))
    p["findings"].append(Finding(id=f"connectivity:{p['key']}:traffic", title="Traffic on the nearest counted road", status=st,
                                 anchor=p["anchor"], source=src, detail=f"{v:,} vehicles a day (annual average) on {road}, at a "
                                 f"count station {d:.0f} m away" + (f", {a['AADT_RPT_YEAR']}" if a.get("AADT_RPT_YEAR") else "")
                                 + ". The station may be on a different road from the address." if v else "The count has no value."))


@tool(id="connectivity", title="Connectivity", icon="wifi",
      summary="How well a place is connected: home broadband on offer, transit stops within a walk, the nearest bikeway "
              "and the traffic on the nearest counted road.",
      model_description="Connectivity of a place in Houston or Los Angeles: FCC broadband availability for its block group "
                        "(share offered 100/20 Mbps, provider, fiber and cable counts), transit stops within `walk_m` "
                        "(nearest, rail), the nearest bikeway, and annual average daily traffic at the nearest state count "
                        "station. Broadband is what providers report offering, not a measured speed.",
      requires=[{"layer": "public.broadband"}, {"layer": "public.transit"}], blocks=["VerdictHeader", "MetricRow", "CheckList", "StepLog"],
      examples=["Can I work from home here?", "Is there fiber?", "How far is the nearest train?"])
def run(ctx, inputs: Inputs) -> ToolResult:
    site = lookup.locate(ctx, inputs.place)
    if site.lat is None:
        raise NotApplicable("This place has no location to measure from.")
    ctx.step(f"Found {site.address or site.key} ({site.located_by})")
    city = lookup.city_at(site.lon, site.lat)
    if city not in ("hou", "la"):
        raise NotApplicable("Connectivity is read for Houston and Los Angeles only.")
    p = {"key": site.key, "anchor": GeoAnchor(geo=(site.lon, site.lat)), "metrics": [], "checks": [], "findings": []}
    for name, fn in (("broadband", lambda: broadband(p, site)), ("transit stops", lambda: transit(p, site, inputs.walk_m)),
                     ("bikeways", lambda: bikes(p, site, city)), ("traffic counts", lambda: traffic(p, site, city))):
        try:
            fn()
            ctx.step(f"Read {name}")
        except Exception as e:  # noqa: BLE001  one source down must not sink the rest
            p["findings"].append(Finding(id=f"connectivity:{site.key}:{name.split()[0]}", title=f"{name.capitalize()} not read",
                                         status="unknown", anchor=p["anchor"], source=source(name, "low"),
                                         detail=f"The source did not answer ({type(e).__name__}); try again later."))
    by = {c.id: c.status for c in p["checks"]}
    words = {"broadband": {"pass": "broadband at 100/20 Mbps for most of the block group", "warn": "patchy 100/20 Mbps broadband",
                           "fail": "little 100/20 Mbps broadband"},
             "transit": {"pass": "a transit stop within 400 m", "warn": f"a transit stop within {inputs.walk_m:.0f} m",
                         "fail": f"no transit stop within {inputs.walk_m:.0f} m"},
             "bike": {"pass": "a bikeway within 400 m", "warn": "a bikeway within 800 m"}}
    said = [words[k][v] for k, v in by.items() if v in words.get(k, {})]
    worst = "fail" if "fail" in by.values() else "warn" if "warn" in by.values() else "pass" if by else "unknown"
    return ToolResult(scope=site.scope(), verdict=Verdict(status=worst, text=(said[0][0].upper() + "; ".join(said)[1:] + ".") if said
                      else "Nothing could be read for this place."), metrics=p["metrics"], checks=p["checks"], findings=p["findings"],
                      )
