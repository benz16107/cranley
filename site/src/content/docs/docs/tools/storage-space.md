---
title: "Storage space"
description: "Totals closet and storage area and its share of the unit, and finds bedrooms without a closet room."
sidebar: {"label": "Storage space"}
---

Totals closet and storage area and its share of the unit, and finds bedrooms without a closet room.

## What it answers

- How much closet space does this unit have?
- Which bedrooms have no closet?

For the agent, the tool is described as: Closet, pantry and storage-room area of one scan, its share of the floor area, each storage room on the plan, and bedrooms with no closet room through a door. Reach-in closets that the scan does not cut out as rooms are not counted.

## Who it is for

[Amenity auditor](/docs/reference/personas/#amenity-auditor), [Apartment manager](/docs/reference/personas/#apartment-manager), [Office tenant](/docs/reference/personas/#office-tenant), [Renter checking a listing](/docs/reference/personas/#renter-checking-a-listing).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `scan` | string | yes |  | Scan id. Filled from the selected building. |
| `label_with_vision` | boolean |  | `true` | Label unlabelled rooms from the panoramas first (slow once). |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Rooms | `matterport.rooms` | required | The verdict is `unknown`, with the reason. |
| Room names | `matterport.room_labels` | optional | room labeller |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Draws on the building: a colour per room; doors, walls or rooms coloured by status.
- Panel blocks: `VerdictHeader`, `MetricRow`, `CheckList`, `MiniChart`, `FloorPlanMini`, `StepLog`.
- Speed: fast. Read-only.

## How it works

Storage space: closet, pantry and storage-room area of a unit or suite, its share of the floor, and bedrooms with no closet room beside them.

## Reliability

Sources this tool gave on the test home:

| Where it came from | Layer | Method | Reliability | Note |
|---|---|---|---|---|
| Measured from the scan | `matterport` | `geometry` | high | Room floor areas from the scan |
| Looked up in the scan | `matterport` | `lookup` | medium | Room types: Matterport's, the labeller's or yours |

The tool sets the label for each value. A model never does. The tools give a scan's wall graph the layer `matterport` whichever device made the scan, so a phone scan's geometry carries that label too.

## Limits

- Needs: rooms. On a scan without it, the verdict is `unknown` and says why.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

<p class="verdict"><span class="st warn">Warn</span> 0 ft² of closets and storage in 0 rooms, 0.0% of 862 ft². 2 of 2 bedrooms have no mapped door to a closet room (the wall graph can miss a door, so check the panorama). Reach-in closets that the scan does not cut out as rooms are not counted.</p>

| Value | Result | Where it came from | Reliability |
|---|---|---|---|
| Storage area | <span class="num">0 ft²</span> | Measured from the scan | high |
| Share of the floor | <span class="num">0 %</span> | Measured from the scan | high |
| Closets and storage rooms | <span class="num">0</span> | Looked up in the scan | medium |
| Floor area | <span class="num">862 ft²</span> | Measured from the scan | high |

| Check | Measured | Against | Status |
|---|---|---|---|
| Bedrooms with a mapped door to a closet room (directly or through an en-suite bathroom) | <span class="num">0</span> | <span class="num">2 bedrooms</span> | <span class="st warn">warn</span> |

Findings: 2 warn.

What it reported while it ran:

1. Found 0 storage rooms among 6

## Run it

```sh
threshold run storage_space --scan <scan-id>
curl -X POST http://127.0.0.1:8787/api/tools/storage_space/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `storage_space`. See [MCP server and CLI](/docs/mcp/).
