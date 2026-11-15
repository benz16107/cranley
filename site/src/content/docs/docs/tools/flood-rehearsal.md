---
title: "Flood rehearsal"
description: "Shows what a flood does inside this house: how deep in each room, which doors and windows go under, and the order rooms flood, with the floor-height error carried through."
sidebar: {"label": "Flood rehearsal"}
---

Shows what a flood does inside this house: how deep in each room, which doors and windows go under, and the order rooms flood, with the floor-height error carried through.

## What it answers

- What happens inside if 60 cm of water comes up the street?
- Rehearse Harvey in this house

For the agent, the tool is described as: Simulate still water at a scenario depth above the ground outside one scanned house. Measures the floor height above ground (drone photos of the door, the scan's outdoor panoramas, Vexcel elevations) with a range, then returns per-room depth, wetted floor and wall area, flood order, overtopped openings, a water overlay and a depth lens. Scenario harvey_2017 reads USGS marks.

## Who it is for

[Emergency manager or caseworker before a storm](/docs/reference/personas/#emergency-manager-or-caseworker-before-a-storm), [Houston homeowner before a storm](/docs/reference/personas/#houston-homeowner-before-a-storm), [Insurance underwriter](/docs/reference/personas/#insurance-underwriter).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `scan` | string | yes |  | Scan id. Filled from the selected building. |
| `depth_m` | number (m) | yes |  | Water above the ground outside. Asked as: "How deep could the water get above the ground outside your house, in metres? Use a storm-surge forecast (given as height above ground) or a street-flooding depth." Saved preference `flood.depth_m`. Range: at least 0, at most 3. |
| `scenario` | string |  | `"depth"` | Where the depth comes from: typed depth, storm surge, rainfall, or Harvey 2017 from USGS high-water marks (then depth_m is not used). Saved preference `flood.scenario`. One of: `depth`, `surge`, `rainfall`, `harvey_2017`. |
| `floor_height_m` | number (m) |  |  | Floor height above the ground at the door, if you measured it. Saved preference `flood.floor_height_m`. |
| `use_drone` | boolean |  | `true` | Measure the door threshold in the drone photos (vision model, cached). |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Rooms | `matterport.rooms` | required | The verdict is `unknown`, with the reason. |
| Doors and windows | `matterport.openings` | optional | depths only, no flood order or openings |
| Drone photos | `drone.photos` | optional | The tool runs without it. |
| Ground heights | `vexcel.elevation` | optional | The tool runs without it. |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Draws on the building: a water level; a colour per room; doors, walls or rooms coloured by status; pins on what it found.
- Panel blocks: `VerdictHeader`, `MetricRow`, `Controls`, `FloorPlanMini`, `CheckList`, `EvidenceStrip`, `MiniChart`, `AssumptionChips`, `StepLog`, `ActionBar`.
- Speed: slow. Read-only.

## How it works

Flood rehearsal: what a water level does inside one scanned house, with the floor-height error carried through.

## Reliability

Sources this tool gave on the test home:

| Where it came from | Layer | Method | Reliability | Note |
|---|---|---|---|---|
| Simulated from the scan | `matterport` | `simulation` | medium | Still water filling the rooms through openings by sill height; no flow, pressure or drainage |
| Measured from a model | `model` | `geometry` | low | Floor height from a typical Houston slab (assumed); range 0.10 to 0.50 m |
| Looked up in a model | `model` | `lookup` | high | Your number |

The tool sets the label for each value. A model never does.

## Limits

- Needs: rooms. On a scan without it, the verdict is `unknown` and says why.
- It is slow: progress steps reach the workspace while it runs.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

Inputs used: `depth_m = 0.6` (an answer given for this example).

<p class="verdict"><span class="st fail">Fail</span> With water 0.60 m above the ground outside, water stands 0.30 m on the entry floor (0.10 to 0.50 m); 6 of 6 rooms take water. The floor height is assumed, not measured.</p>

| Value | Result | Where it came from | Reliability |
|---|---|---|---|
| Water on the entry floor | <span class="num">0.3 m</span> | Simulated from the scan | medium |
| Rooms taking water | <span class="num">6</span> | Simulated from the scan | medium |
| Floor above the ground | <span class="num">0.3 m</span> | Measured from a model | low |
| Wall below the water line | <span class="num">43.4 m2</span> | Simulated from the scan | medium |
| Water on the entry floor, low end | <span class="num">0.1 m</span> | Simulated from the scan | medium |
| Water on the entry floor, high end | <span class="num">0.5 m</span> | Simulated from the scan | medium |
| Rooms taking water, low end | <span class="num">6</span> | Simulated from the scan | medium |
| Rooms taking water, high end | <span class="num">6</span> | Simulated from the scan | medium |
| Water above the ground outside | <span class="num">0.6 m</span> | Looked up in a model | high |
| Floor above the ground, low end | <span class="num">0.1 m</span> | Measured from a model | low |

7 more values are in the full result.

| Check | Measured | Against | Status |
|---|---|---|---|
| Water on the floor, Living Room | <span class="num">0.3</span> | <span class="num">0 m</span> | <span class="st fail">fail</span> |
| Water on the floor, Bedroom | <span class="num">0.3</span> | <span class="num">0 m</span> | <span class="st fail">fail</span> |
| Water on the floor, Bedroom | <span class="num">0.3</span> | <span class="num">0 m</span> | <span class="st fail">fail</span> |
| Water on the floor, Kitchen | <span class="num">0.3</span> | <span class="num">0 m</span> | <span class="st fail">fail</span> |
| Water on the floor, Bathroom | <span class="num">0.3</span> | <span class="num">0 m</span> | <span class="st fail">fail</span> |
| Water on the floor, Hallway | <span class="num">0.3</span> | <span class="num">0 m</span> | <span class="st fail">fail</span> |

Findings: 1 unknown, 7 fail.

What it reported while it ran:

1. The scan has no location, so the aerial and drone methods are off
1. Scan outdoor panoramas: none near an exterior door
1. Water levels in the scan: lo +0.10 m from the entry floor, mid +0.30 m from the entry floor, hi +0.50 m from the entry floor

## Run it

```sh
threshold run flood_rehearsal --scan <scan-id>
curl -X POST http://127.0.0.1:8787/api/tools/flood_rehearsal/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `flood_rehearsal`. See [MCP server and CLI](/docs/mcp/).
