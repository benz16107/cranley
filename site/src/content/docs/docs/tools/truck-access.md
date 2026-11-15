---
title: "Truck access"
description: "Whether a 53 ft trailer can reach and back to the docks: entrance, gate, court depth, turning room, overhead obstructions, arrival directions and a route on the aerial photo."
sidebar: {"label": "Truck access"}
---

Whether a 53 ft trailer can reach and back to the docks: entrance, gate, court depth, turning room, overhead obstructions, arrival directions and a route on the aerial photo.

## What it answers

- Can a 53 foot trailer get into this warehouse?
- Which entrance do trucks use here?

For the agent, the tool is described as: For a warehouse or any commercial address in Houston or Los Angeles: finds the dock wall, measures the truck court depth and the entrance width on the orthophoto and surface model, checks them against a WB-67 (53 ft trailer, AASHTO) and the 130 ft court guideline, names the street and driveway (OpenStreetMap), gate or no gate, posted low clearances within 1.5 km, trailer parking, and writes arrival directions. Returns a route overlay on the map (floor 'geo', points [lon, lat, 0]) and pins on the tight spots.

## Who it is for

[Industrial tenant rep](/docs/reference/personas/#industrial-tenant-rep), [Film or photo location scout](/docs/reference/personas/#film-or-photo-location-scout), [Truck dispatcher](/docs/reference/personas/#truck-dispatcher).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `scan` | string |  |  | Scan id, if the site has one. Filled from the selected building. |
| `property_id` | integer |  |  | CoStar PropertyId, for a commercial address. |
| `lat` | number |  |  | Latitude, for an address with no scan. |
| `lon` | number |  |  | Longitude, for an address with no scan. |
| `court_min_m` | number (m) |  | `39.6` | Truck court depth a 53 ft trailer needs to back in (130 ft). Saved preference `truck.court_min_m`. Range: at least 10, at most 80. |
| `entrance_min_m` | number (m) |  | `12.4` | Entrance width for a WB-67 to turn in without curb returns. Saved preference `truck.entrance_min_m`. Range: at least 3, at most 30. |
| `use_vision` | boolean |  | `true` | Ask the vision model about the gate and, where Vexcel finds no dock doors, the walls (cached). |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Aerial photo | `vexcel.ortho` | required | The verdict is `unknown`, with the reason. |
| Roof heights | `vexcel.dsm` | required | The verdict is `unknown`, with the reason. |
| Angled aerial photos | `vexcel.oblique` | required | The verdict is `unknown`, with the reason. |
| Street map | `osm.streets` | optional | The tool runs without it. |
| Property record | `costar.property` | optional | The tool runs without it. |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Draws on the building: a route with its narrow points; pins on what it found.
- Panel blocks: `VerdictHeader`, `MetricRow`, `CheckList`, `EvidenceStrip`, `Note`, `AssumptionChips`, `StepLog`.
- Speed: slow. Read-only.

## How it works

Truck access: can a 53 ft trailer reach and back to this building's docks? The approach street and driveway, gate or no gate, entrance width and truck court depth measured on the orthophoto and the surface model, room to turn a WB-67, trailer parking, overhead obstructions, arrival directions and a route on the aerial photo.

## Reliability

Every metric and finding carries its layer, its method and a high, medium or low label, set by the tool for each value. See [findings and reliability](/docs/concepts/findings-and-reliability/).

## Limits

- Needs: aerial photo, roof heights, angled aerial photos. On a scan without them, the verdict is `unknown` and says why.
- It is slow: progress steps reach the workspace while it runs.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

<p class="verdict"><span class="st unknown">Cannot answer here</span> Scan u_testhome0001 has no location (a phone scan carries none), so the aerial photo cannot be found. Give a latitude and longitude to run this on the site.</p>

A phone scan has walls, doors, windows, rooms and objects, but no location, no photos and no property record.

## Run it

```sh
threshold run truck_access --scan <scan-id>
curl -X POST http://127.0.0.1:8787/api/tools/truck_access/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `truck_access`. See [MCP server and CLI](/docs/mcp/).
