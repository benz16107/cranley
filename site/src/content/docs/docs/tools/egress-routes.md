---
title: "Egress routes"
description: "The way out of every room: how far, how narrow, which rooms have one way out, and the hose stretch."
sidebar: {"label": "Egress routes"}
---

The way out of every room: how far, how narrow, which rooms have one way out, and the hose stretch.

## What it answers

- How do people get out of each bedroom?
- How much hose do we need to reach the back bedroom?

For the agent, the tool is described as: For one scan: the walking route from every room to the nearest entrance (length, narrowest point, doors), rooms with a single way out, dead-end hallways, bedroom escape windows by sill height, and the hose stretch from each entrance to the farthest point. Returns route overlays and a travel-distance lens.

## Who it is for

[Apartment manager](/docs/reference/personas/#apartment-manager), [Community risk reduction officer](/docs/reference/personas/#community-risk-reduction-officer), [Facility manager](/docs/reference/personas/#facility-manager), [Fire captain](/docs/reference/personas/#fire-captain), [Fire training officer](/docs/reference/personas/#fire-training-officer), [Family planning home security](/docs/reference/personas/#family-planning-home-security), [Los Angeles household preparing for an earthquake](/docs/reference/personas/#los-angeles-household-preparing-for-an-earthquake), [Older adult or family](/docs/reference/personas/#older-adult-or-family).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `scan` | string | yes |  | Scan id. Filled from the selected building. |
| `min_width_m` | number (m) |  | `0.813` | Clear width an exit door needs: 32 in (0.813 m). Saved preference `access.door_width_m`. Range: more than 0.3, at most 3.0. |
| `long_route_m` | number (m) |  | `22.9` | Routes longer than this are flagged (75 ft, IBC 2021 Table 1006.2.1 common path of egress travel, Group R-2 without sprinklers). Saved preference `fire.long_route_m`. Range: more than 1. |
| `hose_m` | number (m) |  | `61.0` | Hose length to compare the stretch with (a 200 ft preconnect). Saved preference `fire.preconnect_m`. Range: more than 5. |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Doors and windows | `matterport.openings` | required | The verdict is `unknown`, with the reason. |
| Room names | `matterport.room_labels` | optional | The tool runs without it. |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Draws on the building: a route with its narrow points; a colour per room; doors, walls or rooms coloured by status; pins on what it found.
- Panel blocks: `VerdictHeader`, `MetricRow`, `CheckList`, `FloorPlanMini`, `AssumptionChips`, `StepLog`.
- Speed: fast. Read-only.

## How it works

Egress routes: from every room the route out, its length and narrowest point; rooms with one way out, dead ends, bedroom escape windows, and the hose stretch from each entrance to the farthest point.

## Reliability

Sources this tool gave on the test cafe:

| Where it came from | Layer | Method | Reliability | Note |
|---|---|---|---|---|
| Measured from the scan | `matterport` | `geometry` | medium | Shortest walkable route over the wall graph in empty rooms; furniture is not counted |

The tool sets the label for each value. A model never does.

## Limits

- Needs: doors and windows. On a scan without it, the verdict is `unknown` and says why.
- A result is a planning aid, not an inspection.

## On the made-up test cafe

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

<p class="verdict"><span class="st pass">Pass</span> Routed 4 rooms; the longest walk out is 8.7 m and the narrowest point 0.71 m. Hose stretch to the farthest point: 15 m.</p>

| Value | Result | Where it came from | Reliability |
|---|---|---|---|
| Longest walk out | <span class="num">8.7 m</span> | Measured from the scan | medium |
| Narrowest point | <span class="num">0.71 m</span> | Measured from the scan | medium |
| Rooms with one way out | <span class="num">2</span> | Measured from the scan | medium |
| Longest hose stretch | <span class="num">14.9 m</span> | Measured from the scan | medium |
| Entrances | <span class="num">2</span> | Measured from the scan | medium |
| Bathroom | <span class="num">8.7 m</span> | Measured from the scan | medium |
| Storage | <span class="num">4.2 m</span> | Measured from the scan | medium |
| Dining Room | <span class="num">4.1 m</span> | Measured from the scan | medium |
| Kitchen | <span class="num">2.3 m</span> | Measured from the scan | medium |

| Check | Measured | Against | Status |
|---|---|---|---|
| Distance to an entrance, Bathroom | <span class="num">8.7</span> | <span class="num">22.9 m</span> | <span class="st pass">pass</span> |
| Distance to an entrance, Storage | <span class="num">4.2</span> | <span class="num">22.9 m</span> | <span class="st pass">pass</span> |
| Distance to an entrance, Dining Room | <span class="num">4.1</span> | <span class="num">22.9 m</span> | <span class="st pass">pass</span> |
| Distance to an entrance, Kitchen | <span class="num">2.3</span> | <span class="num">22.9 m</span> | <span class="st pass">pass</span> |
| Widest doorway out, clear width | <span class="num">0.86</span> | <span class="num">0.813 m</span> | <span class="st pass">pass</span> |
| Doorways to outside or unscanned space on the entry floor | <span class="num">2</span> | <span class="num">2</span> | <span class="st pass">pass</span> |
| Longest hose stretch from an entrance | <span class="num">14.9</span> | <span class="num">61 m</span> | <span class="st pass">pass</span> |

Findings: 6 pass.

What it reported while it ran:

1. Found 2 doorways to outside or unscanned space and 3 connections between rooms
1. Routed 4 of 4 rooms to the nearest entrance

## Run it

```sh
threshold run egress_routes --scan <scan-id>
curl -X POST http://127.0.0.1:8787/api/tools/egress_routes/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `egress_routes`. See [MCP server and CLI](/docs/mcp/).
