---
title: "Takeoff bid"
description: "Quantities for a trade from the scan (floor by finish, paintable wall, glass, doors, fixtures), priced with your own rates: a cleaning bid, an apartment unit turn, or a fit-out estimate."
sidebar: {"label": "Takeoff bid"}
---

Quantities for a trade from the scan (floor by finish, paintable wall, glass, doors, fixtures), priced with your own rates: a cleaning bid, an apartment unit turn, or a fit-out estimate.

## What it answers

- What would it cost to clean this office three nights a week?
- Scope the turn for this unit
- Rough fit-out price for this suite

For the agent, the tool is described as: Measure trade quantities in one scan with geometry.takeoff plus floor finishes and restroom fixtures seen in the panoramas, then price them with editable rates. trade = cleaning (hours per visit and a monthly price), unit_turn (paint gallons, flooring, doors, blinds, fixtures) or fit_out (flooring, ceiling, paint, optional new offices). Quantities are measurements with sources; every price is an assumption.

## Who it is for

[Apartment manager](/docs/reference/personas/#apartment-manager), [Commercial cleaning bidder](/docs/reference/personas/#commercial-cleaning-bidder), [Facility manager](/docs/reference/personas/#facility-manager), [Office tenant](/docs/reference/personas/#office-tenant).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `scan` | string | yes |  | Scan id. Filled from the selected building. |
| `trade` | string | yes |  | Asked as: "Which bid: a cleaning bid, an apartment unit turn, or a fit-out estimate?" Saved preference `bid.trade`. One of: `cleaning`, `unit_turn`, `fit_out`. |
| `carpet_ft2_per_hour` | number (ft²/h) |  | `3500` | Carpet vacuuming rate. Saved preference `bid.clean.carpet_rate`. Range: more than 0. |
| `hard_ft2_per_hour` | number (ft²/h) |  | `2500` | Hard floor mopping rate. Saved preference `bid.clean.hard_rate`. Range: more than 0. |
| `fixture_minutes` | number (min) |  | `4` | Minutes per restroom fixture. Saved preference `bid.clean.fixture_min`. Range: at least 0. |
| `glass_ft2_per_hour` | number (ft²/h) |  | `600` | Glass cleaning rate. Saved preference `bid.clean.glass_rate`. Range: more than 0. |
| `glass_visits_per_month` | number |  | `1` | Window cleaning visits per month. Saved preference `bid.clean.glass_visits`. Range: at least 0. |
| `visits_per_week` | number |  | `3` | Cleaning visits per week. Saved preference `bid.clean.visits`. Range: at least 0, at most 7. |
| `wage` | number ($/h) |  | `22` | Loaded labour cost per hour. Saved preference `bid.wage`. Range: at least 0. |
| `markup` | number |  | `0.35` | Overhead and margin on labour. Saved preference `bid.markup`. Range: at least 0, at most 3. |
| `paint_per_ft2` | number ($/ft²) |  | `0.95` | Paint, two coats, labour and material, per wall ft². Saved preference `bid.turn.paint`. Range: at least 0. |
| `paint_ft2_per_gallon` | number (ft²/gal) |  | `350` | Coverage per gallon per coat. Saved preference `bid.turn.coverage`. Range: more than 0. |
| `carpet_per_yd2` | number ($/yd²) |  | `32` | Carpet replaced, installed. Saved preference `bid.turn.carpet`. Range: at least 0. |
| `replace_carpet` | boolean |  | `false` | Replace carpet (heavy turn) instead of cleaning it. Saved preference `bid.turn.replace_carpet`. |
| `carpet_clean_per_ft2` | number ($/ft²) |  | `0.3` | Carpet cleaning. Saved preference `bid.turn.carpet_clean`. Range: at least 0. |
| `hard_floor_per_ft2` | number ($/ft²) |  | `0.6` | Hard floor clean and touch-up. Saved preference `bid.turn.hard`. Range: at least 0. |
| `per_door` | number ($) |  | `30` | Door and hardware touch-up, each. Saved preference `bid.turn.door`. Range: at least 0. |
| `per_window` | number ($) |  | `35` | Blind replaced, each window. Saved preference `bid.turn.blind`. Range: at least 0. |
| `per_fixture` | number ($) |  | `25` | Fixture service, each. Saved preference `bid.turn.fixture`. Range: at least 0. |
| `flooring_per_ft2` | number ($/ft²) |  | `4.5` | New carpet tile or LVT, installed. Saved preference `bid.fit.floor`. Range: at least 0. |
| `ceiling_per_ft2` | number ($/ft²) |  | `3.0` | Ceiling tile replaced. Saved preference `bid.fit.ceiling`. Range: at least 0. |
| `partition_per_lf` | number ($/lf) |  | `95` | New partition, framed and finished. Saved preference `bid.fit.partition`. Range: at least 0. |
| `new_door` | number ($) |  | `1400` | New door, frame and hardware. Saved preference `bid.fit.door`. Range: at least 0. |
| `add_offices` | integer |  | `0` | Private offices to build in the open area. Saved preference `bid.fit.add_offices`. Range: at least 0, at most 50. |
| `contingency` | number |  | `0.15` | Contingency on the fit-out. Saved preference `bid.fit.contingency`. Range: at least 0, at most 1. |
| `label_with_vision` | boolean |  | `true` | Label rooms and read floor finishes from the panoramas first. |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Wall outline | `matterport.walls` | optional | floor area only |
| 360° photos | `matterport.panos` | required | The verdict is `unknown`, with the reason. |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Draws on the building: a colour per room; pins on what it found.
- Panel blocks: `VerdictHeader`, `MetricRow`, `MiniChart`, `FloorPlanMini`, `AssumptionChips`, `Controls`, `EvidenceStrip`, `StepLog`.
- Speed: slow. Read-only.

## How it works

Takeoff bid: trade quantities from one engine (geometry.takeoff, plus floor finishes and fixtures seen in the panoramas), priced with rates that are the bidder's own editable assumptions. Three price books: a cleaning bid, an apartment unit turn, and a fit-out refresh.

## Reliability

Sources this tool gave on the test cafe:

| Where it came from | Layer | Method | Reliability | Note |
|---|---|---|---|---|
| Measured from the scan | `matterport` | `geometry` | high | geometry.takeoff on the wall graph |
| Simulated | `model` | `simulation` | low | Your rates times measured quantities; rates are assumptions |
| Seen in a model | `model` | `vision` | medium | Fixtures counted in the room's central panorama |

The tool sets the label for each value. A model never does. The tools give a scan's wall graph the layer `matterport` whichever device made the scan, so a phone scan's geometry carries that label too.

## Limits

- Needs: 360° photos. On a scan without it, the verdict is `unknown` and says why.
- It is slow: progress steps reach the workspace while it runs.
- A result is a planning aid, not an inspection.

## On the made-up test cafe

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

Inputs used: `trade = "cleaning"` (preset of the persona "Commercial cleaning bidder"); `visits_per_week = 3` (preset of the persona "Commercial cleaning bidder").

<p class="verdict"><span class="st pass">Pass</span> About 0.4 labour hours per visit and $144 a month at 3 visits a week, for 905 ft² (0 carpet, 0 hard floor, 905 finish not read) and 0 restroom fixtures. Quantities are measured; every price is your assumption. Not measured: interior glass and partitions.</p>

| Value | Result | Where it came from | Reliability |
|---|---|---|---|
| Cleanable floor | <span class="num">905 ft²</span> | Measured from the scan | high |
| Labour hours per visit | <span class="num">0.36 h</span> | Simulated | low |
| Monthly price | <span class="num">144 $</span> | Simulated | low |
| Restroom fixtures | <span class="num">0</span> | Seen in a model | medium |
| Exterior glass (one side) | <span class="num">87 ft²</span> | Measured from the scan | high |
| Floor: not read | <span class="num">905 ft²</span> | Measured from the scan | high |

What it reported while it ran:

1. Measured 4 rooms: 905 ft² of floor
1. Read floor finishes for 0 rooms
1. Counted fixtures in 0 of 1 restrooms or bathrooms

## Run it

```sh
threshold run takeoff_bid --scan <scan-id>
curl -X POST http://127.0.0.1:8787/api/tools/takeoff_bid/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `takeoff_bid`. See [MCP server and CLI](/docs/mcp/).
