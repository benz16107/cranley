---
title: "Fire pre-plan"
description: "Writes the pre-incident plan from the scans, the aerial photo and the property record, with a one-page printable sheet."
sidebar: {"label": "Fire pre-plan"}
---

Writes the pre-incident plan from the scans, the aerial photo and the property record, with a one-page printable sheet.

## What it answers

- Write the pre-plan for this building
- Pre-plan the whole apartment complex

For the agent, the tool is described as: Pre-incident plan (NFPA 1620 sections) for one scan or a whole CoStar property: occupancy and construction, roof hazards, sides A to D and where the first engine parks, doorways out and hose stretch, interior layout, utilities and protection systems seen in the panoramas, hazards, and what no scan covers. Every line has a source; returns a printable HTML sheet.

## Who it is for

[Apartment manager](/docs/reference/personas/#apartment-manager), [Community risk reduction officer](/docs/reference/personas/#community-risk-reduction-officer), [Fire captain](/docs/reference/personas/#fire-captain), [Fire training officer](/docs/reference/personas/#fire-training-officer), [Insurance underwriter](/docs/reference/personas/#insurance-underwriter), [LA homeowner after the fires](/docs/reference/personas/#la-homeowner-after-the-fires).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `scan` | string |  |  | Scan id. Filled from the selected building. |
| `whole_property` | boolean |  | `false` | Plan the whole CoStar property the scan belongs to. |
| `property_id` | integer |  |  | CoStar property id; plans every scan of it. |
| `read_panoramas` | boolean |  | `true` | Send unread panoramas to the vision model for utilities, protection systems and hazards. |
| `max_scans_read` | integer |  | `2` | At most this many unread scans go to the vision model. Range: at least 0, at most 12. |
| `min_width_m` | number (m) |  | `0.813` | Clear width an exit door needs. Saved preference `access.door_width_m`. Range: more than 0.3, at most 3.0. |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Rooms | `matterport.rooms` | required | The verdict is `unknown`, with the reason. |
| Doors and windows | `matterport.openings` | optional | The tool runs without it. |
| Aerial photo | `vexcel.ortho` | optional | The tool runs without it. |
| Property record | `costar.property` | optional | The tool runs without it. |
| 360° photos | `matterport.panoramas` | optional | The tool runs without it. |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Draws on the building: pins on what it found; doors, walls or rooms coloured by status.
- Panel blocks: `VerdictHeader`, `MetricRow`, `CheckList`, `EvidenceStrip`, `FloorPlanMini`, `StepLog`, `Note`, `ActionBar`.
- Speed: slow. Read-only.

## How it works

Fire pre-plan: the pre-incident plan for one scan or a whole property, written from data that already exists and organised by NFPA 1620 (2015) sections (now part of NFPA 1660, 2024). Every line carries its source and confidence; "not seen" is never "absent". Also writes a one-page printable sheet.

## Reliability

Sources this tool gave on the test cafe:

| Where it came from | Layer | Method | Reliability | Note |
|---|---|---|---|---|
| Measured from the scan | `matterport` | `geometry` | high | Matterport scan: floors, rooms, openings |
| Looked up in a model | `model` | `lookup` | low | Not in any data source this tool reads |
| Seen in a model | `model` | `vision` | medium | Vision model on the central panorama of each room; small objects are hit and miss |
| Looked up in a model | `model` | `lookup` | high | Rendered from the lines above |
| Looked up in the scan | `matterport` | `lookup` | medium | Scan segment from the scan index |
| Measured from the scan | `matterport` | `geometry` | medium | Wall graph opening less a 5 cm door allowance; each may lead to an unscanned room |
| Measured from the scan | `matterport` | `geometry` | medium | Empty-room route over the wall graph |
| Measured from the scan | `matterport` | `geometry` | medium | Route over the wall graph plus the straight run to the room's far corner |

The tool sets the label for each value. A model never does.

## Limits

- Needs: rooms. On a scan without it, the verdict is `unknown` and says why.
- It is slow: progress steps reach the workspace while it runs.
- A result is a planning aid, not an inspection.

## On the made-up test cafe

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

<p class="verdict"><span class="st unknown">Unknown</span> Pre-plan for Test cafe (made up): 5 lines filled from the data, 0 hazards or obstacles to note, 7 items to confirm on the walk-around.</p>

| Value | Result | Where it came from | Reliability |
|---|---|---|---|
| Lines filled | <span class="num">5</span> | Measured from the scan | high |
| To confirm on site | <span class="num">7</span> | Looked up in a model | low |
| Hazards noted | <span class="num">0</span> | Seen in a model | medium |
| Hose stretch inside | <span class="num">14.9 m</span> | Measured from the scan | high |

| Check | Measured | Against | Status |
|---|---|---|---|
| §5.2 Construction: lines with data | <span class="num">1</span> | <span class="num">3 lines</span> | <span class="st warn">warn</span> |
| §5.3 Building systems and utilities: lines with data | <span class="num">0</span> | <span class="num">2 lines</span> | <span class="st unknown">unknown</span> |
| §5.4 Site and access: lines with data | <span class="num">0</span> | <span class="num">1 lines</span> | <span class="st unknown">unknown</span> |
| §6 Occupants and means of egress: lines with data | <span class="num">4</span> | <span class="num">4 lines</span> | <span class="st pass">pass</span> |
| §7 Water supply and protection systems: lines with data | <span class="num">0</span> | <span class="num">2 lines</span> | <span class="st unknown">unknown</span> |
| §8 Hazards: lines with data | <span class="num">0</span> | <span class="num">0 lines</span> | <span class="st unknown">unknown</span> |

Findings: 6 pass, 7 unknown.

What it reported while it ran:

1. Read 1 scan plans
1. No CoStar record for these scans
1. Measured egress on 1 scans with a wall graph; read panoramas of 0 scans (0 new)
1. Wrote the printable pre-plan sheet

## Run it

```sh
threshold run fire_preplan --scan <scan-id>
curl -X POST http://127.0.0.1:8787/api/tools/fire_preplan/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `fire_preplan`. See [MCP server and CLI](/docs/mcp/).
