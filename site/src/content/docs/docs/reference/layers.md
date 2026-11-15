---
title: "Map layers"
description: "The 66 map layers, their sources, licences and reliability."
---

The explorer draws 66 layers round a building. Each is served with its source, the date it was fetched and a reliability label. This table is generated from the layer catalogue in `server/threshold/layers/catalog.py`.

Layers in the Coverage and Imagery groups that come from Matterport, Vexcel or CoStar need your own access to those sources.

## Coverage

| Layer | Source | Licence or credit | Reliability | What it is and what it leaves out |
|---|---|---|---|---|
| Scanned buildings | Matterport scan index (CoStar kit) |  | high | One mark per address that has at least one scan. The kind of space is read from the scan's name. |
| With a CoStar property record | CoStar property records (hackathon kit) |  | high | Scanned addresses matched to a CoStar property record. Homes with a listing and no property record are left out. |
| With a drone capture | Matterport scan index (CoStar kit) |  | high | Scanned addresses that also have an exterior drone capture. |

## Live

| Layer | Source | Licence or credit | Reliability | What it is and what it leaves out |
|---|---|---|---|---|
| Weather now | [Open-Meteo (NOAA HRRR and GFS models)](https://open-meteo.com/) |  | medium | Model analysis for the city centre, refreshed every ten minutes. It is a forecast model's present, not a station reading. |
| Rain radar | [NOAA NEXRAD composite, Iowa Environmental Mesonet](https://mesonet.agron.iastate.edu/ogc/) |  | high | Base reflectivity from the national radar network, redrawn every five minutes. Clear air shows nothing. |
| Sun and shadows | [Computed here (NOAA solar position equations)](https://gml.noaa.gov/grad/solcalc/) |  | high | Where the sun stands for the chosen day and hour. Shadows are cast by the 3D city mesh, trees included, so they stop where the mesh does. |
| Air quality now (AirNow monitors) | [US EPA AirNow (current hour)](https://www.airnow.gov/) | Public (US EPA) | medium | The latest hourly reading at each official monitor, as an air quality index for ozone and fine particles. Readings are preliminary until EPA reviews them. Monitors are kilometres apart. |
| 311 service requests (recent) | [City of Houston GIS](https://cohgis-mycity.opendata.arcgis.com/) | City of Houston open data (public) | medium | What residents reported to 311 in recent weeks (potholes, dumping, nuisance lots, flooding), at the reported address. A request is a report, not a confirmed problem. Houston only. |
| Satellite, now (GOES-East) | [NASA GIBS, NOAA GOES-East ABI GeoColor](https://earthdata.nasa.gov/gibs) | Public domain (US government) | high | The geostationary weather satellite's latest picture, about every ten minutes, at about 2 km: storms and cloud now. Night shows city lights in a false colour. |
| Earthquakes, last 30 days | [USGS Earthquake Hazards Program](https://earthquake.usgs.gov/earthquakes/map/) | Public domain (USGS) | medium | Every earthquake USGS located in the last 30 days, of any size; magnitude 3 and up draws larger. Recent events are automatic solutions and can be revised. |
| Weather alerts now | [National Weather Service](https://www.weather.gov/) | Public domain (NOAA) | medium | Active warnings, watches and advisories that the Weather Service drew as a shape. Alerts issued for whole counties or zones are not drawn; check weather.gov for those. |
| River and bayou levels now | [USGS Water Data (instantaneous values)](https://waterdata.usgs.gov/) | Public domain (USGS) | medium | The latest reading at each active USGS stream gauge. Levels are on each gauge's own datum, so compare a gauge with its own history, not with another gauge. Provisional data. |
| Wildfire perimeters now | [National Interagency Fire Center, current perimeters](https://data-nifc.opendata.arcgis.com/) | Public (NIFC) | medium | Perimeters of wildfires burning now, as the incident teams last mapped them (often once a day). |

## People

| Layer | Source | Licence or credit | Reliability | What it is and what it leaves out |
|---|---|---|---|---|
| Population density | [US Census Bureau, American Community Survey 5-year estimates (Esri's hosted copy)](https://P3ePLMYs2RVChkJx.svcs.arcgis.com/P3ePLMYs2RVChkJx/arcgis/rest/services/ACS_Population_and_Housing_Basics_View_Boundaries/FeatureServer) | US Census Bureau ACS; Esri | medium | Population density by census tract. ACS figures are survey estimates with a margin of error, largest in small tracts. Each tract is one colour: it says nothing about a single street. |
| Median household income | [US Census Bureau, American Community Survey 5-year estimates (Esri's hosted copy)](https://P3ePLMYs2RVChkJx.svcs.arcgis.com/P3ePLMYs2RVChkJx/arcgis/rest/services/ACS_Population_and_Housing_Basics_View_Boundaries/FeatureServer) | US Census Bureau ACS; Esri | medium | Median household income by census tract. ACS figures are survey estimates with a margin of error, largest in small tracts. Each tract is one colour: it says nothing about a single street. |
| Median age | [US Census Bureau, American Community Survey 5-year estimates (Esri's hosted copy)](https://P3ePLMYs2RVChkJx.svcs.arcgis.com/P3ePLMYs2RVChkJx/arcgis/rest/services/ACS_Population_and_Housing_Basics_View_Boundaries/FeatureServer) | US Census Bureau ACS; Esri | medium | Median age by census tract. ACS figures are survey estimates with a margin of error, largest in small tracts. Each tract is one colour: it says nothing about a single street. |
| People 65 and over | [US Census Bureau, American Community Survey 5-year estimates (Esri's hosted copy)](https://P3ePLMYs2RVChkJx.svcs.arcgis.com/P3ePLMYs2RVChkJx/arcgis/rest/services/ACS_Population_and_Housing_Basics_View_Boundaries/FeatureServer) | US Census Bureau ACS; Esri | medium | People 65 and over by census tract. ACS figures are survey estimates with a margin of error, largest in small tracts. Each tract is one colour: it says nothing about a single street. |
| Renter households | [US Census Bureau, American Community Survey 5-year estimates (Esri's hosted copy)](https://P3ePLMYs2RVChkJx.svcs.arcgis.com/P3ePLMYs2RVChkJx/arcgis/rest/services/ACS_Population_and_Housing_Basics_View_Boundaries/FeatureServer) | US Census Bureau ACS; Esri | medium | Renter households by census tract. ACS figures are survey estimates with a margin of error, largest in small tracts. Each tract is one colour: it says nothing about a single street. |

## Rules

| Layer | Source | Licence or credit | Reliability | What it is and what it leaves out |
|---|---|---|---|---|
| Property parcels | [Harris Central Appraisal District; Los Angeles County Assessor](https://hcad.org/hcad-online-services/pdata/) |  | medium | Parcel outlines from each county's appraisal map. Lines are the county's drawing, not a survey, and stop at the county line. |
| Special minimum lot size areas | [City of Houston GIS](https://cohgis-mycity.opendata.arcgis.com/) | City of Houston open data (public) | high | Blocks where residents applied under Chapter 42 to keep lots at least this size. Outside them the city-wide Chapter 42 minimums apply. Deed restrictions are separate and not mapped. Houston only. |
| Special minimum building lines | [City of Houston GIS](https://cohgis-mycity.opendata.arcgis.com/) | City of Houston open data (public) | high | Blockfaces where a building must stand back at least this far from the street (Chapter 42). Houston only. |
| Historic districts (city) | [City of Houston GIS](https://cohgis-mycity.opendata.arcgis.com/) | City of Houston open data (public) | high | City of Houston historic districts: exterior changes need a certificate of appropriateness from the Archaeological and Historical Commission. Houston only. |
| Land use (appraisal district) | [City of Houston GIS](https://cohgis-mycity.opendata.arcgis.com/) | City of Houston open data (public) | medium | What each parcel is used for, as the Harris Central Appraisal District classes it for tax. It describes the present use, not what is allowed. Houston only. |
| Zoning | [Los Angeles City Planning, ZIMAS](https://zimas.lacity.org/) | City of Los Angeles open data (public) | high | The zone string on each lot, such as C2-1VL or R1-1: class, then height district. Q and T conditions, D limits, specific plans and overlays can change what it allows; ZIMAS's parcel report lists them. Los Angeles only. |
| General Plan land use | [Los Angeles City Planning, ZIMAS](https://zimas.lacity.org/) | City of Los Angeles open data (public) | high | The land use each community plan intends for an area. Zoning is meant to follow it but does not always yet. Los Angeles only. |
| Building permits (last 2 years) | [Los Angeles Department of Building and Safety (data.lacity.org)](https://data.lacity.org/d/pi9x-tg5x) | City of Los Angeles open data (public) | high | Permits LADBS issued in the last two years, at the permit's address. New buildings draw larger. Work done without a permit is not here. Los Angeles only. |

## Hazards

| Layer | Source | Licence or credit | Reliability | What it is and what it leaves out |
|---|---|---|---|---|
| FEMA flood hazard areas | [FEMA National Flood Hazard Layer, Esri's hosted copy](https://www.arcgis.com/home/item.html?id=11955f1b47ec41a3af86650824e0c634) |  | medium | Special flood hazard areas only (the 1% annual chance floodplain and floodway). Outside a shape means outside the mapped floodplain, not no risk. |
| Hurricane Harvey high-water marks | [USGS Short-Term Network, event 180](https://stn.wim.usgs.gov/STNDataPortal/) |  | medium | Surveyed marks of the peak water, August to September 2017. Height above ground is given where the surveyor recorded it. Data date 2017-09. Houston only. |
| Earthquake fault zones (Alquist-Priolo) | [California Geological Survey](https://maps.conservation.ca.gov/cgs/EQZApp/) | State of California open data (public) | high | Zones around active faults where the state requires a geologic study before most new buildings, and a seller must disclose. A fault can still break outside a zone. Los Angeles only. |
| Active fault traces | [California Geological Survey](https://maps.conservation.ca.gov/cgs/EQZApp/) | State of California open data (public) | high | The surface traces of active faults the zones are drawn around. Los Angeles only. |
| Liquefaction zones | [California Geological Survey](https://maps.conservation.ca.gov/cgs/EQZApp/) | State of California open data (public) | high | Where loose, wet ground could behave like liquid in strong shaking. New building here needs a site study. Areas the survey has not mapped yet are blank, not safe. Los Angeles only. |
| Earthquake-induced landslide zones | [California Geological Survey](https://maps.conservation.ca.gov/cgs/EQZApp/) | State of California open data (public) | high | Slopes the survey judged could slide in an earthquake. New building here needs a site study. Los Angeles only. |
| Fire hazard severity (state areas) | [CAL FIRE Fire Hazard Severity Zones](https://osfm.fire.ca.gov/what-we-do/community-wildfire-preparedness-and-mitigation/fire-hazard-severity-zones) | State of California open data (public) | high | CAL FIRE's fire hazard severity zones where the state fights wildfire. Very high zones carry building and brush clearance rules and a seller's disclosure. Data date 2024. Los Angeles only. |
| Fire hazard severity (local areas) | [CAL FIRE Fire Hazard Severity Zones](https://osfm.fire.ca.gov/what-we-do/community-wildfire-preparedness-and-mitigation/fire-hazard-severity-zones) | State of California open data (public) | high | CAL FIRE's 2025 fire hazard severity zones inside cities, where the city's fire department responds. Each city adopts the map by ordinance, so the adopted zone can lag. Data date 2025. Los Angeles only. |
| Airport noise, 65 dB DNL and up | [City of Houston GIS](https://cohgis-mycity.opendata.arcgis.com/) | City of Houston open data (public) | medium | Where the day-night average sound level from the airports reaches 65 dB, the level the FAA treats as significant for homes. Houston only. |
| Hurricane evacuation zones | [City of Houston GIS](https://cohgis-mycity.opendata.arcgis.com/) | City of Houston open data (public) | high | The zip-code zones the region calls to leave, coast first, before a hurricane. Outside every zone, officials expect people to shelter at home unless told otherwise. Houston only. |
| Transportation noise (road, rail, air) | [US DOT BTS National Transportation Noise Map, 2020](https://www.bts.gov/geospatial/national-transportation-noise-map) | Public domain (US government) | medium | Modelled 24-hour average sound level (LAeq) from roads, rail and aviation at 30 m, from 45 dB up. It is a model of traffic, not a measurement, and leaves out every other noise. Data date 2020. |
| Urban heat severity | [Trust for Public Land, heat severity 2023 (Landsat 8)](https://www.tpl.org/parks-and-an-equitable-recovery/heat) | The Trust for Public Land | medium | Where summer land surface was hottest relative to the rest of the city, on a 1 to 5 scale, from Landsat thermal readings. Surface temperature, not air temperature. Data date 2023. |
| Sea level rise, 3 ft | [NOAA Office for Coastal Management, sea level rise viewer](https://coast.noaa.gov/slr/) | Public domain (US government) | high | Low-lying land that would be under water at high tide with 3 feet more sea, if nothing protected it. Coastal areas only. |
| Sea level rise, 6 ft | [NOAA Office for Coastal Management, sea level rise viewer](https://coast.noaa.gov/slr/) | Public domain (US government) | high | The same with 6 feet more sea. |
| Storm surge, category 3 hurricane | [NOAA National Hurricane Center, storm surge risk maps](https://www.nhc.noaa.gov/nationalsurge/) | Public domain (US government) | high | How deep the sea could push inland in a worst case category 3 hurricane at high tide, from many modelled storms. Inland flooding from rain is not included. Houston only. |

## Getting around

| Layer | Source | Licence or credit | Reliability | What it is and what it leaves out |
|---|---|---|---|---|
| Transit stops | [US DOT National Transit Map](https://www.bts.gov/national-transit-map) |  | medium | Stops of agencies that publish a schedule feed to the federal transit map. Rail and bus are told apart by the feed's own type. |
| EV chargers | [US DOE Alternative Fuels Data Center](https://afdc.energy.gov/stations) |  | medium | Public charging stations that were open when fetched. Home and workplace chargers are not listed. |
| Traffic counts (vehicles a day) | [TxDOT (Houston), Caltrans (Los Angeles) annual average daily traffic](https://gis-txdot.opendata.arcgis.com/) | Public (state DOT open data) | high | Annual average daily traffic at state count stations: every vehicle both ways on an average day. Busy roads draw larger. Caltrans counts state highways only. |
| Transit routes | [US DOT National Transit Map (agencies' GTFS)](https://www.bts.gov/national-transit-map) | Public (US DOT) | medium | The routes transit agencies publish in their schedule feeds, as the federal map collected them. Rail draws thicker. Frequency is not shown. |
| Bikeways | [City of Houston GIS](https://cohgis-mycity.opendata.arcgis.com/) | City of Houston open data (public) | medium | Existing bikeways in the Houston Bike Plan, from protected lanes to signed routes. The class says which. Houston only. |
| High-injury streets (Vision Zero) | [City of Houston GIS](https://cohgis-mycity.opendata.arcgis.com/) | City of Houston open data (public) | medium | The 2022 Vision Zero high-injury network: the streets where a large share of the city's traffic deaths and serious injuries happened, from the city's crash analysis. Data date 2022. Houston only. |
| Bikeways | [LADOT, City of Los Angeles bikeways](https://geohub.lacity.org/) | City of Los Angeles open data (public) | medium | Bike paths (class I), lanes (II), routes (III) and protected lanes (IV) in the City of Los Angeles. Other cities in the county are not included. Los Angeles only. |

## Services

| Layer | Source | Licence or credit | Reliability | What it is and what it leaves out |
|---|---|---|---|---|
| Fire and EMS stations | [USGS National Structures Dataset](https://carto.nationalmap.gov/arcgis/rest/services/structures/MapServer) |  | medium | Federal inventory, last loaded by USGS in the year shown on each station. A station built since then is missing. |
| Fire hydrants | [City of Houston GIS](https://cohgis-mycity.opendata.arcgis.com/) |  | medium | The city's own hydrant inventory, inside Houston's city limits only. Los Angeles publishes no hydrant map without a sign-in. Houston only. |
| Hospitals | [USGS National Structures Dataset](https://carto.nationalmap.gov/arcgis/rest/services/structures/MapServer) |  | medium | Hospitals and medical centres from the federal inventory. Clinics and urgent care are not included. |
| Schools and colleges | [USGS National Structures Dataset](https://carto.nationalmap.gov/arcgis/rest/services/structures/MapServer) |  | medium | Public and private schools, colleges and universities from the federal inventory. |
| Homes without 100/20 Mbps broadband | [FCC National Broadband Map, Broadband Data Collection (Esri's tract summary)](https://broadbandmap.fcc.gov/) | Public (FCC); Esri hosting terms apply | medium | Share of the homes and businesses in each tract that no provider says it can serve at 100 Mbps down and 20 up by wire or licensed fixed wireless. Providers report this themselves; speeds are offered, not measured. Data date 2024-12. |
| Fiber providers | [FCC National Broadband Map, Broadband Data Collection (Esri's tract summary)](https://broadbandmap.fcc.gov/) | Public (FCC); Esri hosting terms apply | medium | How many providers say they offer fiber somewhere in the tract. One provider in a tract does not mean every street has it. Data date 2024-12. |
| Public libraries | [City of Houston GIS](https://cohgis-mycity.opendata.arcgis.com/) | City of Houston open data (public) | high | Houston Public Library branches. Houston only. |
| City parks | [City of Houston GIS](https://cohgis-mycity.opendata.arcgis.com/) | City of Houston open data (public) | high | Parks the City of Houston runs. County, state and private parks are not included. Houston only. |
| Police stations | [City of Houston GIS](https://cohgis-mycity.opendata.arcgis.com/) | City of Houston open data (public) | high | Houston Police Department stations and storefronts. Houston only. |

## Imagery

| Layer | Source | Licence or credit | Reliability | What it is and what it leaves out |
|---|---|---|---|---|
| 3D city mesh coverage | [Vexcel 3D Cities](https://vexceldata.com/products/3d-cities/) |  | medium | The outer box of each 3D collection. The mesh inside it is irregular, so the edge is approximate. |
| Aerial photo (USGS, NAIP) | [USGS National Map, orthoimagery (NAIP)](https://www.usgs.gov/programs/national-geospatial-program/national-map) | Public domain (US government) | high | The national aerial photo at about 60 cm to 1 m, flown every two to three years. Coarser and older than the Vexcel photo, but it covers everywhere. |
| Topographic map (USGS) | [USGS National Map, US Topo](https://www.usgs.gov/programs/national-geospatial-program/us-topo-maps-america) | Public domain (US government) | high | Contours, terrain shading, water and names from the national topographic map. |
| Shaded relief (USGS 3DEP) | [USGS 3D Elevation Program](https://www.usgs.gov/3d-elevation-program) | Public domain (US government) | high | Hillshade from the national elevation model: shows where the land rises and falls, not how high. |
| Satellite, cloudless 2024 (Sentinel-2) | [EOX Sentinel-2 cloudless](https://s2maps.eu/) | Sentinel-2 cloudless - https://s2maps.eu by EOX IT Services GmbH (Contains modified Copernicus Sentinel data 2024) | high | A year of Copernicus Sentinel-2 passes with clouds removed, at 10 m. Licensed for non-commercial use only (CC BY-NC-SA 4.0). Data date 2024. |
| Satellite, yesterday (NASA VIIRS) | [NASA GIBS, NOAA-20 VIIRS true colour](https://earthdata.nasa.gov/gibs) | Public domain (US government) | high | Yesterday's true-colour pass of the NOAA-20 satellite at about 375 m: clouds, smoke and haze, not buildings. Data date 2026-11-14. |
| Night lights (NASA Black Marble) | [NASA Black Marble 2016](https://blackmarble.gsfc.nasa.gov/) | Public domain (US government) | high | City lights seen from space in 2016, at about 500 m: where people and industry are. Data date 2016. |
| Tree canopy (NLCD) | [USDA Forest Service, NLCD tree canopy cover 2021 (MRLC)](https://www.mrlc.gov/data) | Public domain (US government) | medium | Share of each 30 m cell covered by tree crowns, from Landsat. Street trees narrower than a cell are undercounted. Data date 2021. |
| Paved and built surface (NLCD) | [USGS National Land Cover Database 2021 (MRLC)](https://www.mrlc.gov/data) | Public domain (US government) | medium | Share of each 30 m cell that is roof, road or pavement, the surface rain cannot soak into. Data date 2021. |
