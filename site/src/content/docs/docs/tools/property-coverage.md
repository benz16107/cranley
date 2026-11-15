---
title: "Property coverage"
description: "For whoever manages or researches a whole property: which of its floor plans and shared spaces have a scan, and which none covers."
sidebar: {"label": "Property coverage"}
---

For whoever manages or researches a whole property: which of its floor plans and shared spaces have a scan, and which none covers.

For the agent, the tool is described as: For one property (place with property_id), list its floor plans and common areas and which have a scan. Use before or after investigating a whole property, to say what no scan covers.

## Who it is for

[Apartment manager](/docs/reference/personas/#apartment-manager), [CoStar researcher](/docs/reference/personas/#costar-researcher).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `place` | Place | yes |  | Where a tool runs when it does not need a scan: a scan id, a CoStar property id (all its scans), an address,. Filled from the selected building. |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Property record | `costar.property` | required | The verdict is `unknown`, with the reason. |
| Scan index | `matterport.index` | required | The verdict is `unknown`, with the reason. |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Panel blocks: `VerdictHeader`, `MetricRow`, `CheckList`, `StepLog`.
- Speed: fast. Read-only.

## How it works

Property coverage: which floor plans and common areas of a property have a scan, and which no scan covers.

## Reliability

Every metric and finding carries its layer, its method and a high, medium or low label, set by the tool for each value. See [findings and reliability](/docs/concepts/findings-and-reliability/).

## Limits

- Needs: property record, scan index. On a scan without them, the verdict is `unknown` and says why.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

<p class="verdict"><span class="st unknown">Cannot answer here</span> There is no CoStar property record for this place, so there is no list of floor plans or shared spaces to hold its 1 scan against.</p>

A phone scan has walls, doors, windows, rooms and objects, but no location, no photos and no property record.

## Run it

```sh
threshold run property_coverage -i place='{"scan": "<scan-id>"}'
curl -X POST http://127.0.0.1:8787/api/tools/property_coverage/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `property_coverage`. See [MCP server and CLI](/docs/mcp/).
