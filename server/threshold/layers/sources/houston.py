"""City of Houston's own GIS (mycity2.houstontx.gov, no key): the rules Houston uses instead of zoning (special
minimum lot sizes and building lines, historic districts), land use as the appraisal district records it, bikeways,
the Vision Zero high-injury streets, airport noise, hurricane evacuation zones, the 500-year floodplain, libraries,
parks, police stations, and 311 service requests from the last weeks.

Houston has no zoning code. What a lot can be used for is set by private deed restrictions, which the city does not
map, and by Chapter 42 of the city code (lot size, building lines), which it does.
"""
from __future__ import annotations

from ..lookup import day
from ._arcgis import collect, join, layer

GIS = "https://mycity2.houstontx.gov/gisweb02/rest/services/HoustonMap/"
PD, TR, NB, PS, FH = (GIS + s + "/MapServer/" for s in ("Planning_and_Development", "Transportation", "Neighborhood",
                                                        "Public_Safety", "Flood_Hazard"))
SR311 = "https://mycity2.houstontx.gov/gisweb01/rest/services/311/HOUSTON311_RECENT_SR_SNOW/FeatureServer/0"
COH = dict(source="City of Houston GIS", source_url="https://cohgis-mycity.opendata.arcgis.com/",
           licence="City of Houston open data (public)", cities=("hou",))

MIN_LOT = PD + "13"
BUILD_LINE = PD + "12"
HISTORIC = PD + "8"
LAND_USE = GIS + "Landuse/MapServer/0"

