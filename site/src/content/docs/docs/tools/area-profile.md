---
title: "Area profile"
description: "Who lives around a building: population, density, household income, age mix, households, the share renting, rent and home value for its census tract, next to the county."
sidebar: {"label": "Area profile"}
---

Who lives around a building: population, density, household income, age mix, households, the share renting, rent and home value for its census tract, next to the county.

## What it answers

- Who lives around here?
- Is this a family neighbourhood?
- What do people earn around this shop?

For the agent, the tool is described as: Census profile of the tract around a place in Houston or Los Angeles (ACS 5-year): population, density, median household income, median age, under 18 and 65+ shares, households, renters, median rent and home value, each with the county value for comparison. Use for questions about the neighbourhood's people or market, not about the building.

## Who it is for

[Business checking a site](/docs/reference/personas/#business-checking-a-site), [Family checking a neighbourhood](/docs/reference/personas/#family-checking-a-neighbourhood), [Remote worker](/docs/reference/personas/#remote-worker).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `place` | Place | yes |  | Where a tool runs when it does not need a scan: a scan id, a CoStar property id (all its scans), an address,. Filled from the selected building. |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Census acs | `public.census_acs` | required | The verdict is `unknown`, with the reason. |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Panel blocks: `VerdictHeader`, `MetricRow`, `CheckList`, `Note`, `StepLog`.
- Speed: fast. Read-only.

## How it works

Area profile: who lives around a place, from the census tract it stands in, next to its county.

## Reliability

Every metric and finding carries its layer, its method and a high, medium or low label, set by the tool for each value. See [findings and reliability](/docs/concepts/findings-and-reliability/).

## Limits

- Needs: public.census_acs. On a scan without it, the verdict is `unknown` and says why.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

<p class="verdict"><span class="st unknown">Cannot answer here</span> This place has no location, so there is no census tract to read.</p>

A phone scan has walls, doors, windows, rooms and objects, but no location, no photos and no property record.

## Run it

```sh
threshold run area_profile -i place='{"scan": "<scan-id>"}'
curl -X POST http://127.0.0.1:8787/api/tools/area_profile/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `area_profile`. See [MCP server and CLI](/docs/mcp/).
