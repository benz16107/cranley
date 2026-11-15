---
title: "Retail site"
description: "Parking counted from the air and its ratio, the road the site faces, anchors and neighbouring shops, and walk-in proxies."
sidebar: {"label": "Retail site"}
---

Parking counted from the air and its ratio, the road the site faces, anchors and neighbouring shops, and walk-in proxies.

## What it answers

- Is this a good spot for our next store?
- How much parking does this retail site have per 1,000 ft²?

For the agent, the tool is described as: For a shop or restaurant site (scan, CoStar property or point): parking stalls counted on the aerial (parking_count) and stalls per 1,000 ft² of the store; the main road it faces (class, lanes, setback); anchor stores within 1.5 km and shops, food and services within a walk radius (co-tenancy); bus stops and mapped homes and offices nearby as walk-in proxies. OpenStreetMap based.

## Who it is for

[Commercial property underwriter](/docs/reference/personas/#commercial-property-underwriter), [Retail site selector](/docs/reference/personas/#retail-site-selector).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `place` | Place | yes |  | The site: a scan, a CoStar property, an address or a point. Filled from the selected building. |
| `store_sf` | number (ft²) |  |  | Store size, for the parking ratio; default the building's rentable area. Saved preference `retail.store_sf`. |
| `parking_ratio_min` | number (per 1,000 ft²) |  | `4.0` | Stalls per 1,000 ft² the store needs. Saved preference `site.parking_ratio_min`. Range: at least 0, at most 20. |
| `radius_m` | integer (m) |  | `400` | Walk radius for neighbours. Saved preference `retail.radius_m`. Range: at least 100, at most 1500. |
| `count_parking` | boolean |  | `true` | Count stalls on the aerial with parking_count (slow, cached). |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Osm | `osm` | required | The verdict is `unknown`, with the reason. |
| Aerial photo | `vexcel.ortho` | optional | no stall count |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Panel blocks: `VerdictHeader`, `MetricRow`, `CheckList`, `EvidenceStrip`, `AssumptionChips`, `StepLog`.
- Speed: slow. Read-only.

## How it works

Retail site: what a chain looks at before it signs for a shop.

## Reliability

Every metric and finding carries its layer, its method and a high, medium or low label, set by the tool for each value. See [findings and reliability](/docs/concepts/findings-and-reliability/).

## Limits

- Needs: osm. On a scan without it, the verdict is `unknown` and says why.
- It is slow: progress steps reach the workspace while it runs.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

Inputs used: `parking_ratio_min = 4` (preset of the persona "Retail site selector").

<p class="verdict"><span class="st unknown">Unknown</span> This place has no location.</p>


## Run it

```sh
threshold run retail_site -i place='{"scan": "<scan-id>"}'
curl -X POST http://127.0.0.1:8787/api/tools/retail_site/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `retail_site`. See [MCP server and CLI](/docs/mcp/).
