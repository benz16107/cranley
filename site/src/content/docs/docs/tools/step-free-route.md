---
title: "Step-free route"
description: "Draws the route from the entrance to each room you need, with every door's width, the narrowest point and any step, and says whether you can get there."
sidebar: {"label": "Step-free route"}
---

Draws the route from the entrance to each room you need, with every door's width, the narrowest point and any step, and says whether you can get there.

## What it answers

- Can I get from the front door to the bathroom in my wheelchair?
- Is there a step-free way to the bedroom?

For the agent, the tool is described as: Route audit for a wheelchair or walker user in one scan: from the entrance to each destination room (Bathroom, Bedroom, Kitchen or named rooms), every doorway with width, the narrowest point, level changes, and a verdict per destination. Implausible door widths are flagged as data errors and checked against the panorama.

## Who it is for

[Planning for an older parent](/docs/reference/personas/#planning-for-an-older-parent), [Film or photo location scout](/docs/reference/personas/#film-or-photo-location-scout), [Office relocation lead](/docs/reference/personas/#office-relocation-lead), [Older adult or family](/docs/reference/personas/#older-adult-or-family), [Older dog that cannot do stairs](/docs/reference/personas/#older-dog-that-cannot-do-stairs), [Wheelchair user looking for a home](/docs/reference/personas/#wheelchair-user-looking-for-a-home), [Wheelchair user](/docs/reference/personas/#wheelchair-user), [Wheelchair van owner](/docs/reference/personas/#wheelchair-van-owner).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `scan` | string | yes |  | Scan id. Filled from the selected building. |
| `destinations` | array |  | `["Bathroom", "Bedroom", "Kitchen"]` | Room types (Bathroom, Bedroom, Kitchen, Living Room...) or room ids. Saved preference `access.destinations`. |
| `min_width_m` | number (m) |  | `0.815` | Clear width you need through doors. Saved preference `access.door_width_m`. Range: more than 0.3, at most 2.0. |
| `entrance` | string |  |  | Opening id of the entrance to start from; default the main one. |
| `read_panoramas` | boolean |  | `true` | Ask the panoramas about steps and about doorways whose width is a data error. |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Doors and windows | `matterport.openings` | required | The verdict is `unknown`, with the reason. |
| Rooms | `matterport.rooms` | required | The verdict is `unknown`, with the reason. |
| 360° photos | `matterport.panos` | optional | The tool runs without it. |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Draws on the building: a route with its narrow points; pins on what it found; doors, walls or rooms coloured by status.
- Panel blocks: `VerdictHeader`, `MetricRow`, `CheckList`, `EvidenceStrip`, `FloorPlanMini`, `Controls`, `AssumptionChips`, `StepLog`, `ActionBar`.
- Speed: slow. Read-only.

## How it works

Step-free route: from the entrance to each room that matters, every doorway with its width, the narrowest point, level changes, and a verdict per destination. Doorways whose recorded width is a data error are checked against the panorama before anything is failed.

## Reliability

Sources this tool gave on the test home:

| Where it came from | Layer | Method | Reliability | Note |
|---|---|---|---|---|
| Measured from the scan | `matterport` | `geometry` | medium | Matterport wall graph, empty rooms; door widths are the opening in the wall |
| Measured from the scan | `matterport` | `geometry` | low | Matterport wall graph; part of this answer rests on an assumption named in the result |

The tool sets the label for each value. A model never does.

## Limits

- Needs: doors and windows, rooms. On a scan without them, the verdict is `unknown` and says why.
- It is slow: progress steps reach the workspace while it runs.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

Inputs used: `min_width_m = 0.815` (preset of the persona "Planning for an older parent").

<p class="verdict"><span class="st fail">Fail</span> No step-free route wide enough to: bathroom, bedroom. The entrance is a doorway with a room on one side only; the scan cannot tell outside from unscanned.</p>

| Value | Result | Where it came from | Reliability |
|---|---|---|---|
| Destinations reachable | <span class="num">1</span> | Measured from the scan | medium |
| Narrowest point on the routes | <span class="num">0.66 m</span> | Measured from the scan | medium |
| Steps at doorways | <span class="num">0</span> | Measured from the scan | low |
| Door widths that are data errors | <span class="num">0</span> | Measured from the scan | medium |
| Entrance to nearest bathroom | <span class="num">7.7 m</span> | Measured from the scan | medium |

| Check | Measured | Against | Status |
|---|---|---|---|
| Step-free route, entrance to Bathroom: 7.7 m from the entrance through 3 doorways; narrowest 0.66 m. | <span class="num">0.66</span> | <span class="num">0.815 m</span> | <span class="st fail">fail</span> |
| Step-free route, entrance to Bedroom 1: 9.0 m from the entrance through 3 doorways; narrowest 0.71 m. | <span class="num">0.71</span> | <span class="num">0.815 m</span> | <span class="st fail">fail</span> |
| Step-free route, entrance to Bedroom 2: 7.5 m from the entrance through 2 doorways; narrowest 0.76 m. | <span class="num">0.76</span> | <span class="num">0.815 m</span> | <span class="st fail">fail</span> |
| Step-free route, entrance to Kitchen: 6.5 m from the entrance through 2 doorways; narrowest 0.86 m. | <span class="num">0.86</span> | <span class="num">0.815 m</span> | <span class="st pass">pass</span> |

Findings: 1 warn, 3 fail.

What it reported while it ran:

1. Started at the entrance into the living room; routed to 4 rooms
1. 4 findings; verdict fail

## Run it

```sh
threshold run step_free_route --scan <scan-id>
curl -X POST http://127.0.0.1:8787/api/tools/step_free_route/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `step_free_route`. See [MCP server and CLI](/docs/mcp/).