LAYERS, FETCH = collect(
    layer("hou_min_lot", "Special minimum lot size areas", "Rules", "area", MIN_LOT, scope="city",
          fields="ORDINANCE,LOTSIZE,Effective_Date,Expiration_Date,Status",
          name=lambda a: f"Minimum lot size {a['LOTSIZE']:,} sq ft" if a.get("LOTSIZE") else "Special minimum lot size area",
          detail=lambda a: join(f"Ordinance {a.get('ORDINANCE')}" if a.get("ORDINANCE") else "", a.get("Status"),
                                f"in force from {day(a.get('Effective_Date'))}" if a.get("Effective_Date") else "",
                                f"expires {day(a.get('Expiration_Date'))}" if a.get("Expiration_Date") else ""),
          confidence="high", note="Blocks where residents applied under Chapter 42 to keep lots at least this size. "
          "Outside them the city-wide Chapter 42 minimums apply. Deed restrictions are separate and not mapped.",
          extra={"hue": "--tool-7"}, **COH),
    layer("hou_build_line", "Special minimum building lines", "Rules", "area", BUILD_LINE, scope="city",
          fields="BLD__LINE,ORDINANCE_,Status",
          name=lambda a: f"Building line {a['BLD__LINE']} ft" if a.get("BLD__LINE") else "Special minimum building line",
          detail=lambda a: join(f"Ordinance {a.get('ORDINANCE_')}" if a.get("ORDINANCE_") else "", a.get("Status")),
          confidence="high", note="Blockfaces where a building must stand back at least this far from the street (Chapter 42).",
          extra={"hue": "--tool-8"}, **COH),
    layer("hou_historic", "Historic districts (city)", "Rules", "area", HISTORIC, scope="city", fields="NAME", name="NAME",
          confidence="high", note="City of Houston historic districts: exterior changes need a certificate of appropriateness "
          "from the Archaeological and Historical Commission.", extra={"hue": "--tool-6"}, **COH),
    layer("hou_land_use", "Land use (appraisal district)", "Rules", "area", LAND_USE, grid_z=16, minzoom=15,
          fields="SITE_ADDR_1,LANDUSE_DSCR,GROUP_DSCR,YR_IMPR", offset=0.000005,
          name=lambda a: (a.get("LANDUSE_DSCR") or a.get("GROUP_DSCR") or "").strip().title(),
          detail=lambda a: join((a.get("SITE_ADDR_1") or "").strip().title(),
                                f"built {a['YR_IMPR']}" if a.get("YR_IMPR") and str(a["YR_IMPR"]) != "0" else ""),
          props=lambda a: {"group": (a.get("GROUP_DSCR") or "").strip()},
          confidence="medium", note="What each parcel is used for, as the Harris Central Appraisal District classes it for tax. "
          "It describes the present use, not what is allowed.", extra={"hue": "--tool-7"}, **COH),
    layer("hou_bikeways", "Bikeways", "Getting around", "line", TR + "7", scope="city",
          fields="Full_Name,HC_Status,HC_Class,Description", where="HC_Status='Existing'", name="Full_Name",
          detail=lambda a: join(a.get("HC_Class"), a.get("HC_Status")),
          confidence="medium", note="Existing bikeways in the Houston Bike Plan, from protected lanes to signed routes. "
          "The class says which.", extra={"hue": "--tool-1"}, **COH),
    layer("hou_high_injury", "High-injury streets (Vision Zero)", "Getting around", "line", TR + "22", scope="city",
          fields="Full_Name,total_crash_count,ped_crash_count,bike_crash_count,ped_death_count,bike_death_count,car_death_count",
          name="Full_Name",
          detail=lambda a: join(f"{a['total_crash_count']} serious crashes" if a.get("total_crash_count") is not None else "",
                                f"{a['ped_crash_count']} involving people walking" if a.get("ped_crash_count") else ""),
          confidence="medium", note="The 2022 Vision Zero high-injury network: the streets where a large share of the city's "
          "traffic deaths and serious injuries happened, from the city's crash analysis.", data_date="2022",
          extra={"hue": "--tool-3"}, **COH),
    layer("hou_airport_noise", "Airport noise, 65 dB DNL and up", "Hazards", "area", TR + "18", scope="city",
          name="Airport noise contour, 65 dB DNL", confidence="medium",
          note="Where the day-night average sound level from the airports reaches 65 dB, the level the FAA treats as "
          "significant for homes.", extra={"hue": "--tool-4"}, **COH),
    layer("hou_evacuation", "Hurricane evacuation zones", "Hazards", "area", FH + "8", scope="city", fields="Zone,Name,County",
          name=lambda a: (a.get("Zone") or "").replace("Zip-Zone", "Zone").strip() or "Evacuation zone",
          detail=lambda a: join((a.get("Name") or "").title(), (a.get("County") or "").title()),
          confidence="high", note="The zip-code zones the region calls to leave, coast first, before a hurricane. "
          "Outside every zone, officials expect people to shelter at home unless told otherwise.", extra={"hue": "--tool-2"}, **COH),
    layer("hou_500yr", "500-year floodplain (0.2% a year)", "Hazards", "area", FH + "6", grid_z=13, minzoom=11,
          fields="FLD_ZONE,ZONE_SUBTY", offset=0.00003, name="0.2% annual chance floodplain",
          detail=lambda a: (a.get("ZONE_SUBTY") or "").strip().capitalize(), confidence="medium",
          note="FEMA's 0.2% annual chance (500-year) floodplain in Harris County, as the city republishes it. Harvey flooded "
          "many homes outside both this and the 100-year floodplain.", extra={"hue": "--tool-2"}, **COH),
    layer("hou_libraries", "Public libraries", "Services", "point", NB + "12", scope="city", fields="LIBRARY,ADDRESS",
          name="LIBRARY", detail=lambda a: a.get("ADDRESS") or "", confidence="high",
          note="Houston Public Library branches.", extra={"hue": "--tool-6"}, **COH),
    layer("hou_parks", "City parks", "Services", "area", NB + "14", scope="city", fields="Name,Park_Acres,Park_Type",
          offset=0.00002, name=lambda a: (a.get("Name") or "Park").title(),
          detail=lambda a: join(f"{a['Park_Acres']:.1f} acres" if a.get("Park_Acres") else "", a.get("Park_Type")),
          confidence="high", note="Parks the City of Houston runs. County, state and private parks are not included.",
          extra={"hue": "--tool-4"}, **COH),
    layer("hou_police", "Police stations", "Services", "point", PS + "1", scope="city", fields="STATION,ADDRESS",
          name=lambda a: (a.get("STATION") or "Police station").title(), detail=lambda a: (a.get("ADDRESS") or "").title(),
          confidence="high", note="Houston Police Department stations and storefronts.", extra={"hue": "--tool-3"}, **COH),
    layer("hou_311", "311 service requests (recent)", "Live", "point", SR311, grid_z=14, minzoom=13,
          fields="CASE_TYPE,STATUS,CREATED_ON,DEPARTMENT", name="CASE_TYPE",
          detail=lambda a: join(a.get("DEPARTMENT"), a.get("STATUS"), f"opened {day(a.get('CREATED_ON'))}"),
          confidence="medium", note="What residents reported to 311 in recent weeks (potholes, dumping, nuisance lots, "
          "flooding), at the reported address. A request is a report, not a confirmed problem.",
          extra={"hue": "--tool-8", "ttl_s": 3600}, **COH),
)
