---
title: "Measure search"
description: "Finds homes by what is measured inside them: door widths on the way to the bathroom, turning space, wall lengths, floors, steps. No listing site can search this."
sidebar: {"label": "Measure search"}
---

Finds homes by what is measured inside them: door widths on the way to the bathroom, turning space, wall lengths, floors, steps. No listing site can search this.

## What it answers

- Homes where a wheelchair can reach a bathroom through 0.81 m doors, on one floor
- Apartments with a bedroom wall of at least 2.2 m and a 1.5 m turning circle in the bathroom

For the agent, the tool is described as: Search about two thousand Houston and Los Angeles homes by measured facts. Criteria are (measure, op, value) and must all hold; returns the matching scans ranked by how comfortably they pass, with each measured value and why it passed. Key measures: bath_route_door (narrowest door from the entrance to the best bathroom), bed_route_door_min, bath_turn, bed_wall, floors, step_free_bath, wheelchair_bath, ceiling_median, glazing_ratio.

## Who it is for

[Car owner checking a garage](/docs/reference/personas/#car-owner-checking-a-garage), [Moving large furniture](/docs/reference/personas/#moving-large-furniture), [Older adult or family](/docs/reference/personas/#older-adult-or-family), [Renter checking a listing](/docs/reference/personas/#renter-checking-a-listing), [Home robot maker](/docs/reference/personas/#home-robot-maker), [Wheelchair user looking for a home](/docs/reference/personas/#wheelchair-user-looking-for-a-home), [Wheelchair user](/docs/reference/personas/#wheelchair-user).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `need` | string |  |  | A common search, picked from a list. Asked as: "What must the home allow? wheelchair: A wheelchair reaches a bathroom from the entrance; step_free_bath: No step between the entrance and a bathroom; one_floor_living: Bedroom and bathroom on the entrance floor, no doorway steps; king_bed: A king bed fits: a bedroom wall of 3 m and 0.76 m doors to every bedroom; upright_piano: An upright piano fits: a living room wall of 3 m and a 0.85 m entrance" Saved preference `search.need`. |
| `criteria` | array |  | `[]` | Every criterion must hold; added to the need's own criteria. |
| `city` | string |  |  | Houston or Los Angeles. |
| `kind` | string |  |  | House or apartment. |
| `sort` | string |  |  | Rank by this measure, highest first; default by margin. |
| `limit` | integer |  | `20` | Rows to return. Range: at least 1, at most 100. |
| `near` | array |  |  | Point to search around, (lat, lon). |
| `within_km` | number |  |  | Only scans this close to `near`. |
| `rooms` | array |  | `[]` | Rooms the home must have, each meeting its measures (e.g. a Kitchen with area >= 12). Needs the facts database. |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Measures table | `threshold.measures` | required | The verdict is `unknown`, with the reason. |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Panel blocks: `VerdictHeader`, `MetricRow`, `RankedTable`, `EvidenceStrip`, `StepLog`, `ActionBar`.
- Its own ranked table: Margin over the criteria.
- Speed: fast. Read-only.

## How it works

Measure search: find homes by what is measured inside them (door widths on the way to the bathroom, turning circles, free wall lengths, floors...), over the measures table (table.py).

## Reliability

Every metric and finding carries its layer, its method and a high, medium or low label, set by the tool for each value. See [findings and reliability](/docs/concepts/findings-and-reliability/).

## Limits

- Needs: measures table. On a scan without it, the verdict is `unknown` and says why.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

<p class="verdict"><span class="st unknown">Unknown</span> The measures table has not been built yet.</p>


## Run it

```sh
threshold run measure_search
curl -X POST http://127.0.0.1:8787/api/tools/measure_search/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `measure_search`. See [MCP server and CLI](/docs/mcp/).
