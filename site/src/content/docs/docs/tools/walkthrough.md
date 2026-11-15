---
title: "Walk-through"
description: "A quick safety census of a home with no scan, from a short video you record walking through it: rooms, smoke alarms, hazards and belongings."
sidebar: {"label": "Walk-through"}
---

A quick safety census of a home with no scan, from a short video you record walking through it: rooms, smoke alarms, hazards and belongings.

## What it answers

- Check my own home for smoke alarms
- My home was never scanned

For the agent, the tool is described as: Phone only: a person runs this from the phone app, an agent cannot. Read frames of a walk-through video of an unscanned home: room types, smoke alarms seen or not seen per bedroom and hallway (IRC R314.3), trip and fire hazards, belongings. A first look; rooms the camera missed are not in it. Needs a video capture from the phone app.

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `capture` | string | yes |  | Capture id of the walk-through video. |
| `geo` | array |  |  | [lon, lat] of the home, from the phone's fix. |
| `max_frames` | integer |  | `8` | Frames read from the video. Range: at least 2, at most 16. |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Video | `phone.video` | required | The verdict is `unknown`, with the reason. |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Panel blocks: `VerdictHeader`, `MetricRow`, `CheckList`, `EvidenceStrip`, `AssumptionChips`, `StepLog`.
- Speed: slow. Read-only.

## How it works

Walk-through: a quick safety census of a home that has no scan, from a short video the person records walking through it. Frames go to the vision reader for the room type, whether a smoke alarm is on the ceiling, hazards and belongings. It is a first look, not a survey: a room the camera did not show is not in it, and "not seen" is a lead to check, never a finding of absence.

## Reliability

Every metric and finding carries its layer, its method and a high, medium or low label, set by the tool for each value. See [findings and reliability](/docs/concepts/findings-and-reliability/).

## Limits

- Needs: phone.video. On a scan without it, the verdict is `unknown` and says why.
- It is slow: progress steps reach the workspace while it runs.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

Not run: it needs `capture`, which only a person or a phone on site can give.

## Run it

```sh
threshold run walkthrough
curl -X POST http://127.0.0.1:8787/api/tools/walkthrough/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `walkthrough`. See [MCP server and CLI](/docs/mcp/).
