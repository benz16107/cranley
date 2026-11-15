---
title: "Wildfire defensible space"
description: "Vegetation and tree canopy in California's 5, 30 and 100 ft zones round the house, what to clear first, roof material, slope, the nearest fire station and the CAL FIRE hazard zone."
sidebar: {"label": "Wildfire defensible space"}
---

Vegetation and tree canopy in California's 5, 30 and 100 ft zones round the house, what to clear first, roof material, slope, the nearest fire station and the CAL FIRE hazard zone.

## What it answers

- Is my defensible space good enough?
- What should I clear first before fire season?

For the agent, the tool is described as: Defensible space for a house at a scan or a point: tree canopy (surface minus ground above 2 m, green in the orthophoto) and low vegetation in California's Zone 0 (0-5 ft), Zone 1 (5-30 ft) and Zone 2 (30-100 ft), each with a verdict and the side with the most canopy; roof material from Vexcel; ground slope; nearest fire station from OpenStreetMap; and whether the point is in a CAL FIRE Fire Hazard Severity Zone. Draws the zone edges on the map and round the building in 3D. Houston houses get the same rings with a note that the zones are California's.

## Who it is for

[Insurance underwriter](/docs/reference/personas/#insurance-underwriter), [LA homeowner after the fires](/docs/reference/personas/#la-homeowner-after-the-fires).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `scan` | string |  |  | Scan id, if the site has one. Filled from the selected building. |
| `property_id` | integer |  |  | CoStar PropertyId, for a commercial address. |
| `lat` | number |  |  | Latitude, for an address with no scan. |
| `lon` | number |  |  | Longitude, for an address with no scan. |
| `station_radius_km` | number (km) |  | `8` | How far to look for a fire station. Saved preference `wildfire.station_radius_km`. Range: more than 0, at most 20. |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Aerial photo | `vexcel.ortho` | required | The verdict is `unknown`, with the reason. |
| Roof heights | `vexcel.dsm` | required | The verdict is `unknown`, with the reason. |
| Aerial property facts | `vexcel.property` | required | The verdict is `unknown`, with the reason. |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Draws on the building: a route with its narrow points; pins on what it found.
- Panel blocks: `VerdictHeader`, `MetricRow`, `MiniChart`, `CheckList`, `EvidenceStrip`, `AssumptionChips`, `StepLog`.
- Speed: fast. Read-only.

## How it works

Wildfire defensible space: vegetation and tree canopy in California's three zones round a house (0 to 5 ft, 5 to 30 ft, 30 to 100 ft), with a verdict per zone and what to clear first; roof material, slope, the nearest fire station and the CAL FIRE Fire Hazard Severity Zone. Houston houses get the same rings, with a note that the zones are California's.

## Reliability

Every metric and finding carries its layer, its method and a high, medium or low label, set by the tool for each value. See [findings and reliability](/docs/concepts/findings-and-reliability/).

## Limits

- Needs: aerial photo, roof heights, aerial property facts. On a scan without them, the verdict is `unknown` and says why.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

<p class="verdict"><span class="st unknown">Cannot answer here</span> Scan u_testhome0001 has no location (a phone scan carries none), so the aerial photo cannot be found. Give a latitude and longitude to run this on the site.</p>

A phone scan has walls, doors, windows, rooms and objects, but no location, no photos and no property record.

## Run it

```sh
threshold run wildfire_space --scan <scan-id>
curl -X POST http://127.0.0.1:8787/api/tools/wildfire_space/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `wildfire_space`. See [MCP server and CLI](/docs/mcp/).
