---
title: "Sun by room"
description: "Hours of direct sun in each room on a day and at the solstices and equinoxes, with neighbours and trees in the way, and the best room for plants, a home office and a cool bedroom."
sidebar: {"label": "Sun by room"}
---

Hours of direct sun in each room on a day and at the solstices and equinoxes, with neighbours and trees in the way, and the best room for plants, a home office and a cool bedroom.

## What it answers

- Which room is best for my plants?
- Where should my home office go to avoid glare?
- Which bedroom stays coolest in summer?

For the agent, the tool is described as: For one scan with windows and geocoordinates: per room, hours of direct sun through its windows on a date (default today) and on the two solstices and equinoxes, with obstruction by neighbouring buildings and trees from Vexcel's surface model along each window's sight line. Picks the best room for plants (most sun across the year), for a home office (daylight with the least direct sun in working hours, so the least glare) and for a bedroom that stays cool (least sunlit glass on summer afternoons). Lens of sun hours per room, pins on the windows.

## Who it is for

[Renter checking a listing](/docs/reference/personas/#renter-checking-a-listing), [Plant lover or home office worker choosing a room](/docs/reference/personas/#plant-lover-or-home-office-worker-choosing-a-room).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `scan` | string | yes |  | Scan id. Filled from the selected building. |
| `date` | string |  |  | Day to trace the sun on, YYYY-MM-DD; today if empty. The equinoxes and solstices of its year are always traced too. Saved preference `sun_rooms.date`. |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Doors and windows | `matterport.openings` | required | The verdict is `unknown`, with the reason. |
| Scan position | `matterport.geo` | required | The verdict is `unknown`, with the reason. |
| Roof heights | `vexcel.dsm` | optional | sun hours with nothing in the way |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Draws on the building: a colour per room; pins on what it found.
- Panel blocks: `VerdictHeader`, `MetricRow`, `MiniChart`, `RankedTable`, `CheckList`, `FloorPlanMini`, `Controls`, `AssumptionChips`, `StepLog`.
- Speed: fast. Read-only.

## How it works

Sun rooms: which rooms get direct sun, for how many hours, on a day and at the solstices and equinoxes, with neighbours and trees from Vexcel's surface model in the way; and the best room for plants, for a home office without glare and for a bedroom that stays cool.

## Reliability

Every metric and finding carries its layer, its method and a high, medium or low label, set by the tool for each value. See [findings and reliability](/docs/concepts/findings-and-reliability/).

## Limits

- Needs: doors and windows, scan position. On a scan without them, the verdict is `unknown` and says why.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

<p class="verdict"><span class="st unknown">Unknown</span> This scan has no geocoordinates, so its windows cannot be placed on a compass and the sun cannot be traced.</p>


## Run it

```sh
threshold run sun_rooms --scan <scan-id>
curl -X POST http://127.0.0.1:8787/api/tools/sun_rooms/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `sun_rooms`. See [MCP server and CLI](/docs/mcp/).
