---
title: "Bathroom clearance"
description: "Checks each bathroom for a wheelchair: door, turning space, floor space at the toilet and clear of the door, wall for grab bars, and whether the shower has a step."
sidebar: {"label": "Bathroom clearance"}
---

Checks each bathroom for a wheelchair: door, turning space, floor space at the toilet and clear of the door, wall for grab bars, and whether the shower has a step.

## What it answers

- Is the bathroom usable from a wheelchair?
- Is there room for grab bars by the toilet?

For the agent, the tool is described as: Wheelchair bathroom audit for one scan: per bathroom the door clear width, turning circle, the FHA 30 x 48 in space outside the door swing, the ADA 60 x 56 in and FHA clear floor space at the toilet (toilet located in the panorama), free wall for side and rear grab bars, and the tub or shower type and visible grab bars from the panorama.

## Who it is for

[Planning for an older parent](/docs/reference/personas/#planning-for-an-older-parent), [Facility manager](/docs/reference/personas/#facility-manager), [Older adult or family](/docs/reference/personas/#older-adult-or-family), [Wheelchair user looking for a home](/docs/reference/personas/#wheelchair-user-looking-for-a-home), [Wheelchair user](/docs/reference/personas/#wheelchair-user).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `scan` | string | yes |  | Scan id. Filled from the selected building. |
| `door_width_m` | number (m) |  | `0.815` | Clear width you need through the bathroom door. Saved preference `access.door_width_m`. Range: more than 0.3, at most 2.0. |
| `diameter_m` | number (m) |  | `1.525` | Turning circle you need. Saved preference `access.turning_diameter_m`. Range: more than 0.3, at most 3.0. |
| `read_panoramas` | boolean |  | `true` | Find the toilet, tub or shower and grab bars in the panoramas. |
| `chairs` | array |  | `[]` | Each chair the person uses; each is checked against the bathroom door and turning circle. Saved preference `access.chairs`. |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Wall outline | `matterport.walls` | required | The verdict is `unknown`, with the reason. |
| Room names | `matterport.room_labels` | required | The verdict is `unknown`, with the reason. |
| 360° photos | `matterport.panos` | optional | The tool runs without it. |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Draws on the building: pins on what it found; a box or 3D model placed in the room.
- Panel blocks: `VerdictHeader`, `MetricRow`, `CheckList`, `EvidenceStrip`, `FloorPlanMini`, `AssumptionChips`, `StepLog`.
- Speed: slow. Read-only.

## How it works

Bathroom clearance: turning circle, the door, clear floor space outside the door swing and at the toilet, wall space for grab bars, and the tub or shower type, against the ADA 2010 Standards and the FHA Design Manual.

## Reliability

Sources this tool gave on the test home:

| Where it came from | Layer | Method | Reliability | Note |
|---|---|---|---|---|
| Measured from the scan | `matterport` | `geometry` | medium | Matterport wall graph, empty rooms; door widths are the opening in the wall |
| Measured from the scan | `matterport` | `geometry` | low | Matterport wall graph; part of this answer rests on an assumption named in the result |
| Measured from the scan | `matterport` | `geometry` | medium | Object measured by the phone scan (Apple RoomPlan); its footprint blocks the floor |

The tool sets the label for each value. A model never does. The tools give a scan's wall graph the layer `matterport` whichever device made the scan, so a phone scan's geometry carries that label too.

## Limits

- Needs: wall outline, room names. On a scan without them, the verdict is `unknown` and says why.
- It is slow: progress steps reach the workspace while it runs.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

Inputs used: `door_width_m = 0.815` (preset of the persona "Planning for an older parent").

<p class="verdict"><span class="st fail">Fail</span> Every bathroom fails at least one check: 30 x 48 in clear floor space outside the door swing; 60 x 56 in clearance around the toilet; FHA clear floor space at the toilet; clear floor beside the toilet (side transfer), 48 in deep; clear floor.</p>

| Value | Result | Where it came from | Reliability |
|---|---|---|---|
| Bathrooms | <span class="num">1</span> | Measured from the scan | medium |
| Bathrooms that pass | <span class="num">0</span> | Measured from the scan | medium |
| Best turning circle | <span class="num">1.68 m</span> | Measured from the scan | medium |

| Check | Measured | Against | Status |
|---|---|---|---|
| Bathroom: turning circle in the empty room | <span class="num">1.678</span> | <span class="num">1.525 m</span> | <span class="st pass">pass</span> |
| Bathroom: door clear width | <span class="num">0.66</span> | <span class="num">0.815 m</span> | <span class="st fail">fail</span> |
| Bathroom: 30 x 48 in clear floor space outside the door swing | not measured |  | <span class="st fail">fail</span> |
| Bathroom: which way the door opens: not in the scan | not measured |  | <span class="st unknown">unknown</span> |
| Bathroom: clear floor in front of the toilet (front transfer), 30 in wide | <span class="num">0</span> | <span class="num">1.219 m</span> | <span class="st fail">fail</span> |
| Bathroom: clear floor beside the toilet (side transfer), 48 in deep | <span class="num">0.42</span> | <span class="num">0.762 m</span> | <span class="st fail">fail</span> |
| Bathroom: 60 x 56 in clearance around the toilet | not measured |  | <span class="st fail">fail</span> |
| Bathroom: FHA clear floor space at the toilet | not measured |  | <span class="st fail">fail</span> |

4 more checks are in the full result.

Findings: 7 fail, 1 unknown.

What it reported while it ran:

1. Reading 0 bathroom panoramas for the toilet, tub, shower and grab bars
1. Measured 1 bathrooms

## Run it

```sh
threshold run bathroom_clearance --scan <scan-id>
curl -X POST http://127.0.0.1:8787/api/tools/bathroom_clearance/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `bathroom_clearance`. See [MCP server and CLI](/docs/mcp/).
