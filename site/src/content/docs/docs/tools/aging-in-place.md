---
title: "Aging in place"
description: "Goes through the CDC home fall-prevention checklist for the parts the scan can answer, floor by floor: clear paths, steps, stairs, the night path from bed to bathroom, and grab bars."
sidebar: {"label": "Aging in place"}
---

Goes through the CDC home fall-prevention checklist for the parts the scan can answer, floor by floor: clear paths, steps, stairs, the night path from bed to bathroom, and grab bars.

## What it answers

- Is this home safe for my mother to age in?
- Where could someone trip in this house?

For the agent, the tool is described as: CDC STEADI 'Check for Safety' items answerable from one scan, level by level: clear path widths from the entrance, the bedroom-to-bathroom route, doorway steps, stairs between floors, bed and bath on the entrance floor (AARP HomeFit), and grab bars and tub or shower type seen in bathroom panoramas. Lists the checklist items the scan cannot answer.

## Who it is for

[Planning for an older parent](/docs/reference/personas/#planning-for-an-older-parent), [Older adult or family](/docs/reference/personas/#older-adult-or-family).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `scan` | string | yes |  | Scan id. Filled from the selected building. |
| `read_panoramas` | boolean |  | `true` | Look at the bathroom panoramas for grab bars and the tub or shower. |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Wall outline | `matterport.walls` | required | The verdict is `unknown`, with the reason. |
| Room names | `matterport.room_labels` | required | The verdict is `unknown`, with the reason. |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Draws on the building: pins on what it found.
- Panel blocks: `VerdictHeader`, `MetricRow`, `CheckList`, `EvidenceStrip`, `FloorPlanMini`, `StepLog`, `ActionBar`.
- Speed: slow. Read-only.

## How it works

Aging in place: the CDC STEADI 'Check for Safety' items the scan can answer, level by level, from the aging_in_place rule pack (geometry), the stairs summary, and the bathroom panoramas. Items about belongings (rugs, cords, shelves) or things the scan cannot see (handrails, lights, slippery floors) are listed as such.

## Reliability

Sources this tool gave on the test home:

| Where it came from | Layer | Method | Reliability | Note |
|---|---|---|---|---|
| Measured from the scan | `matterport` | `geometry` | medium | Matterport wall graph, empty rooms; door widths are the opening in the wall |
| Measured from the scan | `matterport` | `geometry` | medium | CDC STEADI 'Check for Safety' (2017), Bedrooms: 'Is the path from your bed to the bathroom dark?' The checklist asks about light; the scan gives this path's length and width instead. Width from ADA 2010 Standards 403.5.1 (36 in, 915 mm). Tolerance 2.5 cm. |
| Measured from the scan | `matterport` | `geometry` | medium | CDC STEADI 'Check for Safety' (2017), Stairs and steps: 'Are some steps broken or uneven?'; limit from ADA 2010 Standards 303.3 (1/2 in, 13 mm). Tolerance 4.0 cm. |
| Measured from the scan | `matterport` | `geometry` | medium | AARP HomeFit Guide (bedroom and full bathroom on the main level). Tolerance 2.5 cm. |

The tool sets the label for each value. A model never does. The tools give a scan's wall graph the layer `matterport` whichever device made the scan, so a phone scan's geometry carries that label too.

## Limits

- Needs: wall outline, room names. On a scan without them, the verdict is `unknown` and says why.
- It is slow: progress steps reach the workspace while it runs.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

<p class="verdict"><span class="st fail">Fail</span> 9 places to fix or check, at least one clear hazard.</p>

| Value | Result | Where it came from | Reliability |
|---|---|---|---|
| Places to fix or check | <span class="num">9</span> | Measured from the scan | medium |
| Floors | <span class="num">1</span> | Measured from the scan | medium |
| Checklist items the scan answers | <span class="num">5</span> | Measured from the scan | medium |

| Check | Measured | Against | Status |
|---|---|---|---|
| The path from the entrance through the main rooms is wide enough to walk without stepping around things: 36 in (914 mm) between walls. Furniture is not in the scan, so this is the most room there can be. | <span class="num">1.191</span> | <span class="num">0.914 m</span> | <span class="st pass">pass</span> |
| The night-time route from each bedroom to the nearest bathroom on the same floor is at least 36 in (914 mm) wide, so a walker fits. The route length is in each finding. | <span class="num">0.66</span> | <span class="num">0.914 m</span> | <span class="st fail">fail</span> |
| No raised threshold or single step at a doorway (over 1/2 in, 13 mm). Steps found here are trip hazards to fix first. | <span class="num">0</span> | <span class="num">0.013 m</span> | <span class="st warn">warn</span> |
| A bedroom and a bathroom are on the floor with the entrance, so stairs are not needed day to day. | <span class="num">1</span> | <span class="num">1 rooms</span> | <span class="st warn">warn</span> |
| If the home has stairs, check handrails on both sides for the full length and a light switch at the top and bottom. The scan cannot see either. | <span class="num">1</span> | <span class="num">1 floors</span> | <span class="st pass">pass</span> |
| Floors: 'Do you have throw rugs on the floor?' Not answerable: belongings change after the scan. | not measured |  | <span class="st unknown">unknown</span> |
| Floors: 'Do you have to walk over or around wires or cords?' Not answerable: belongings change after the scan. | not measured |  | <span class="st unknown">unknown</span> |
| Stairs: 'Is there a light and light switch at the top and bottom of the stairs?' Not answerable: switches are not in the scan; look on site. | not measured |  | <span class="st unknown">unknown</span> |

4 more checks are in the full result.

Findings: 2 fail, 7 warn.

What it reported while it ran:

1. Evaluated the Aging in place rule pack: 5 checks
1. 9 places to fix or check, at least one clear hazard.

## Run it

```sh
threshold run aging_in_place --scan <scan-id>
curl -X POST http://127.0.0.1:8787/api/tools/aging_in_place/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `aging_in_place`. See [MCP server and CLI](/docs/mcp/).
