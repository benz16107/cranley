---
title: "Risk sheet"
description: "One printable page for an underwriter: roof, flood position, wildfire space, pool, trees and interior hazards, each with its evidence and confidence."
sidebar: {"label": "Risk sheet"}
---

One printable page for an underwriter: roof, flood position, wildfire space, pool, trees and interior hazards, each with its evidence and confidence.

## What it answers

- Give me a risk summary of this house
- Should I send an inspector to this property?

For the agent, the tool is described as: For one property at a scan, a CoStar id or a lat/lon in Houston or Los Angeles: runs roof_facts, compares the ground at the building with rings 50 to 200 m around it (Vexcel DTM), reads defensible-space tree cover (Los Angeles), pool and enclosure, trees over the roof, and with a scan reads interior hazards (smoke alarms, extinguishers, panels, water heaters, stoves) from the panoramas. Returns checks and findings and a printable HTML sheet at /api/site/sheet/&lt;name>.html.

## Who it is for

[Commercial property underwriter](/docs/reference/personas/#commercial-property-underwriter), [Houston homeowner before a storm](/docs/reference/personas/#houston-homeowner-before-a-storm), [Insurance underwriter](/docs/reference/personas/#insurance-underwriter), [Parent of a toddler, house with a pool](/docs/reference/personas/#parent-of-a-toddler-house-with-a-pool).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `scan` | string |  |  | Scan id, if the site has one. Filled from the selected building. |
| `property_id` | integer |  |  | CoStar PropertyId, for a commercial address. |
| `lat` | number |  |  | Latitude, for an address with no scan. |
| `lon` | number |  |  | Longitude, for an address with no scan. |
| `use_vision` | boolean |  | `true` | Read interior hazards from the panoramas (cached). |
| `max_panos` | integer |  | `5` | Panoramas to read for interior hazards. Range: at least 1, at most 12. |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Aerial property facts | `vexcel.property` | required | The verdict is `unknown`, with the reason. |
| Ground heights | `vexcel.dtm` | required | The verdict is `unknown`, with the reason. |
| 360° photos | `matterport.panos` | optional | The tool runs without it. |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Draws on the building: pins on what it found.
- Panel blocks: `VerdictHeader`, `MetricRow`, `CheckList`, `EvidenceStrip`, `StepLog`, `ActionBar`.
- Speed: slow. Read-only.

## How it works

Risk sheet: one page for an insurance underwriter on one property. Roof, flood position (ground at the building against the ground around it), wildfire defensible space where it matters, pool, trees over the roof and, where a scan exists, interior hazards from the panoramas, each with evidence and confidence. Also written as a printable HTML page under the data folder and served at /api/site/sheet/&lt;name>.html (api/site_media.py).

## Reliability

Every metric and finding carries its layer, its method and a high, medium or low label, set by the tool for each value. See [findings and reliability](/docs/concepts/findings-and-reliability/).

## Limits

- Needs: aerial property facts, ground heights. On a scan without them, the verdict is `unknown` and says why.
- It is slow: progress steps reach the workspace while it runs.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

<p class="verdict"><span class="st unknown">Cannot answer here</span> Scan u_testhome0001 has no location (a phone scan carries none), so the aerial photo cannot be found. Give a latitude and longitude to run this on the site.</p>

A phone scan has walls, doors, windows, rooms and objects, but no location, no photos and no property record.

## Run it

```sh
threshold run risk_sheet --scan <scan-id>
curl -X POST http://127.0.0.1:8787/api/tools/risk_sheet/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `risk_sheet`. See [MCP server and CLI](/docs/mcp/).
