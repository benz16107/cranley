---
title: "Storm plan"
description: "An ordered plan for the hours before the storm: what to carry up first, where it goes, plywood cut from your real window sizes, sandbags per door, which shutoffs to turn off, and where a generator can safely stand. It changes when the storm or the household changes."
sidebar: {"label": "Storm plan"}
---

An ordered plan for the hours before the storm: what to carry up first, where it goes, plywood cut from your real window sizes, sandbags per door, which shutoffs to turn off, and where a generator can safely stand. It changes when the storm or the household changes.

## What it answers

- The storm is 72 hours out and there are two of us. What do we do first?
- We only have 6 hours now. What changes?

For the agent, the tool is described as: Plan the hours before a flood for one scanned house. Inputs: hours left, able adults, upper floor or attic, the flood scenario. Ranks and schedules work into the crew-minutes available (carry belongings by value per minute and loss certainty; plywood cut list from ScanPlan window sizes; sandbag lengths per exterior door; shutoffs; a generator spot 20 ft from the house on the aerial photo). Says what it dropped and why, and what changed since the last plan.

## Who it is for

[Emergency manager or caseworker before a storm](/docs/reference/personas/#emergency-manager-or-caseworker-before-a-storm), [Houston homeowner before a storm](/docs/reference/personas/#houston-homeowner-before-a-storm).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `scan` | string | yes |  | Scan id. Filled from the selected building. |
| `depth_m` | number (m) | yes |  | Water above the ground outside. Asked as: "How deep could the water get above the ground outside your house, in metres? Use a storm-surge forecast (given as height above ground) or a street-flooding depth." Saved preference `flood.depth_m`. Range: at least 0, at most 3. |
| `scenario` | string |  | `"depth"` | Where the depth comes from: typed depth, storm surge, rainfall, or Harvey 2017 from USGS high-water marks (then depth_m is not used). Saved preference `flood.scenario`. One of: `depth`, `surge`, `rainfall`, `harvey_2017`. |
| `floor_height_m` | number (m) |  |  | Floor height above the ground at the door, if you measured it. Saved preference `flood.floor_height_m`. |
| `use_drone` | boolean |  | `true` | Measure the door threshold in the drone photos (vision model, cached). |
| `hours_left` | number (h) | yes |  | Hours until the storm. Asked as: "How many hours until the storm reaches you?" Saved preference `storm.hours_left`. Range: more than 0, at most 168. |
| `adults` | integer | yes |  | Adults who can lift and carry. Asked as: "How many adults can lift and carry?" Saved preference `storm.adults`. Range: at least 1, at most 12. |
| `upper_floor` | string |  | `"auto"` | Is there an upper floor? auto reads the scan. Saved preference `storm.upper_floor`. One of: `auto`, `yes`, `no`. |
| `attic` | boolean |  | `false` | There is an attic you can reach and get out of. Saved preference `storm.attic`. |
| `board_windows` | boolean |  | `true` | Board the windows against wind. Saved preference `storm.board_windows`. |
| `max_rooms` | integer |  | `8` | Most rooms to read with the vision model. Range: at least 1, at most 12. |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Doors and windows | `matterport.openings` | required | The verdict is `unknown`, with the reason. |
| 360° photos | `matterport.panoramas` | required | The verdict is `unknown`, with the reason. |
| Building footprint | `vexcel.footprint` | optional | no generator spot |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Draws on the building: pins on what it found; doors, walls or rooms coloured by status; a water level.
- Panel blocks: `VerdictHeader`, `MetricRow`, `Controls`, `CheckList`, `FloorPlanMini`, `EvidenceStrip`, `AssumptionChips`, `StepLog`, `ActionBar`.
- Speed: slow. Read-only.

## How it works

Storm plan: an ordered plan for the hours before a flood, fitted to the people and time the household has.

## Reliability

Sources this tool gave on the test home:

| Where it came from | Layer | Method | Reliability | Note |
|---|---|---|---|---|
| Simulated | `model` | `simulation` | medium | Planner over the scan's geometry and the vision inventory; times are rules of thumb |
| Seen in a model | `model` | `vision` | low | Sum of cost-class maximums of the items carried |
| Seen in a model | `model` | `vision` | low | Cost-class minimums of carried items that are under water even at the low end |
| Measured from the scan | `matterport` | `geometry` | high | Window and door sizes from the wall graph |

The tool sets the label for each value. A model never does.

## Limits

- Needs: doors and windows, 360° photos. On a scan without them, the verdict is `unknown` and says why.
- It is slow: progress steps reach the workspace while it runs.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

Inputs used: `depth_m = 0.6` (an answer given for this example); `hours_left = 6` (an answer given for this example); `adults = 2` (an answer given for this example).

<p class="verdict"><span class="st warn">Warn</span> With 2 adults and 6 h: turn the power off last. Everything fits, with 5.8 crew-hours to spare.</p>

| Value | Result | Where it came from | Reliability |
|---|---|---|---|
| Crew-hours the whole list needs | <span class="num">0.2 h</span> | Simulated | medium |
| Crew-hours you have | <span class="num">6 h</span> | Simulated | medium |
| Belongings saved, up to | <span class="num">0 USD</span> | Seen in a model | low |
| Tasks left out | <span class="num">0</span> | Simulated | medium |
| Belongings saved, at least | <span class="num">0 USD</span> | Seen in a model | low |
| Plywood sheets (all windows) | <span class="num">7 sheets</span> | Measured from the scan | high |
| Window boards (all windows) | <span class="num">8</span> | Measured from the scan | high |
| Sandbags (doors that a dam can hold) | <span class="num">60</span> | Measured from the scan | high |
| Things carried | <span class="num">0</span> | Simulated | medium |

| Check | Measured | Against | Status |
|---|---|---|---|
| 1. Find and label the main breaker, the water main and the gas meter | <span class="num">10</span> |  | <span class="st pass">pass</span> |
| 2. Turn off the main breaker, standing on dry ground | <span class="num">5</span> |  | <span class="st pass">pass</span> |

Findings: 2 pass, 3 warn, 1 unknown.

What it reported while it ran:

1. The scan has no location, so the aerial and drone methods are off
1. Scan outdoor panoramas: none near an exterior door
1. Water levels in the scan: lo +0.10 m from the entry floor, mid +0.30 m from the entry floor, hi +0.50 m from the entry floor
1. 2 adults x 6 h x 50% working = 6.0 crew-hours; belongings go onto counters, beds and tables in the same room
1. Planned 2 tasks, dropped 0; 0.2 crew-hours used

## Run it

```sh
threshold run storm_plan --scan <scan-id>
curl -X POST http://127.0.0.1:8787/api/tools/storm_plan/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `storm_plan`. See [MCP server and CLI](/docs/mcp/).
