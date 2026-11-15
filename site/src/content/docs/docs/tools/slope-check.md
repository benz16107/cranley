---
title: "Slope check"
description: "Uses the phone as a level: a ramp's slope and cross slope against the ADA limits, a threshold's bevel, or how far a door frame is out of plumb."
sidebar: {"label": "Slope check"}
---

Uses the phone as a level: a ramp's slope and cross slope against the ADA limits, a threshold's bevel, or how far a door frame is out of plumb.

## What it answers

- Is this ramp too steep for a wheelchair?
- Is the door frame straight?

For the agent, the tool is described as: Phone only: a person runs this from the phone app, an agent cannot. Judge a slope read by a phone's tilt sensor. mode ramp: running slope against ADA 405.2 (1:12) and cross slope against 405.3 (1:48). mode threshold: a bevel against ADA 303.3 (1:2). mode plumb: a door frame's lean. Needs readings from the phone app; it cannot run from a scan alone.

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `mode` | string |  | `"ramp"` | ramp: laid on the surface, long edge up the slope. threshold: laid on the bevel. plumb: long edge held against a door frame. One of: `ramp`, `threshold`, `plumb`. |
| `reading_deg` | number | yes |  | Tilt along the phone's long axis, degrees, averaged while it lay still. Range: at least -90, at most 90. |
| `flipped_deg` | number |  |  | The same after turning the phone end for end. |
| `cross_deg` | number |  |  | Tilt across the phone's short axis. |
| `cross_flipped_deg` | number |  |  |  |
| `spread_deg` | number |  | `0.0` | Standard deviation of the samples: how still it lay. Range: at least 0, at most 45. |
| `scan` | string |  |  |  |
| `room` | string |  |  |  |
| `opening` | string |  |  |  |
| `capture` | string |  |  | Capture id of the sensor reading. |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Tilt | `phone.tilt` | required | The verdict is `unknown`, with the reason. |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Panel blocks: `VerdictHeader`, `MetricRow`, `CheckList`, `AssumptionChips`, `StepLog`.
- Speed: fast. Read-only.

## How it works

Slope check: the phone as a level. Laid on a ramp it reads the running slope and the cross slope from its tilt sensor, judged against the ADA ramp limits; on a threshold's bevel, against the ADA bevel limit; held against a door frame, how far the frame is out of plumb.

## Reliability

Every metric and finding carries its layer, its method and a high, medium or low label, set by the tool for each value. See [findings and reliability](/docs/concepts/findings-and-reliability/).

## Limits

- Needs: phone.tilt. On a scan without it, the verdict is `unknown` and says why.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

Not run: it needs `reading_deg`, which only a person or a phone on site can give.

## Run it

```sh
threshold run slope_check --scan <scan-id>
curl -X POST http://127.0.0.1:8787/api/tools/slope_check/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `slope_check`. See [MCP server and CLI](/docs/mcp/).
