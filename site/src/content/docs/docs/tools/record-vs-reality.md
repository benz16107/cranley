---
title: "Record versus reality"
description: "Sets each fact in the CoStar or listing record beside what the scan and the aerial photo measure, with the evidence."
sidebar: {"label": "Record versus reality"}
---

Sets each fact in the CoStar or listing record beside what the scan and the aerial photo measure, with the evidence.

## What it answers

- Does this listing match the scan?
- Is the record's square footage right?
- How many parking spaces does it really have?

For the agent, the tool is described as: For one scan, compare every checkable claim in its CoStar property record or residential listing (area, bedrooms, bathrooms, stories, ceiling height, parking, sprinklers, dock doors, pool, listing feature sentences, the scan title) with what the plan, panoramas and aerial photo measure. Returns one check and one finding per claim with a verdict: confirmed, contradicted or cannot verify. Set deep=true to read the aerial photo and panoramas.

## Who it is for

[Apartment manager](/docs/reference/personas/#apartment-manager), [CoStar research lead](/docs/reference/personas/#costar-research-lead), [CoStar researcher](/docs/reference/personas/#costar-researcher), [Insurance underwriter](/docs/reference/personas/#insurance-underwriter), [Renter checking a listing's claims](/docs/reference/personas/#renter-checking-a-listings-claims), [Renter checking a listing](/docs/reference/personas/#renter-checking-a-listing).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `scan` | string | yes |  | Scan id. Filled from the selected building. |
| `deep` | boolean |  | `false` | Also read the aerial photo and the panoramas (slower; uses the shared aerial and vision services). Saved preference `truth.deep`. |
| `area_low` | number |  | `0.85` | Lowest share of a listed area the measured interior area may be and still confirm it (interior area runs below a gross listed area). Saved preference `truth.area_low`. Range: at least 0.5, at most 1.0. |
| `area_high` | number |  | `1.05` | Highest share of a listed area the measured interior area may be. Saved preference `truth.area_high`. Range: at least 1.0, at most 1.5. |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Property record | `costar.property` | required | The verdict is `unknown`, with the reason. |
| Rooms | `matterport.rooms` | required | The verdict is `unknown`, with the reason. |
| Room names | `matterport.room_labels` | optional | The tool runs without it. |
| Aerial photo | `vexcel.ortho` | optional | aerial claims cannot be verified |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Draws on the building: doors, walls or rooms coloured by status; pins on what it found.
- Panel blocks: `VerdictHeader`, `MetricRow`, `CheckList`, `EvidenceStrip`, `FloorPlanMini`, `AssumptionChips`, `StepLog`, `ActionBar`.
- Speed: slow. Read-only.

## How it works

Record versus reality: every checkable claim in a scan's CoStar or listing record beside what the data measures.

## Reliability

Every metric and finding carries its layer, its method and a high, medium or low label, set by the tool for each value. See [findings and reliability](/docs/concepts/findings-and-reliability/).

## Limits

- Needs: property record, rooms. On a scan without them, the verdict is `unknown` and says why.
- It is slow: progress steps reach the workspace while it runs.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

<p class="verdict"><span class="st unknown">Cannot answer here</span> This scan has no CoStar or listing record, and its title states no size or room count, so there is nothing to check it against.</p>

A phone scan has walls, doors, windows, rooms and objects, but no location, no photos and no property record.

## Run it

```sh
threshold run record_vs_reality --scan <scan-id>
curl -X POST http://127.0.0.1:8787/api/tools/record_vs_reality/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `record_vs_reality`. See [MCP server and CLI](/docs/mcp/).
