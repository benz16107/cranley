---
title: "Kids fit"
description: "Whether a home suits young children: stairs that need gates, the pool path with no barrier, windows a child could fall from, a back yard the kitchen looks onto, and the walk to playgrounds, parks and schools."
sidebar: {"label": "Kids fit"}
---

Whether a home suits young children: stairs that need gates, the pool path with no barrier, windows a child could fall from, a back yard the kitchen looks onto, and the walk to playgrounds, parks and schools.

## What it answers

- Is this house safe for my toddler?
- Is there a playground within walking distance?
- Which windows need a window guard?

For the agent, the tool is described as: For one scanned home and the youngest child's age: staircases to gate (floors in the scan), every route from a bedroom to the pool with the missing barrier (runs path_to_water), upper-floor windows judged against IRC R312.2.1 (sill under 24 in with a drop over 72 in), kitchen windows that look onto the back yard (plan placed on the Vexcel footprint), and the walk along the streets to the nearest playground, park, elementary, middle and high school, library, public pool and childcare, with busy roads crossed (OpenStreetMap).

## Who it is for

[Parent with young kids choosing a home](/docs/reference/personas/#parent-with-young-kids-choosing-a-home), [Parent of a toddler, house with a pool](/docs/reference/personas/#parent-of-a-toddler-house-with-a-pool), [Family with a teenager who plays soccer](/docs/reference/personas/#family-with-a-teenager-who-plays-soccer).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `scan` | string | yes |  | Scan id. Filled from the selected building. |
| `youngest_age` | integer (years) | yes |  | Asked as: "How old is your youngest child, in years?" Saved preference `kids.youngest_age`. Range: at least 0, at most 17. |
| `lat` | number |  |  | For a phone scan with no location. |
| `lon` | number |  |  |  |
| `use_vision` | boolean |  | `true` | Inspect pool-side doors and the yard with the vision model (cached). |
| `nearby` | boolean |  | `true` | Look up playgrounds, parks and schools in OpenStreetMap (cached). |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Doors and windows | `matterport.openings` | required | The verdict is `unknown`, with the reason. |
| Aerial property facts | `vexcel.property` | optional | The tool runs without it. |
| Places | `osm.places` | optional | The tool runs without it. |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Draws on the building: a route with its narrow points; pins on what it found; doors, walls or rooms coloured by status.
- Panel blocks: `VerdictHeader`, `MetricRow`, `CheckList`, `EvidenceStrip`, `FloorPlanMini`, `AssumptionChips`, `StepLog`.
- Speed: slow. Read-only.

## How it works

Kids fit: is this home right for young children? Stairs that need gates, every route a small child could take to the pool (path_to_water, folded in), windows a child could fall from, whether the kitchen looks onto the back yard, and the walk to the nearest playground, park and schools with the busy roads crossed on the way.

## Reliability

Sources this tool gave on the test home:

| Where it came from | Layer | Method | Reliability | Note |
|---|---|---|---|---|
| Measured from the scan | `matterport` | `geometry` | low | Stairs are not in the scan; one flight per floor change |
| Measured from the scan | `matterport` | `geometry` | medium | Matterport wall graph and opening sills |

The tool sets the label for each value. A model never does. The tools give a scan's wall graph the layer `matterport` whichever device made the scan, so a phone scan's geometry carries that label too.

## Limits

- Needs: doors and windows. On a scan without it, the verdict is `unknown` and says why.
- It is slow: progress steps reach the workspace while it runs.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

Inputs used: `youngest_age = 3` (preset of the persona "Parent with young kids choosing a home").

<p class="verdict"><span class="st pass">Pass</span> Suits your children (youngest 3). Not checked: the scan has no location, so the pool, yard and places nearby were not checked.</p>

| Value | Result | Where it came from | Reliability |
|---|---|---|---|
| Staircases to gate (floors in the scan, less one) | <span class="num">0</span> | Measured from the scan | low |
| Upper windows with a low sill | <span class="num">0</span> | Measured from the scan | medium |

| Check | Measured | Against | Status |
|---|---|---|---|
| Stairs gated top and bottom | <span class="num">0</span> | <span class="num">0 gates</span> | <span class="st pass">pass</span> |
| Pool, yard and places nearby | not measured |  | <span class="st unknown">unknown</span> |

Findings: 1 pass.

## Run it

```sh
threshold run kids_fit --scan <scan-id>
curl -X POST http://127.0.0.1:8787/api/tools/kids_fit/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `kids_fit`. See [MCP server and CLI](/docs/mcp/).
