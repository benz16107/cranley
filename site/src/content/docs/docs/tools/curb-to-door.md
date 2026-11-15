---
title: "Curb to door"
description: "Looks at the way in from outside: parking near the entrance, accessible stalls if the aerial photo shows them, how far it is to the door, and steps at the door."
sidebar: {"label": "Curb to door"}
---

Looks at the way in from outside: parking near the entrance, accessible stalls if the aerial photo shows them, how far it is to the door, and steps at the door.

## What it answers

- How far is it from parking to the front door?
- Are there steps up to the entrance?

For the agent, the tool is described as: The outside part of an access audit for one scan, from the Vexcel aerial photo and the entry panoramas: parking near the building (stalls, parked cars, driveway), wheelchair symbols, straight-line distance and ground rise from the nearest parking to the entrance, and steps, stairs or ramps at the entrance. Confidence is low where the scan's geo position is approximate.

## Who it is for

[Planning for an older parent](/docs/reference/personas/#planning-for-an-older-parent), [Film or photo location scout](/docs/reference/personas/#film-or-photo-location-scout), [Older adult or family](/docs/reference/personas/#older-adult-or-family), [Wheelchair user looking for a home](/docs/reference/personas/#wheelchair-user-looking-for-a-home), [Wheelchair user](/docs/reference/personas/#wheelchair-user).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `scan` | string | yes |  | Scan id. Filled from the selected building. |
| `radius_m` | number (m) |  | `40` | How far around the building to look. Range: at least 10, at most 100. |
| `read_panoramas` | boolean |  | `true` | Look for steps in the panoramas by the entrance. |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Aerial photo | `vexcel.ortho` | required | The verdict is `unknown`, with the reason. |
| Scan position | `matterport.geo` | required | The verdict is `unknown`, with the reason. |
| 360° photos | `matterport.panos` | optional | The tool runs without it. |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Draws on the building: pins on what it found.
- Panel blocks: `VerdictHeader`, `MetricRow`, `CheckList`, `EvidenceStrip`, `AssumptionChips`, `StepLog`.
- Speed: slow. Read-only.

## How it works

Curb to door: the part outside. Parking near the entrance and accessible stalls if the aerial photo shows them, the distance from parking to the entrance, the ground rise along it, and steps at the entrance seen in the entry panoramas. The join between the aerial photo and the scan is uncertain, and the tool says so.

## Reliability

Every metric and finding carries its layer, its method and a high, medium or low label, set by the tool for each value. See [findings and reliability](/docs/concepts/findings-and-reliability/).

## Limits

- Needs: aerial photo, scan position. On a scan without them, the verdict is `unknown` and says why.
- It is slow: progress steps reach the workspace while it runs.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

<p class="verdict"><span class="st unknown">Unknown</span> This scan has no geocoordinates, so it cannot be placed on the aerial photo.</p>


## Run it

```sh
threshold run curb_to_door --scan <scan-id>
curl -X POST http://127.0.0.1:8787/api/tools/curb_to_door/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `curb_to_door`. See [MCP server and CLI](/docs/mcp/).
