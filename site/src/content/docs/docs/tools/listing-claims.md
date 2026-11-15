---
title: "Listing claims"
description: "Checks what a listing says against the scan, and lists what it leaves out."
sidebar: {"label": "Listing claims"}
---

Checks what a listing says against the scan, and lists what it leaves out.

## What it answers

- Is this listing honest?
- What does the listing not tell me?

For the agent, the tool is described as: For one scan and a listing (pasted text, or the scan's own listing when text is empty): extracts each claim (bedrooms, bathrooms, area, stories, ceilings, light, facing, parking, fireplace, island, walk-in closet, hardwood, laundry, garage, pool), checks it against the scan and aerial photo, and adds what the listing does not say: bedrooms with no window, bathrooms reached only through a bedroom, bedrooms with no closet, low ceilings.

## Who it is for

[Renter checking a listing's claims](/docs/reference/personas/#renter-checking-a-listings-claims), [Renter checking a listing](/docs/reference/personas/#renter-checking-a-listing).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `scan` | string | yes |  | Scan id. Filled from the selected building. |
| `text` | string |  |  | Listing text to check; empty uses the scan's own listing. Asked as: "Paste the listing text, or leave it empty to use this scan's own listing." |
| `deep` | boolean |  | `false` | Also read the aerial photo and the panoramas. Saved preference `truth.deep`. |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Rooms | `matterport.rooms` | required | The verdict is `unknown`, with the reason. |
| Doors and windows | `matterport.openings` | optional | The tool runs without it. |
| Listing | `costar.listing` | optional | pasted listing text |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Draws on the building: doors, walls or rooms coloured by status; pins on what it found.
- Panel blocks: `VerdictHeader`, `MetricRow`, `CheckList`, `EvidenceStrip`, `FloorPlanMini`, `AssumptionChips`, `StepLog`, `ActionBar`.
- Speed: fast. Read-only.

## How it works

Listing claims: the renter's check. Every claim in a listing's text and record, checked against the scan, plus what the listing leaves out that the scan shows (a bedroom with no window, a bathroom reached only through a bedroom, bedrooms with no closet, a low ceiling).

## Reliability

Every metric and finding carries its layer, its method and a high, medium or low label, set by the tool for each value. See [findings and reliability](/docs/concepts/findings-and-reliability/).

## Limits

- Needs: rooms. On a scan without it, the verdict is `unknown` and says why.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

<p class="verdict"><span class="st unknown">Cannot answer here</span> This scan has no listing, so there is nothing to check. Paste the listing text to check it.</p>

A phone scan has walls, doors, windows, rooms and objects, but no location, no photos and no property record.

## Run it

```sh
threshold run listing_claims --scan <scan-id>
curl -X POST http://127.0.0.1:8787/api/tools/listing_claims/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `listing_claims`. See [MCP server and CLI](/docs/mcp/).
