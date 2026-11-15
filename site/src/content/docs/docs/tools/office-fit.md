---
title: "Office fit"
description: "Whether your team fits this suite as built: desks, private offices, meeting rooms and kitchen, with the listed size and the last tenant beside it."
sidebar: {"label": "Office fit"}
---

Whether your team fits this suite as built: desks, private offices, meeting rooms and kitchen, with the listed size and the last tenant beside it.

## What it answers

- Will 28 people with 6 private offices and two meeting rooms fit here?
- How many desks does this suite hold?

For the agent, the tool is described as: Test a tenant program (headcount, private offices, meeting rooms and seats, kitchen) against one office scan. Counts what the suite has from room labels and measured areas, shows which room serves as what, compares listed against measured area (load factor), the last tenant's employee count against computed capacity, and the asking rent. Returns pass/warn/fail and up to three changes that would make it fit. Labels unlabelled rooms first (slow once).

## Who it is for

[CoStar researcher](/docs/reference/personas/#costar-researcher), [Office relocation lead](/docs/reference/personas/#office-relocation-lead), [Office tenant](/docs/reference/personas/#office-tenant), [Remote worker](/docs/reference/personas/#remote-worker), [Plant lover or home office worker choosing a room](/docs/reference/personas/#plant-lover-or-home-office-worker-choosing-a-room).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `scan` | string | yes |  | Scan id. Filled from the selected building. |
| `headcount` | integer | yes |  | Asked as: "How many people need a seat?" Saved preference `office.headcount`. Range: at least 1, at most 2000. |
| `private_offices` | integer |  | `0` | Asked as: "How many of them need a private office?" Saved preference `office.private_offices`. Range: at least 0. |
| `meeting_rooms` | integer |  | `1` | Asked as: "How many meeting rooms do you need?" Saved preference `office.meeting_rooms`. Range: at least 0. |
| `meeting_seats` | integer |  | `6` | Asked as: "How many seats should the largest meeting room have?" Saved preference `office.meeting_seats`. Range: at least 2. |
| `kitchen` | boolean |  | `true` | Needs a kitchen or break room. Saved preference `office.kitchen`. |
| `desk_m2` | number (m2) |  | `6.5` | Open-plan area per workstation, aisles included. Saved preference `office.desk_m2`. Range: at least 3.5, at most 15. |
| `seat_m2` | number (m2) |  | `2.3` | Meeting room area per seat. Saved preference `office.meeting_seat_m2`. Range: at least 1.4, at most 5. |
| `office_min_m2` | number (m2) |  | `7.5` | Smallest room that works as a private office. Saved preference `office.private_office_min_m2`. Range: at least 4, at most 20. |
| `label_with_vision` | boolean |  | `true` | Label unlabelled rooms from the panoramas first (slow once). |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Rooms | `matterport.rooms` | required | The verdict is `unknown`, with the reason. |
| 360° photos | `matterport.panos` | optional | existing labels |
| Property record | `costar.property` | optional | no record comparison |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Draws on the building: a colour per room; pins on what it found; doors, walls or rooms coloured by status.
- Panel blocks: `VerdictHeader`, `MetricRow`, `CheckList`, `MiniChart`, `FloorPlanMini`, `AssumptionChips`, `Controls`, `EvidenceStrip`, `StepLog`.
- Speed: slow. Read-only.

## How it works

Office fit: does a team's program fit this suite as built? Rooms come from the label overlay (room_labeller), areas from the scan, the comparison from the CoStar record (listed space, last tenant, asking rent).

## Reliability

Sources this tool gave on the test cafe:

| Where it came from | Layer | Method | Reliability | Note |
|---|---|---|---|---|
| Simulated from the scan | `matterport` | `simulation` | medium | Capacity from measured areas and your space standards |
| Measured from the scan | `matterport` | `geometry` | high | Room floor areas from the scan |
| Seen in a model | `model` | `vision` | medium | Room types from the room labeller |

The tool sets the label for each value. A model never does.

## Limits

- Needs: rooms. On a scan without it, the verdict is `unknown` and says why.
- It is slow: progress steps reach the workspace while it runs.
- A result is a planning aid, not an inspection.

## On the made-up test cafe

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

Inputs used: `headcount = 6` (an answer given for this example).

<p class="verdict"><span class="st fail">Fail</span> Your team does not fit: 0 desks for 6 people, 0 private offices, 0 meeting rooms for the 1 you need.</p>

| Value | Result | Where it came from | Reliability |
|---|---|---|---|
| People seated as built | <span class="num">0</span> | Simulated from the scan | medium |
| People to seat | <span class="num">6</span> | Simulated from the scan | medium |
| Measured area inside the suite | <span class="num">84 m²</span> | Measured from the scan | high |
| Area your program needs | <span class="num">74.5 m²</span> | Simulated from the scan | medium |
| Desks in open areas and spare offices | <span class="num">0</span> | Seen in a model | medium |
| Private offices | <span class="num">0</span> | Seen in a model | medium |
| Meeting rooms | <span class="num">0</span> | Seen in a model | medium |
| Kitchens | <span class="num">1</span> | Seen in a model | medium |
| Restrooms in the suite | <span class="num">1</span> | Seen in a model | medium |
| Reception | <span class="num">0</span> | Seen in a model | medium |

1 more values are in the full result.

| Check | Measured | Against | Status |
|---|---|---|---|
| Desks for everyone without a private office | <span class="num">0</span> | <span class="num">6 desks</span> | <span class="st fail">fail</span> |
| Private offices | <span class="num">0</span> | <span class="num">0 rooms</span> | <span class="st pass">pass</span> |
| Meeting rooms | <span class="num">0</span> | <span class="num">1 rooms</span> | <span class="st fail">fail</span> |
| Seats in the largest meeting room | <span class="num">0</span> | <span class="num">6 seats</span> | <span class="st warn">warn</span> |
| Kitchen or break room | <span class="num">1</span> | <span class="num">1 rooms</span> | <span class="st pass">pass</span> |

Findings: 1 fail, 1 warn.

What it reported while it ran:

1. Read 4 rooms and their labels
1. Allocated rooms: 0 desks, 0 private offices, 0 meeting rooms

## Run it

```sh
threshold run office_fit --scan <scan-id>
curl -X POST http://127.0.0.1:8787/api/tools/office_fit/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `office_fit`. See [MCP server and CLI](/docs/mcp/).
