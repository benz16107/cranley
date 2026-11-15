---
title: "Daylight"
description: "Windows, glass area, the way each room faces and its hours of direct sun on a chosen day."
sidebar: {"label": "Daylight"}
---

Windows, glass area, the way each room faces and its hours of direct sun on a chosen day.

## What it answers

- Which bedroom gets morning sun?
- Is the living room bright in winter?

For the agent, the tool is described as: For one scan, per room: window count and glazed area from the wall graph, the compass direction of each window and the hours of direct sun on a date. Returns a lens of sun hours per room and findings for rooms with no window. Directions are low confidence until the scan's compass rotation is verified.

## Who it is for

[Light sleeper or night-shift worker](/docs/reference/personas/#light-sleeper-or-night-shift-worker), [Film or photo location scout](/docs/reference/personas/#film-or-photo-location-scout), [Office tenant](/docs/reference/personas/#office-tenant), [Older adult or family](/docs/reference/personas/#older-adult-or-family), [Remote worker](/docs/reference/personas/#remote-worker), [Renter checking a listing's claims](/docs/reference/personas/#renter-checking-a-listings-claims), [Renter checking a listing](/docs/reference/personas/#renter-checking-a-listing), [Plant lover or home office worker choosing a room](/docs/reference/personas/#plant-lover-or-home-office-worker-choosing-a-room), [Agent or host staging a home virtually](/docs/reference/personas/#agent-or-host-staging-a-home-virtually).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `scan` | string | yes |  | Scan id. Filled from the selected building. |
| `date` | string |  |  | Day to trace the sun on, YYYY-MM-DD; today if empty. Saved preference `daylight.date`. |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Doors and windows | `matterport.openings` | required | The verdict is `unknown`, with the reason. |
| Scan position | `matterport.geo` | optional | window counts and glass area only |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Draws on the building: a colour per room.
- Panel blocks: `VerdictHeader`, `MetricRow`, `MiniChart`, `CheckList`, `FloorPlanMini`, `Controls`, `AssumptionChips`, `StepLog`.
- Speed: fast. Read-only.

## How it works

Daylight: per room, how many windows, how much glass, which way they face and how long the sun reaches them.

## Reliability

Sources this tool gave on the test home:

| Where it came from | Layer | Method | Reliability | Note |
|---|---|---|---|---|
| Measured from the scan | `matterport` | `geometry` | high | Window widths and heights in the wall graph |

The tool sets the label for each value. A model never does.

## Limits

- Needs: doors and windows. On a scan without it, the verdict is `unknown` and says why.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

<p class="verdict"><span class="st pass">Pass</span> 5 windows over 5 rooms. This scan has no geocoordinates. Hours of sun cannot be traced.</p>

| Value | Result | Where it came from | Reliability |
|---|---|---|---|
| Windows | <span class="num">5</span> | Measured from the scan | high |
| Glass area | <span class="num">6.6 m²</span> | Measured from the scan | high |
| Glass to floor | <span class="num">8 %</span> | Measured from the scan | high |
| Rooms with no window | <span class="num">0</span> | Measured from the scan | high |

| Check | Measured | Against | Status |
|---|---|---|---|
| Direct sun, Bedroom | not measured |  | <span class="st pass">pass</span> |
| Direct sun, Bedroom | not measured |  | <span class="st pass">pass</span> |
| Direct sun, Living Room | not measured |  | <span class="st pass">pass</span> |
| Direct sun, Kitchen | not measured |  | <span class="st pass">pass</span> |
| Direct sun, Bathroom | not measured |  | <span class="st pass">pass</span> |
| Direct sun, Hallway | not measured |  | <span class="st unknown">unknown</span> |

What it reported while it ran:

1. Read windows in 5 rooms from the wall graph
1. No sun trace: This scan has no geocoordinates.

## Run it

```sh
threshold run daylight --scan <scan-id>
curl -X POST http://127.0.0.1:8787/api/tools/daylight/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `daylight`. See [MCP server and CLI](/docs/mcp/).
