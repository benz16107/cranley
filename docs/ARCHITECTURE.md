# Architecture

## What we are building

A base explorer of scanned buildings in Houston and Los Angeles (map, a 3D dollhouse we draw ourselves, floor
plan, 360° panoramas, drone Gaussian splats), plus tools that an agent adds to a user's workspace according
to their need. Flagship tools: flood rehearsal, fire pre-plan, step-free access audit, office fit, record
versus reality. Many smaller tools share the same engines.

```
 web (React, Vite)                               server (Python, FastAPI)
 ┌──────────────────────────────────────┐        ┌───────────────────────────────────────┐
 │ Map        MapLibre + deck.gl        │        │ agent/      composer + investigator   │
 │ Scene      three.js: dollhouse,      │        │ tools/      manifest + handler each   │
 │            panorama, splat, plan     │        │ geometry/   routes, clearance, rules  │
 │ Workspace  panels, tool dock, plan   │        │ vision/     panorama reader           │
 │   ▲ renders the workspace document   │◄─SSE───┤ aerial/     Vexcel site reader        │
 │   └ user ops (same vocabulary) ──────┼──────► │ sources/    Matterport, CoStar, index │
 └──────────────────────────────────────┘        │ api/        one router per file       │
                                                  └───────────────────────────────────────┘
```

Data facts that shape everything (measured on 2026-11-13):

- The scans are mostly apartment units and amenity rooms, then houses, then offices. Few shops or warehouses.
- The wall graph (walls, doorways and windows with real widths, room polygons, heights) exists for every house
  sampled but only about half of apartment units and two thirds of offices. The rest have rooms, panoramas,
  floor plan images and a schematic DXF, but no walls. Every tool must check `plan.quality` and say plainly
  when a scan cannot answer.
- The mesh download (MatterPak) is unavailable. The dollhouse is built from the wall graph.
- `geocoordinates` gives each scan's compass rotation. Panoramas carry a position, a rotation and their
  walkable neighbours.
- Offices have no room labels (`Other`). Homes do.
- Drone splats and photos exist for a small set of properties, mostly Houston houses.
- Vexcel gives 7.5 cm orthophotos, oblique views, ground and surface elevation, 165 ready-made facts per
  property (roof, pools, vehicles, paved area) and detection by name.

## Workstreams and the folders they own

| Workstream | Owns |
|---|---|
| data | `server/pyproject.toml`, `server/threshold/sources/`, `server/threshold/scanplan.py`, `server/threshold/api/app.py`, `server/threshold/api/data.py`, `server/threshold/config.py` |
| geometry | `server/threshold/geometry/`, `server/tests/geometry/` |
| perception | `server/threshold/vision/`, `server/threshold/aerial/`, `server/tests/perception/` |
| agent | `server/threshold/agent/`, `server/threshold/tools/` (registry, manifest and result types, one reference tool), `server/threshold/api/agent.py`, `server/tests/agent/` |
| shell | `web/` except `web/src/scene/` |
| scene | `web/src/scene/`, `web/scene-lab.html` |
| later: one per flagship tool | `server/threshold/tools/<tool>/`, `web/src/tools/<tool>/` |

Shared-file rule: `api/app.py` includes every `router` it finds in `threshold/api/*.py`, so nobody edits
another workstream's file to register routes. Python dependencies: add yours to `server/pyproject.toml` in
your own commit, one line each; the lead resolves the merge. Web dependencies the same way in `web/package.json`.

## Contract 1: ScanPlan (the scan, normalized)

Code: `server/threshold/scanplan.py` (`normalize`). Fixtures of 12 real scans:
`$THRESHOLD_DATA_DIR/fixtures/scanplan/<sid>.json` (houses, apartments, offices, one with no walls).
More: `python3 server/scripts/fetch_fixtures.py <sid>`.

Metres, the scan's own frame, x and y on the floor, z up.

