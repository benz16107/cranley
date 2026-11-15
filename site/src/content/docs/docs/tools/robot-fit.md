---
title: "Robot fit"
description: "Shows which rooms a robot of a given width, turning circle and step height can reach and turn in, across one home or many, and which single change to the robot gains the most."
sidebar: {"label": "Robot fit"}
---

Shows which rooms a robot of a given width, turning circle and step height can reach and turn in, across one home or many, and which single change to the robot gains the most.

## What it answers

- What share of homes can a 50 cm robot reach every room of?
- Would a narrower robot or a better step climber help more?

For the agent, the tool is described as: For a wheeled body (width, turning diameter, climbable step), the share of rooms and of homes it can reach from the entrance and turn in, over one scan, a list, or every measured scan; and the gain from each single change (5 cm narrower, 1 or 2 cm more step, 10 cm tighter turn), best first.

## Who it is for

[Home robot maker](/docs/reference/personas/#home-robot-maker).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `scan` | string |  |  | One scan; leave out for many. Filled from the selected building. |
| `scans` | array |  |  | Scan ids to test; default every scan in the measures table that has a wall graph. |
| `body_width_m` | number (m) |  | `0.5` | Robot width. Saved preference `robot.body_width_m`. Range: more than 0.1, at most 1.5. |
| `turning_diameter_m` | number (m) |  | `0.7` | Turning circle the robot needs. Saved preference `robot.turning_diameter_m`. Range: more than 0.1, at most 3. |
| `step_height_m` | number (m) |  | `0.02` | Highest step the robot can climb. Saved preference `robot.step_height_m`. Range: at least 0, at most 0.3. |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Wall outline | `matterport.walls` | required | The verdict is `unknown`, with the reason. |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Draws on the building: a colour per room.
- Panel blocks: `VerdictHeader`, `MetricRow`, `CheckList`, `FloorPlanMini`, `Controls`, `AssumptionChips`, `StepLog`.
- Speed: slow. Read-only.

## How it works

Robot fit: which rooms a wheeled body (width, turning circle, climbable step) can reach and turn in, for one scan or many, and which single change to the body gains the most rooms. Reach and turning circles come from geometry.

## Reliability

Sources this tool gave on the test home:

| Where it came from | Layer | Method | Reliability | Note |
|---|---|---|---|---|
| Measured from the scan | `matterport` | `geometry` | medium | Reach from the entrance over the wall graph and the largest circle per room, 1 scans |

The tool sets the label for each value. A model never does. The tools give a scan's wall graph the layer `matterport` whichever device made the scan, so a phone scan's geometry carries that label too.

## Limits

- Needs: wall outline. On a scan without it, the verdict is `unknown` and says why.
- It is slow: progress steps reach the workspace while it runs.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

Inputs used: `body_width_m = 0.5` (preset of the persona "Home robot maker"); `turning_diameter_m = 0.7` (preset of the persona "Home robot maker"); `step_height_m = 0.02` (preset of the persona "Home robot maker").

<p class="verdict"><span class="st pass">Pass</span> The robot reaches and turns in 100% of rooms. No single change gains rooms.</p>

| Value | Result | Where it came from | Reliability |
|---|---|---|---|
| Rooms reached and turnable | <span class="num">100 %</span> | Measured from the scan | medium |
| Homes with every room usable | <span class="num">100 %</span> | Measured from the scan | medium |
| Best single change: turning circle 10 cm smaller | <span class="num">0 points</span> | Measured from the scan | medium |
| Scans measured | <span class="num">1</span> | Measured from the scan | medium |
| Turning circle 10 cm smaller | <span class="num">0 points</span> | Measured from the scan | medium |
| Climbs 2 cm higher | <span class="num">0 points</span> | Measured from the scan | medium |
| Climbs 1 cm higher | <span class="num">0 points</span> | Measured from the scan | medium |
| 5 cm narrower | <span class="num">0 points</span> | Measured from the scan | medium |

| Check | Measured | Against | Status |
|---|---|---|---|
| As given: share of rooms reached and turnable | <span class="num">100</span> |  | <span class="st pass">pass</span> |
| 5 cm narrower: share of rooms reached and turnable | <span class="num">100</span> |  | <span class="st pass">pass</span> |
| Climbs 1 cm higher: share of rooms reached and turnable | <span class="num">100</span> |  | <span class="st pass">pass</span> |
| Climbs 2 cm higher: share of rooms reached and turnable | <span class="num">100</span> |  | <span class="st pass">pass</span> |
| Turning circle 10 cm smaller: share of rooms reached and turnable | <span class="num">100</span> |  | <span class="st pass">pass</span> |

What it reported while it ran:

1. Tested 1 scans with a wall graph (0 could not be measured)

## Run it

```sh
threshold run robot_fit --scan <scan-id>
curl -X POST http://127.0.0.1:8787/api/tools/robot_fit/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `robot_fit`. See [MCP server and CLI](/docs/mcp/).
