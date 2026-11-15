---
title: "Photo measure"
description: "Measures a width or a height from one photo that has a bank card, a sheet of paper or a door of known size in it."
sidebar: {"label": "Photo measure"}
---

Measures a width or a height from one photo that has a bank card, a sheet of paper or a door of known size in it.

## What it answers

- Measure this doorway from my photo

For the agent, the tool is described as: Phone only: a person runs this from the phone app, an agent cannot. Measure a length from a phone photo with a reference of known size in frame (card, letter, a4, or a door leaf), by perspective correction onto the reference's plane. Returns the length with an error that grows as the reference gets small or far. Needs a photo capture.

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `capture` | string | yes |  | Capture id of the photo. |
| `reference` | string |  | `"card"` | What of known size is in frame. One of: `card`, `letter`, `a4`, `door`. |
| `door_width_m` | number |  |  | For reference door: the leaf's width. |
| `what` | string |  | `"the clear width of the doorway"` | What to measure, in words. |
| `points` | Points |  |  | Where the reference's corners and the two ends are; found by the vision reader when missing. |
| `points_from` | string |  | `"vision"` | One of: `vision`, `manual`. |
| `threshold_m` | number |  |  | A minimum to judge the result against. |
| `standard` | string |  |  |  |
| `scan` | string |  |  |  |
| `room` | string |  |  |  |
| `opening` | string |  |  |  |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Photo | `phone.photo` | required | The verdict is `unknown`, with the reason. |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Panel blocks: `VerdictHeader`, `MetricRow`, `CheckList`, `EvidenceStrip`, `AssumptionChips`, `StepLog`.
- Speed: fast. Read-only.

## How it works

Photo measure: a width or a height from one photo with an object of known size in frame.

## Reliability

Every metric and finding carries its layer, its method and a high, medium or low label, set by the tool for each value. See [findings and reliability](/docs/concepts/findings-and-reliability/).

## Limits

- Needs: phone.photo. On a scan without it, the verdict is `unknown` and says why.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

Not run: it needs `capture`, which only a person or a phone on site can give.

## Run it

```sh
threshold run photo_measure --scan <scan-id>
curl -X POST http://127.0.0.1:8787/api/tools/photo_measure/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `photo_measure`. See [MCP server and CLI](/docs/mcp/).
