---
title: "Turning space"
description: "Finds the largest clear circle in each room and checks it against the turning circle you need."
sidebar: {"label": "Turning space"}
---

Finds the largest clear circle in each room and checks it against the turning circle you need.

## What it answers

- Can I turn my wheelchair around in the bathroom?

For the agent, the tool is described as: Largest turning circle that fits in each room of one scan (empty room, wall face to wall face) against a diameter, default the ADA 60 in (1.525 m). Returns a lens of diameters, a check per room and pins at each circle's centre.

## Who it is for

[Home robot maker](/docs/reference/personas/#home-robot-maker), [Wheelchair user looking for a home](/docs/reference/personas/#wheelchair-user-looking-for-a-home), [Wheelchair user](/docs/reference/personas/#wheelchair-user).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `scan` | string | yes |  | Scan id. Filled from the selected building. |
| `diameter_m` | number (m) |  | `1.525` | Turning circle you need. Saved preference `access.turning_diameter_m`. Range: more than 0.3, at most 3.0. |
| `rooms` | array |  |  | Room types or ids to check; default every room but closets. |
| `aisle_width_m` | number (m) |  | `0.915` | Clear aisle width you need between objects on the floor. Saved preference `access.route_width_m`. Range: more than 0.3, at most 3.0. |
| `chairs` | array |  | `[]` | Each chair the person uses; each is checked with its own turning circle. Saved preference `access.chairs`. |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Rooms | `matterport.rooms` | required | The verdict is `unknown`, with the reason. |
| Wall outline | `matterport.walls` | required | The verdict is `unknown`, with the reason. |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Draws on the building: a colour per room; pins on what it found.
- Panel blocks: `VerdictHeader`, `MetricRow`, `CheckList`, `FloorPlanMini`, `Controls`, `AssumptionChips`, `StepLog`.
- Speed: fast. Read-only.

## How it works

Turning space: the largest circle in each room, against the 60 in (1525 mm) wheelchair turning circle.

## Reliability

Sources this tool gave on the test home:

| Where it came from | Layer | Method | Reliability | Note |
|---|---|---|---|---|
| Measured from the scan | `matterport` | `geometry` | medium | Matterport wall graph, empty rooms; door widths are the opening in the wall |

The tool sets the label for each value. A model never does. The tools give a scan's wall graph the layer `matterport` whichever device made the scan, so a phone scan's geometry carries that label too.

## Limits

- Needs: rooms, wall outline. On a scan without them, the verdict is `unknown` and says why.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

<p class="verdict"><span class="st fail">Fail</span> 3 of 6 rooms cannot hold the turning circle with the scanned objects on the floor.</p>

| Value | Result | Where it came from | Reliability |
|---|---|---|---|
| Rooms that hold the circle | <span class="num">3</span> | Measured from the scan | medium |
| Best bathroom circle | <span class="num">0.97 m</span> | Measured from the scan | medium |
| Kitchen circle | <span class="num">2.42 m</span> | Measured from the scan | medium |
| Largest circle | <span class="num">3.14 m</span> | Measured from the scan | medium |
| Living Room | <span class="num">3.14 m</span> | Measured from the scan | medium |
| Bedroom | <span class="num">1.61 m</span> | Measured from the scan | medium |
| Bedroom | <span class="num">1.33 m</span> | Measured from the scan | medium |
| Kitchen | <span class="num">2.42 m</span> | Measured from the scan | medium |
| Bathroom | <span class="num">0.97 m</span> | Measured from the scan | medium |
| Hallway | <span class="num">1.07 m</span> | Measured from the scan | medium |

| Check | Measured | Against | Status |
|---|---|---|---|
| Turning circle, Bathroom, objects on the floor counted (1.68 m empty) | <span class="num">0.967</span> | <span class="num">1.525 m</span> | <span class="st fail">fail</span> |
| Aisle from the doorway to the turning spot, Bathroom, objects on the floor: bathtub, sink, toilet | <span class="num">0.966</span> | <span class="num">0.915 m</span> | <span class="st pass">pass</span> |
| Turning circle, Hallway | <span class="num">1.072</span> | <span class="num">1.525 m</span> | <span class="st fail">fail</span> |
| Turning circle, Bedroom, objects on the floor counted (3.86 m empty) | <span class="num">1.33</span> | <span class="num">1.525 m</span> | <span class="st fail">fail</span> |
| Aisle from the doorway to the turning spot, Bedroom, objects on the floor: bed, storage | <span class="num">1.33</span> | <span class="num">0.915 m</span> | <span class="st pass">pass</span> |
| Turning circle, Bedroom, objects on the floor counted (3.87 m empty) | <span class="num">1.608</span> | <span class="num">1.525 m</span> | <span class="st pass">pass</span> |
| Aisle from the doorway to the turning spot, Bedroom, objects on the floor: bed | <span class="num">1.453</span> | <span class="num">0.915 m</span> | <span class="st pass">pass</span> |
| Turning circle, Kitchen, objects on the floor counted (2.88 m empty) | <span class="num">2.418</span> | <span class="num">1.525 m</span> | <span class="st pass">pass</span> |

4 more checks are in the full result.

Findings: 3 fail.

What it reported while it ran:

1. Fitted the largest circle in 6 rooms

## Run it

```sh
threshold run turning_space --scan <scan-id>
curl -X POST http://127.0.0.1:8787/api/tools/turning_space/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `turning_space`. See [MCP server and CLI](/docs/mcp/).