```
{ schema: "scanplan/1", sid, name, notes, address, city, segment, created, summary,
  geo: { lat, lon, altitude, yaw_deg, translation, source } | null,
  ids: { costar_property, homes_listing, defurnished_view },
  has: { splat, defurnished, room_labels, openings },
  floors:   [{ id, label, sequence }],
  walls:    [{ id, floor, a:[x,y], b:[x,y], type:"wall"|"invisible", thickness, length, rooms:[roomId], openings:[openingId] }],
  openings: [{ id, wall, floor, type:"doorway"|"window"|"opening", width, height, sill, center:[x,y], rooms:[roomId] }],
  rooms:    [{ id, floor, label|null, label_confidence, label_source:"matterport"|"vision"|"user"|null,
               polygon:[[x,y],…] (may be empty), area, height, width, depth, walls:[wallId], holes }],
  panos:    [{ id, label, position:[x,y,z], rotation:[x,y,z,w]|null, floor, room|null, neighbors:[panoId] }],
  floorplans: [{ floor, format, flags, width, height, resolution (px per metre), origin:{x,y} }] }
```

`geo.yaw_deg` is the rotation about z from the scan frame to east-north-up; the geometry workstream owns
the exact convention and must verify it against an aerial photo before anyone relies on it.
An opening with one room in `rooms` leads outside or to unscanned space.

## Contract 2: data API (served by the data workstream, port 8787)

```
GET  /api/buildings                     GeoJSON, one feature per address, properties: scans[], counts, flags
GET  /api/scans?address=…|q=…           index rows
GET  /api/scan/{sid}/plan               ScanPlan
GET  /api/scan/{sid}/pano/{pano}/{face}.jpg?res=2k|4k&view=furnished|defurnished   cube face 0..5 (0 up, 1-4 sides, 5 down)
GET  /api/scan/{sid}/pano/{pano}/equirect.jpg?w=2048&view=…
GET  /api/scan/{sid}/floorplan/{floor}.{jpg|png}?flags=…
GET  /api/scan/{sid}/splat              byte-range capable stream of splat.ply (232 scans)
GET  /api/scan/{sid}/drone              list; /api/scan/{sid}/drone/{name} image
GET  /api/scan/{sid}/record             CoStar record, 404 until the kit is configured
GET  /api/aerial/ortho?lat=&lon=&size_m=&px=      (perception)
GET  /api/aerial/property?lat=&lon=               (perception)
GET  /api/aerial/elevation?lat=&lon=              (perception) ground and surface
POST /api/aerial/detect                           (perception)
GET  /api/tools                         manifests            (agent)
POST /api/tools/{id}/run                ToolResult           (agent)
POST /api/agent/turn                    SSE stream of workspace ops (agent)
GET  /api/workspace/{id}  POST /api/workspace/{id}/ops      (agent)
```

Signed Matterport links expire, so the browser never sees them; the server fetches, caches on disk and serves.

## Contract 3: ToolResult (what every tool returns)

```
{ tool, scope: { sid } | { address } | { sids:[…] },
  verdict:  { status: "pass"|"warn"|"fail"|"unknown", text },
  metrics:  [{ id, label, value, unit, source }],
  checks:   [{ id, rule, measured, threshold, unit, status, standard|null, findings:[findingId] }],
  findings: [{ id, title, status, detail, anchor, source, media:[{ kind:"pano"|"ortho"|"drone", ref, box|null }] }],
  overlays: [Overlay],
  assumptions: [{ id, label, value, unit, editable }],
  actions:  [{ id, label, tool, inputs }] }

source = { layer: "matterport"|"vexcel"|"costar"|"drone"|"model", method: "geometry"|"vision"|"lookup"|"simulation",
           confidence: "high"|"medium"|"low", note }
anchor = { sid, point:[x,y,z] } | { sid, room } | { sid, opening } | { sid, wall }
       | { sid, pano, yaw_deg, pitch_deg } | { geo:[lon,lat] }
```

A tool is a manifest (id, title, summary, who it is for, JSON Schema of inputs with `x-ask` questions, the
data it needs, the panel blocks it fills) plus a handler `run(ctx, inputs) -> ToolResult`. The same manifest
feeds the agent, the web tool dock, and later an MCP server and a CLI. The agent workstream owns the exact
manifest type; start from `research/05-adaptive-interface.md`, section "The tool manifest".

## Contract 4: overlays (how anything draws on the building, the plan, a panorama or the map)

```
{ kind:"lens",  values:{ roomId: number }, ramp:"sequential"|"status", legend:{ title, unit, min, max } }
{ kind:"rule",  select:{ rooms:[…] } | { room_labels:[…] } | { openings:[…] } | { walls:[…] }, style:"solid"|"dim"|"hide"|"highlight"|"pass"|"warn"|"fail" }
{ kind:"pins",  pins:[{ id, anchor, label, status }] }
{ kind:"route", floor, points:[[x,y,z],…], chokes:[{ point, width, status }], label }
{ kind:"water", level_m, datum:"scan_z" }
{ kind:"box",   center:[x,y,z], size:[w,d,h], yaw_deg, label, status }
```

