---
title: "What if: renovate"
description: "What it would take to make this home wheelchair-ready: the edits, what each one fixes and what it costs, with the renovated plan to compare side by side."
sidebar: {"label": "What if: renovate"}
---

What it would take to make this home wheelchair-ready: the edits, what each one fixes and what it costs, with the renovated plan to compare side by side.

## What it answers

- What would it take to make this apartment wheelchair-ready?
- Widen the bathroom door to 36 inches: what changes?

For the agent, the tool is described as: Renovation what-if for one scan with a wall graph. With only a goal (wheelchair_ready, bathroom_route, bathroom_turn, door_widths) it proposes edits from the failing checks (widen doors, move or remove a wall, ramp a step, grab bars); or pass `edits`. Re-runs door_widths, step_free_route, turning_space and bathroom_clearance on the edited copy, saves it as a what-if scan id (in the first metric's source note and the actions) that any tool accepts, and returns the checks that flipped, a ranked table of edits by fixes and cost, and the unit costs as assumptions. `city` adds a city-wide count on a database fork.

## Who it is for

[Apartment manager](/docs/reference/personas/#apartment-manager), [Older adult or family](/docs/reference/personas/#older-adult-or-family), [Wheelchair user looking for a home](/docs/reference/personas/#wheelchair-user-looking-for-a-home), [Wheelchair user](/docs/reference/personas/#wheelchair-user).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `scan` | string | yes |  | Scan id (a what-if scan adds to its edits). Filled from the selected building. |
| `goal` | string |  | `"wheelchair_ready"` | Asked as: "What should the home be ready for: a step-free route to the bathroom, a turning circle in the bathroom, wide doors, or all of it (wheelchair-ready)?" Saved preference `renovate.goal`. One of: `wheelchair_ready`, `bathroom_route`, `bathroom_turn`, `door_widths`. |
| `edits` | array |  |  | Your own edits instead of the proposed ones: widen_door &#123;opening, width_m}, move_wall &#123;wall, offset_m, grow}, remove_wall &#123;wall}, add_ramp &#123;opening}, grab_bars &#123;room, bars}, door_swing &#123;opening, swing}. |
| `city` | boolean |  | `false` | Also ask the facts database, on a throwaway fork, how many homes in the city would pass with one door widened (30 to 90 s). |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Wall outline | `matterport.walls` | required | The verdict is `unknown`, with the reason. |
| Doors and windows | `matterport.openings` | required | The verdict is `unknown`, with the reason. |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Draws on the building: doors, walls or rooms coloured by status.
- Panel blocks: `VerdictHeader`, `MetricRow`, `RankedTable`, `CheckList`, `AssumptionChips`, `StepLog`, `ActionBar`.
- Its own ranked table: Checks fixed, Cost, Per $1k.
- Speed: fast. Read-only.

## How it works

Renovate: what it would take to make a home meet a goal (step-free route to the bathroom, a turning circle in the bathroom, door widths, or all of it). Proposes edits from the failing checks, or takes yours, tries each alone, saves the best package as a what-if scan (`w_...`, which every tool runs on), re-runs the goal's tools on it, and prices each edit from takeoff quantities with unit costs that are labelled assumptions.

## Reliability

Sources this tool gave on the test home:

| Where it came from | Layer | Method | Reliability | Note |
|---|---|---|---|---|
| Simulated | `model` | `simulation` | low | Takeoff quantities times national-average unit costs from cost guides; not a quote. Renovated plan: w_a3ef63a6aef9 |
| Measured from the scan | `matterport` | `geometry` | medium | The goal's tools re-run on the edited wall graph; panoramas are not read (they show the home as it is) |
| Simulated | `model` | `simulation` | low | Takeoff quantities times national-average unit costs from cost guides; not a quote |

The tool sets the label for each value. A model never does. The tools give a scan's wall graph the layer `matterport` whichever device made the scan, so a phone scan's geometry carries that label too.

## Limits

- Needs: wall outline, doors and windows. On a scan without them, the verdict is `unknown` and says why.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

<p class="verdict"><span class="st warn">Warn</span> 5 edits fix 8 of 16 failing checks; still failing: Turning circle, Bathroom, objects on the floor counted (1.68 m empty), Turning circle, Hallway, Turning circle, Bedroom, objects on the floor counted (3.86 m empty) and 6 more.</p>

| Value | Result | Where it came from | Reliability |
|---|---|---|---|
| Estimated cost | <span class="num">4250 $</span> | Simulated | low |
| Checks fixed | <span class="num">8</span> | Measured from the scan | medium |
| Failing now | <span class="num">16</span> | Measured from the scan | medium |
| Failing after | <span class="num">9</span> | Measured from the scan | medium |
| Widen door, Bathroom to Hallway | <span class="num">2</span> | Measured from the scan | medium |
| Widen door, Bathroom to Hallway | <span class="num">1200 $</span> | Simulated | low |
| Widen door, Bathroom to Hallway | <span class="num">1.67</span> | Simulated | low |
| Widen door, Living Room to Bedroom | <span class="num">2</span> | Measured from the scan | medium |
| Widen door, Living Room to Bedroom | <span class="num">1200 $</span> | Simulated | low |
| Widen door, Living Room to Bedroom | <span class="num">1.67</span> | Simulated | low |

12 more values are in the full result.

| Check | Measured | Against | Status |
|---|---|---|---|
| Doorway width, Bathroom to Hallway (fixed: 0.71 to 0.915 m) | <span class="num">0.915</span> | <span class="num">0.815 m</span> | <span class="st pass">pass</span> |
| Doorway width, Hallway to Bedroom (fixed: 0.76 to 0.915 m) | <span class="num">0.915</span> | <span class="num">0.815 m</span> | <span class="st pass">pass</span> |
| Doorway width, Living Room to Bedroom (fixed: 0.81 to 0.915 m) | <span class="num">0.915</span> | <span class="num">0.815 m</span> | <span class="st pass">pass</span> |
| Doorway width, Hallway to Living Room (fixed: 0.86 to 0.91 m) | <span class="num">0.91</span> | <span class="num">0.815 m</span> | <span class="st pass">pass</span> |
| Step-free route, entrance to Bathroom: 7.7 m from the entrance through 3 doorways; narrowest 0.86 m. (fixed: 0.66 to 0.86 m) | <span class="num">0.86</span> | <span class="num">0.815 m</span> | <span class="st pass">pass</span> |
| Step-free route, entrance to Bedroom 1: 9.0 m from the entrance through 3 doorways; narrowest 0.86 m. (fixed: 0.71 to 0.86 m) | <span class="num">0.86</span> | <span class="num">0.815 m</span> | <span class="st pass">pass</span> |
| Step-free route, entrance to Bedroom 2: 7.5 m from the entrance through 2 doorways; narrowest 0.86 m. (fixed: 0.76 to 0.86 m) | <span class="num">0.86</span> | <span class="num">0.815 m</span> | <span class="st pass">pass</span> |
| Bathroom: door clear width (fixed: 0.66 to 0.865 m) | <span class="num">0.865</span> | <span class="num">0.815 m</span> | <span class="st pass">pass</span> |

1 more checks are in the full result.

Findings: 5 pass.

What it reported while it ran:

1. Running the 4 tools for 'Wheelchair-ready home' on the scan as it is
1. Found 6 doorways and passages in the wall graph
1. Compared each with 0.815 m: 3 fail, 1 close
1. Started at the entrance into the living room; routed to 4 rooms
1. 4 findings; verdict fail
1. Fitted the largest circle in 6 rooms
1. Measured 1 bathrooms
1. Proposed 6 edits from the failing checks

## Run it

```sh
threshold run renovate --scan <scan-id>
curl -X POST http://127.0.0.1:8787/api/tools/renovate/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `renovate`. See [MCP server and CLI](/docs/mcp/).
