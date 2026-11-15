---
title: "Industrial fit"
description: "Warehouse check: clear height, dock and drive-in doors, truck court and trailer parking, sprinklers, highway, rail, port and power nearby, and flood zone."
sidebar: {"label": "Industrial fit"}
---

Warehouse check: clear height, dock and drive-in doors, truck court and trailer parking, sprinklers, highway, rail, port and power nearby, and flood zone.

## What it answers

- Does this warehouse work for 53 ft trailers?
- Clear height, docks and power for this building

For the agent, the tool is described as: For a warehouse, distribution or flex building (scan, CoStar property or point): clear height from the record and the scan, truck doors on the scan's exterior walls and from the aerial (loading_docks), truck court depth for a 53 ft trailer and trailer parking (truck_access), sprinkler heads on ceiling photos (ESFR only when confidently seen), straight-line distance to highway on-ramps, rail, airports, ports and the nearest substation, and the FEMA flood zone.

## Who it is for

[Commercial property underwriter](/docs/reference/personas/#commercial-property-underwriter), [Industrial tenant rep](/docs/reference/personas/#industrial-tenant-rep), [Truck dispatcher](/docs/reference/personas/#truck-dispatcher).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `place` | Place | yes |  | The building: a scan, a CoStar property, an address or a point. Filled from the selected building. |
| `clear_min_ft` | number (ft) |  | `24` | Clear height needed. Saved preference `site.clear_height_min_ft`. Range: at least 8, at most 60. |
| `docks_min` | integer |  | `2` | Dock doors needed. Saved preference `site.docks_min`. Range: at least 0, at most 500. |
| `court_min_m` | number (m) |  | `39.6` | Truck court depth a 53 ft trailer needs (130 ft). Saved preference `truck.court_min_m`. Range: at least 10, at most 80. |
| `site_tools` | boolean |  | `true` | Run truck_access and loading_docks on the aerial (slow, cached). |
| `read_panoramas` | boolean |  | `true` | Ask the vision model about sprinkler heads on up to three ceiling photos. |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Property record | `costar.property` | optional | The tool runs without it. |
| Aerial photo | `vexcel.ortho` | optional | The tool runs without it. |
| Rooms | `matterport.rooms` | optional | The tool runs without it. |
| Osm | `osm` | optional | The tool runs without it. |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Panel blocks: `VerdictHeader`, `MetricRow`, `CheckList`, `EvidenceStrip`, `AssumptionChips`, `StepLog`.
- Speed: slow. Read-only.

## How it works

Industrial fit: one check of a warehouse or flex building for a distribution or production tenant.

## Reliability

Sources this tool gave on the test home:

| Where it came from | Layer | Method | Reliability | Note |
|---|---|---|---|---|
| Measured from the scan | `matterport` | `geometry` | high | Measured on the scan |

The tool sets the label for each value. A model never does.

## Limits

- It is slow: progress steps reach the workspace while it runs.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

Inputs used: `clear_min_ft = 28` (preset of the persona "Industrial tenant rep"); `docks_min = 4` (preset of the persona "Industrial tenant rep").

<p class="verdict"><span class="st fail">Fail</span> u_testhome0001: 8 ft clear (scan), 0 truck doors. Short of need: clear height; truck doors (most of record, aerial and scan).</p>

| Value | Result | Where it came from | Reliability |
|---|---|---|---|
| Largest room height on the scan | <span class="num">8 ft</span> | Measured from the scan | high |
| Truck-width doors on the scan | <span class="num">0</span> | Measured from the scan | high |

| Check | Measured | Against | Status |
|---|---|---|---|
| Clear height | <span class="num">8</span> | <span class="num">28 ft</span> | <span class="st fail">fail</span> |
| Truck doors (most of record, aerial and scan) | <span class="num">0</span> | <span class="num">4</span> | <span class="st fail">fail</span> |

Findings: 1 fail.

What it reported while it ran:

1. u_testhome0001: no commercial record

## Run it

```sh
threshold run industrial_fit -i place='{"scan": "<scan-id>"}'
curl -X POST http://127.0.0.1:8787/api/tools/industrial_fit/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `industrial_fit`. See [MCP server and CLI](/docs/mcp/).
