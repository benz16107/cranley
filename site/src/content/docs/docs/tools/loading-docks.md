---
title: "Loading docks"
description: "Counts dock doors and drive-in doors on each wall from the oblique aerial views and beside the CoStar record."
sidebar: {"label": "Loading docks"}
---

Counts dock doors and drive-in doors on each wall from the oblique aerial views and beside the CoStar record.

## What it answers

- How many dock doors does this warehouse have?
- Which side are the docks on?

For the agent, the tool is described as: For a warehouse, flex building or any commercial address: dock doors counted per wall on Vexcel oblique views, split into dock-high and drive-in by the vision model on the dock face, from inside when a scan exists, and compared with the CoStar record (numExternalLoadingDocks + numInternalLoadingDocks, driveInBays). Returns pins per door, the dock side, and checks.

## Who it is for

[Commercial property underwriter](/docs/reference/personas/#commercial-property-underwriter), [CoStar researcher](/docs/reference/personas/#costar-researcher), [Industrial tenant rep](/docs/reference/personas/#industrial-tenant-rep), [Truck dispatcher](/docs/reference/personas/#truck-dispatcher).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `scan` | string |  |  | Scan id, if the site has one. Filled from the selected building. |
| `property_id` | integer |  |  | CoStar PropertyId, for a commercial address. |
| `lat` | number |  |  | Latitude, for an address with no scan. |
| `lon` | number |  |  | Longitude, for an address with no scan. |
| `use_vision` | boolean |  | `true` | Ask the vision model to check the count on the dock face (cached). |
| `inside` | boolean |  | `true` | With a scan, also look for dock doors in its panoramas. |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Angled aerial photos | `vexcel.oblique` | required | The verdict is `unknown`, with the reason. |
| Property record | `costar.property` | optional | The tool runs without it. |
| 360° photos | `matterport.panos` | optional | The tool runs without it. |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Draws on the building: pins on what it found.
- Panel blocks: `VerdictHeader`, `MetricRow`, `CheckList`, `EvidenceStrip`, `StepLog`, `ActionBar`.
- Speed: slow. Read-only.

## How it works

Loading docks: dock doors and drive-in doors counted on the four oblique views (Vexcel detection, checked by the vision model on the dock face), from inside where a scan exists, and set beside the CoStar record's counts.

## Reliability

Every metric and finding carries its layer, its method and a high, medium or low label, set by the tool for each value. See [findings and reliability](/docs/concepts/findings-and-reliability/).

## Limits

- Needs: angled aerial photos. On a scan without it, the verdict is `unknown` and says why.
- It is slow: progress steps reach the workspace while it runs.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

<p class="verdict"><span class="st unknown">Cannot answer here</span> Scan u_testhome0001 has no location (a phone scan carries none), so the aerial photo cannot be found. Give a latitude and longitude to run this on the site.</p>

A phone scan has walls, doors, windows, rooms and objects, but no location, no photos and no property record.

## Run it

```sh
threshold run loading_docks --scan <scan-id>
curl -X POST http://127.0.0.1:8787/api/tools/loading_docks/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `loading_docks`. See [MCP server and CLI](/docs/mcp/).
