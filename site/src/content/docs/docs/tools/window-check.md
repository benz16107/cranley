---
title: "Window check"
description: "Point the phone out of a window: its compass confirms or corrects which way the room faces and its hours of sun."
sidebar: {"label": "Window check"}
---

Point the phone out of a window: its compass confirms or corrects which way the room faces and its hours of sun.

## What it answers

- Does the bedroom really face east?

For the agent, the tool is described as: Phone only: a person runs this from the phone app, an agent cannot. Compare a phone compass heading taken at a window with the scan's facing for that room's windows (the daylight tool's source), and recompute direct sun hours for the heading. Needs a heading from the phone app.

## Who it is for

[Family planning home security](/docs/reference/personas/#family-planning-home-security), [Plant lover or home office worker choosing a room](/docs/reference/personas/#plant-lover-or-home-office-worker-choosing-a-room).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `scan` | string | yes |  | Scan id. Filled from the selected building. |
| `room` | string | yes |  | Room id the window is in. |
| `heading_deg` | number | yes |  | Compass heading of the phone's top edge, pointing out of the window. Range: at least 0, less than 360. |
| `magnetic` | boolean |  | `true` | The heading is from magnetic north (what phone browsers give). |
| `heading_accuracy_deg` | number |  |  | The phone's own figure, when it gives one. |
| `lat` | number |  |  | From the phone's fix, used when the scan has no location. |
| `lon` | number |  |  |  |
| `date` | string |  |  | Saved preference `daylight.date`. |
| `capture` | string |  |  |  |
| `by_hand` | boolean |  | `false` | The direction was picked by hand (one of eight), not read from the compass. |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Compass | `phone.compass` | required | The verdict is `unknown`, with the reason. |
| Scan position | `matterport.geo` | optional | the phone's facing only, nothing to compare with |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Panel blocks: `VerdictHeader`, `MetricRow`, `CheckList`, `AssumptionChips`, `StepLog`.
- Speed: fast. Read-only.

## How it works

Window check: stand at a window, point the phone straight out, and its compass says which way the window faces. That confirms or corrects the daylight tool's facing and sun hours for the room, which otherwise rest on the scan's compass rotation.

## Reliability

Every metric and finding carries its layer, its method and a high, medium or low label, set by the tool for each value. See [findings and reliability](/docs/concepts/findings-and-reliability/).

## Limits

- Needs: phone.compass. On a scan without it, the verdict is `unknown` and says why.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

Not run: it needs `room`, `heading_deg`, which only a person or a phone on site can give.

## Run it

```sh
threshold run window_check --scan <scan-id>
curl -X POST http://127.0.0.1:8787/api/tools/window_check/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `window_check`. See [MCP server and CLI](/docs/mcp/).
