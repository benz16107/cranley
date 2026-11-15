---
title: "City census"
description: "Rolls up what has been measured across the city: share of homes a wheelchair can live in by zip code, listed-versus-measured area by property type, smoke alarm coverage by building."
sidebar: {"label": "City census"}
---

Rolls up what has been measured across the city: share of homes a wheelchair can live in by zip code, listed-versus-measured area by property type, smoke alarm coverage by building.

## What it answers

- Which Houston zip codes have the highest share of homes a wheelchair can reach a bathroom in?
- Median gap between listed and measured area by property type

For the agent, the tool is described as: Aggregate one measured field across all buildings in the facts database, grouped by zip, city, property type, kind or building. Use for questions about many buildings at once ('which zip codes have the most wheelchair-accessible homes', 'how far off are listed areas for apartments'). Returns one check per group with the scans counted, share, mean and median, and the SQL it ran. Each scan counts once, at its latest value.

## Who it is for

[Apartment manager](/docs/reference/personas/#apartment-manager), [Commercial property underwriter](/docs/reference/personas/#commercial-property-underwriter), [CoStar research lead](/docs/reference/personas/#costar-research-lead), [CoStar researcher](/docs/reference/personas/#costar-researcher), [Insurance underwriter](/docs/reference/personas/#insurance-underwriter), [Wheelchair user looking for a home](/docs/reference/personas/#wheelchair-user-looking-for-a-home).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `preset` | string |  |  | wheelchair_homes: share of homes a wheelchair can reach a bathroom in, by zip; area_gap: measured over listed area minus one, median by property type; smoke_alarms: share of scans with a smoke alarm seen, by building; step_free_bath; bath_route_door (median door width). |
| `measure` | string |  |  | Any recorded field instead of a preset (see /api/facts/fields), e.g. bath_turn, glazing_ratio, vs_record.beds. |
| `by` | string |  |  | Group by. |
| `stat` | string |  |  | share: fraction above zero. |
| `city` | string |  |  | Houston or Los Angeles. |
| `kind` | string |  |  |  |
| `min_scans` | integer |  | `3` | Leave out groups with fewer scans. Range: at least 1, at most 100. |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Facts database | `threshold.facts` | required | The verdict is `unknown`, with the reason. |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Panel blocks: `VerdictHeader`, `MetricRow`, `RankedTable`, `StepLog`.
- Its own ranked table: Share, Median, Mean, Scans.
- Speed: fast. Read-only.

## How it works

City census: rollups across every building the facts database holds, by zip code, city, property type or building. Reads the `fact_daily` continuous aggregate, so a building the agent measured a moment ago is counted.

## Reliability

Every metric and finding carries its layer, its method and a high, medium or low label, set by the tool for each value. See [findings and reliability](/docs/concepts/findings-and-reliability/).

## Limits

- Needs: facts database. On a scan without it, the verdict is `unknown` and says why.
- The agent asks before running it, because it rolls up every measured building in the city.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

<p class="verdict"><span class="st unknown">Cannot answer here</span> The facts database is not configured (TIGER_DATABASE_URL)</p>

A phone scan has walls, doors, windows, rooms and objects, but no location, no photos and no property record.

## Run it

```sh
threshold run city_census
curl -X POST http://127.0.0.1:8787/api/tools/city_census/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `city_census`. See [MCP server and CLI](/docs/mcp/).
