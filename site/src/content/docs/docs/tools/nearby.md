---
title: "Nearby"
description: "Parks, playgrounds, schools, sports courts and fields, vets, shops and transit near a home, with the walk or ride to the nearest of each along the streets."
sidebar: {"label": "Nearby"}
---

Parks, playgrounds, schools, sports courts and fields, vets, shops and transit near a home, with the walk or ride to the nearest of each along the streets.

## What it answers

- Is there a playground within a 10-minute walk?
- How far is the nearest pickleball court?
- Where is the closest emergency vet?

For the agent, the tool is described as: Places near a scan, CoStar property or point from OpenStreetMap (cached), by profile (pets: dog parks, vets, emergency vets, trails; kids: playgrounds, parks, schools by level, libraries, pools, childcare; sports: tennis, pickleball, basketball, soccer, baseball, pools, gyms, climbing, golf, skate parks, tracks, bike paths, ice rinks; everyday: grocery, pharmacy, transit, coffee) or any categories. Walking or cycling minutes along the street network, busy roads crossed, pins and routes on the map.

## Who it is for

[Cat owner in an apartment](/docs/reference/personas/#cat-owner-in-an-apartment), [Dog owner choosing a home](/docs/reference/personas/#dog-owner-choosing-a-home), [Parent with young kids choosing a home](/docs/reference/personas/#parent-with-young-kids-choosing-a-home), [Tennis or pickleball player](/docs/reference/personas/#tennis-or-pickleball-player), [Older dog that cannot do stairs](/docs/reference/personas/#older-dog-that-cannot-do-stairs), [Family with a teenager who plays soccer](/docs/reference/personas/#family-with-a-teenager-who-plays-soccer).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `scan` | string |  |  | Scan id, if the site has one. Filled from the selected building. |
| `property_id` | integer |  |  | CoStar PropertyId, for a commercial address. |
| `lat` | number |  |  | Latitude, for an address with no scan. |
| `lon` | number |  |  | Longitude, for an address with no scan. |
| `profile` | string |  |  | A ready-made set of categories. Asked as: "What should be near the home? pets, kids, sports or everyday (grocery, pharmacy, transit, coffee)" Saved preference `nearby.profile`. |
| `categories` | array |  | `[]` | Categories to look for, added to the profile's. Sports: trail, pool, tennis, pickleball, basketball, soccer, baseball, gym, climbing, golf, skate_park, running_track, cycleway, ice_rink. Saved preference `nearby.categories`. |
| `mode` | string |  | `"walk"` | Walking or cycling time. Saved preference `nearby.mode`. One of: `walk`, `cycle`. |
| `ok_min` | number (min) |  | `10` | Minutes counted as close. Saved preference `nearby.ok_min`. Range: more than 0, at most 60. |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Places | `osm.places` | required | The verdict is `unknown`, with the reason. |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Draws on the building: pins on what it found; a route with its narrow points.
- Panel blocks: `VerdictHeader`, `MetricRow`, `CheckList`, `MiniChart`, `AssumptionChips`, `StepLog`.
- Speed: fast. Read-only.

## How it works

Nearby: parks, playgrounds, schools, courts and fields, vets, shops and transit around a home, with the walk or ride along the street network to the nearest of each. One profile (pets, kids, sports, everyday) or any categories the person picks. `report()` is shared by pet_fit and kids_fit so all three answer the same way.

## Reliability

Every metric and finding carries its layer, its method and a high, medium or low label, set by the tool for each value. See [findings and reliability](/docs/concepts/findings-and-reliability/).

## Limits

- Needs: osm.places. On a scan without it, the verdict is `unknown` and says why.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

<p class="verdict"><span class="st unknown">Cannot answer here</span> Scan u_testhome0001 has no location (a phone scan carries none), so the aerial photo cannot be found. Give a latitude and longitude to run this on the site.</p>

A phone scan has walls, doors, windows, rooms and objects, but no location, no photos and no property record.

## Run it

```sh
threshold run nearby --scan <scan-id>
curl -X POST http://127.0.0.1:8787/api/tools/nearby/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `nearby`. See [MCP server and CLI](/docs/mcp/).
