---
title: "Roof facts"
description: "Roof material, shape, condition, defects, solar, rooftop objects, trees over the roof and height, read from the aerial photo."
sidebar: {"label": "Roof facts"}
---

Roof material, shape, condition, defects, solar, rooftop objects, trees over the roof and height, read from the aerial photo.

## What it answers

- What shape is this roof in?
- Is there damage on the roof?
- Does it have solar?

For the agent, the tool is described as: Roof of one building at a scan, a CoStar property or a lat/lon: Vexcel material, shape, condition score, each defect with its share of the roof, solar, rooftop object counts, tree cover over the roof and roof height, with the orthophoto and capture date. For insurers and storm plans. Works for any address in Houston or Los Angeles.

## Who it is for

[Commercial property underwriter](/docs/reference/personas/#commercial-property-underwriter), [CoStar researcher](/docs/reference/personas/#costar-researcher), [Houston homeowner before a storm](/docs/reference/personas/#houston-homeowner-before-a-storm), [Insurance underwriter](/docs/reference/personas/#insurance-underwriter), [LA homeowner after the fires](/docs/reference/personas/#la-homeowner-after-the-fires), [Homeowner considering solar](/docs/reference/personas/#homeowner-considering-solar).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `scan` | string |  |  | Scan id, if the site has one. Filled from the selected building. |
| `property_id` | integer |  |  | CoStar PropertyId, for a commercial address. |
| `lat` | number |  |  | Latitude, for an address with no scan. |
| `lon` | number |  |  | Longitude, for an address with no scan. |
| `max_tree_cover_pct` | number (%) |  | `25` | Tree cover over the roof above this is a warning. Saved preference `roof.max_tree_cover_pct`. Range: at least 0, at most 100. |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Aerial property facts | `vexcel.property` | required | The verdict is `unknown`, with the reason. |
| Aerial photo | `vexcel.ortho` | required | The verdict is `unknown`, with the reason. |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Draws on the building: pins on what it found.
- Panel blocks: `VerdictHeader`, `MetricRow`, `CheckList`, `EvidenceStrip`, `MiniChart`, `AssumptionChips`, `StepLog`.
- Speed: fast. Read-only.

## How it works

Roof facts: material, shape, condition, defects and their share of the roof, solar, roof objects, tree overhang and height, from Vexcel's aerial facts, with the aerial crop and the capture date as evidence.

## Reliability

Every metric and finding carries its layer, its method and a high, medium or low label, set by the tool for each value. See [findings and reliability](/docs/concepts/findings-and-reliability/).

## Limits

- Needs: aerial property facts, aerial photo. On a scan without them, the verdict is `unknown` and says why.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

<p class="verdict"><span class="st unknown">Cannot answer here</span> Scan u_testhome0001 has no location (a phone scan carries none), so the aerial photo cannot be found. Give a latitude and longitude to run this on the site.</p>

A phone scan has walls, doors, windows, rooms and objects, but no location, no photos and no property record.

## Run it

```sh
threshold run roof_facts --scan <scan-id>
curl -X POST http://127.0.0.1:8787/api/tools/roof_facts/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `roof_facts`. See [MCP server and CLI](/docs/mcp/).
