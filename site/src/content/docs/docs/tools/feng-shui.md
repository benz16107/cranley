---
title: "Feng shui reading"
description: "How a feng shui practitioner would read this home: the front door's direction, the Bagua grid on each floor, the command position for beds and desks, and the usual layout notes. A cultural tradition, not a measured effect."
sidebar: {"label": "Feng shui reading"}
---

How a feng shui practitioner would read this home: the front door's direction, the Bagua grid on each floor, the command position for beds and desks, and the usual layout notes. A cultural tradition, not a measured effect.

## What it answers

- Where should the bed go for good feng shui?
- Is the front door in line with the back door?
- I was born in 1988 and I'm a woman: which rooms suit my directions?

For the agent, the tool is described as: Traditional Chinese feng shui reading of one scanned home from its floor plan and true north: front door facing direction, Bagua (Lo Shu) sectors per floor with life area and element, which rooms fall in each sector, command position for the bed in each bedroom and the desk in each office (with boxes), notes such as front and back doors in line, stairs facing the door, missing corners and a bathroom at the centre, and with a birth year and gender the person's Kua number and favourable directions. Compass School by default; Western (BTB) door-aligned on request. Describe it as a cultural layout tradition, never as a proven effect.

## Who it is for

[Arranging a home by feng shui](/docs/reference/personas/#arranging-a-home-by-feng-shui).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `scan` | string | yes |  | Scan id. Filled from the selected building. |
| `convention` | string |  | `"compass"` | compass: Compass School, the eight sectors named by true north. western: Western (BTB) Bagua, the grid turned so the front door wall is the Career row. Saved preference `feng_shui.convention`. One of: `compass`, `western`. |
| `birth_year` | integer |  |  | Birth year for the Kua number; use the year before for a birth before about 4 February. Saved preference `feng_shui.birth_year`. |
| `gender` | string |  |  | The Kua formula differs for men and women. Saved preference `feng_shui.gender`. |
| `bed` | string |  | `"queen"` | Bed size to place. Saved preference `feng_shui.bed`. One of: `twin`, `full`, `queen`, `king`. |
| `front_door` | string |  |  | Opening id of the front door, when the first guess is wrong. |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Wall outline | `matterport.walls` | required | The verdict is `unknown`, with the reason. |
| Rooms | `matterport.rooms` | required | The verdict is `unknown`, with the reason. |
| Scan position | `matterport.geo` | optional | Western (door-aligned) convention, no compass |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Draws on the building: a colour per room; pins on what it found; a route with its narrow points; a box or 3D model placed in the room.
- Panel blocks: `VerdictHeader`, `MetricRow`, `CheckList`, `FloorPlanMini`, `AssumptionChips`, `Note`, `StepLog`.
- Speed: fast. Read-only.

## How it works

Feng shui: how a practitioner of this Chinese layout tradition would read the plan.

## Reliability

Sources this tool gave on the test home:

| Where it came from | Layer | Method | Reliability | Note |
|---|---|---|---|---|
| Measured from the scan | `matterport` | `geometry` | high | Wall graph and room outlines |

The tool sets the label for each value. A model never does. The tools give a scan's wall graph the layer `matterport` whichever device made the scan, so a phone scan's geometry carries that label too.

## Limits

- Needs: wall outline, rooms. On a scan without them, the verdict is `unknown` and says why.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

<p class="verdict"><span class="st pass">Pass</span> Western (BTB) reading: 0 layout notes a practitioner would raise, and 2 suggested bed or desk spots. A cultural tradition, not a measured effect.</p>

| Value | Result | Where it came from | Reliability |
|---|---|---|---|
| Layout notes | <span class="num">0</span> | Measured from the scan | high |

| Check | Measured | Against | Status |
|---|---|---|---|
| Floor 1: Health and balance (centre), Earth. Rooms: Hallway | <span class="num">100</span> | <span class="num">50 % inside</span> | <span class="st pass">pass</span> |
| Floor 1: Knowledge and self-cultivation (entrance side, left), Earth. Rooms: Living Room | <span class="num">100</span> | <span class="num">50 % inside</span> | <span class="st pass">pass</span> |
| Floor 1: Family and health (middle, left), Wood. Rooms: Living Room | <span class="num">100</span> | <span class="num">50 % inside</span> | <span class="st pass">pass</span> |
| Floor 1: Wealth (far side, left), Wood. Rooms: Kitchen | <span class="num">100</span> | <span class="num">50 % inside</span> | <span class="st pass">pass</span> |
| Floor 1: Career and life path (entrance side, middle), Water. Rooms: no room | <span class="num">100</span> | <span class="num">50 % inside</span> | <span class="st pass">pass</span> |
| Floor 1: Fame and reputation (far side, middle), Fire. Rooms: Bathroom, Hallway | <span class="num">100</span> | <span class="num">50 % inside</span> | <span class="st pass">pass</span> |
| Floor 1: Helpful people and travel (entrance side, right), Metal. Rooms: Bedroom 2 | <span class="num">100</span> | <span class="num">50 % inside</span> | <span class="st pass">pass</span> |
| Floor 1: Children and creativity (middle, right), Metal. Rooms: Bedroom 1, Bedroom 2 | <span class="num">100</span> | <span class="num">50 % inside</span> | <span class="st pass">pass</span> |

5 more checks are in the full result.

Findings: 2 pass, 1 warn.

What it reported while it ran:

1. Reading the plan by the Western (BTB) convention
1. Laying the Bagua grid over each floor's outline
1. Looking for the command position in each bedroom and office

## Run it

```sh
threshold run feng_shui --scan <scan-id>
curl -X POST http://127.0.0.1:8787/api/tools/feng_shui/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `feng_shui`. See [MCP server and CLI](/docs/mcp/).
