---
title: "Where am I"
description: "Finds the scanned building you are standing in from the phone's GPS, or says there is none here."
sidebar: {"label": "Where am I"}
---

Finds the scanned building you are standing in from the phone's GPS, or says there is none here.

## What it answers

- Which building am I in?
- Is this address scanned?

For the agent, the tool is described as: Phone only: a person runs this from the phone app, an agent cannot. From a phone GPS fix [lon, lat]: the scanned buildings within 2 km, nearest first, and whether the person is at one. Where there is no scan it offers the aerial-only tools (roof_facts, truck_access, parking_count, risk_sheet) at that point.

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `geo` | array | yes |  | [lon, lat] of the phone's fix. |
| `accuracy_m` | number |  |  | The fix's horizontal accuracy as the phone reports it. |
| `capture` | string |  |  |  |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Gps | `phone.gps` | required | The verdict is `unknown`, with the reason. |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Draws on the building: pins on what it found.
- Panel blocks: `VerdictHeader`, `MetricRow`, `EvidenceStrip`, `StepLog`, `ActionBar`.
- Speed: fast. Read-only.

## How it works

Where am I: the phone's GPS fix finds the scanned building the person is standing in, or says there is none and offers the tools that need only an aerial photo at that spot.

## Reliability

Every metric and finding carries its layer, its method and a high, medium or low label, set by the tool for each value. See [findings and reliability](/docs/concepts/findings-and-reliability/).

## Limits

- Needs: phone.gps. On a scan without it, the verdict is `unknown` and says why.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

Not run: it needs `geo`, which only a person or a phone on site can give.

## Run it

```sh
threshold run where_am_i
curl -X POST http://127.0.0.1:8787/api/tools/where_am_i/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `where_am_i`. See [MCP server and CLI](/docs/mcp/).
