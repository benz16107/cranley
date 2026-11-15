---
title: "Site scorecard"
description: "Ranks candidate buildings against your requirements and weights, with a score per criterion, the deal-breakers and the evidence for each cell."
sidebar: {"label": "Site scorecard"}
---

Ranks candidate buildings against your requirements and weights, with a score per criterion, the deal-breakers and the evidence for each cell.

## What it answers

- Find me a 40,000 to 80,000 ft² distribution warehouse in Houston under $12 a foot with 24 ft clear
- Compare these three office buildings for a 120-person team
- Score these retail sites for our next store

For the agent, the tool is described as: The enterprise site-selection scorecard. A business gives a profile (office, industrial, retail, flex), requirements (size range or headcount, budget per ft², docks, clear height, parking ratio, step-free entrance, highway and transit distance, flood tolerance, employee home zips) and optional weights; give 2 to 10 candidates (scans, CoStar properties, addresses, points) or none to search CoStar listings around the selected place (it is included) or in Houston or Los Angeles. Returns a ranked table, per-criterion checks with evidence and source, and deal-breakers. `deep` also runs industrial_fit or retail_site on each candidate.

## Who it is for

[Commercial property underwriter](/docs/reference/personas/#commercial-property-underwriter), [CoStar researcher](/docs/reference/personas/#costar-researcher), [Industrial tenant rep](/docs/reference/personas/#industrial-tenant-rep), [Office relocation lead](/docs/reference/personas/#office-relocation-lead), [Retail site selector](/docs/reference/personas/#retail-site-selector).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `profile` | string | yes |  | Asked as: "What kind of space is it: office, industrial (warehouse or distribution), retail or flex?" Saved preference `site.profile`. One of: `office`, `industrial`, `retail`, `flex`. |
| `candidates` | array |  | `[]` | Buildings to compare (scans, CoStar properties, addresses or points); empty to find candidates. |
| `place` | Place |  |  | With no candidates: this building and the CoStar properties for lease around it. Filled from the selected building. |
| `search_km` | number (km) |  | `25` | Search radius around `place`. Range: at least 1, at most 80. |
| `city` | string |  |  | With no candidates and no place: search this city. |
| `max_candidates` | integer |  | `5` | How many candidates a search keeps. Range: at least 2, at most 10. |
| `size_min_sf` | number (ft²) |  |  | Smallest space that works. Saved preference `site.size_min_sf`. |
| `size_max_sf` | number (ft²) |  |  | Largest space wanted. Saved preference `site.size_max_sf`. |
| `budget_sf_yr` | number ($/ft²/yr) |  |  | Highest asking rent per ft² per year. Saved preference `site.budget_sf_yr`. |
| `headcount` | integer |  |  | People to house; sets the size range when none is given. Saved preference `office.headcount`. |
| `docks_min` | integer |  |  | Dock doors needed. Saved preference `site.docks_min`. |
| `clear_height_min_ft` | number (ft) |  |  | Clear height needed under the structure. Saved preference `site.clear_height_min_ft`. |
| `parking_ratio_min` | number (per 1,000 ft²) |  |  | Parking spaces per 1,000 ft² needed. Saved preference `site.parking_ratio_min`. |
| `step_free` | boolean |  | `false` | Needs a step-free entrance (ADA). Saved preference `site.step_free`. |
| `highway_max_km` | number (km) |  |  | Furthest acceptable distance to a highway on-ramp. Saved preference `site.highway_max_km`. |
| `transit_max_m` | number (m) |  |  | Furthest acceptable walk to a bus stop or station. Saved preference `site.transit_max_m`. |
| `flood` | string |  | `"prefer_outside"` | Flood risk tolerance: avoid the 1% zone outright, prefer outside it, or ignore it. Saved preference `site.flood`. One of: `avoid`, `prefer_outside`, `any`. |
| `employees` | array |  | `[]` | Home zip codes (77002:12 for 12 people) or lon,lat points, for commutes. Saved preference `commute.employees`. |
| `weights` | object |  | `{}` | Weight per criterion, 0 to 5; overrides the profile's defaults. |
| `must` | array |  |  | Criteria a candidate must meet; default per profile. |
| `deep` | boolean |  | `false` | Also run the profile's site tool on each candidate (slow, cached). |
| `use_osm` | boolean |  | `true` | Look up highways, transit and substations in OpenStreetMap (cached). |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Property record | `costar.property` | required | The verdict is `unknown`, with the reason. |
| Osm | `osm` | optional | no distances |
| Rooms | `matterport.rooms` | optional | record values only |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Panel blocks: `VerdictHeader`, `MetricRow`, `RankedTable`, `MiniChart`, `CheckList`, `EvidenceStrip`, `AssumptionChips`, `ActionBar`, `StepLog`.
- Its own ranked table: Score.
- Speed: slow. Read-only.

## How it works

Site scorecard: rank 2 to 10 candidate buildings against a business's requirements and weights.

## Reliability

Every metric and finding carries its layer, its method and a high, medium or low label, set by the tool for each value. See [findings and reliability](/docs/concepts/findings-and-reliability/).

## Limits

- Needs: property record. On a scan without it, the verdict is `unknown` and says why.
- It is slow: progress steps reach the workspace while it runs.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

<p class="verdict"><span class="st unknown">Cannot answer here</span> Give candidate buildings, or a place or a city (Houston or Los Angeles) to search.</p>

A phone scan has walls, doors, windows, rooms and objects, but no location, no photos and no property record.

## Run it

```sh
threshold run site_scorecard -i place='{"scan": "<scan-id>"}'
curl -X POST http://127.0.0.1:8787/api/tools/site_scorecard/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `site_scorecard`. See [MCP server and CLI](/docs/mcp/).
