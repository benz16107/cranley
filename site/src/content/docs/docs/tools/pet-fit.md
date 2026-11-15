---
title: "Pet fit"
description: "Whether a home suits your dog, cat or small animal: stairs, floors, a crate and litter spot, a pet door, fall-risk windows, the yard's size, slope, shade and fence, the pool, busy roads, the pet policy and fees, and dog parks and vets nearby."
sidebar: {"label": "Pet fit"}
---

Whether a home suits your dog, cat or small animal: stairs, floors, a crate and litter spot, a pet door, fall-risk windows, the yard's size, slope, shade and fence, the pool, busy roads, the pet policy and fees, and dog parks and vets nearby.

## What it answers

- Is this house good for my 70 lb lab?
- Does this apartment allow a dog over 50 lb?
- Can my older dog live here without stairs?
- Is it safe for an indoor cat?

For the agent, the tool is described as: Per pet profile (dog by weight and age, indoor or outdoor cat, small animal), a verdict with reasons for one home: from the scan (stairs, open floor, floor finishes read in the panoramas, a crate or pen spot, a litter box 3 m from food, a pet door candidate with the route to the yard, upper-floor windows and balconies), from Vexcel (yard behind the house, flat share from ground heights, tree shade, fence, pool), from CoStar (the community's pet policy, weight limit, pet rent and fees; the listing's fence, floor and pet lines) and OpenStreetMap (busy road, next building, dog parks, vets, emergency vets). Works on a house, an apartment unit, a phone scan (indoor only) or a point (outdoor only).

## Who it is for

[Cat owner in an apartment](/docs/reference/personas/#cat-owner-in-an-apartment), [Dog owner choosing a home](/docs/reference/personas/#dog-owner-choosing-a-home), [Older dog that cannot do stairs](/docs/reference/personas/#older-dog-that-cannot-do-stairs).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `scan` | string |  |  | Scan id, if the site has one. Filled from the selected building. |
| `property_id` | integer |  |  | CoStar PropertyId, for a commercial address. |
| `lat` | number |  |  | Latitude, for an address with no scan. |
| `lon` | number |  |  | Longitude, for an address with no scan. |
| `pets` | array |  | `[]` | One profile per pet; each gets its own verdict. Empty: built from the fields below. Saved preference `pets.profile`. |
| `dog_lb` | number (lb) |  |  | A dog's weight, in pounds. Saved preference `pets.dog_lb`. |
| `dog_age` | string |  | `"adult"` | The dog's age. Saved preference `pets.dog_age`. One of: `young`, `adult`, `senior`. |
| `cat` | string |  | `"none"` | A cat, indoor or outdoor. Saved preference `pets.cat`. One of: `none`, `indoor`, `outdoor`. |
| `small_animal` | boolean |  | `false` | A rabbit, guinea pig, bird or reptile. |
| `use_vision` | boolean |  | `true` | Read floor finishes in the panoramas and a fence from the aerial photo (cached). |
| `nearby` | boolean |  | `true` | Look up dog parks, vets and trails in OpenStreetMap (cached). |
| `riser_m` | number (m) |  | `0.178` | Saved preference `access.riser_m`. Range: more than 0.1, at most 0.25. |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Rooms | `matterport.rooms` | required | The verdict is `unknown`, with the reason. |
| Aerial property facts | `vexcel.property` | optional | The tool runs without it. |
| Property record | `costar.property` | optional | The tool runs without it. |
| Places | `osm.places` | optional | The tool runs without it. |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Draws on the building: a box or 3D model placed in the room; a route with its narrow points; pins on what it found; doors, walls or rooms coloured by status.
- Panel blocks: `VerdictHeader`, `MetricRow`, `CheckList`, `EvidenceStrip`, `FloorPlanMini`, `AssumptionChips`, `StepLog`.
- Speed: slow. Read-only.

## How it works

Pet fit: is this home right for these pets? Per pet profile (a dog by weight and age, an indoor or outdoor cat, a small animal), a verdict with reasons, from the scan (stairs, open floor, floor finishes, a crate or pen spot, a litter box away from food, a pet door to the yard, windows and balconies a cat could fall from), the air (yard off the footprint, flat share from Vexcel ground heights, tree shade, a fence, the pool), the records (the apartment community's pet policy, weight limit and fees; the listing's fence, floor and pet lines), and OpenStreetMap (busy road, next building, dog parks, vets, emergency vets, trails).

## Reliability

Sources this tool gave on the test home:

| Where it came from | Layer | Method | Reliability | Note |
|---|---|---|---|---|
| Measured from the scan | `matterport` | `geometry` | low | Floor heights from the panoramas; the step count is the rise over a 17.8 cm riser |
| Measured from the scan | `matterport` | `geometry` | medium | Matterport wall graph, empty rooms |
| Measured from a model | `model` | `geometry` | medium | Rules over the measured checks; see each check's source |

The tool sets the label for each value. A model never does. The tools give a scan's wall graph the layer `matterport` whichever device made the scan, so a phone scan's geometry carries that label too.

## Limits

- Needs: rooms. On a scan without it, the verdict is `unknown` and says why.
- It is slow: progress steps reach the workspace while it runs.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

Inputs used: `pets = [{"kind": "cat", "outdoor": false}]` (preset of the persona "Cat owner in an apartment"); `cat = "indoor"` (preset of the persona "Cat owner in an apartment").

<p class="verdict"><span class="st pass">Pass</span> Indoor cat: fits.</p>

| Value | Result | Where it came from | Reliability |
|---|---|---|---|
| Most steps from the entrance floor (estimate) | <span class="num">0 steps</span> | Measured from the scan | low |
| Longest open room | <span class="num">5.89 m</span> | Measured from the scan | medium |

| Check | Measured | Against | Status |
|---|---|---|---|
| Indoor cat: A litter box spot away from food | <span class="num">7.55</span> | <span class="num">3 m</span> | <span class="st pass">pass</span> |
| Indoor cat: Upper-floor windows and balconies screened | <span class="num">0</span> | <span class="num">0 openings</span> | <span class="st pass">pass</span> |

Findings: 5 pass.

What it reported while it ran:

1. Home; records: none in the kit
1. Indoors: 1 floors, 1 exterior doors for a pet door, 0 upper-floor windows

## Run it

```sh
threshold run pet_fit --scan <scan-id>
curl -X POST http://127.0.0.1:8787/api/tools/pet_fit/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `pet_fit`. See [MCP server and CLI](/docs/mcp/).
