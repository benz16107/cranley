---
title: "Facility audit"
description: "Your building in one pass: doors, restrooms, ways out, life-safety equipment seen, occupant load and cleaning cost, ending in a prioritised fix list with rough costs."
sidebar: {"label": "Facility audit"}
---

Your building in one pass: doors, restrooms, ways out, life-safety equipment seen, occupant load and cleaning cost, ending in a prioritised fix list with rough costs.

## What it answers

- Audit our office for accessibility and life safety
- What should we fix first in this building, and what will it cost?

For the agent, the tool is described as: For a business auditing its current building or suite (one scan): ADA Title III style checks (32 in door clear width, restroom clearances), egress routes and exit widths, occupant load at 150 ft² per person against the doorways out, smoke alarms, sprinkler heads, exit signs and extinguishers seen on the panoramas, and a cleaning contract price from the takeoff. Returns a prioritised fix list priced from the what-if cost book (low reliability), and says where a fix needs a quote.

## Who it is for

[Facility manager](/docs/reference/personas/#facility-manager), [Office tenant](/docs/reference/personas/#office-tenant).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `scan` | string | yes |  | Scan id of the building or suite. Filled from the selected building. |
| `door_width_m` | number (m) |  | `0.813` | Clear width a door needs (32 in, ADA 404.2.3). Saved preference `access.door_width_m`. Range: more than 0.3, at most 2.0. |
| `read_panoramas` | boolean |  | `true` | Let the vision model read the panoramas (restroom fixtures, life-safety objects); cached after the first run. |
| `cleaning` | boolean |  | `true` | Price a cleaning contract from the takeoff. |
| `cart_m` | array (m) |  | `[0.51, 0.66, 1.78]` | Cart or rolling rack stock moves on: width, length, height (default a full-size sheet-pan rack, 20 x 26 x 70 in). Saved preference `facility.cart_m`. |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Doors and windows | `matterport.openings` | required | The verdict is `unknown`, with the reason. |
| 360° photos | `matterport.panos` | optional | The tool runs without it. |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Panel blocks: `VerdictHeader`, `MetricRow`, `MiniChart`, `CheckList`, `EvidenceStrip`, `AssumptionChips`, `StepLog`.
- Speed: slow. Read-only.

## How it works

Facility audit: one bundle for a business's own building, ending in a prioritised fix list with rough costs.

## Reliability

Sources this tool gave on the test cafe:

| Where it came from | Layer | Method | Reliability | Note |
|---|---|---|---|---|
| Measured from the scan | `matterport` | `geometry` | high | Sum of room areas on the scan |
| Measured from a model | `model` | `geometry` | medium | IBC 2021 Table 1004.5, business areas |
| Simulated | `model` | `simulation` | low | What-if cost book: national averages from cost guides, not a quote, no local labour rate |
| Simulated | `model` | `simulation` | low | Your rates times measured quantities; rates are assumptions |
| Measured from the scan | `matterport` | `geometry` | medium | Opening width in the wall graph; a hinged door's leaf takes a few centimetres off it |
| Measured from the scan | `matterport` | `geometry` | medium | Matterport wall graph, empty rooms; door widths are the opening in the wall |
| Measured from the scan | `matterport` | `geometry` | low | Matterport wall graph; part of this answer rests on an assumption named in the result |

The tool sets the label for each value. A model never does. The tools give a scan's wall graph the layer `matterport` whichever device made the scan, so a phone scan's geometry carries that label too.

## Limits

- Needs: doors and windows. On a scan without it, the verdict is `unknown` and says why.
- It is slow: progress steps reach the workspace while it runs.
- A result is a planning aid, not an inspection.

## On the made-up test cafe

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

Inputs used: `door_width_m = 0.813` (preset of the persona "Facility manager").

<p class="verdict"><span class="st warn">Warn</span> 3 fixes found, $1,850 priced (low reliability); occupant load 6 at 150 ft² a person. Cleaning about $144 a month.</p>

| Value | Result | Where it came from | Reliability |
|---|---|---|---|
| Scanned floor area | <span class="num">905 ft²</span> | Measured from the scan | high |
| Occupant load (150 ft² each) | <span class="num">6 people</span> | Measured from a model | medium |
| Priced fixes | <span class="num">1850 $</span> | Simulated | low |
| Fixes found | <span class="num">3</span> | Simulated | low |
| Storage room floor area | <span class="num">0 ft²</span> | Measured from the scan | high |
| Sharpest bend on a cart route | <span class="num">0 °</span> | Measured from the scan | high |
| Widen doorways well under 32 in | <span class="num">1200 $</span> | Simulated | low |
| Grab bars at the toilet (side and rear) | <span class="num">400 $</span> | Simulated | low |
| Swing-clear hinges on doors just under 32 in | <span class="num">250 $</span> | Simulated | low |
| Cleaning contract per month | <span class="num">144 $</span> | Simulated | low |

| Check | Measured | Against | Status |
|---|---|---|---|
| Ways out for 6 occupants | <span class="num">2</span> | <span class="num">1</span> | <span class="st pass">pass</span> |
| Doorway width, Bathroom to Dining Room | <span class="num">0.76</span> | <span class="num">0.813 m</span> | <span class="st fail">fail</span> |
| Doorway width, Kitchen to Storage | <span class="num">0.81</span> | <span class="num">0.813 m</span> | <span class="st fail">fail</span> |
| Doorway width, Kitchen to outside | <span class="num">0.86</span> | <span class="num">0.813 m</span> | <span class="st warn">warn</span> |
| Bathroom: door clear width | <span class="num">0.71</span> | <span class="num">0.815 m</span> | <span class="st fail">fail</span> |
| Bathroom: free wall behind the toilet for a rear grab bar | <span class="num">0</span> | <span class="num">0.914 m</span> | <span class="st fail">fail</span> |
| Cart route, entrance to kitchen or break room: 2 doors and 0 bends, straight | <span class="num">0.25</span> | <span class="num">0 m</span> | <span class="st pass">pass</span> |
| Not in the scan: how far the sinks are from the water heater: no water heater was located on the panoramas | not measured |  | <span class="st unknown">unknown</span> |

4 more checks are in the full result.

Findings: 4 warn, 4 fail, 1 unknown.

What it reported while it ran:

1. Scan u_testcafe0001: 4 rooms, 905 ft²
1. Found 5 doorways and passages in the wall graph
1. Compared each with 0.813 m: 2 fail, 1 close
1. door_widths: 2 of 5 doorways are narrower than 0.813 m.
1. Reading 0 bathroom panoramas for the toilet, tub, shower and grab bars
1. Measured 1 bathrooms
1. bathroom_clearance: Every bathroom fails at least one check: door clear width; free wall behind the toilet for a rear grab bar.
1. Found 2 doorways to outside or unscanned space and 3 connections between rooms

## Run it

```sh
threshold run facility_audit --scan <scan-id>
curl -X POST http://127.0.0.1:8787/api/tools/facility_audit/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `facility_audit`. See [MCP server and CLI](/docs/mcp/).
