---
title: "Permit history"
description: "What was permitted at and near an address, by type and year, and any code enforcement cases (Los Angeles); residents' recent service requests to the city nearby in Houston."
sidebar: {"label": "Permit history"}
---

What was permitted at and near an address, by type and year, and any code enforcement cases (Los Angeles); residents' recent service requests to the city nearby in Houston.

## What it answers

- What was permitted here?
- Any code violations at this address?
- Is the block being redeveloped?

For the agent, the tool is described as: Building permits since 2010 at and within a radius of a Los Angeles address (LADBS open data), counted by year and type, with the permits at the address itself and LADBS code enforcement cases on that street number. In Houston, which publishes no permit locations, recent 311 service requests nearby. Use for 'what was built or permitted here' and 'any violations'.

## Who it is for

[Business checking a site](/docs/reference/personas/#business-checking-a-site), [Family checking a neighbourhood](/docs/reference/personas/#family-checking-a-neighbourhood).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `place` | Place | yes |  | Where a tool runs when it does not need a scan: a scan id, a CoStar property id (all its scans), an address,. Filled from the selected building. |
| `radius_m` | number |  | `150` | How far round the address to count permits or requests. Range: at least 20, at most 800. |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Permits | `public.permits` | required | The verdict is `unknown`, with the reason. |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Draws on the building: pins on what it found.
- Panel blocks: `VerdictHeader`, `MetricRow`, `MiniChart`, `CheckList`, `StepLog`.
- Speed: fast. Read-only.

## How it works

Permit history: building permits and code enforcement at and near an address, by type and year.

## Reliability

Every metric and finding carries its layer, its method and a high, medium or low label, set by the tool for each value. See [findings and reliability](/docs/concepts/findings-and-reliability/).

## Limits

- Needs: public.permits. On a scan without it, the verdict is `unknown` and says why.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

<p class="verdict"><span class="st unknown">Cannot answer here</span> This place has no location, so there is nothing to look up round it.</p>

A phone scan has walls, doors, windows, rooms and objects, but no location, no photos and no property record.

## Run it

```sh
threshold run permit_history -i place='{"scan": "<scan-id>"}'
curl -X POST http://127.0.0.1:8787/api/tools/permit_history/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `permit_history`. See [MCP server and CLI](/docs/mcp/).
