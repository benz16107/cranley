---
title: "Path to water"
description: "Traces every route a small child could take from each bedroom to the pool and names the missing barrier."
sidebar: {"label": "Path to water"}
---

Traces every route a small child could take from each bedroom to the pool and names the missing barrier.

## What it answers

- Could my toddler get from the bedroom to the pool?
- Which door needs an alarm?

For the agent, the tool is described as: For a scanned house with a pool: places the floor plan on the aerial footprint (checked per house), finds exterior doors that open toward the pool, traces routes from each bedroom through the wall graph and across the yard, inspects each pool-side door in the panoramas (self-closing, high latch, pet door, alarm), checks the yard for a pool fence or cover from the air, and judges each route against CPSC Pub. 362. Returns routes (scan frame and map), pins, checks and a fix list.

## Who it is for

[Daycare operator](/docs/reference/personas/#daycare-operator), [Dog owner choosing a home](/docs/reference/personas/#dog-owner-choosing-a-home), [Houston homeowner before a storm](/docs/reference/personas/#houston-homeowner-before-a-storm), [Insurance underwriter](/docs/reference/personas/#insurance-underwriter), [Older adult or family](/docs/reference/personas/#older-adult-or-family), [Parent with young kids choosing a home](/docs/reference/personas/#parent-with-young-kids-choosing-a-home), [Parent of a toddler, house with a pool](/docs/reference/personas/#parent-of-a-toddler-house-with-a-pool).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `scan` | string |  |  | Scan id, if the site has one. Filled from the selected building. |
| `property_id` | integer |  |  | CoStar PropertyId, for a commercial address. |
| `lat` | number |  |  | Latitude, for an address with no scan. |
| `lon` | number |  |  | Longitude, for an address with no scan. |
| `max_doors` | integer |  | `3` | Pool-side doors to inspect in the panoramas. Range: at least 1, at most 6. |
| `use_vision` | boolean |  | `true` | Inspect doors and the yard with the vision model (cached). |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Doors and windows | `matterport.openings` | required | The verdict is `unknown`, with the reason. |
| Room names | `matterport.room_labels` | required | The verdict is `unknown`, with the reason. |
| 360° photos | `matterport.panos` | required | The verdict is `unknown`, with the reason. |
| Aerial property facts | `vexcel.property` | required | The verdict is `unknown`, with the reason. |
| Aerial photo | `vexcel.ortho` | required | The verdict is `unknown`, with the reason. |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Draws on the building: a route with its narrow points; pins on what it found.
- Panel blocks: `VerdictHeader`, `MetricRow`, `CheckList`, `EvidenceStrip`, `FloorPlanMini`, `Note`, `StepLog`.
- Speed: slow. Read-only.

## How it works

Path to water: every route a small child could take from each bedroom to the pool, through the house and across the yard, each door on the way inspected in the panoramas, and the missing barrier named against the US Consumer Product Safety Commission's pool barrier guidance.

## Reliability

Every metric and finding carries its layer, its method and a high, medium or low label, set by the tool for each value. See [findings and reliability](/docs/concepts/findings-and-reliability/).

## Limits

- Needs: doors and windows, room names, 360° photos, aerial property facts, aerial photo. On a scan without them, the verdict is `unknown` and says why.
- It is slow: progress steps reach the workspace while it runs.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

<p class="verdict"><span class="st unknown">Cannot answer here</span> Scan u_testhome0001 has no location (a phone scan carries none), so the aerial photo cannot be found. Give a latitude and longitude to run this on the site.</p>

A phone scan has walls, doors, windows, rooms and objects, but no location, no photos and no property record.

## Run it

```sh
threshold run path_to_water --scan <scan-id>
curl -X POST http://127.0.0.1:8787/api/tools/path_to_water/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `path_to_water`. See [MCP server and CLI](/docs/mcp/).
