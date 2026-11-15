---
title: "Door widths"
description: "Measures every doorway and flags the ones too narrow for you or what you are moving."
sidebar: {"label": "Door widths"}
---

Measures every doorway and flags the ones too narrow for you or what you are moving.

## What it answers

- Can my wheelchair get through every door?
- Will a 90 cm sofa fit through?

For the agent, the tool is described as: Check every doorway and open passage in one scan against a minimum width. Returns one check per doorway, findings for the ones that fail or are close, pins and a coloured rule overlay.

## Who it is for

[Apartment manager](/docs/reference/personas/#apartment-manager), [Daycare operator](/docs/reference/personas/#daycare-operator), [Facility manager](/docs/reference/personas/#facility-manager), [Fire captain](/docs/reference/personas/#fire-captain), [Moving large furniture](/docs/reference/personas/#moving-large-furniture), [Office tenant](/docs/reference/personas/#office-tenant), [Older adult or family](/docs/reference/personas/#older-adult-or-family), [Parent of a toddler, house with a pool](/docs/reference/personas/#parent-of-a-toddler-house-with-a-pool), [Truck dispatcher](/docs/reference/personas/#truck-dispatcher), [Wheelchair user](/docs/reference/personas/#wheelchair-user), [Wheelchair van owner](/docs/reference/personas/#wheelchair-van-owner).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `scan` | string | yes |  | Scan id. Filled from the selected building. |
| `min_width_m` | number (m) | yes |  | Asked as: "How wide a door do you need, in metres? For furniture, use its narrowest side; a wheelchair needs 0.813 m (32 in)." Saved preference `access.door_width_m`. Range: more than 0.3, at most 3.0. |
| `warn_margin_m` | number (m) |  | `0.05` | Doorways this close above the threshold are a warning. Saved preference `access.door_warn_margin_m`. Range: at least 0, at most 0.5. |
| `standard` | string |  |  | The rule the threshold comes from. Saved preference `access.door_standard`. |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Doors and windows | `matterport.openings` | required | The verdict is `unknown`, with the reason. |
| Room names | `matterport.room_labels` | optional | The tool runs without it. |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Draws on the building: pins on what it found; doors, walls or rooms coloured by status.
- Panel blocks: `VerdictHeader`, `MetricRow`, `CheckList`, `FloorPlanMini`, `Controls`, `AssumptionChips`, `StepLog`, `ActionBar`.
- Speed: fast. Read-only.

## How it works

Every doorway's width against a threshold, as checks, pins and a pass/warn/fail rule overlay.

## Reliability

Sources this tool gave on the test home:

| Where it came from | Layer | Method | Reliability | Note |
|---|---|---|---|---|
| Measured from the scan | `matterport` | `geometry` | medium | Opening width in the wall graph; a hinged door's leaf takes a few centimetres off it |

The tool sets the label for each value. A model never does.

## Limits

- Needs: doors and windows. On a scan without it, the verdict is `unknown` and says why.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

Inputs used: `min_width_m = 0.813` (preset of the persona "Apartment manager").

<p class="verdict"><span class="st fail">Fail</span> 3 of 6 doorways are narrower than 0.813 m.</p>

| Value | Result | Where it came from | Reliability |
|---|---|---|---|
| Doorways | <span class="num">6</span> | Measured from the scan | medium |
| Narrowest | <span class="num">0.71 m</span> | Measured from the scan | medium |
| Too narrow | <span class="num">3</span> | Measured from the scan | medium |

| Check | Measured | Against | Status |
|---|---|---|---|
| Doorway width, Bathroom to Hallway | <span class="num">0.71</span> | <span class="num">0.813 m</span> | <span class="st fail">fail</span> |
| Doorway width, Hallway to Bedroom | <span class="num">0.76</span> | <span class="num">0.813 m</span> | <span class="st fail">fail</span> |
| Doorway width, Living Room to Bedroom | <span class="num">0.81</span> | <span class="num">0.813 m</span> | <span class="st fail">fail</span> |
| Doorway width, Hallway to Living Room | <span class="num">0.86</span> | <span class="num">0.813 m</span> | <span class="st warn">warn</span> |
| Doorway width, Living Room to outside | <span class="num">0.91</span> | <span class="num">0.813 m</span> | <span class="st pass">pass</span> |
| Doorway width, Kitchen to Living Room | <span class="num">1.2</span> | <span class="num">0.813 m</span> | <span class="st pass">pass</span> |

Findings: 3 fail, 1 warn.

What it reported while it ran:

1. Found 6 doorways and passages in the wall graph
1. Compared each with 0.813 m: 3 fail, 1 close

## Run it

```sh
threshold run door_widths --scan <scan-id>
curl -X POST http://127.0.0.1:8787/api/tools/door_widths/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `door_widths`. See [MCP server and CLI](/docs/mcp/).
