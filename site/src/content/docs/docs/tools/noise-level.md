---
title: "Noise level"
description: "How loud each room is, from the phone's microphone: an uncalibrated A-weighted level per room, best read as which rooms are quieter."
sidebar: {"label": "Noise level"}
---

How loud each room is, from the phone's microphone: an uncalibrated A-weighted level per room, best read as which rooms are quieter.

## What it answers

- Which bedroom is quietest?
- How loud is the street side?

For the agent, the tool is described as: Phone only: a person runs this from the phone app, an agent cannot. A-weighted sound level (LAeq) per room from a phone microphone, as a per-room lens, against the WHO indoor guideline levels. Uncalibrated: absolute levels are good to about 10 dB, differences between rooms to about 3 dB. Needs readings from the phone app.

## Who it is for

[Light sleeper or night-shift worker](/docs/reference/personas/#light-sleeper-or-night-shift-worker).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `readings` | array | yes |  | One A-weighted level per room, from the phone app. |
| `scan` | string |  |  |  |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Microphone | `phone.microphone` | required | The verdict is `unknown`, with the reason. |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Draws on the building: a colour per room.
- Panel blocks: `VerdictHeader`, `MetricRow`, `MiniChart`, `CheckList`, `FloorPlanMini`, `AssumptionChips`, `StepLog`.
- Speed: fast. Read-only.

## How it works

Noise level: an A-weighted sound level per room from the phone's microphone, as a lens.

## Reliability

Every metric and finding carries its layer, its method and a high, medium or low label, set by the tool for each value. See [findings and reliability](/docs/concepts/findings-and-reliability/).

## Limits

- Needs: phone.microphone. On a scan without it, the verdict is `unknown` and says why.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

Not run: it needs `readings`, which only a person or a phone on site can give.

## Run it

```sh
threshold run noise_level --scan <scan-id>
curl -X POST http://127.0.0.1:8787/api/tools/noise_level/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `noise_level`. See [MCP server and CLI](/docs/mcp/).
