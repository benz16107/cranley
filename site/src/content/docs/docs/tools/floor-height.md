---
title: "Floor height"
description: "Narrows the floor's height above the ground, the flood result's widest uncertainty, from steps counted and fixes taken at your own front door."
sidebar: {"label": "Floor height"}
---

Narrows the floor's height above the ground, the flood result's widest uncertainty, from steps counted and fixes taken at your own front door.

## What it answers

- How high is my floor above the yard?
- Narrow the flood range

For the agent, the tool is described as: Phone only: a person runs this from the phone app, an agent cannot. Combine on-site phone inputs (steps counted at the door and a measured riser, GPS fixes at the door and the street with Vexcel ground elevation, a barometer rise) with the flood rehearsal's own floor-height methods, and report how much the range of water inside and of rooms taking water shrank. Needs inputs from the phone app.

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `scan` | string | yes |  | Scan id. Filled from the selected building. |
| `steps` | integer |  |  | Steps up from the ground to the door, counted on site. |
| `riser_m` | number (m) |  |  | One step's height, if measured. |
| `door` | Spot |  |  | The phone's fix standing at the front door. |
| `street` | Spot |  |  | The phone's fix standing at the street or the edge of the yard. |
| `baro_rise_m` | number (m) |  |  | Barometer: how much higher the door is than the street (native app). |
| `depth_m` | number (m) |  | `0.5` | Water above the ground outside, for the before and after. Saved preference `flood.depth_m`. Range: at least 0, at most 3. |
| `use_drone` | boolean |  | `true` | As in the flood rehearsal: use the drone photos when there are any. |
| `capture` | string |  |  | Capture id of the photo of the threshold. |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Gps | `phone.gps` | optional | The tool runs without it. |
| Rooms | `matterport.rooms` | required | The verdict is `unknown`, with the reason. |
| Ground heights | `vexcel.elevation` | optional | The tool runs without it. |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Panel blocks: `VerdictHeader`, `MetricRow`, `CheckList`, `EvidenceStrip`, `AssumptionChips`, `StepLog`, `ActionBar`.
- Speed: slow. Read-only.

## How it works

Floor height: the flood tool's weak number, measured by a person at the front door.

## Reliability

Every metric and finding carries its layer, its method and a high, medium or low label, set by the tool for each value. See [findings and reliability](/docs/concepts/findings-and-reliability/).

## Limits

- Needs: rooms. On a scan without it, the verdict is `unknown` and says why.
- It is slow: progress steps reach the workspace while it runs.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

<p class="verdict"><span class="st unknown">Unknown</span> Nothing from the phone could be turned into a floor height. Count the steps up to the door: that alone is enough.</p>


What it reported while it ran:

1. The scan has no location, so the aerial and drone methods are off
1. Scan outdoor panoramas: none near an exterior door
1. Water levels in the scan: lo +0.00 m from the entry floor, mid +0.20 m from the entry floor, hi +0.40 m from the entry floor

## Run it

```sh
threshold run floor_height --scan <scan-id>
curl -X POST http://127.0.0.1:8787/api/tools/floor_height/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `floor_height`. See [MCP server and CLI](/docs/mcp/).
