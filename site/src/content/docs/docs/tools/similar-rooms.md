---
title: "Similar rooms"
description: "Finds rooms by what they look like ('a sunlit kitchen with an island'), with measured filters: over 12 m\u00b2, in Houston, room for a wheelchair to turn."
sidebar: {"label": "Similar rooms"}
---

Finds rooms by what they look like ('a sunlit kitchen with an island'), with measured filters: over 12 m², in Houston, room for a wheelchair to turn.

## What it answers

- A sunlit kitchen with an island, over 12 m², in Houston
- Bathrooms like this one with room to turn a wheelchair

For the agent, the tool is described as: Search a few hundred described rooms in Houston and Los Angeles by meaning, or find rooms like a given one. Filters on room type, city and measured area and turning circle in the same query. Returns rooms ranked by similarity, each with its description, measured area and a panorama to look at. Descriptions come from a vision model; sizes from the floor plan.

## Who it is for

[CoStar research lead](/docs/reference/personas/#costar-research-lead), [CoStar researcher](/docs/reference/personas/#costar-researcher), [Older adult or family](/docs/reference/personas/#older-adult-or-family), [Renter checking a listing](/docs/reference/personas/#renter-checking-a-listing), [Wheelchair user looking for a home](/docs/reference/personas/#wheelchair-user-looking-for-a-home).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `query` | string |  |  | e.g. 'sunlit kitchen with an island and white cabinets'. Asked as: "Describe the room you are looking for" |
| `scan` | string |  |  | With room: find rooms like this one. Filled from the selected building. |
| `room` | string |  |  | Room id in `scan`. Filled from the selected building. |
| `label` | string |  |  | Room type: Kitchen, Bathroom, Bedroom, Living Room, ... |
| `city` | string |  |  | Houston or Los Angeles. |
| `min_area_m2` | number (m2) |  |  | Measured floor area at least. |
| `min_turn_m` | number (m) |  |  | Largest turning circle at least. |
| `words` | number |  | `0.3` | Weight of exact word matches (BM25) against meaning. Range: at least 0, at most 1. |
| `limit` | integer |  | `8` | Range: at least 1, at most 30. |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Room descriptions | `threshold.facts.rooms` | required | The verdict is `unknown`, with the reason. |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Panel blocks: `VerdictHeader`, `EvidenceStrip`, `CheckList`, `StepLog`.
- Speed: fast. Read-only.

## How it works

Similar rooms: search inside buildings by meaning. Each indexed room has a vision-model description of its panorama, embedded locally; StreamingDiskANN (pgvectorscale) finds the nearest, filtered by room type inside the index, and measured facts (area, turning circle, city) filter in the same query. BM25 word matching (pg_textsearch) can be blended in.

## Reliability

Every metric and finding carries its layer, its method and a high, medium or low label, set by the tool for each value. See [findings and reliability](/docs/concepts/findings-and-reliability/).

## Limits

- Needs: room descriptions. On a scan without it, the verdict is `unknown` and says why.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

<p class="verdict"><span class="st unknown">Cannot answer here</span> The facts database is not configured (TIGER_DATABASE_URL)</p>

A phone scan has walls, doors, windows, rooms and objects, but no location, no photos and no property record.

## Run it

```sh
threshold run similar_rooms --scan <scan-id>
curl -X POST http://127.0.0.1:8787/api/tools/similar_rooms/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `similar_rooms`. See [MCP server and CLI](/docs/mcp/).
