---
title: Architecture
description: A React web app, a FastAPI server, five contracts between them, and two cloud databases.
---

```
 web (React 19, Vite)                              server (Python 3.12, FastAPI)
 +---------------------------------------+         +----------------------------------------+
 | /app   Home, Explore, Building,       |         | agent/     composer + deepagents       |
 |        Investigations, Insights,      |<--SSE---|            investigator, workspace ops |
 |        Tools, Settings                |         | tools/     one folder per tool         |
 | /m     phone companion (QR pairing)   |---ops-->| geometry/  routes, clearance, rules,   |
 | scene/ three.js: dollhouse, plan,     |         |            takeoff, georef, water      |
 |        panoramas, mesh, splats        |         | vision/    panorama reader             |
 +---------------------------------------+         | aerial/    site facts, elevation       |
 ios/   SwiftUI app: RoomPlan scan, LiDAR          | sources/   Matterport, Vexcel, CoStar  |
        measure, barometer -> /api/scans/user      | world/     3D city, terrain, storms    |
                                                   | splat/     interior splat training     |
                                                   | report/    PDF site reports            |
                                                   | whatif/    plan edits, cost, forks     |
                                                   +----------+---------------+-------------+
                                              MongoDB Atlas <-+               +-> Tiger Cloud
                                    workspaces, op log, live sync,     building facts, history,
                                    search, memory, checkpoints        search by measurement, forks
```

## The five contracts

The parts of the system meet at five contracts. Each was written before the code on either side of it.

| Contract | What it fixes | Where |
|---|---|---|
| 1. The plan | One scan, normalized: floors, walls, openings with real widths, rooms and panoramas, in metres, plus a quality block | `server/threshold/scanplan.py` |
| 2. The data API | The routes the web app and the phone call | [HTTP API](/docs/reference/api/) |
| 3. The tool result | What every tool returns | [Result format](/docs/reference/result-format/) |
| 4. Overlays | How anything draws on the building, the plan, a panorama or the map | [Result format](/docs/reference/result-format/#overlays) |
| 5. The workspace | One document and the operations that change it | [The workspace](/docs/concepts/workspace/) |

## The plan

Every source becomes the same plan: a Matterport scan, or a RoomPlan export from an iPhone. Lengths are in metres, in the scan's own frame, with x and y on the floor and z up.

The plan's `quality` block says what the scan has: walls, room polygons, openings, labels and a georeference. Every tool reads it first. A scan with rooms and panoramas but no wall graph gets what photos and records can say, and an `unknown` verdict for the rest.

## Engines, built once

Tools call shared engines and never copy them.

| Engine | What it does |
|---|---|
| `threshold.geometry` | Routes and reach through the wall graph, clearance, fit, rule packs, takeoff, georeference and sun, water |
| `threshold.vision` | Room labels and objects from panoramas, read by a vision model |
| `threshold.aerial` | Site facts, orthophotos, elevation and detection from the air |
| `threshold.sources` | Plans, panoramas, records and the scan index |

## The server

`api/app.py` includes every router it finds in `threshold/api/`, one per file. Signed scan links expire, so the browser never sees them: the server fetches, caches on disk and serves.

## The web app

The web app is a shared core and one folder per look. The core is the product: the workspace, the link to the agent, the data clients, the address bar and the bridge to the 3D scene. A look draws it. The App look at `/app` is the default.

The 3D scene is three.js through React Three Fiber: a dollhouse drawn from the wall graph, the plan, panoramas, the scanned mesh baked with its own panoramas, and Gaussian splats through Spark. The map is MapLibre with deck.gl.

## The databases

- **MongoDB Atlas** holds the people side: workspaces, their operation logs, live sync, memory and search over past work.
- **Tiger Cloud** holds the building side: what was measured, when, and how it changed.

Both are optional. Without them, workspaces are files in the data folder and the tools that query the facts database say it is not configured. What each feature is used for is under [sponsor integrations](/docs/sponsor-integrations/).

## Hardware

One mini PC with an AMD Ryzen 9 7940HS and its integrated Radeon 780M runs the API, the CFAST fire model, Ollama for embeddings, and the training of the interior Gaussian splats with Brush through Vulkan.
