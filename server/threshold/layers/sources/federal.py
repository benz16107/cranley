"""National sources that cover both cities: FCC broadband availability by census tract, state DOT traffic counts
(TxDOT in Houston, Caltrans in Los Angeles), transit routes from the federal transit map, and EPA AirNow monitors."""
from __future__ import annotations

from ..lookup import cached
from ._arcgis import collect, join, layer
from .census import bands, level

FCC = ("https://services8.arcgis.com/peDZJliSvYims39Q/arcgis/rest/services/"
       "FCC_Broadband_Data_Collection_December_2024_View/FeatureServer/{}")
FCC_TRACT, FCC_BLOCK_GROUP = FCC.format(2), FCC.format(3)
FCC_FIELDS = ("GEOID,TotalBSLs,UnservedBSLs,UnderservedBSLs,ServedBSLs,ServedBSLsFiber,ServedBSLsCable,UniqueProviders,"
              "UniqueProvidersFiber,UniqueProvidersCable,UniqueProvidersLTFW")
TXDOT = "https://services.arcgis.com/KTcxiTD9dsQw4r7Z/arcgis/rest/services/TxDOT_AADT_Annuals_(Public_View)/FeatureServer/0"
CALTRANS = "https://caltrans-gis.dot.ca.gov/arcgis/rest/services/CHhighway/Traffic_AADT/FeatureServer/0"
ROUTES = "https://services.arcgis.com/xOi1kZaI0eWDREZv/arcgis/rest/services/NTAD_National_Transit_Map_Routes/FeatureServer/0"
AIRNOW = "https://services.arcgis.com/cJ9YHowT8TU7DUyn/arcgis/rest/services/Air_Now_Current_Monitors_Ozone_and_PM/FeatureServer/0"
FCC_SRC = {"source": "FCC National Broadband Map, Broadband Data Collection (Esri's tract summary)",
               "source_url": "https://broadbandmap.fcc.gov/", "licence": "Public (FCC); Esri hosting terms apply",
               "confidence": "medium", "scope": "city", "minzoom": 8, "data_date": "2024-12"}
GAP_EDGES = [1, 3, 10, 25, 50]


def gap(a: dict) -> float | None:
    """Share of broadband serviceable locations with no wired or licensed fixed offer of 100/20 Mbps."""
    total = a.get("TotalBSLs")
    return round(100 * (total - (a.get("ServedBSLs") or 0)) / total, 1) if total else None


def fcc_detail(a: dict) -> str:
    g = gap(a)
    return join(f"{a['TotalBSLs']:,} locations" if a.get("TotalBSLs") else "",
                f"{g:g}% without 100/20 Mbps" if g is not None else "",
                f"{a['UniqueProviders']} providers" if a.get("UniqueProviders") is not None else "",
                f"{a['UniqueProvidersFiber']} offering fiber" if a.get("UniqueProvidersFiber") is not None else "")


def aadt_tx(a: dict) -> dict:
    return {"aadt": a.get("AADT_RPT_QTY"), "year": a.get("AADT_RPT_YEAR"), "fast": (a.get("AADT_RPT_QTY") or 0) >= 100000}


def aadt_ca(a: dict) -> dict:
    v = max((int(x) for x in (a.get("AHEAD_AADT"), a.get("BACK_AADT")) if str(x or "").isdigit()), default=None)
    return {"aadt": v, "fast": (v or 0) >= 100000}


# EPA's AQI categories by upper bound (40 CFR 58, appendix G)
AQI_BANDS = ((50, "Good"), (100, "Moderate"), (150, "Unhealthy for sensitive groups"), (200, "Unhealthy"), (300, "Very unhealthy"))


def aqi_word(v) -> str:
    return "" if v is None else next((w for top, w in AQI_BANDS if v <= top), "Hazardous")

