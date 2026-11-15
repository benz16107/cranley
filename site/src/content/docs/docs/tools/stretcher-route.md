---
title: "Stretcher route"
description: "Checks whether a flat ambulance stretcher can be carried from the entrance to each bedroom, and where it would have to be tilted."
sidebar: {"label": "Stretcher route"}
---

Checks whether a flat ambulance stretcher can be carried from the entrance to each bedroom, and where it would have to be tilted.

## What it answers

- Could paramedics get a stretcher to the bedroom?

For the agent, the tool is described as: Carry a flat ambulance stretcher (IBC 3002.4 size, 24 x 84 in, editable) from the main entrance to each bedroom (or named rooms) in one scan: the route, each door and turn with its margin, and a box at the tightest point per room.

## Who it is for

[Planning for an older parent](/docs/reference/personas/#planning-for-an-older-parent), [Fire captain](/docs/reference/personas/#fire-captain), [Older adult or family](/docs/reference/personas/#older-adult-or-family).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `scan` | string | yes |  | Scan id. Filled from the selected building. |
| `length_m` | number (m) |  | `2.134` | Stretcher length. Saved preference `stretcher.length_m`. Range: more than 1, at most 3. |
| `width_m` | number (m) |  | `0.61` | Stretcher width. Saved preference `stretcher.width_m`. Range: more than 0.3, at most 1.2. |
| `height_m` | number (m) |  | `0.5` | Height with the patient on it, lowered. Saved preference `stretcher.height_m`. Range: more than 0.1, at most 1.5. |
| `rooms` | array |  | `["Bedroom"]` | Room types or ids to reach. |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Wall outline | `matterport.walls` | required | The verdict is `unknown`, with the reason. |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Draws on the building: a route with its narrow points; a box or 3D model placed in the room.
- Panel blocks: `VerdictHeader`, `MetricRow`, `CheckList`, `FloorPlanMini`, `AssumptionChips`, `StepLog`.
- Speed: fast. Read-only.

## How it works

Stretcher route: can paramedics carry a flat stretcher from the entrance to each bedroom? The furniture_fit engine with the IBC 3002.4 stretcher, kept flat.

## Reliability

Sources this tool gave on the test home:

| Where it came from | Layer | Method | Reliability | Note |
|---|---|---|---|---|
| Measured from the scan | `matterport` | `geometry` | medium | Matterport wall graph, empty rooms; door widths are the opening in the wall |
| Measured from the scan | `matterport` | `geometry` | medium | Right-angle corner formula on empty-room widths |

The tool sets the label for each value. A model never does.

## Limits

- Needs: wall outline. On a scan without it, the verdict is `unknown` and says why.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

<p class="verdict"><span class="st warn">Warn</span> Some routes are too close to call or not in the scan; measure on site.</p>

| Value | Result | Where it came from | Reliability |
|---|---|---|---|
| Rooms reached flat | <span class="num">1</span> | Measured from the scan | medium |
| Rooms checked | <span class="num">2</span> | Measured from the scan | medium |
| Least room to spare | <span class="num">-0.02 m</span> | Measured from the scan | medium |

| Check | Measured | Against | Status |
|---|---|---|---|
| To Bedroom 1, entrance door: margin | <span class="num">0.25</span> | <span class="num">0 m</span> | <span class="st pass">pass</span> |
| To Bedroom 1, doorway 1: margin | <span class="num">0.2</span> | <span class="num">0 m</span> | <span class="st pass">pass</span> |
| To Bedroom 1, doorway 2: margin | <span class="num">0.1</span> | <span class="num">0 m</span> | <span class="st pass">pass</span> |
| To Bedroom 1, turn 1 (37 degrees): margin | <span class="num">0.352</span> | <span class="num">0 m</span> | <span class="st pass">pass</span> |
| To Bedroom 2, entrance door: margin | <span class="num">0.25</span> | <span class="num">0 m</span> | <span class="st pass">pass</span> |
| To Bedroom 2, doorway 1: margin | <span class="num">0.15</span> | <span class="num">0 m</span> | <span class="st pass">pass</span> |
| To Bedroom 2, turn 1 (77 degrees): margin | <span class="num">-0.024</span> | <span class="num">0 m</span> | <span class="st warn">warn</span> |

Findings: 1 warn.

What it reported while it ran:

1. Carried a 2.13 x 0.61 m flat stretcher to 2 rooms

## Run it

```sh
threshold run stretcher_route --scan <scan-id>
curl -X POST http://127.0.0.1:8787/api/tools/stretcher_route/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `stretcher_route`. See [MCP server and CLI](/docs/mcp/).