One overlay draws in every view that can show it. Renderers ignore kinds they do not know. New kinds are
added here by the lead. The scene workstream exposes `<BuildingScene plan overlays view onPick />` and the
shell never reaches into three.js.

## Contract 5: the workspace document and its operations

One JSON document per user session: brief, enabled tools, runs, findings, overlays, panels, plan steps,
preferences, shortlist. The agent and the user change it only through these operations, each appended to a
log with `by`, a time and a run id:

`brief.set`, `question.ask`, `question.answer`, `tool.enable`, `tool.disable`, `run.start`, `run.finish`,
`finding.add`, `layer.upsert`, `overlay.upsert`, `panel.upsert`, `camera.focus`, `plan.set`, `pref.set`,
`shortlist.add`, `shortlist.remove`.

Panels are built only from the block catalog in `research/05-adaptive-interface.md`, section "Composing
from building blocks" (VerdictHeader, MetricRow, CheckList, EvidenceStrip, RankedTable, MiniChart,
FloorPlanMini, Controls, AssumptionChips, StepLog, Note, ActionBar). The agent workstream owns the document
schema and the op validator (`server/threshold/agent/workspace.py`, exported as JSON Schema to
`docs/contracts/workspace.schema.json`); the shell workstream renders it. Until that schema lands, the
shell codes against the op names above and the block catalog.

## Amendments after wave 1 (2026-11-13)

**Contract 1.** Added, nothing renamed: `plan.quality` (`walls`, `polygons`, `openings`, `labels`, `georef` as booleans,
plus `counts` and `notes`); `floors[].elevation` (metres above the lowest floor) and `elevation_source`;
`rooms[].center`, `hole_polygons`, `extra_polygons`, `area_source`. Room polygons are counter-clockwise.
`openings[].sill` is absolute scan z, so subtract the floor's elevation for height above that floor. A doorway
with one room may lead outside or to an unscanned room; until the plan says which, treat it as "entrance,
unverified". About 60% of rooms have no `height`; use the plan's median and mark it.

**Contract 2.** Also served: `/api/scans` filters, `/api/property/{id}/scans`, `/api/scan/{sid}/splat/envmap/{face}.jpg`,
`POST /api/workspace`, `POST /api/workspace/{id}/undo`. `/api/scan/{sid}/record` returns the CoStar or listing record
with related records and a `claims` list (each claim has the exact field path it came from).

**Contract 3.** A check may also carry `result` (`likely pass`, `likely fail`, `measure on site`), `tolerance`,
`severity` and `items`; a finding may carry `result`, `label` and `room`. Renderers ignore fields they do not know.
A panorama anchor's `yaw_deg` is measured in the scan frame, counter-clockwise from +x; `pitch_deg` is positive
looking up. A panorama media ref is `"<sid>/<pano>/<face>"` with `box` as fractions of the face (x0, y0, x1, y1).
Run inputs and timestamps live on the workspace's run record, not on the result.

**Contract 5.** `finding.add` is an upsert and carries user feedback (`feedback`, `superseded_by`). Undo is a log
entry. The schema and TypeScript types are in `docs/contracts/workspace.schema.json` and `workspace.ts`.

**Tools.** How to write one: `server/threshold/tools/README.md`. A tool lives in `server/threshold/tools/<id>/`,
tests in `server/tests/tools/<id>/`. Use the ids already named in `server/threshold/agent/personas/*.json` so the
presets pick the tool up. Engines to call, never to copy: `threshold.geometry` (routes, reach, fit, rule packs,
takeoff, georef and sun, water), `threshold.vision` (label_rooms, find_objects, contents), `threshold.aerial`
(site_facts, ortho, elevation, detect, obliques), `threshold.sources` (plans, panoramas, CoStar records, index).

**Ports.** 8787 is the lead's merged server. 8791 and 8796 are taken by other software on this machine. Pick a
free port above 8800 for your own server.

## Run it

```
cd server && uv sync && uv run uvicorn threshold.api.app:app --port 8787
cd web && pnpm install && pnpm dev          # proxies /api to 8787
```
