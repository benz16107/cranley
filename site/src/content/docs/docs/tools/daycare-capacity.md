---
title: "Daycare capacity"
description: "How many children this space could be licensed for: indoor room area, outdoor play area, toilets and sinks against the Texas or California rule, with the limiting factor named."
sidebar: {"label": "Daycare capacity"}
---

How many children this space could be licensed for: indoor room area, outdoor play area, toilets and sinks against the Texas or California rule, with the limiting factor named.

## What it answers

- How many kids could I license here?
- Is there enough outdoor play space for a daycare?

For the agent, the tool is described as: For a scanned building in Houston (Texas, 26 TAC 746) or Los Angeles (California, 22 CCR 101238): indoor activity area from the scan's labelled rooms (bathrooms, kitchens, halls, offices and storage left out), outdoor play area from the aerial parcel less building, pool and paving, toilets and sinks counted in the panoramas, each turned into a child count by the state rule. Returns the capacity, the limiting factor, room highlights and the play-area outline on the map.

## Who it is for

[Daycare operator](/docs/reference/personas/#daycare-operator).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `scan` | string |  |  | Scan id, if the site has one. Filled from the selected building. |
| `property_id` | integer |  |  | CoStar PropertyId, for a commercial address. |
| `lat` | number |  |  | Latitude, for an address with no scan. |
| `lon` | number |  |  | Longitude, for an address with no scan. |
| `state` | string |  |  | TX or CA; from the location when left out. |
| `use_vision` | boolean |  | `true` | Count toilets and sinks in the panoramas with the vision model (cached). |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Rooms | `matterport.rooms` | required | The verdict is `unknown`, with the reason. |
| Room names | `matterport.room_labels` | required | The verdict is `unknown`, with the reason. |
| Aerial property facts | `vexcel.property` | required | The verdict is `unknown`, with the reason. |
| 360° photos | `matterport.panos` | optional | The tool runs without it. |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Draws on the building: doors, walls or rooms coloured by status; a route with its narrow points; pins on what it found.
- Panel blocks: `VerdictHeader`, `MetricRow`, `CheckList`, `FloorPlanMini`, `EvidenceStrip`, `AssumptionChips`, `StepLog`.
- Speed: slow. Read-only.

## How it works

Daycare capacity: could this space be licensed as a child-care centre, and for how many children? Indoor activity area from the scan, outdoor play area from the aerial photo, toilets and sinks from the panoramas, each against the state rule. The capacity is the smallest of the four, and the limiting one is named.

## Reliability

Every metric and finding carries its layer, its method and a high, medium or low label, set by the tool for each value. See [findings and reliability](/docs/concepts/findings-and-reliability/).

## Limits

- Needs: rooms, room names, aerial property facts. On a scan without them, the verdict is `unknown` and says why.
- It is slow: progress steps reach the workspace while it runs.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

<p class="verdict"><span class="st unknown">Cannot answer here</span> Scan u_testhome0001 has no location (a phone scan carries none), so the aerial photo cannot be found. Give a latitude and longitude to run this on the site.</p>

A phone scan has walls, doors, windows, rooms and objects, but no location, no photos and no property record.

## Run it

```sh
threshold run daycare_capacity --scan <scan-id>
curl -X POST http://127.0.0.1:8787/api/tools/daycare_capacity/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `daycare_capacity`. See [MCP server and CLI](/docs/mcp/).
