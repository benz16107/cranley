---
title: "Market comps"
description: "Comparable properties from CoStar: asking rent, sale price per ft\u00b2, class, year built and space for lease, and where this building sits against them."
sidebar: {"label": "Market comps"}
---

Comparable properties from CoStar: asking rent, sale price per ft², class, year built and space for lease, and where this building sits against them.

## What it answers

- What do comparable warehouses rent for near this one?
- Is this office's asking rent above the market?
- Pull sale comps for this building

For the agent, the tool is described as: Comparable commercial properties (same type, similar size, nearby) from the CoStar kit for one candidate: asking rent per ft² per year, last sale price per ft², building class, year built, share of the building marketed for lease; and the candidate's rent percentile among them. Says what the kit does not contain (no market vacancy, asking not effective rents).

## Who it is for

[Commercial property underwriter](/docs/reference/personas/#commercial-property-underwriter), [CoStar researcher](/docs/reference/personas/#costar-researcher), [Industrial tenant rep](/docs/reference/personas/#industrial-tenant-rep), [Office relocation lead](/docs/reference/personas/#office-relocation-lead), [Office tenant](/docs/reference/personas/#office-tenant), [Retail site selector](/docs/reference/personas/#retail-site-selector).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `place` | Place |  |  | The candidate: a scan, a CoStar property, an address or a point. Filled from the selected building. |
| `property_type` | string |  |  | Type to compare with when the place has no CoStar record (a bare point). |
| `size_sf` | number |  |  | Size to compare with when the place has no record, ft². |
| `radius_km` | number (km) |  | `10` | Search radius for comps. Saved preference `comps.radius_km`. Range: at least 1, at most 60. |
| `size_band` | number |  | `2.5` | Comps may be this many times smaller or larger than the candidate. Saved preference `comps.size_band`. Range: at least 1.2, at most 10. |
| `max_comps` | integer |  | `8` | At most this many comps. Range: at least 3, at most 20. |
| `same_class` | boolean |  | `false` | Only comps of the candidate's building class. |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Property record | `costar.property` | required | The verdict is `unknown`, with the reason. |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Panel blocks: `VerdictHeader`, `MetricRow`, `RankedTable`, `CheckList`, `EvidenceStrip`, `Note`, `StepLog`.
- Its own ranked table: Asking $/ft²/yr, Sale $/ft², Size ft², Year built, For lease %, Distance km.
- Speed: fast. Read-only.

## How it works

Market comps: comparable commercial properties from the CoStar kit for one candidate building.

## Reliability

Every metric and finding carries its layer, its method and a high, medium or low label, set by the tool for each value. See [findings and reliability](/docs/concepts/findings-and-reliability/).

## Limits

- Needs: property record. On a scan without it, the verdict is `unknown` and says why.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

<p class="verdict"><span class="st unknown">Cannot answer here</span> This place has no location, so there are no comps near it.</p>

A phone scan has walls, doors, windows, rooms and objects, but no location, no photos and no property record.

## Run it

```sh
threshold run market_comps -i place='{"scan": "<scan-id>"}'
curl -X POST http://127.0.0.1:8787/api/tools/market_comps/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `market_comps`. See [MCP server and CLI](/docs/mcp/).
