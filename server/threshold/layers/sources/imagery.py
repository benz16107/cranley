"""Raster layers the browser loads straight from the publisher's tile or image service: aerial and satellite
pictures, and hazard and environment maps that exist only as pictures (noise, heat, sea level rise, storm surge,
tree canopy). Nothing passes through this server, so nothing here is cached on our side.

`{bbox-epsg-3857}` in a template is filled by the map for services that draw a picture for any box (WMS, ArcGIS
export) instead of serving fixed tiles.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ..catalog import Layer

# NASA's daily mosaics are complete about a day later; a server running past midnight keeps the day it started with
YESTERDAY = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%d")
USGS = "https://basemap.nationalmap.gov/arcgis/rest/services/{}/MapServer/tile/{{z}}/{{y}}/{{x}}"
GIBS = "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/{}/default/{}/GoogleMapsCompatible_Level{}/{{z}}/{{y}}/{{x}}.{}"
NOAA_TILES = "https://tiles.arcgis.com/tiles/C8EMgrsFcRFL6LrL/arcgis/rest/services/{}/MapServer/tile/{{z}}/{{y}}/{{x}}"
EXPORT = "bbox={bbox-epsg-3857}&bboxSR=3857&imageSR=3857&size=256,256&format=png32&transparent=true&f=image"
WMS = ("https://www.mrlc.gov/geoserver/mrlc_display/wms?service=WMS&version=1.1.1&request=GetMap&layers={}&styles=&"
       "srs=EPSG:3857&bbox={{bbox-epsg-3857}}&width=256&height=256&format=image/png&transparent=true")
PD = "Public domain (US government)"


def raster(id, title, group, tiles, source, source_url, note, *, licence=PD, confidence="high", max_z=18, data_date="",
           cities=("hou", "la"), attribution="", hue="--ink-2", minzoom=0):
    return Layer(id, title, group, "raster", "tiles", source, source_url, confidence, note, data_date=data_date,
                 cities=cities, tiles=tiles, licence=licence, attribution=attribution, minzoom=minzoom,
                 extra={"tile_maxzoom": max_z, "hue": hue})


LAYERS = (
    raster("naip", "Aerial photo (USGS, NAIP)", "Imagery", USGS.format("USGSImageryOnly"), "USGS National Map, orthoimagery (NAIP)",
           "https://www.usgs.gov/programs/national-geospatial-program/national-map", "The national aerial photo at about "
           "60 cm to 1 m, flown every two to three years. Coarser and older than the Vexcel photo, but it covers everywhere.",
           max_z=16),
    raster("usgs_topo", "Topographic map (USGS)", "Imagery", USGS.format("USGSTopo"), "USGS National Map, US Topo",
           "https://www.usgs.gov/programs/national-geospatial-program/us-topo-maps-america", "Contours, terrain shading, "
           "water and names from the national topographic map.", max_z=16),
    raster("relief", "Shaded relief (USGS 3DEP)", "Imagery", USGS.format("USGSShadedReliefOnly"), "USGS 3D Elevation Program",
           "https://www.usgs.gov/3d-elevation-program", "Hillshade from the national elevation model: shows where the land "
           "rises and falls, not how high.", max_z=13),
    raster("sentinel2", "Satellite, cloudless 2024 (Sentinel-2)", "Imagery",
           "https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2024_3857/default/g/{z}/{y}/{x}.jpg", "EOX Sentinel-2 cloudless",
           "https://s2maps.eu/", "A year of Copernicus Sentinel-2 passes with clouds removed, at 10 m. Licensed for "
           "non-commercial use only (CC BY-NC-SA 4.0).", licence="CC BY-NC-SA 4.0 (non-commercial)",
           attribution="Sentinel-2 cloudless - https://s2maps.eu by EOX IT Services GmbH (Contains modified Copernicus Sentinel data 2024)",
           max_z=14, data_date="2024"),
    raster("satellite_today", "Satellite, yesterday (NASA VIIRS)", "Imagery",
           GIBS.format("VIIRS_NOAA20_CorrectedReflectance_TrueColor", YESTERDAY, 9, "jpg"), "NASA GIBS, NOAA-20 VIIRS true colour",
           "https://earthdata.nasa.gov/gibs", "Yesterday's true-colour pass of the NOAA-20 satellite at about 375 m: clouds, "
           "smoke and haze, not buildings.", max_z=9, data_date=YESTERDAY, confidence="high"),
    raster("goes_now", "Satellite, now (GOES-East)", "Live",
           GIBS.format("GOES-East_ABI_GeoColor", "default", 7, "png"), "NASA GIBS, NOAA GOES-East ABI GeoColor",
           "https://earthdata.nasa.gov/gibs", "The geostationary weather satellite's latest picture, about every ten minutes, "
           "at about 2 km: storms and cloud now. Night shows city lights in a false colour.", max_z=7),
    raster("night_lights", "Night lights (NASA Black Marble)", "Imagery",
           GIBS.format("VIIRS_Black_Marble", "2016-01-01", 8, "png"), "NASA Black Marble 2016",
           "https://blackmarble.gsfc.nasa.gov/", "City lights seen from space in 2016, at about 500 m: where people and "
           "industry are.", max_z=8, data_date="2016"),
    raster("noise", "Transportation noise (road, rail, air)", "Hazards",
           "https://geo.dot.gov/server/rest/services/Hosted/NTAD_Noise_2020_CONUS_Aviation_Road_Rail/MapServer/tile/{z}/{y}/{x}",
           "US DOT BTS National Transportation Noise Map, 2020", "https://www.bts.gov/geospatial/national-transportation-noise-map",
           "Modelled 24-hour average sound level (LAeq) from roads, rail and aviation at 30 m, from 45 dB up. It is a "
           "model of traffic, not a measurement, and leaves out every other noise.", max_z=12, data_date="2020",
           confidence="medium", hue="--tool-4"),
    raster("heat", "Urban heat severity", "Hazards",
           "https://server4.tplgis.org/arcgis4/rest/services/NATIONAL/uhi_city_severity_2023/ImageServer/exportImage?" + EXPORT,
           "Trust for Public Land, heat severity 2023 (Landsat 8)", "https://www.tpl.org/parks-and-an-equitable-recovery/heat",
           "Where summer land surface was hottest relative to the rest of the city, on a 1 to 5 scale, from Landsat "
           "thermal readings. Surface temperature, not air temperature.", max_z=15, data_date="2023", confidence="medium",
           licence="Trust for Public Land (free to use with credit)", attribution="The Trust for Public Land", hue="--tool-3"),
    raster("sea_level_3ft", "Sea level rise, 3 ft", "Hazards", NOAA_TILES.format("slr_3ft"),
           "NOAA Office for Coastal Management, sea level rise viewer", "https://coast.noaa.gov/slr/",
           "Low-lying land that would be under water at high tide with 3 feet more sea, if nothing protected it. "
           "Coastal areas only.", max_z=16, hue="--tool-2"),
    raster("sea_level_6ft", "Sea level rise, 6 ft", "Hazards", NOAA_TILES.format("slr_6ft"),
           "NOAA Office for Coastal Management, sea level rise viewer", "https://coast.noaa.gov/slr/",
           "The same with 6 feet more sea.", max_z=16, hue="--tool-2"),
    raster("storm_surge", "Storm surge, category 3 hurricane", "Hazards", NOAA_TILES.format("Storm_Surge_HazardMaps_Category3_v3"),
           "NOAA National Hurricane Center, storm surge risk maps", "https://www.nhc.noaa.gov/nationalsurge/",
           "How deep the sea could push inland in a worst case category 3 hurricane at high tide, from many modelled "
           "storms. Inland flooding from rain is not included.", max_z=14, cities=("hou",), hue="--tool-2"),
    raster("tree_canopy", "Tree canopy (NLCD)", "Imagery", WMS.format("nlcd_tcc_conus_2021_v2021-4"),
           "USDA Forest Service, NLCD tree canopy cover 2021 (MRLC)", "https://www.mrlc.gov/data", "Share of each 30 m cell "
           "covered by tree crowns, from Landsat. Street trees narrower than a cell are undercounted.", max_z=16, data_date="2021",
           confidence="medium", hue="--tool-4"),
    raster("impervious", "Paved and built surface (NLCD)", "Imagery", WMS.format("NLCD_2021_Impervious_L48"),
           "USGS National Land Cover Database 2021 (MRLC)", "https://www.mrlc.gov/data", "Share of each 30 m cell that is "
           "roof, road or pavement, the surface rain cannot soak into.", max_z=16, data_date="2021", confidence="medium"),
)
FETCH: dict = {}
