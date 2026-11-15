---
title: "Room census"
description: "Which rooms this space has, how big each kind is, and which rooms have no type."
sidebar: {"label": "Room census"}
---

Which rooms this space has, how big each kind is, and which rooms have no type.

## What it answers

- What rooms does this unit have?
- How big are the bedrooms?

For the agent, the tool is described as: Count rooms by type with floor areas for one scan, from the wall graph. Cheap; run it first on any building to learn its layout. Returns one metric per room type and an area lens.

## Who it is for

[Apartment manager](/docs/reference/personas/#apartment-manager), [Commercial cleaning bidder](/docs/reference/personas/#commercial-cleaning-bidder), [CoStar research lead](/docs/reference/personas/#costar-research-lead), [CoStar researcher](/docs/reference/personas/#costar-researcher), [Daycare operator](/docs/reference/personas/#daycare-operator), [Fire captain](/docs/reference/personas/#fire-captain), [Moving large furniture](/docs/reference/personas/#moving-large-furniture), [Family planning home security](/docs/reference/personas/#family-planning-home-security), [Houston homeowner before a storm](/docs/reference/personas/#houston-homeowner-before-a-storm), [Insurance underwriter](/docs/reference/personas/#insurance-underwriter), [Light sleeper or night-shift worker](/docs/reference/personas/#light-sleeper-or-night-shift-worker), [Office tenant](/docs/reference/personas/#office-tenant), [Older adult or family](/docs/reference/personas/#older-adult-or-family), [Remote worker](/docs/reference/personas/#remote-worker), [Renter checking a listing's claims](/docs/reference/personas/#renter-checking-a-listings-claims), [Renter checking a listing](/docs/reference/personas/#renter-checking-a-listing), [Wheelchair user](/docs/reference/personas/#wheelchair-user).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `scan` | string | yes |  | Scan id. Filled from the selected building. |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Rooms | `matterport.rooms` | required | The verdict is `unknown`, with the reason. |
| Room names | `matterport.room_labels` | optional | The tool runs without it. |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Draws on the building: a colour per room.
- Panel blocks: `VerdictHeader`, `MetricRow`, `MiniChart`, `FloorPlanMini`, `StepLog`.
- Speed: fast. Read-only.

## How it works

Rooms by type with their areas, and a lens that tints each room by area.

## Reliability

Sources this tool gave on the test home:

| Where it came from | Layer | Method | Reliability | Note |
|---|---|---|---|---|
| Measured from the scan | `matterport` | `geometry` | high | Matterport room floor area |
| Looked up in the scan | `matterport` | `lookup` | medium | Matterport room classification |

The tool sets the label for each value. A model never does.

## Limits

- Needs: rooms. On a scan without it, the verdict is `unknown` and says why.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

<p class="verdict"><span class="st pass">Pass</span> 6 rooms, 80 m²: Living Room, Bedroom, Kitchen, Bathroom, Hallway.</p>

| Value | Result | Where it came from | Reliability |
|---|---|---|---|
| Rooms | <span class="num">6</span> | Measured from the scan | high |
| Floor area | <span class="num">80.1 m²</span> | Measured from the scan | high |
| Rooms with a type | <span class="num">100 %</span> | Looked up in the scan | medium |
| Bedroom (2) | <span class="num">32 m²</span> | Measured from the scan | high |
| Living Room (1) | <span class="num">30.1 m²</span> | Measured from the scan | high |
| Kitchen (1) | <span class="num">10.5 m²</span> | Measured from the scan | high |
| Bathroom (1) | <span class="num">4.5 m²</span> | Measured from the scan | high |
| Hallway (1) | <span class="num">3 m²</span> | Measured from the scan | high |

| Check | Measured | Against | Status |
|---|---|---|---|
| At least half the rooms have a type | <span class="num">100</span> | <span class="num">50 %</span> | <span class="st pass">pass</span> |

What it reported while it ran:

1. Read 6 rooms from the wall graph
1. Grouped them into 5 types

## Run it

```sh
threshold run room_census --scan <scan-id>
curl -X POST http://127.0.0.1:8787/api/tools/room_census/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `room_census`. See [MCP server and CLI](/docs/mcp/).
