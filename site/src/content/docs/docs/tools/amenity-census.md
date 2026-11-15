---
title: "Amenity census"
description: "Finds and counts a community's amenities in its scans (gym equipment, laundry machines, pool, lounge, business centre, mail room, playground) and sets them beside what the listing claims."
sidebar: {"label": "Amenity census"}
---

Finds and counts a community's amenities in its scans (gym equipment, laundry machines, pool, lounge, business centre, mail room, playground) and sets them beside what the listing claims.

## What it answers

- What amenities does this community really have?
- How many treadmills are in the gym?

For the agent, the tool is described as: For one apartment community (a scan of it, or its CoStar property id), read its amenity scans and list each amenity seen with evidence and counts (gym equipment, washers and dryers, parcel lockers), beside the listing's claims (scan titles, photo captions). Flags claims no scan shows and amenities the listing never mentions. Slow on first run.

## Who it is for

[Amenity auditor](/docs/reference/personas/#amenity-auditor), [Apartment manager](/docs/reference/personas/#apartment-manager), [Cat owner in an apartment](/docs/reference/personas/#cat-owner-in-an-apartment), [CoStar researcher](/docs/reference/personas/#costar-researcher), [Renter checking a listing](/docs/reference/personas/#renter-checking-a-listing).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `scan` | string |  |  | Any scan of the community. Filled from the selected building. |
| `property` | integer |  |  | CoStar property id of the community. |
| `max_scans_read` | integer |  | `8` | At most this many amenity scans are read by the model. Range: at least 1, at most 30. |
| `count_equipment` | boolean |  | `true` | Count gym equipment and laundry machines (one model call per view). |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Property record | `costar.property` | required | The verdict is `unknown`, with the reason. |
| 360° photos | `matterport.panos` | required | The verdict is `unknown`, with the reason. |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Draws on the building: pins on what it found.
- Panel blocks: `VerdictHeader`, `MetricRow`, `CheckList`, `MiniChart`, `EvidenceStrip`, `StepLog`.
- Speed: slow. Read-only.

## How it works

Amenity census: for an apartment community, which amenities its scans show, with counts of gym equipment and laundry machines, each with the panorama that proves it, beside what the listing claims (scan titles and photo captions).

## Reliability

Every metric and finding carries its layer, its method and a high, medium or low label, set by the tool for each value. See [findings and reliability](/docs/concepts/findings-and-reliability/).

## Limits

- Needs: property record, 360° photos. On a scan without them, the verdict is `unknown` and says why.
- The agent asks before running it, because it reads the panoramas of every amenity scan with the vision model.
- It is slow: progress steps reach the workspace while it runs.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

<p class="verdict"><span class="st unknown">Cannot answer here</span> This scan does not belong to an apartment community in the CoStar kit, so there are no shared amenities to count. Pick a scan of a community, or give its property id.</p>

A phone scan has walls, doors, windows, rooms and objects, but no location, no photos and no property record.

## Run it

```sh
threshold run amenity_census --scan <scan-id>
curl -X POST http://127.0.0.1:8787/api/tools/amenity_census/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `amenity_census`. See [MCP server and CLI](/docs/mcp/).
