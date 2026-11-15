---
title: "Earthquake readiness"
description: "A safe spot in each room away from windows, tall or heavy furniture near the beds, and where to find the gas shutoff on site."
sidebar: {"label": "Earthquake readiness"}
---

A safe spot in each room away from windows, tall or heavy furniture near the beds, and where to find the gas shutoff on site.

## What it answers

- Where should we take cover in each room during an earthquake?
- Is anything tall near the kids' beds?

For the agent, the tool is described as: Earthquake preparation for one scanned home (Drop, Cover and Hold On): per room, the spot along an inside wall farthest from windows; tall or heavy furniture near each bed from the bedroom panoramas (a checklist when they cannot be read); and an on-site task to find the gas meter shutoff. For Los Angeles households and anyone in an earthquake zone.

## Who it is for

[Los Angeles household preparing for an earthquake](/docs/reference/personas/#los-angeles-household-preparing-for-an-earthquake).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `scan` | string | yes |  | Scan id. Filled from the selected building. |
| `look` | boolean |  | `true` | Read the bedroom panoramas for tall or heavy furniture. Saved preference `quake.look`. |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Wall outline | `matterport.walls` | required | The verdict is `unknown`, with the reason. |
| 360° photos | `matterport.panoramas` | optional | a checklist per bedroom |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Draws on the building: pins on what it found.
- Panel blocks: `VerdictHeader`, `MetricRow`, `CheckList`, `EvidenceStrip`, `Note`, `StepLog`.
- Speed: slow. Read-only.

## How it works

Earthquake readiness: a safe spot in each room, tall or heavy things near the beds, and what to check on site.

## Reliability

Sources this tool gave on the test home:

| Where it came from | Layer | Method | Reliability | Note |
|---|---|---|---|---|
| Measured from the scan | `matterport` | `geometry` | high | Wall graph: windows and walls shared with another room |
| Seen in a model | `model` | `vision` | low | Vision model reading the bedroom panoramas |
| Looked up in a model | `model` | `lookup` | high | Earthquake Country Alliance and ready.gov guidance |

The tool sets the label for each value. A model never does.

## Limits

- Needs: wall outline. On a scan without it, the verdict is `unknown` and says why.
- It is slow: progress steps reach the workspace while it runs.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

<p class="verdict"><span class="st pass">Pass</span> Safe spots found in 6 of 6 rooms. Bedrooms get a checklist; the panoramas were not read. The gas shutoff is a job for someone on site.</p>

| Value | Result | Where it came from | Reliability |
|---|---|---|---|
| Rooms with a safe spot | <span class="num">6</span> | Measured from the scan | high |
| Tall items seen | <span class="num">0</span> | Seen in a model | low |

| Check | Measured | Against | Status |
|---|---|---|---|
| Living Room: safe spot, distance to the nearest window | <span class="num">4.01</span> |  | <span class="st pass">pass</span> |
| Bedroom 1: safe spot, distance to the nearest window | <span class="num">3.6</span> |  | <span class="st pass">pass</span> |
| Bedroom 2: safe spot, distance to the nearest window | <span class="num">3.6</span> |  | <span class="st pass">pass</span> |
| Kitchen: safe spot, distance to the nearest window | <span class="num">2.9</span> |  | <span class="st pass">pass</span> |
| Bathroom: safe spot, distance to the nearest window | <span class="num">1.55</span> |  | <span class="st pass">pass</span> |
| Hallway: safe spot, distance to the nearest window | <span class="num">2.54</span> |  | <span class="st pass">pass</span> |

Findings: 6 pass, 3 unknown.

What it reported while it ran:

1. Finding a safe spot in 6 rooms, along an inside wall and away from windows

## Run it

```sh
threshold run quake_ready --scan <scan-id>
curl -X POST http://127.0.0.1:8787/api/tools/quake_ready/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `quake_ready`. See [MCP server and CLI](/docs/mcp/).
