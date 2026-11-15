---
title: "Solar roof"
description: "Usable roof for solar after setbacks and shade, how many panels, kW, kWh a year and payback."
sidebar: {"label": "Solar roof"}
---

Usable roof for solar after setbacks and shade, how many panels, kW, kWh a year and payback.

## What it answers

- Is my roof good for solar?
- How many panels fit and what would they save?

For the agent, the tool is described as: Rooftop solar for a house at a scan or a point in Houston or Los Angeles: roof facets with area, pitch and facing from Vexcel's surface model, shading by trees and neighbours over a clear-sky year, usable area after 36 in fire-code setbacks and ridges, then panels, kW, annual kWh (PVWatts yield, labelled) and simple payback at a labelled electricity price. Draws the usable patches on the map.

## Who it is for

[Houston homeowner before a storm](/docs/reference/personas/#houston-homeowner-before-a-storm), [Homeowner considering solar](/docs/reference/personas/#homeowner-considering-solar).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `scan` | string |  |  | Scan id, if the site has one. Filled from the selected building. |
| `property_id` | integer |  |  | CoStar PropertyId, for a commercial address. |
| `lat` | number |  |  | Latitude, for an address with no scan. |
| `lon` | number |  |  | Longitude, for an address with no scan. |
| `cost_per_w` | number ($/W) |  | `2.75` | Installed cost per watt before incentives. Saved preference `solar.cost_per_w`. Range: more than 0, at most 10. |
| `price_per_kwh` | number ($/kWh) |  |  | What a kWh from the grid costs you; the state average if empty. Saved preference `solar.price_per_kwh`. |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Aerial property facts | `vexcel.property` | required | The verdict is `unknown`, with the reason. |
| Roof heights | `vexcel.dsm` | required | The verdict is `unknown`, with the reason. |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Draws on the building: pins on what it found; a route with its narrow points.
- Panel blocks: `VerdictHeader`, `MetricRow`, `MiniChart`, `CheckList`, `AssumptionChips`, `StepLog`.
- Speed: fast. Read-only.

## How it works

Solar roof: how much of a roof can carry panels, how much sun it gets after trees and neighbours, and what a system would make and save, for any house in Houston or Los Angeles.

## Reliability

Every metric and finding carries its layer, its method and a high, medium or low label, set by the tool for each value. See [findings and reliability](/docs/concepts/findings-and-reliability/).

## Limits

- Needs: aerial property facts, roof heights. On a scan without them, the verdict is `unknown` and says why.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

<p class="verdict"><span class="st unknown">Cannot answer here</span> Scan u_testhome0001 has no location (a phone scan carries none), so the aerial photo cannot be found. Give a latitude and longitude to run this on the site.</p>

A phone scan has walls, doors, windows, rooms and objects, but no location, no photos and no property record.

## Run it

```sh
threshold run solar_roof --scan <scan-id>
curl -X POST http://127.0.0.1:8787/api/tools/solar_roof/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `solar_roof`. See [MCP server and CLI](/docs/mcp/).
