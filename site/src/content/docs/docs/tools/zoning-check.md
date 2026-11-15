---
title: "Zoning check"
description: "What the zoning allows on a lot: the zone, its main uses and height or density limits in Los Angeles; in Houston, which has no zoning, the city's lot-size, building-line and historic rules."
sidebar: {"label": "Zoning check"}
---

What the zoning allows on a lot: the zone, its main uses and height or density limits in Los Angeles; in Houston, which has no zoning, the city's lot-size, building-line and historic rules.

## What it answers

- Can I open a cafe here?
- Is this lot zoned for apartments?
- How tall can I build?

For the agent, the tool is described as: Zoning at a place. Los Angeles: zone string from ZIMAS, its class and main uses (summary of LAMC chapter 1), height district floor area ratio and height (LAMC 12.21.1), General Plan land use, and whether a stated use is on the zone's use list. Houston: explains there is no zoning and reports special minimum lot size, building lines, historic districts and the parcel's present use; deed restrictions are not mapped. Give `use` in the person's words when they name one.

## Who it is for

[Business checking a site](/docs/reference/personas/#business-checking-a-site).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `place` | Place | yes |  | Where a tool runs when it does not need a scan: a scan id, a CoStar property id (all its scans), an address,. Filled from the selected building. |
| `use` | string |  |  | What the person wants to do there, in their words (a cafe, a daycare, apartments). |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Zoning | `public.zoning` | required | The verdict is `unknown`, with the reason. |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Panel blocks: `VerdictHeader`, `MetricRow`, `CheckList`, `Note`, `StepLog`.
- Speed: fast. Read-only.

## How it works

Zoning check: the zone on a lot and what it allows, as the city's own map and code say.

## Reliability

Every metric and finding carries its layer, its method and a high, medium or low label, set by the tool for each value. See [findings and reliability](/docs/concepts/findings-and-reliability/).

## Limits

- Needs: public.zoning. On a scan without it, the verdict is `unknown` and says why.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

<p class="verdict"><span class="st unknown">Cannot answer here</span> This place has no location, so there is no zone to read.</p>

A phone scan has walls, doors, windows, rooms and objects, but no location, no photos and no property record.

## Run it

```sh
threshold run zoning_check -i place='{"scan": "<scan-id>"}'
curl -X POST http://127.0.0.1:8787/api/tools/zoning_check/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `zoning_check`. See [MCP server and CLI](/docs/mcp/).
