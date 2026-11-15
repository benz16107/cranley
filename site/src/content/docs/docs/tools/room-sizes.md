---
title: "Room sizes"
description: "Every room's floor area, width, depth and ceiling height, biggest first."
sidebar: {"label": "Room sizes"}
---

Every room's floor area, width, depth and ceiling height, biggest first.

## What it answers

- What's the biggest room, and how high is its ceiling?

For the agent, the tool is described as: Per-room floor area, width, depth and ceiling height of one scan, ranked by area, with the largest room and the highest ceiling. For location scouts, stagers, event planners and anyone choosing a room by size.

## Who it is for

[Arranging a home by feng shui](/docs/reference/personas/#arranging-a-home-by-feng-shui), [Film or photo location scout](/docs/reference/personas/#film-or-photo-location-scout), [Agent or host staging a home virtually](/docs/reference/personas/#agent-or-host-staging-a-home-virtually).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `scan` | string | yes |  | Scan id. Filled from the selected building. |
| `min_area_m2` | number (m²) |  | `0` | Flag rooms smaller than this (0: flag none). Saved preference `space.min_area_m2`. Range: at least 0. |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Rooms | `matterport.rooms` | required | The verdict is `unknown`, with the reason. |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Panel blocks: `VerdictHeader`, `MetricRow`, `RankedTable`, `CheckList`, `StepLog`.
- Its own ranked table: Area, m², Width, m, Depth, m, Ceiling, m.
- Speed: fast. Read-only.

## How it works

Room sizes: every room's floor area, width, depth and ceiling height, biggest first, for picking a room to use.

## Reliability

Sources this tool gave on the test home:

| Where it came from | Layer | Method | Reliability | Note |
|---|---|---|---|---|
| Measured from the scan | `matterport` | `geometry` | high | Room outlines in the wall graph |
| Measured from the scan | `matterport` | `geometry` | medium | Matterport room heights stop near the camera's reach, about 4 m |

The tool sets the label for each value. A model never does.

## Limits

- Needs: rooms. On a scan without it, the verdict is `unknown` and says why.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

<p class="verdict"><span class="st pass">Pass</span> 6 rooms measured; the largest is the Living Room.</p>

| Value | Result | Where it came from | Reliability |
|---|---|---|---|
| Largest room (Living Room) | <span class="num">30.1 m²</span> | Measured from the scan | high |
| Highest measured ceiling (Living Room) | <span class="num">2.44 m</span> | Measured from the scan | medium |
| Living Room | <span class="num">30.1 m²</span> | Measured from the scan | high |
| Living Room | <span class="num">6.01 m</span> | Measured from the scan | high |
| Living Room | <span class="num">5.04 m</span> | Measured from the scan | high |
| Living Room | <span class="num">2.44 m</span> | Measured from the scan | medium |
| Bedroom 1 | <span class="num">16.1 m²</span> | Measured from the scan | high |
| Bedroom 1 | <span class="num">4.03 m</span> | Measured from the scan | high |
| Bedroom 1 | <span class="num">4 m</span> | Measured from the scan | high |
| Bedroom 1 | <span class="num">2.44 m</span> | Measured from the scan | medium |

16 more values are in the full result.

| Check | Measured | Against | Status |
|---|---|---|---|
| Living Room: floor area | <span class="num">30.1</span> |  | <span class="st pass">pass</span> |
| Bedroom 1: floor area | <span class="num">16.1</span> |  | <span class="st pass">pass</span> |
| Bedroom 2: floor area | <span class="num">15.9</span> |  | <span class="st pass">pass</span> |
| Kitchen: floor area | <span class="num">10.5</span> |  | <span class="st pass">pass</span> |
| Bathroom: floor area | <span class="num">4.5</span> |  | <span class="st pass">pass</span> |
| Hallway: floor area | <span class="num">3</span> |  | <span class="st pass">pass</span> |

What it reported while it ran:

1. Measured 6 room outlines

## Run it

```sh
threshold run room_sizes --scan <scan-id>
curl -X POST http://127.0.0.1:8787/api/tools/room_sizes/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `room_sizes`. See [MCP server and CLI](/docs/mcp/).
