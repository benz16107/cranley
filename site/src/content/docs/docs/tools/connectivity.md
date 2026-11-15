---
title: "Connectivity"
description: "How well a place is connected: home broadband on offer (fiber, cable, how many providers), bus and rail stops within a walk, the nearest bikeway and the traffic on the nearest counted road. Offered speeds, not measured ones."
sidebar: {"label": "Connectivity"}
---

How well a place is connected: home broadband on offer (fiber, cable, how many providers), bus and rail stops within a walk, the nearest bikeway and the traffic on the nearest counted road. Offered speeds, not measured ones.

## What it answers

- Can I work from home here?
- Is there fiber?
- How far is the nearest train?

For the agent, the tool is described as: Connectivity of a place in Houston or Los Angeles: FCC broadband availability for its block group (share offered 100/20 Mbps, provider, fiber and cable counts), transit stops within `walk_m` (nearest, rail), the nearest bikeway, and annual average daily traffic at the nearest state count station. Broadband is what providers report offering, not a measured speed.

## Who it is for

[Business checking a site](/docs/reference/personas/#business-checking-a-site), [Family checking a neighbourhood](/docs/reference/personas/#family-checking-a-neighbourhood), [Remote worker](/docs/reference/personas/#remote-worker).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `place` | Place | yes |  | Where a tool runs when it does not need a scan: a scan id, a CoStar property id (all its scans), an address,. Filled from the selected building. |
| `walk_m` | number (m) |  | `800` | How far the person is willing to walk to a stop, in metres. Saved preference `getting_around.walk_m`. Range: at least 200, at most 2000. |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Broadband | `public.broadband` | required | The verdict is `unknown`, with the reason. |
| Transit | `public.transit` | required | The verdict is `unknown`, with the reason. |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Panel blocks: `VerdictHeader`, `MetricRow`, `CheckList`, `StepLog`.
- Speed: fast. Read-only.

## How it works

Connectivity: how well a place is connected, by wire and on foot.

## Reliability

Every metric and finding carries its layer, its method and a high, medium or low label, set by the tool for each value. See [findings and reliability](/docs/concepts/findings-and-reliability/).

## Limits

- Needs: public.broadband, public.transit. On a scan without them, the verdict is `unknown` and says why.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

<p class="verdict"><span class="st unknown">Cannot answer here</span> This place has no location to measure from.</p>

A phone scan has walls, doors, windows, rooms and objects, but no location, no photos and no property record.

## Run it

```sh
threshold run connectivity -i place='{"scan": "<scan-id>"}'
curl -X POST http://127.0.0.1:8787/api/tools/connectivity/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `connectivity`. See [MCP server and CLI](/docs/mcp/).
