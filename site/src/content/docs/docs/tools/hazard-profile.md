---
title: "Hazard profile"
description: "Every hazard map at an address in one place: FEMA flood zone, hurricane evacuation zone, storm surge, Hurricane Harvey's high-water marks nearby, sea level rise, earthquake faults, liquefaction and landslide zones, fire hazard zones, urban heat, traffic noise, and weather alerts, earthquakes and wildfires now."
sidebar: {"label": "Hazard profile"}
---

Every hazard map at an address in one place: FEMA flood zone, hurricane evacuation zone, storm surge, Hurricane Harvey's high-water marks nearby, sea level rise, earthquake faults, liquefaction and landslide zones, fire hazard zones, urban heat, traffic noise, and weather alerts, earthquakes and wildfires now.

## What it answers

- Is this house in a flood zone?
- What hazards should a family know about here?
- Is this on a fault?

For the agent, the tool is described as: All public hazard layers at one place in Houston or Los Angeles: FEMA flood zone, transportation noise, urban heat, sea level rise 3 and 6 ft, weather alerts now, earthquakes and wildfires nearby; Houston also hurricane evacuation zone, airport noise, category 3 storm surge and Harvey high-water marks; Los Angeles also Alquist-Priolo fault, liquefaction and landslide zones and CAL FIRE fire hazard severity. Each row says its source; a blank map means not mapped, not no risk.

## Who it is for

[Family checking a neighbourhood](/docs/reference/personas/#family-checking-a-neighbourhood), [Remote worker](/docs/reference/personas/#remote-worker).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `place` | Place | yes |  | Where a tool runs when it does not need a scan: a scan id, a CoStar property id (all its scans), an address,. Filled from the selected building. |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Hazards | `public.hazards` | required | The verdict is `unknown`, with the reason. |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Panel blocks: `VerdictHeader`, `MetricRow`, `CheckList`, `StepLog`.
- Speed: fast. Read-only.

## How it works

Hazard profile: every hazard map at one address in one result.

## Reliability

Every metric and finding carries its layer, its method and a high, medium or low label, set by the tool for each value. See [findings and reliability](/docs/concepts/findings-and-reliability/).

## Limits

- Needs: public.hazards. On a scan without it, the verdict is `unknown` and says why.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

<p class="verdict"><span class="st unknown">Cannot answer here</span> This place has no location, so no hazard map can be read.</p>

A phone scan has walls, doors, windows, rooms and objects, but no location, no photos and no property record.

## Run it

```sh
threshold run hazard_profile -i place='{"scan": "<scan-id>"}'
curl -X POST http://127.0.0.1:8787/api/tools/hazard_profile/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `hazard_profile`. See [MCP server and CLI](/docs/mcp/).
