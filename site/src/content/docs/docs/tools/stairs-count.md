---
title: "Stairs"
description: "Counts the floors, estimates the steps between the entrance and the bedrooms, and finds steps at doorways, floor by floor."
sidebar: {"label": "Stairs"}
---

Counts the floors, estimates the steps between the entrance and the bedrooms, and finds steps at doorways, floor by floor.

## What it answers

- How many stairs are there to the bedrooms?
- Is everything on one floor?

For the agent, the tool is described as: Stairs and level changes in one scan, level by level: each floor's height above the entrance floor, an estimated step count (height over an editable riser), bedrooms and bathrooms per floor, staircase rooms, doorway sill steps, and stairs seen in panoramas.

## Who it is for

[Planning for an older parent](/docs/reference/personas/#planning-for-an-older-parent), [Older adult or family](/docs/reference/personas/#older-adult-or-family), [Parent with young kids choosing a home](/docs/reference/personas/#parent-with-young-kids-choosing-a-home), [Older dog that cannot do stairs](/docs/reference/personas/#older-dog-that-cannot-do-stairs), [Wheelchair user](/docs/reference/personas/#wheelchair-user).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `scan` | string | yes |  | Scan id. Filled from the selected building. |
| `riser_m` | number (m) |  | `0.178` | Riser height used to estimate a step count. Saved preference `access.riser_m`. Range: more than 0.1, at most 0.25. |
| `read_panoramas` | boolean |  | `true` | Look for stairs in the staircase and entrance panoramas. |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Rooms | `matterport.rooms` | required | The verdict is `unknown`, with the reason. |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Draws on the building: pins on what it found.
- Panel blocks: `VerdictHeader`, `MetricRow`, `CheckList`, `EvidenceStrip`, `MiniChart`, `AssumptionChips`, `StepLog`.
- Speed: fast. Read-only.

## How it works

Stairs: floors, how far each is above the entrance, an estimate of the steps between, where the bedrooms and bathrooms are, and steps at doorways, level by level. The scan does not contain the stairs themselves: floors are not linked in the plan, so a step count is the height difference over an assumed riser, labelled as an estimate.

## Reliability

Sources this tool gave on the test home:

| Where it came from | Layer | Method | Reliability | Note |
|---|---|---|---|---|
| Measured from the scan | `matterport` | `geometry` | medium | Matterport wall graph, empty rooms; door widths are the opening in the wall |
| Measured from the scan | `matterport` | `geometry` | low | Floor heights from the panorama heights; step count is the rise over the assumed riser |
| Measured from the scan | `matterport` | `geometry` | low | Matterport wall graph; part of this answer rests on an assumption named in the result |

The tool sets the label for each value. A model never does.

## Limits

- Needs: rooms. On a scan without it, the verdict is `unknown` and says why.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

Inputs used: `riser_m = 0.178` (preset of the persona "Planning for an older parent").

<p class="verdict"><span class="st pass">Pass</span> One floor in the scan and no step found at a doorway.</p>

| Value | Result | Where it came from | Reliability |
|---|---|---|---|
| Floors | <span class="num">1</span> | Measured from the scan | medium |
| Most steps from the entrance floor (estimate) | <span class="num">0 steps</span> | Measured from the scan | low |
| Steps at doorways | <span class="num">0</span> | Measured from the scan | low |
| Bedrooms on the entrance floor | <span class="num">2</span> | Measured from the scan | medium |
| floor 1 | <span class="num">0 m</span> | Measured from the scan | low |

| Check | Measured | Against | Status |
|---|---|---|---|
| Floor 1: entrance floor, 2 bedrooms, 1 bathrooms, 0 doorway steps | <span class="num">0</span> | <span class="num">0 steps</span> | <span class="st pass">pass</span> |

What it reported while it ran:

1. 1 floors; entrance on floor 1

## Run it

```sh
threshold run stairs_count --scan <scan-id>
curl -X POST http://127.0.0.1:8787/api/tools/stairs_count/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `stairs_count`. See [MCP server and CLI](/docs/mcp/).
