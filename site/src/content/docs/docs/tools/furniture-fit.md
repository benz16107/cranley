---
title: "Furniture fit"
description: "Checks whether a sofa, bed, piano or fridge can be carried from the entrance to a room: each door and turn with its margin, and where it would stick."
sidebar: {"label": "Furniture fit"}
---

Checks whether a sofa, bed, piano or fridge can be carried from the entrance to a room: each door and turn with its margin, and where it would stick.

## What it answers

- Will my sofa fit into the living room?
- Can we get a piano in here?

For the agent, the tool is described as: Carry one named object (sofa, loveseat, king or queen mattress, upright piano, refrigerator, washer, wardrobe, dining table; sizes editable) from the main entrance to a room in one scan. Returns the route, a check per doorway and turn with its margin, a box overlay at the tightest point, and whether the object fits along a wall in the room.

## Who it is for

[Arranging a home by feng shui](/docs/reference/personas/#arranging-a-home-by-feng-shui), [Moving large furniture](/docs/reference/personas/#moving-large-furniture), [Agent or host staging a home virtually](/docs/reference/personas/#agent-or-host-staging-a-home-virtually).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `scan` | string | yes |  | Scan id. Filled from the selected building. |
| `object` | string |  | `"sofa"` | A named object; its size is an editable assumption. Asked as: "What are you moving?" Saved preference `furniture.object`. One of: `sofa`, `loveseat`, `king mattress`, `queen mattress`, `upright piano`, `refrigerator`, `washer`, `wardrobe`, `dining table`. |
| `room` | string |  |  | Room id or type to carry it to; default the usual room for it. |
| `length_m` | number (m) |  |  | Longest side, if not the preset's. Saved preference `furniture.length_m`. |
| `depth_m` | number (m) |  |  | Depth. Saved preference `furniture.depth_m`. |
| `height_m` | number (m) |  |  | Height. Saved preference `furniture.height_m`. |
| `entrance` | string |  |  | Opening id of the door to come in by; default the main entrance. |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Wall outline | `matterport.walls` | required | The verdict is `unknown`, with the reason. |
| Doors and windows | `matterport.openings` | required | The verdict is `unknown`, with the reason. |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Draws on the building: a route with its narrow points; a box or 3D model placed in the room.
- Panel blocks: `VerdictHeader`, `MetricRow`, `CheckList`, `FloorPlanMini`, `Controls`, `AssumptionChips`, `StepLog`, `ActionBar`.
- Speed: fast. Read-only.

## How it works

Furniture fit: carry a named object from the entrance to a room. The path, each doorway and turn with its margin, where it sticks (a Contract 4 box at the tightest point), and whether it fits along a wall once there. `carry_audit` is shared with stretcher_route.

## Reliability

Sources this tool gave on the test home:

| Where it came from | Layer | Method | Reliability | Note |
|---|---|---|---|---|
| Measured from the scan | `matterport` | `geometry` | medium | Matterport wall graph, empty rooms; door widths are the opening in the wall |

The tool sets the label for each value. A model never does.

## Limits

- Needs: wall outline, doors and windows. On a scan without them, the verdict is `unknown` and says why.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

<p class="verdict"><span class="st warn">Warn</span> Too close to call at the entrance door: measure before moving.</p>

| Value | Result | Where it came from | Reliability |
|---|---|---|---|
| Least room to spare | <span class="num">0 m</span> | Measured from the scan | medium |
| Doorways on the way | <span class="num">1</span> | Measured from the scan | medium |
| Turns on the way | <span class="num">0</span> | Measured from the scan | medium |
| Carry distance | <span class="num">2.7 m</span> | Measured from the scan | medium |

| Check | Measured | Against | Status |
|---|---|---|---|
| To Living Room, entrance door: margin | <span class="num">0</span> | <span class="num">0 m</span> | <span class="st warn">warn</span> |
| Free wall in the living room as long as the sofa | <span class="num">4.881</span> | <span class="num">2.13 m</span> | <span class="st pass">pass</span> |

Findings: 1 warn.

What it reported while it ran:

1. Carried a 2.13 x 0.97 x 0.86 m sofa toward the living room

## Run it

```sh
threshold run furniture_fit --scan <scan-id>
curl -X POST http://127.0.0.1:8787/api/tools/furniture_fit/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `furniture_fit`. See [MCP server and CLI](/docs/mcp/).
