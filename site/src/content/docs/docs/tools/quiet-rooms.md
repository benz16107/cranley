---
title: "Quiet rooms"
description: "Ranks the bedrooms and office from quietest to loudest against road, rail and aircraft noise, from the national noise map, the nearest roads and which way each room faces."
sidebar: {"label": "Quiet rooms"}
---

Ranks the bedrooms and office from quietest to loudest against road, rail and aircraft noise, from the national noise map, the nearest roads and which way each room faces.

## What it answers

- Which bedroom is quietest?
- Is the office on the road side?
- Will planes keep me up?

For the agent, the tool is described as: Estimated outside transport noise per room for one scan: DOT National Transportation Noise Map level at the house (road, aviation, rail), nearest highway, major road, railway and airport from OpenStreetMap, each room's facade direction and the walls between it and the source. Ranks bedrooms and offices quietest to loudest; per-room lens in dBA. Low reliability estimate; needs the scan's geocoordinates.

## Who it is for

[Light sleeper or night-shift worker](/docs/reference/personas/#light-sleeper-or-night-shift-worker), [Remote worker](/docs/reference/personas/#remote-worker).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `scan` | string | yes |  | Scan id. Filled from the selected building. |
| `windows_open` | boolean |  | `false` | Sleep with a window partly open. Saved preference `noise.windows_open`. |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Wall outline | `matterport.walls` | required | The verdict is `unknown`, with the reason. |
| Scan position | `matterport.geo` | required | The verdict is `unknown`, with the reason. |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Draws on the building: a colour per room; pins on what it found.
- Panel blocks: `VerdictHeader`, `MetricRow`, `MiniChart`, `CheckList`, `FloorPlanMini`, `AssumptionChips`, `StepLog`.
- Speed: fast. Read-only.

## How it works

Quiet rooms: ranks the bedrooms and office from quietest to loudest against outside transport noise.

## Reliability

Every metric and finding carries its layer, its method and a high, medium or low label, set by the tool for each value. See [findings and reliability](/docs/concepts/findings-and-reliability/).

## Limits

- Needs: wall outline, scan position. On a scan without them, the verdict is `unknown` and says why.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

Inputs used: `windows_open = false` (preset of the persona "Light sleeper or night-shift worker").

<p class="verdict"><span class="st unknown">Unknown</span> This scan has no geocoordinates, so distance and direction to roads cannot be worked out.</p>


## Run it

```sh
threshold run quiet_rooms --scan <scan-id>
curl -X POST http://127.0.0.1:8787/api/tools/quiet_rooms/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `quiet_rooms`. See [MCP server and CLI](/docs/mcp/).
