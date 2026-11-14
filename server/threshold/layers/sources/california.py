"""California's state hazard maps for Los Angeles: the Geological Survey's earthquake fault zones (Alquist-Priolo),
liquefaction and landslide zones, and CAL FIRE's fire hazard severity zones (state and local responsibility areas).
All are regulatory maps: a sale must disclose them, and building in a fault zone needs a geologic study."""
from __future__ import annotations

from ._arcgis import collect, join, layer

CGS = "https://services2.arcgis.com/zr3KAIbsRSUyARHG/arcgis/rest/services/{}/FeatureServer/0"
CALFIRE = "https://services1.arcgis.com/jUJYIo9tSA7EHvfZ/arcgis/rest/services/{}/FeatureServer/0"
AP, AP_TRACES = CGS.format("CGS_Alquist_Priolo_Fault_Zones"), CGS.format("CGS_Alquist_Priolo_Fault_Traces")
LIQUEFACTION, LANDSLIDE = CGS.format("CGS_Liquefaction_Zones"), CGS.format("CGS_Landslide_Zones")
FHSZ_SRA, FHSZ_LRA = CALFIRE.format("FHSZSRA_23_3"), CALFIRE.format("FHSALRA25_v1_All")  # sic: the service is spelled FHSA
STATE = {"cities": ("la",), "source": "California Geological Survey", "licence": "State of California open data (public)",
             "source_url": "https://maps.conservation.ca.gov/cgs/EQZApp/", "confidence": "high"}
FIRE = {"cities": ("la",), "source": "CAL FIRE Fire Hazard Severity Zones", "licence": "State of California open data (public)",
            "source_url": "https://osfm.fire.ca.gov/what-we-do/community-wildfire-preparedness-and-mitigation/fire-hazard-severity-zones",
            "confidence": "high"}
SEVERITY = {"Moderate": 2, "High": 3, "Very High": 5}
quad = lambda a: join(f"{a['QUAD_NAME']} quadrangle" if a.get("QUAD_NAME") else "",
                      f"released {a.get('RELEASED') or a.get('MAP_RELEASED')}" if a.get("RELEASED") or a.get("MAP_RELEASED") else "")
fire = lambda resp: lambda a: {"level": SEVERITY.get(a.get("FHSZ_Description") or "", 1), "resp": resp}

LAYERS, FETCH = collect(
    layer("ca_fault_zones", "Earthquake fault zones (Alquist-Priolo)", "Hazards", "area", AP, grid_z=12, minzoom=10,
          fields="QUAD_NAME,MAP_RELEASED", offset=0.00002, name="Alquist-Priolo earthquake fault zone", detail=quad,
          note="Zones around active faults where the state requires a geologic study before most new buildings, and a "
          "seller must disclose. A fault can still break outside a zone.", extra={"hue": "--tool-3"}, **STATE),
    layer("ca_fault_traces", "Active fault traces", "Hazards", "line", AP_TRACES, grid_z=12, minzoom=10,
          fields="QUAD_NAME", offset=0.00002, name="Active fault trace", detail=quad,
          note="The surface traces of active faults the zones are drawn around.", extra={"hue": "--tool-3"}, **STATE),
    layer("ca_liquefaction", "Liquefaction zones", "Hazards", "area", LIQUEFACTION, grid_z=12, minzoom=10,
          fields="QUAD_NAME,RELEASED", offset=0.00002, name="Liquefaction zone", detail=quad,
          note="Where loose, wet ground could behave like liquid in strong shaking. New building here needs a site study. "
          "Areas the survey has not mapped yet are blank, not safe.", extra={"hue": "--tool-2"}, **STATE),
    layer("ca_landslide", "Earthquake-induced landslide zones", "Hazards", "area", LANDSLIDE, grid_z=12, minzoom=10,
          fields="QUAD_NAME,RELEASED", offset=0.00002, name="Landslide zone", detail=quad,
          note="Slopes the survey judged could slide in an earthquake. New building here needs a site study.",
          extra={"hue": "--tool-4"}, **STATE),
    layer("ca_fire_sra", "Fire hazard severity (state areas)", "Hazards", "area", FHSZ_SRA, grid_z=12, minzoom=9,
          fields="FHSZ_Description", offset=0.00003, name=lambda a: f"{a.get('FHSZ_Description') or ''} fire hazard severity".strip(),
          detail=lambda a: "State responsibility area (2024 map)", props=fire("state"),
          note="CAL FIRE's fire hazard severity zones where the state fights wildfire. Very high zones carry building "
          "and brush clearance rules and a seller's disclosure.", data_date="2024",
          extra={"hue": "--tool-3", "legend": {"title": "Fire hazard severity", "unit": "", "stops": [[2, "Moderate"], [3, "High"], [5, "Very high"]]}},
          **FIRE),
    layer("ca_fire_lra", "Fire hazard severity (local areas)", "Hazards", "area", FHSZ_LRA, grid_z=12, minzoom=9,
          fields="FHSZ_Description", where="FHSZ IN (1, 2, 3)", offset=0.00003, name=lambda a: f"{a.get('FHSZ_Description') or ''} fire hazard severity".strip(),
          detail=lambda a: "Local responsibility area (2025 map)", props=fire("local"),
          note="CAL FIRE's 2025 fire hazard severity zones inside cities, where the city's fire department responds. "
          "Each city adopts the map by ordinance, so the adopted zone can lag.", data_date="2025",
          extra={"hue": "--tool-3", "legend": {"title": "Fire hazard severity", "unit": "", "stops": [[2, "Moderate"], [3, "High"], [5, "Very high"]]}},
          **FIRE),
)
