---
title: "What sits below the water"
description: "Finds the belongings, appliances, outlets and utilities in the rooms that flood, how high each sits off the floor, and what the water would cost, as a range."
sidebar: {"label": "What sits below the water"}
---

Finds the belongings, appliances, outlets and utilities in the rooms that flood, how high each sits off the floor, and what the water would cost, as a range.

## What it answers

- What would I lose at two feet of water?
- Is the water heater high enough?

For the agent, the tool is described as: Inventory the rooms that can flood in one scanned house from its panoramas (vision model, cached), with each item's height off the floor, replacement-cost class and whether a person can carry it; electrical panel, water heater, furnace, washer, dryer and low outlets with heights. Totals the loss at the flood scenario as a low-high range. Pins every item.

## Who it is for

[Emergency manager or caseworker before a storm](/docs/reference/personas/#emergency-manager-or-caseworker-before-a-storm), [Houston homeowner before a storm](/docs/reference/personas/#houston-homeowner-before-a-storm), [Insurance underwriter](/docs/reference/personas/#insurance-underwriter).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `scan` | string | yes |  | Scan id. Filled from the selected building. |
| `depth_m` | number (m) | yes |  | Water above the ground outside. Asked as: "How deep could the water get above the ground outside your house, in metres? Use a storm-surge forecast (given as height above ground) or a street-flooding depth." Saved preference `flood.depth_m`. Range: at least 0, at most 3. |
| `scenario` | string |  | `"depth"` | Where the depth comes from: typed depth, storm surge, rainfall, or Harvey 2017 from USGS high-water marks (then depth_m is not used). Saved preference `flood.scenario`. One of: `depth`, `surge`, `rainfall`, `harvey_2017`. |
| `floor_height_m` | number (m) |  |  | Floor height above the ground at the door, if you measured it. Saved preference `flood.floor_height_m`. |
| `use_drone` | boolean |  | `true` | Measure the door threshold in the drone photos (vision model, cached). |
| `max_rooms` | integer |  | `8` | Most rooms to read with the vision model. Range: at least 1, at most 12. |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| 360° photos | `matterport.panoramas` | required | The verdict is `unknown`, with the reason. |
| Rooms | `matterport.rooms` | required | The verdict is `unknown`, with the reason. |
| Empty-room photos | `matterport.defurnished` | optional | The tool runs without it. |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Draws on the building: pins on what it found; a water level.
- Panel blocks: `VerdictHeader`, `MetricRow`, `Controls`, `CheckList`, `EvidenceStrip`, `FloorPlanMini`, `AssumptionChips`, `StepLog`, `ActionBar`.
- Speed: slow. Read-only.

## How it works

Valuables height: what sits below the water line, from the panoramas, with heights off the floor and a loss range.

## Reliability

Every metric and finding carries its layer, its method and a high, medium or low label, set by the tool for each value. See [findings and reliability](/docs/concepts/findings-and-reliability/).

## Limits

- Needs: 360° photos, rooms. On a scan without them, the verdict is `unknown` and says why.
- The agent asks before running it, because it reads the panoramas of every room that floods with the vision model.
- It is slow: progress steps reach the workspace while it runs.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

Inputs used: `depth_m = 0.6` (an answer given for this example).

<p class="verdict"><span class="st unknown">Unknown</span> No room that can take water has a panorama.</p>


What it reported while it ran:

1. The scan has no location, so the aerial and drone methods are off
1. Scan outdoor panoramas: none near an exterior door
1. Water levels in the scan: lo +0.10 m from the entry floor, mid +0.30 m from the entry floor, hi +0.50 m from the entry floor

## Run it

```sh
threshold run valuables_height --scan <scan-id>
curl -X POST http://127.0.0.1:8787/api/tools/valuables_height/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `valuables_height`. See [MCP server and CLI](/docs/mcp/).
