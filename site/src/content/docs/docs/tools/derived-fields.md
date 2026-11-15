---
title: "Derived fields"
description: "Proposes the record fields this property lacks, measured from the scan and the aerial photo."
sidebar: {"label": "Derived fields"}
---

Proposes the record fields this property lacks, measured from the scan and the aerial photo.

## What it answers

- What could we add to this record?
- What does the scan know that CoStar doesn't?

For the agent, the tool is described as: For one scan, list the fields its CoStar or listing record lacks that the data can supply: area by room type, ceiling heights, door and window counts, glazed area, amenities, parking, roof material and condition, building height, footprint, pool. Each with value, method, confidence, evidence, and whether the record already has it.

## Who it is for

[CoStar research lead](/docs/reference/personas/#costar-research-lead), [CoStar researcher](/docs/reference/personas/#costar-researcher), [Insurance underwriter](/docs/reference/personas/#insurance-underwriter).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `scan` | string | yes |  | Scan id. Filled from the selected building. |
| `aerial` | boolean |  | `true` | Read the aerial facts (roof, height, footprint, pool); cached lookups. |
| `vision` | boolean |  | `false` | Also read panoramas and count stalls from above (uses the shared vision model). Saved preference `truth.deep`. |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Rooms | `matterport.rooms` | required | The verdict is `unknown`, with the reason. |
| Property record | `costar.property` | optional | The tool runs without it. |
| Aerial photo | `vexcel.ortho` | optional | The tool runs without it. |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Panel blocks: `VerdictHeader`, `MetricRow`, `MiniChart`, `CheckList`, `EvidenceStrip`, `StepLog`.
- Speed: slow. Read-only.

## How it works

Derived fields: the record fields a property lacks that the scan and the aerial photo can supply.

## Reliability

Sources this tool gave on the test home:

| Where it came from | Layer | Method | Reliability | Note |
|---|---|---|---|---|
| Measured from the scan | `matterport` | `geometry` | high | Matterport room areas and the wall graph |
| Measured from the scan | `matterport` | `geometry` | high | 6 of 6 rooms have a measured height |
| Measured from the scan | `matterport` | `geometry` | high | Openings in the wall graph |
| Looked up in the scan | `matterport` | `lookup` | medium | Matterport room labels (by furniture) |
| Looked up in the scan | `matterport` | `lookup` | high |  |

The tool sets the label for each value. A model never does. The tools give a scan's wall graph the layer `matterport` whichever device made the scan, so a phone scan's geometry carries that label too.

## Limits

- Needs: rooms. On a scan without it, the verdict is `unknown` and says why.
- It is slow: progress steps reach the workspace while it runs.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

<p class="verdict"><span class="st pass">Pass</span> 15 fields the record lacks, 0 it already has.</p>

| Value | Result | Where it came from | Reliability |
|---|---|---|---|
| Measured interior area | <span class="num">862 ft²</span> | Measured from the scan | high |
| Typical ceiling height | <span class="num">8 ft</span> | Measured from the scan | high |
| Tallest ceiling | <span class="num">8 ft</span> | Measured from the scan | high |
| Doors and openings | <span class="num">6</span> | Measured from the scan | high |
| Area, bedroom | <span class="num">344 ft²</span> | Measured from the scan | high |
| Area, living room | <span class="num">324 ft²</span> | Measured from the scan | high |
| Area, kitchen | <span class="num">113 ft²</span> | Measured from the scan | high |
| Area, bathroom | <span class="num">48 ft²</span> | Measured from the scan | high |
| Area, hallway | <span class="num">32 ft²</span> | Measured from the scan | high |
| Windows | <span class="num">5</span> | Measured from the scan | high |

5 more values are in the full result.

| Check | Measured | Against | Status |
|---|---|---|---|
| Measured interior area | <span class="num">862</span> |  | <span class="st pass">pass</span> |
| Area, bedroom | <span class="num">344</span> |  | <span class="st pass">pass</span> |
| Area, living room | <span class="num">324</span> |  | <span class="st pass">pass</span> |
| Area, kitchen | <span class="num">113</span> |  | <span class="st pass">pass</span> |
| Area, bathroom | <span class="num">48</span> |  | <span class="st pass">pass</span> |
| Area, hallway | <span class="num">32</span> |  | <span class="st pass">pass</span> |
| Typical ceiling height | <span class="num">8</span> |  | <span class="st pass">pass</span> |
| Tallest ceiling | <span class="num">8</span> |  | <span class="st pass">pass</span> |

7 more checks are in the full result.

Findings: 15 pass.

What it reported while it ran:

1. Derived 15 fields from the plan

## Run it

```sh
threshold run derived_fields --scan <scan-id>
curl -X POST http://127.0.0.1:8787/api/tools/derived_fields/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `derived_fields`. See [MCP server and CLI](/docs/mcp/).