LAYERS, FETCH = collect(
    layer("fcc_gap", "Homes without 100/20 Mbps broadband", "Services", "area", FCC_TRACT, fields=FCC_FIELDS,
          offset=0.0003, name=lambda a: f"Tract {a.get('GEOID', '')[-6:]}", detail=fcc_detail,
          props=lambda a: {"level": level(gap(a), GAP_EDGES)} if gap(a) is not None else {},
          note="Share of the homes and businesses in each tract that no provider says it can serve at 100 Mbps down and "
          "20 up by wire or licensed fixed wireless. Providers report this themselves; speeds are offered, not measured.",
          extra={"hue": "--tool-5", "legend": {"title": "Locations without 100/20 Mbps", "unit": "%",
                                               "stops": bands(GAP_EDGES, lambda v: f"{v:g}%")}}, **FCC_SRC),
    layer("fcc_fiber", "Fiber providers", "Services", "area", FCC_TRACT, fields=FCC_FIELDS, offset=0.0003,
          name=lambda a: f"{a.get('UniqueProvidersFiber') or 0} fiber providers", detail=fcc_detail,
          props=lambda a: {"level": min(5, a.get("UniqueProvidersFiber") or 0)},
          note="How many providers say they offer fiber somewhere in the tract. One provider in a tract does not mean "
          "every street has it.", extra={"hue": "--tool-5", "legend": {"title": "Fiber providers in the tract", "unit": "",
                                                                         "stops": [[0, "none"], [1, "1"], [2, "2"], [3, "3"], [4, "4"], [5, "5 or more"]]}},
          **FCC_SRC),
    layer("traffic_counts", "Traffic counts (vehicles a day)", "Getting around", "point", {"hou": TXDOT},
          scope="city", cities=("hou", "la"), minzoom=10, fields="TRFC_STATN_ID,AADT_RPT_YEAR,AADT_RPT_QTY,ON_ROAD",
          name=lambda a: f"{a['AADT_RPT_QTY']:,} vehicles a day" if a.get("AADT_RPT_QTY") else "Traffic count station",
          detail=lambda a: join(a.get("ON_ROAD"), f"annual average, {a['AADT_RPT_YEAR']}" if a.get("AADT_RPT_YEAR") else ""),
          props=aadt_tx, source="TxDOT (Houston), Caltrans (Los Angeles) annual average daily traffic",
          source_url="https://gis-txdot.opendata.arcgis.com/", licence="Public (state DOT open data)", confidence="high",
          note="Annual average daily traffic at state count stations: every vehicle both ways on an average day. Busy "
          "roads draw larger. Caltrans counts state highways only.", extra={"hue": "--tool-3"}),
    layer("transit_routes", "Transit routes", "Getting around", "line", ROUTES, grid_z=12, minzoom=10.5,
          fields="route_short_name,route_long_name,route_type_text,agency_id", offset=0.0001,
          name=lambda a: join(a.get("route_short_name"), a.get("route_long_name")) or "Transit route",
          detail=lambda a: join(a.get("route_type_text"), a.get("agency_id")),
          props=lambda a: {"rail": (a.get("route_type_text") or "").lower() not in ("bus", "")},
          source="US DOT National Transit Map (agencies' GTFS)", source_url="https://www.bts.gov/national-transit-map",
          licence="Public (US DOT)", confidence="medium",
          note="The routes transit agencies publish in their schedule feeds, as the federal map collected them. Rail draws "
          "thicker. Frequency is not shown.", extra={"hue": "--tool-1"}),
    layer("air_quality", "Air quality now (AirNow monitors)", "Live", "point", AIRNOW, scope="city",
          fields="SiteName,OZONEPM_AQI,PM25,PM25_AQI,OZONE,LocalTimeString",
          name=lambda a: f"AQI {a['OZONEPM_AQI']}, {aqi_word(a['OZONEPM_AQI']).lower()}" if a.get("OZONEPM_AQI") is not None else "Air quality monitor",
          detail=lambda a: join(a.get("SiteName"), f"PM2.5 {a['PM25']} µg/m³" if a.get("PM25") is not None else "",
                                a.get("LocalTimeString")),
          props=lambda a: {"aqi": a.get("OZONEPM_AQI"), "fast": (a.get("OZONEPM_AQI") or 0) > 100},
          source="US EPA AirNow (current hour)", source_url="https://www.airnow.gov/", licence="Public (US EPA)",
          confidence="medium", note="The latest hourly reading at each official monitor, as an air quality index for ozone "
          "and fine particles. Readings are preliminary until EPA reviews them. Monitors are kilometres apart.",
          extra={"hue": "--tool-4", "ttl_s": 1800}),
)
# Caltrans' station rows carry different fields: one fetch with each city's own field list
_LA_FIELDS = "DESCRIPTION,RTE,AHEAD_AADT,BACK_AADT"
_tx_fetch = FETCH["traffic_counts"]
_ca = layer("traffic_counts", "", "", "point", CALTRANS, scope="city", fields=_LA_FIELDS,
            name=lambda a: f"{aadt_ca(a)['aadt']:,} vehicles a day" if aadt_ca(a)["aadt"] else "Traffic count station",
            detail=lambda a: join(f"Route {a['RTE']}" if a.get("RTE") else "", (a.get("DESCRIPTION") or "").title()),
            props=aadt_ca, source="", source_url="", confidence="high", note="")[1]
FETCH["traffic_counts"] = lambda box, city: (_ca if city == "la" else _tx_fetch)(box, city)


def tract_broadband(geoid: str) -> dict | None:
    """The FCC summary for one tract (for the connectivity tool)."""
    from ..catalog import AGENT, send
    if not geoid.isdigit():
        return None

    def make():
        body = send("GET", FCC_TRACT + "/query", headers=AGENT, timeout=60, params={
            "where": f"GEOID='{geoid}'", "outFields": FCC_FIELDS, "returnGeometry": "false", "f": "json"}).json()
        rows = body.get("features") or []
        return rows[0]["attributes"] if rows else None
    return cached(f"fcc-tract|{geoid}", make)
