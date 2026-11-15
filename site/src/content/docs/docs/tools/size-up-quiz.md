---
title: "Size-up quiz"
description: "Training: read a house from outside (bedrooms, stairs, kitchen side, floors) and get graded against its measured interior."
sidebar: {"label": "Size-up quiz"}
---

Training: read a house from outside (bedrooms, stairs, kitchen side, floors) and get graded against its measured interior.

## What it answers

- Give me a size-up drill on this house
- Score my size-up

For the agent, the tool is described as: Builds a size-up training exercise for one house: outside views of sides A to D (drone photos, else oblique aerials), questions a company officer answers from outside, the answer key from the measured interior, and scoring when `answers` are given.

## Who it is for

[Fire captain](/docs/reference/personas/#fire-captain), [Fire training officer](/docs/reference/personas/#fire-training-officer).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `scan` | string | yes |  | Scan id of a house. Filled from the selected building. |
| `answers` | object |  |  | Trainee answers to score: &#123;question id: answer}. Choice and count questions take a value; point questions take a list of [lon, lat]. |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Rooms | `matterport.rooms` | required | The verdict is `unknown`, with the reason. |
| Room names | `matterport.room_labels` | required | The verdict is `unknown`, with the reason. |
| Drone photos | `drone.photos` | optional | vexcel obliques |
| Aerial photo | `vexcel.ortho` | required | The verdict is `unknown`, with the reason. |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Panel blocks: `VerdictHeader`, `EvidenceStrip`, `CheckList`, `MetricRow`, `StepLog`.
- Speed: fast. Read-only.

## How it works

Size-up quiz: the questions a company officer answers from outside a house (how many floors, which side has the kitchen, where the bedrooms and stairs are), shown with drone or oblique views of each side, with the measured interior as the answer key and a scoring function. Pass `answers` to score a trainee.

## Reliability

Sources this tool gave on the test home:

| Where it came from | Layer | Method | Reliability | Note |
|---|---|---|---|---|
| Measured from the scan | `matterport` | `geometry` | high | Answer key from the scan's rooms and floors, placed on the map by its geocoordinates |
| Looked up in the drone capture | `drone` | `lookup` | high | Drone photos chosen by camera bearing and gimbal |

The tool sets the label for each value. A model never does.

## Limits

- Needs: rooms, room names, aerial photo. On a scan without them, the verdict is `unknown` and says why.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

<p class="verdict"><span class="st unknown">Unknown</span> Only the floor count can be asked: this scan has no geocoordinates or aerial reading to place rooms on a side.</p>

| Value | Result | Where it came from | Reliability |
|---|---|---|---|
| Questions | <span class="num">1</span> | Measured from the scan | high |
| Outside views | <span class="num">0</span> | Looked up in the drone capture | high |

Findings: 1 unknown, 1 pass.

## Run it

```sh
threshold run size_up_quiz --scan <scan-id>
curl -X POST http://127.0.0.1:8787/api/tools/size_up_quiz/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `size_up_quiz`. See [MCP server and CLI](/docs/mcp/).
