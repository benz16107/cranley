---
title: "Room labeller"
description: "Names every room of a commercial space from its panoramas, shows what decided each call, and learns from your corrections."
sidebar: {"label": "Room labeller"}
---

Names every room of a commercial space from its panoramas, shows what decided each call, and learns from your corrections.

## What it answers

- What rooms does this office have?
- Label the rooms in this suite
- That room is a kitchen, not storage

For the agent, the tool is described as: Walk one scan's panoramas and label every room (open office, private office, conference room, restroom, gym, laundry, ...), with confidence, the panorama that shows it and the reason. Writes the labels so every other tool sees them. Pass `corrections` &#123;room id: label} when the person corrects a room; similar rooms here and in sibling scans are re-checked. Slow on first run (one model call per room), cached after.

## Who it is for

[Amenity auditor](/docs/reference/personas/#amenity-auditor), [Apartment manager](/docs/reference/personas/#apartment-manager), [Commercial cleaning bidder](/docs/reference/personas/#commercial-cleaning-bidder), [CoStar researcher](/docs/reference/personas/#costar-researcher), [Office tenant](/docs/reference/personas/#office-tenant).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `scan` | string | yes |  | Scan id. Filled from the selected building. |
| `corrections` | object |  | `{}` | Room id -> the label a person says is right. |
| `include_labelled` | boolean |  | `false` | Also read rooms Matterport already labelled (to compare). |
| `relabel` | boolean |  | `false` | Read rooms again even if the overlay already has a vision label. |
| `max_rooms` | integer |  | `60` | At most this many rooms are read by the model in one run. Range: at least 1, at most 200. |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| 360° photos | `matterport.panos` | required | The verdict is `unknown`, with the reason. |
| Rooms | `matterport.rooms` | required | The verdict is `unknown`, with the reason. |
| Property record | `costar.property` | optional | labels without the property type |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Draws on the building: pins on what it found; a colour per room.
- Panel blocks: `VerdictHeader`, `MetricRow`, `EvidenceStrip`, `FloorPlanMini`, `StepLog`.
- Speed: slow. **Writes** (a plan edit or a saved label), so over MCP it needs `--write`.

## How it works

Room labeller: an agent pass that walks a scan's panoramas and names every room, then writes the labels into the overlay (store.py) that every other tool's plan carries. A person's correction wins and teaches: rooms of the same scan, and similar rooms in sibling scans of the same property, that the correction makes doubtful are read again with the corrected room shown as a reference.

## Reliability

Sources this tool gave on the test home:

| Where it came from | Layer | Method | Reliability | Note |
|---|---|---|---|---|
| Measured from the scan | `matterport` | `geometry` | high | Rooms and areas from the scan |
| Seen in a model | `model` | `vision` | medium | Vision model on the room's panorama |

The tool sets the label for each value. A model never does.

## Limits

- Needs: 360° photos, rooms. On a scan without them, the verdict is `unknown` and says why.
- The agent asks before running it, because it reads every panorama with the vision model and writes new room labels into the plan.
- It is slow: progress steps reach the workspace while it runs.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

<p class="verdict"><span class="st pass">Pass</span> 6 of 6 rooms labelled: 2 Bedroom, 1 Living Room, 1 Kitchen, 1 Bathroom, 1 Hallway.</p>

| Value | Result | Where it came from | Reliability |
|---|---|---|---|
| Rooms | <span class="num">6</span> | Measured from the scan | high |
| Rooms with a label | <span class="num">6</span> | Seen in a model | medium |
| Vision labels at high confidence | <span class="num">not measured %</span> | Seen in a model | medium |
| Rooms read by the model this run | <span class="num">0</span> | Seen in a model | medium |
| Seconds this run | <span class="num">0 s</span> | Seen in a model | medium |
| Bedroom | <span class="num">2 rooms</span> | Seen in a model | medium |
| Living Room | <span class="num">1 rooms</span> | Seen in a model | medium |
| Kitchen | <span class="num">1 rooms</span> | Seen in a model | medium |
| Bathroom | <span class="num">1 rooms</span> | Seen in a model | medium |
| Hallway | <span class="num">1 rooms</span> | Seen in a model | medium |

| Check | Measured | Against | Status |
|---|---|---|---|
| Every room has a label | <span class="num">100</span> | <span class="num">100 %</span> | <span class="st pass">pass</span> |

Findings: 6 unknown.

## Run it

```sh
threshold run room_labeller --scan <scan-id>
curl -X POST http://127.0.0.1:8787/api/tools/room_labeller/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `room_labeller`. See [MCP server and CLI](/docs/mcp/).
