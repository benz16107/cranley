---
title: Data sources and licences
description: What comes from Matterport, Vexcel, CoStar, OpenStreetMap and the public layers, and how each is credited.
---

Cranley joins three sponsor layers with public data and your own scans. This page says what comes from where.

## Sponsor data

The sponsor data was given for HackPrinceton Fall 2026 under CoStar's hackathon terms. **None of it is in the repository or on this site.** To run Cranley on these layers you need your own access to each source, under your own agreement.

| Source | What Cranley reads | Used for |
|---|---|---|
| Matterport, through the Model API | Walls, doorways and windows with real widths, room polygons and heights, panoramas with their positions, floor plan images, and the scanned mesh. Drone captures for some properties | Every check inside a building |
| Vexcel | Orthophotos, oblique views, ground and surface elevation, ready-made property facts such as roof, pools and paved area, detection by name, and a 3D city mesh | Site tools, floor height, flood, parking, roofs, and the city around a building |
| CoStar | Property records and listings | Record versus reality, market comps, site scorecards |

## Your own scans

A scan you make with the iPhone app uses Apple RoomPlan and ARKit on your device. It is yours. The server stores the converted plan in your data folder.

## Public data

| Source | What Cranley reads | Licence or credit |
|---|---|---|
| OpenStreetMap, through Overpass | Parks, schools, vets, shops, transit and the walkable street network near a place | © OpenStreetMap contributors, Open Database License (ODbL) |
| USGS Short-Term Network | Hurricane Harvey high-water marks | U.S. Geological Survey |
| USGS National Structures Dataset | Fire and EMS stations, hospitals, schools | U.S. Geological Survey |
| FEMA National Flood Hazard Layer | Special flood hazard areas | FEMA, through Esri's hosted copy |
| City and state open data | Zoning, permits, hydrants, transit and hazard zones | Credited per layer |

Every map layer is listed with its source, its licence or credit, and its reliability in the [map layer reference](/docs/reference/layers/), which is generated from the layer catalogue. Each layer is served with the date it was fetched.

## Models and software run as they are

| What | Use | Licence |
|---|---|---|
| NIST CFAST | The smoke model behind the smoke clock, run as an external program | Public domain |
| Brush | Gaussian splat training, run as an external program | Apache-2.0 |
| 3D models of vehicles and furniture | Drawn at the exact size a tool measured | CC0 1.0 (Kenney, Quaternius) and CC BY 3.0 (Poly by Google). The full list is `web/public/models/LICENSES.md` in the repository |
| Archivo and Martian Mono | The typefaces of the app and this site | SIL Open Font License 1.1 |

The libraries Cranley is built on are credited in the repository's README. None is under a copyleft licence.

## Reliability by source

A tool labels every value with its layer and method. See [findings and reliability](/docs/concepts/findings-and-reliability/).

## Licence of Cranley itself

All rights reserved. CoStar's hackathon terms, section 4.2, assign the project's intellectual property to CoStar. The code is public so that it can be read and judged.

## Names

Matterport, Vexcel, CoStar, Apple, RoomPlan, ARKit, MongoDB, Tiger Data, LangChain, Photon, Amazon and the other names on this site belong to their owners. Cranley is a hackathon project and is not endorsed by any of them.
