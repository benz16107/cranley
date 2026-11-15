---
title: "Smoke clock"
description: "Minutes of survivable air in each bedroom with its door open and closed, from NIST's fire model run on the measured rooms."
sidebar: {"label": "Smoke clock"}
---

Minutes of survivable air in each bedroom with its door open and closed, from NIST's fire model run on the measured rooms.

## What it answers

- How long do the kids have if the living room catches fire?
- Does closing the bedroom door help?

For the agent, the tool is described as: Runs NIST CFAST (two-zone fire model) on one scan's rooms and doorways for a fire in a chosen room, twice: bedroom doors open, then closed. Returns per bedroom the time until toxic gas, heat or smoke make it untenable at head height, a lens of minutes, and the assumptions.

## Who it is for

[Community risk reduction officer](/docs/reference/personas/#community-risk-reduction-officer), [Fire captain](/docs/reference/personas/#fire-captain), [Fire training officer](/docs/reference/personas/#fire-training-officer), [Houston homeowner before a storm](/docs/reference/personas/#houston-homeowner-before-a-storm), [Older adult or family](/docs/reference/personas/#older-adult-or-family).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `scan` | string | yes |  | Scan id. Filled from the selected building. |
| `fire_room` | string |  |  | Room id or room type (e.g. 'Living Room'); default: living room, then kitchen, then the largest room. Asked as: "Which room does the fire start in?" |
| `growth` | string |  | `"fast"` | t-squared growth: slow, medium, fast or ultrafast. Saved preference `fire.growth`. |
| `peak_kw` | number (kW) |  | `2000` | Peak heat release (an upholstered sofa is about 2 MW). Saved preference `fire.peak_kw`. Range: more than 50, at most 10000. |
| `escape_min` | number (min) |  | `3.0` | Time people need to wake and get out. Saved preference `fire.escape_min`. Range: more than 0, at most 15. |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Doors and windows | `matterport.openings` | required | The verdict is `unknown`, with the reason. |
| Room names | `matterport.room_labels` | required | The verdict is `unknown`, with the reason. |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Draws on the building: a colour per room.
- Panel blocks: `VerdictHeader`, `MetricRow`, `MiniChart`, `CheckList`, `FloorPlanMini`, `AssumptionChips`, `StepLog`.
- Speed: slow. Read-only.

## How it works

Smoke Clock: survivable time in each bedroom, bedroom doors open and closed, for a fire in a chosen room. Runs NIST's CFAST two-zone fire model (public domain) on the measured rooms and doorways and reports CFAST's own outputs.

## Reliability

Every metric and finding carries its layer, its method and a high, medium or low label, set by the tool for each value. See [findings and reliability](/docs/concepts/findings-and-reliability/).

## Limits

- Needs: doors and windows, room names. On a scan without them, the verdict is `unknown` and says why.
- The agent asks before running it, because it runs NIST's CFAST smoke model, which takes minutes per scan.
- It is slow: progress steps reach the workspace while it runs.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

Not run when the docs are built: it takes minutes. In the app the agent asks before it starts.

## Run it

```sh
threshold run smoke_clock --scan <scan-id>
curl -X POST http://127.0.0.1:8787/api/tools/smoke_clock/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `smoke_clock`. See [MCP server and CLI](/docs/mcp/).
