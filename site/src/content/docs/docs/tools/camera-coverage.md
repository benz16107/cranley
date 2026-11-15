---
title: "Camera coverage"
description: "Shows what indoor security cameras would see, which doors, windows and entry paths they cover, and the blind spots; proposes camera spots if you have none."
sidebar: {"label": "Camera coverage"}
---

Shows what indoor security cameras would see, which doors, windows and entry paths they cover, and the blind spots; proposes camera spots if you have none.

## What it answers

- Where should I put security cameras?
- Which doors does this camera miss?

For the agent, the tool is described as: Indoor security camera coverage through the scan's wall graph: a visibility polygon per camera (field of view and range), which exterior doors and ground-floor windows are in view, how much of each door's walking route to the bedrooms is on camera, and coverage per room. Give cameras, or leave empty to propose up to max_cameras spots. Returns a coverage lens, camera pins, uncovered openings highlighted, entry routes.

## Who it is for

[Family planning home security](/docs/reference/personas/#family-planning-home-security).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `scan` | string | yes |  | Scan id. Filled from the selected building. |
| `cameras` | array |  |  | Camera positions; empty to let the tool propose them. |
| `max_cameras` | integer |  | `4` | How many cameras the proposal may use. Saved preference `security.max_cameras`. Range: at least 1, at most 12. |
| `fov_deg` | number (deg) |  | `110.0` | Saved preference `security.camera_fov_deg`. Range: more than 10, at most 360. |
| `range_m` | number (m) |  | `9.0` | Saved preference `security.camera_range_m`. Range: more than 1, at most 30. |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Wall outline | `matterport.walls` | required | The verdict is `unknown`, with the reason. |
| Doors and windows | `matterport.openings` | required | The verdict is `unknown`, with the reason. |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Draws on the building: a colour per room; doors, walls or rooms coloured by status; pins on what it found; a route with its narrow points.
- Panel blocks: `VerdictHeader`, `MetricRow`, `CheckList`, `FloorPlanMini`, `Controls`, `AssumptionChips`, `StepLog`.
- Speed: fast. Read-only.

## How it works

Camera coverage: what indoor security cameras see through the wall graph, which entry points and entry paths they cover, and the blind spots.

## Reliability

Sources this tool gave on the test cafe:

| Where it came from | Layer | Method | Reliability | Note |
|---|---|---|---|---|
| Measured from the scan | `matterport` | `geometry` | medium | 2D sight lines through the scan's walls; doors assumed open, furniture not modelled |

The tool sets the label for each value. A model never does. The tools give a scan's wall graph the layer `matterport` whichever device made the scan, so a phone scan's geometry carries that label too.

## Limits

- Needs: wall outline, doors and windows. On a scan without them, the verdict is `unknown` and says why.
- A result is a planning aid, not an inspection.

## On the made-up test cafe

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

Inputs used: `max_cameras = 4` (preset of the persona "Family planning home security"); `fov_deg = 110` (preset of the persona "Family planning home security"); `range_m = 9` (preset of the persona "Family planning home security").

<p class="verdict"><span class="st pass">Pass</span> The proposed 2 cameras see 5 of 5 entry points. Doors assumed open; furniture not modelled.</p>

| Value | Result | Where it came from | Reliability |
|---|---|---|---|
| Cameras | <span class="num">2</span> | Measured from the scan | medium |
| Entry points on camera | <span class="num">5 of 5</span> | Measured from the scan | medium |
| Exterior doors not on camera | <span class="num">0</span> | Measured from the scan | medium |
| Ground floor in view | <span class="num">47 %</span> | Measured from the scan | medium |
| Dining Room | <span class="num">53 %</span> | Measured from the scan | medium |
| Kitchen | <span class="num">46 %</span> | Measured from the scan | medium |
| Storage | <span class="num">45 %</span> | Measured from the scan | medium |
| Bathroom | <span class="num">0 %</span> | Measured from the scan | medium |

| Check | Measured | Against | Status |
|---|---|---|---|
| On camera, door in dining room | <span class="num">1</span> | <span class="num">1</span> | <span class="st pass">pass</span> |
| On camera, door in kitchen | <span class="num">1</span> | <span class="num">1</span> | <span class="st pass">pass</span> |
| On camera, window in dining room | <span class="num">1</span> | <span class="num">1</span> | <span class="st pass">pass</span> |
| On camera, window in dining room | <span class="num">1</span> | <span class="num">1</span> | <span class="st pass">pass</span> |
| On camera, window in dining room | <span class="num">1</span> | <span class="num">1</span> | <span class="st pass">pass</span> |

Findings: 1 warn, 2 pass.

What it reported while it ran:

1. 2 exterior doors and 3 ground-floor windows to watch
1. Trying 49 corner mounts and aims
1. 2 cameras: 5 of 5 entry points in view

## Run it

```sh
threshold run camera_coverage --scan <scan-id>
curl -X POST http://127.0.0.1:8787/api/tools/camera_coverage/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `camera_coverage`. See [MCP server and CLI](/docs/mcp/).
