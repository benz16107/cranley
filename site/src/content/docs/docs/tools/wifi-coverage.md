---
title: "Wi-Fi coverage"
description: "Estimates Wi-Fi strength in every room from a router spot, finds dead zones, the best router spot for the bedrooms and office, and where a mesh node helps most."
sidebar: {"label": "Wi-Fi coverage"}
---

Estimates Wi-Fi strength in every room from a router spot, finds dead zones, the best router spot for the bedrooms and office, and where a mesh node helps most.

## What it answers

- Where should the router go?
- Will Wi-Fi reach the back bedroom?
- Do I need a mesh node?

For the agent, the tool is described as: Wi-Fi signal estimate per room through the scan's wall graph (COST 231 multi-wall model, wall materials assumed from thickness), for 2.4 and 5 GHz. Give router_room or router_point, or leave both empty to find the best spot for the bedrooms and office. Returns a per-room lens (5 GHz dBm), checks per room, dead zones, router and mesh node pins. Low confidence estimate.

## Who it is for

[Family planning home security](/docs/reference/personas/#family-planning-home-security), [Remote worker](/docs/reference/personas/#remote-worker).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `scan` | string | yes |  | Scan id. Filled from the selected building. |
| `router_room` | string |  |  | Room id where the router is; empty to let the tool find the best spot. |
| `router_point` | array |  |  | Router position [x, y] in the scan frame (metres). |
| `router_floor` | string |  |  | Floor id of router_point, when the scan has several floors. |
| `router` | string |  | `"typical"` | typical: 20 dBm at 2.4 GHz, 23 dBm at 5 GHz. long_range: 4 dB more. Saved preference `wifi.router_class`. One of: `typical`, `long_range`. |
| `targets` | array |  |  | Room ids that must have good signal; default the bedrooms and office. |
| `wall_materials` | object |  | `{}` | Walls the scan cannot tell apart by thickness: wall id or room id (all its walls) to a material (metal ductwork, coated glass, clear glass, masonry, drywall). |
| `outbuilding_m` | number (m) |  |  | A detached garage or studio this far from the house; estimates the signal inside it. Saved preference `wifi.outbuilding_m`. |
| `outbuilding_wall` | string |  | `"masonry"` | What the detached building's wall facing the house is (a metal garage door: metal ductwork). Saved preference `wifi.outbuilding_wall`. One of: `metal ductwork`, `coated glass`, `clear glass`, `masonry`, `drywall`. |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Wall outline | `matterport.walls` | required | The verdict is `unknown`, with the reason. |
| Doors and windows | `matterport.openings` | required | The verdict is `unknown`, with the reason. |
| Room names | `matterport.room_labels` | optional | The tool runs without it. |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Draws on the building: a colour per room; pins on what it found.
- Panel blocks: `VerdictHeader`, `MetricRow`, `MiniChart`, `CheckList`, `FloorPlanMini`, `AssumptionChips`, `StepLog`.
- Speed: fast. Read-only.

## How it works

Wi-Fi coverage: expected signal per room from a router, through the walls and floors of the scan.

## Reliability

Sources this tool gave on the test home:

| Where it came from | Layer | Method | Reliability | Note |
|---|---|---|---|---|
| Simulated from the scan | `matterport` | `simulation` | low | COST 231 Final Report (1999), 4.7.2, multi-wall model over the scan's walls; wall materials assumed from thickness; furniture, doors and interference not modelled |

The tool sets the label for each value. A model never does. The tools give a scan's wall graph the layer `matterport` whichever device made the scan, so a phone scan's geometry carries that label too.

## Limits

- Needs: wall outline, doors and windows. On a scan without them, the verdict is `unknown` and says why.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

<p class="verdict"><span class="st pass">Pass</span> With the router in Bedroom, 2 of 2 bedrooms get good 5 GHz signal. The scan labels no office, so only bedrooms were targeted. Estimate from the walls alone.</p>

| Value | Result | Where it came from | Reliability |
|---|---|---|---|
| Rooms with good 5 GHz | <span class="num">6 of 6</span> | Simulated from the scan | low |
| Dead zones (5 GHz) | <span class="num">0 rooms</span> | Simulated from the scan | low |
| Weakest target: Bedroom 2 | <span class="num">-37.2 dBm</span> | Simulated from the scan | low |
| Dead zones (2.4 GHz) | <span class="num">0 rooms</span> | Simulated from the scan | low |
| Bedroom | <span class="num">-31.1 dBm</span> | Simulated from the scan | low |
| Bedroom 2 | <span class="num">-37.2 dBm</span> | Simulated from the scan | low |
| Bathroom | <span class="num">-41.3 dBm</span> | Simulated from the scan | low |
| Hallway | <span class="num">-44.5 dBm</span> | Simulated from the scan | low |
| Living Room | <span class="num">-45.3 dBm</span> | Simulated from the scan | low |
| Kitchen | <span class="num">-50.4 dBm</span> | Simulated from the scan | low |

| Check | Measured | Against | Status |
|---|---|---|---|
| 5 GHz signal, Bedroom | <span class="num">-31.1</span> | <span class="num">-67 dBm</span> | <span class="st pass">pass</span> |
| 5 GHz signal, Bedroom 2 | <span class="num">-37.2</span> | <span class="num">-67 dBm</span> | <span class="st pass">pass</span> |
| 5 GHz signal, Bathroom | <span class="num">-41.3</span> | <span class="num">-67 dBm</span> | <span class="st pass">pass</span> |
| 5 GHz signal, Hallway | <span class="num">-44.5</span> | <span class="num">-67 dBm</span> | <span class="st pass">pass</span> |
| 5 GHz signal, Living Room | <span class="num">-45.3</span> | <span class="num">-67 dBm</span> | <span class="st pass">pass</span> |
| 5 GHz signal, Kitchen | <span class="num">-50.4</span> | <span class="num">-67 dBm</span> | <span class="st pass">pass</span> |

Findings: 1 pass.

What it reported while it ran:

1. Cut 25 wall pieces at their doors and windows; 111 sample points in 6 rooms
1. Trying 58 router spots against 2 rooms (bedrooms)
1. Router placed in Bedroom

## Run it

```sh
threshold run wifi_coverage --scan <scan-id>
curl -X POST http://127.0.0.1:8787/api/tools/wifi_coverage/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `wifi_coverage`. See [MCP server and CLI](/docs/mcp/).
