---
title: "Unit compare"
description: "Ranks several units or suites side by side on measured area, rooms, storage, windows and door widths, with rent per measured square foot."
sidebar: {"label": "Unit compare"}
---

Ranks several units or suites side by side on measured area, rooms, storage, windows and door widths, with rent per measured square foot.

## What it answers

- Compare the units in this building
- Which floor plan gives the most space for the rent?

For the agent, the tool is described as: Compare apartment units (or office suites) on measured facts: floor area, layout, area per room type, storage, windows, narrowest doorway, listed against measured size, and the listing's rent per measured ft². Give `scans`, a `property` id, or one selected unit (it is compared with the other units of its property). Ranked by rent per measured ft², else by area.

## Who it is for

[Amenity auditor](/docs/reference/personas/#amenity-auditor), [Apartment manager](/docs/reference/personas/#apartment-manager), [CoStar researcher](/docs/reference/personas/#costar-researcher), [Office tenant](/docs/reference/personas/#office-tenant), [Renter checking a listing](/docs/reference/personas/#renter-checking-a-listing).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `scans` | array |  | `[]` | Scan ids of the units or suites to compare. |
| `property` | integer |  |  | CoStar property id: compare all its unit scans. |
| `scan` | string |  |  | One unit: compare it with the other units of its property. Filled from the selected building. |
| `max_units` | integer |  | `12` | At most this many units. Range: at least 2, at most 40. |
| `label_with_vision` | boolean |  | `false` | Label unlabelled rooms from the panoramas first (slow once). |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Rooms | `matterport.rooms` | required | The verdict is `unknown`, with the reason. |
| Property record | `costar.property` | optional | no rent |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Panel blocks: `VerdictHeader`, `MetricRow`, `RankedTable`, `MiniChart`, `CheckList`, `EvidenceStrip`, `StepLog`.
- Speed: fast. Read-only.

## How it works

Unit compare: several apartment units (or suites) of one property side by side on measured facts, with the listing's rent per measured square foot where the record has a rent.

## Reliability

Every metric and finding carries its layer, its method and a high, medium or low label, set by the tool for each value. See [findings and reliability](/docs/concepts/findings-and-reliability/).

## Limits

- Needs: rooms. On a scan without it, the verdict is `unknown` and says why.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

<p class="verdict"><span class="st unknown">Cannot answer here</span> This scan does not belong to a property in the kit, so there are no sibling units to compare. Give two or more scans, or a CoStar property id.</p>

A phone scan has walls, doors, windows, rooms and objects, but no location, no photos and no property record.

## Run it

```sh
threshold run unit_compare --scan <scan-id>
curl -X POST http://127.0.0.1:8787/api/tools/unit_compare/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `unit_compare`. See [MCP server and CLI](/docs/mcp/).
