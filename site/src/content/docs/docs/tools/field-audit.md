---
title: "Field audit"
description: "Across many scans, which record fields disagree with what the scans measure, ranked, with evidence."
sidebar: {"label": "Field audit"}
---

Across many scans, which record fields disagree with what the scans measure, ranked, with evidence.

## What it answers

- Where are our records most often wrong?

For the agent, the tool is described as: For a set of scans (or a spread sample of homes, apartment units, offices and industrial), compare every cheap record claim with the plan, count disagreements by field (area off by more than 10%, bedroom and bathroom counts, stories, ceiling height), then re-check the most interesting disagreements with the aerial photo and panoramas and judge which side looks wrong. Slow: minutes for 150 scans.

## Who it is for

[CoStar research lead](/docs/reference/personas/#costar-research-lead), [CoStar researcher](/docs/reference/personas/#costar-researcher).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `scans` | array |  |  | Scan ids to audit; empty draws a spread sample. |
| `sample` | integer |  | `150` | Scans to draw when none are given. Range: at least 4, at most 400. |
| `deep_top` | integer |  | `15` | Disagreements to re-check with the aerial photo and panoramas. Range: at least 0, at most 30. |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Property record | `costar.property` | required | The verdict is `unknown`, with the reason. |
| Rooms | `matterport.rooms` | required | The verdict is `unknown`, with the reason. |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Panel blocks: `VerdictHeader`, `MetricRow`, `MiniChart`, `CheckList`, `EvidenceStrip`, `StepLog`.
- Speed: slow. Read-only.

## How it works

Field audit: the CoStar researcher's version of record versus reality, across many properties.

## Reliability

Every metric and finding carries its layer, its method and a high, medium or low label, set by the tool for each value. See [findings and reliability](/docs/concepts/findings-and-reliability/).

## Limits

- Needs: property record, rooms. On a scan without them, the verdict is `unknown` and says why.
- It is slow: progress steps reach the workspace while it runs.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

<p class="verdict"><span class="st unknown">Cannot answer here</span> the CoStar kit is not configured: set COSTAR_KIT_DIR (the unpacked kit), COSTAR_KIT_ZIP or COSTAR_KIT_URL, with COSTAR_ZIP_PASSWORD for a zip</p>

A phone scan has walls, doors, windows, rooms and objects, but no location, no photos and no property record.

## Run it

```sh
threshold run field_audit
curl -X POST http://127.0.0.1:8787/api/tools/field_audit/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `field_audit`. See [MCP server and CLI](/docs/mcp/).
