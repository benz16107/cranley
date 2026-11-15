---
title: "Parking count"
description: "Counts parking stalls and parked cars from the aerial photo and compares them with the record."
sidebar: {"label": "Parking count"}
---

Counts parking stalls and parked cars from the aerial photo and compares them with the record.

## What it answers

- How many parking spaces does this property have?
- Is the lot full?

For the agent, the tool is described as: For any address in Houston or Los Angeles: parking stalls on the parcel counted on the Vexcel orthophoto by the vision model on 90 m tiles (whole-row boxes split into stalls), cross-checked against the lot area Vexcel's detector outlines and the cars it counts, accessible stalls where visible, vehicles on capture day and occupancy, beside the CoStar record's parking spaces and ratio. Surface lots only: garages and stalls under trees are invisible.

## Who it is for

[Apartment manager](/docs/reference/personas/#apartment-manager), [Commercial property underwriter](/docs/reference/personas/#commercial-property-underwriter), [CoStar researcher](/docs/reference/personas/#costar-researcher), [Film or photo location scout](/docs/reference/personas/#film-or-photo-location-scout), [Office tenant](/docs/reference/personas/#office-tenant), [Retail site selector](/docs/reference/personas/#retail-site-selector), [Truck dispatcher](/docs/reference/personas/#truck-dispatcher).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `scan` | string |  |  | Scan id, if the site has one. Filled from the selected building. |
| `property_id` | integer |  |  | CoStar PropertyId, for a commercial address. |
| `lat` | number |  |  | Latitude, for an address with no scan. |
| `lon` | number |  |  | Longitude, for an address with no scan. |
| `use_vision` | boolean |  | `true` | Cross-check the count with the vision model (cached). |
| `agree_pct` | number (%) |  | `15` | Counts within this share of the record agree. Saved preference `parking.agree_pct`. Range: at least 1, at most 100. |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Aerial photo | `vexcel.ortho` | required | The verdict is `unknown`, with the reason. |
| Aerial property facts | `vexcel.property` | required | The verdict is `unknown`, with the reason. |
| Property record | `costar.property` | optional | The tool runs without it. |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Draws on the building: pins on what it found.
- Panel blocks: `VerdictHeader`, `MetricRow`, `CheckList`, `EvidenceStrip`, `AssumptionChips`, `StepLog`.
- Speed: slow. Read-only.

## How it works

Parking count: marked stalls counted from above by the vision model on orthophoto tiles (whole-row boxes split into stalls or dropped), cross-checked by Vexcel detection: its lot outlines give a capacity estimate and its cars a floor. Accessible stalls where the model sees them, vehicles on capture day, beside the CoStar record's spaces and ratio. Vexcel's SAM 3 boxes whole lots for "parking space", not stalls (seen 2026-11-13 at three lots, four tile sizes).

## Reliability

Every metric and finding carries its layer, its method and a high, medium or low label, set by the tool for each value. See [findings and reliability](/docs/concepts/findings-and-reliability/).

## Limits

- Needs: aerial photo, aerial property facts. On a scan without them, the verdict is `unknown` and says why.
- It is slow: progress steps reach the workspace while it runs.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

<p class="verdict"><span class="st unknown">Cannot answer here</span> Scan u_testhome0001 has no location (a phone scan carries none), so the aerial photo cannot be found. Give a latitude and longitude to run this on the site.</p>

A phone scan has walls, doors, windows, rooms and objects, but no location, no photos and no property record.

## Run it

```sh
threshold run parking_count --scan <scan-id>
curl -X POST http://127.0.0.1:8787/api/tools/parking_count/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `parking_count`. See [MCP server and CLI](/docs/mcp/).
