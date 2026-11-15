---
title: "Home search for pets and kids"
description: "Finds scanned homes across Houston or Los Angeles that suit your pets or kids: apartments that allow your dog's weight or cats, houses with a fenced, flat yard and no pool, near playgrounds, parks or dog parks."
sidebar: {"label": "Home search for pets and kids"}
---

Finds scanned homes across Houston or Los Angeles that suit your pets or kids: apartments that allow your dog's weight or cats, houses with a fenced, flat yard and no pool, near playgrounds, parks or dog parks.

## What it answers

- Houston houses with a flat yard over 100 m2 and no pool
- LA apartments that allow dogs over 50 lb
- Houston homes within a 10-minute walk of a playground and a park

For the agent, the tool is described as: City-wide search over the scanned homes. Apartments: by the community's CoStar pet policy (dog_lb: allows a dog this heavy; cats; max_pet_rent). Houses: fenced (listing), no_pool (Vexcel, else the listing), min_yard_m2 and min_flat_pct (measured by earlier pet_fit runs; yard area also from cached Vexcel answers), and near: categories each within walk_min (straight-line estimate from one city-wide OpenStreetMap request). Says how many homes could answer each criterion. Pins the matches.

## Who it is for

[Cat owner in an apartment](/docs/reference/personas/#cat-owner-in-an-apartment), [Dog owner choosing a home](/docs/reference/personas/#dog-owner-choosing-a-home), [Parent with young kids choosing a home](/docs/reference/personas/#parent-with-young-kids-choosing-a-home), [Tennis or pickleball player](/docs/reference/personas/#tennis-or-pickleball-player), [Older dog that cannot do stairs](/docs/reference/personas/#older-dog-that-cannot-do-stairs), [Family with a teenager who plays soccer](/docs/reference/personas/#family-with-a-teenager-who-plays-soccer).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `city` | string | yes |  | Asked as: "Which city, Houston or Los Angeles?" Saved preference `search.city`. One of: `Houston`, `Los Angeles`. |
| `kind` | string |  | `"house"` | Houses or apartments. Saved preference `search.kind`. One of: `house`, `apartment_unit`. |
| `dog_lb` | number |  |  | Apartments: the community allows a dog of this weight. |
| `cats` | boolean |  | `false` | Apartments: the community allows cats. |
| `max_pet_rent` | number |  |  | Apartments: monthly pet rent at most this, in dollars. |
| `fenced` | boolean |  | `false` | Houses: the listing says the yard is fenced. |
| `no_pool` | boolean |  | `false` | Houses: no pool (Vexcel, else the listing). |
| `min_yard_m2` | number |  |  | Houses: yard at least this big (behind the house when pet_fit measured it). |
| `min_flat_pct` | number |  |  | Houses: at least this share of the back yard flat (pet_fit runs only). |
| `near` | array |  | `[]` | Each of these within `walk_min` (straight-line estimate). |
| `near_set` | string |  |  | A common set of places to be near, added to `near`. |
| `walk_min` | number (min) |  | `10` | Walk for `near`. Range: more than 0, at most 60. |
| `limit` | integer |  | `20` | Range: at least 1, at most 100. |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Property record | `costar.property` | required | The verdict is `unknown`, with the reason. |
| Places | `osm.places` | optional | The tool runs without it. |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Draws on the building: pins on what it found.
- Panel blocks: `VerdictHeader`, `MetricRow`, `RankedTable`, `CheckList`, `StepLog`.
- Its own ranked table: Yard (m2), Dog limit (lb), Walk to the farthest place asked (min).
- Speed: fast. Read-only.

## How it works

Home search for pets and kids: scanned homes across Houston or Los Angeles filtered by what pet owners and parents ask. Apartments by the community's pet policy (dogs up to a weight, cats, pet rent) from the CoStar kit; houses by the listing (fenced yard, no pool, pet friendly), the yard measured by pet_fit runs or worked out from cached Vexcel answers, and the distance to playgrounds, parks, dog parks, schools or courts from one city-wide OpenStreetMap request. Nothing here calls Vexcel or Matterport: homes no earlier run has measured cannot answer a yard criterion, and the result says how many could.

## Reliability

Every metric and finding carries its layer, its method and a high, medium or low label, set by the tool for each value. See [findings and reliability](/docs/concepts/findings-and-reliability/).

## Limits

- Needs: property record. On a scan without it, the verdict is `unknown` and says why.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

Not run: it needs `city`, which only a person or a phone on site can give.

## Run it

```sh
threshold run home_search
curl -X POST http://127.0.0.1:8787/api/tools/home_search/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `home_search`. See [MCP server and CLI](/docs/mcp/).
