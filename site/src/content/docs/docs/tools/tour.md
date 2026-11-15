---
title: "Tour"
description: "Answers by showing: a camera tour from the way in to each piece of evidence the other tools found, with one spoken line at each stop. The last step of a fire pre-plan or a wheelchair check of a home."
sidebar: {"label": "Tour"}
---

Answers by showing: a camera tour from the way in to each piece of evidence the other tools found, with one spoken line at each stop. The last step of a fire pre-plan or a wheelchair check of a home.

## What it answers

- Show me what matters for a fire crew in this house
- Walk me through what a wheelchair user would hit

For the agent, the tool is described as: Call this last on a scan, after the other tools have run there. It turns their findings into a camera tour that answers the person's question by showing: from the way in, along the route, stopping at each finding that matters (a narrow door, a bedroom with no smoke alarm seen, a room that floods). Pass the person's question. Suits a fire captain's pre-plan and a wheelchair user's check of a home. Returns the stops in order; each is a finding id.

## Who it is for

[Dog owner choosing a home](/docs/reference/personas/#dog-owner-choosing-a-home), [Fire captain](/docs/reference/personas/#fire-captain), [Fire training officer](/docs/reference/personas/#fire-training-officer), [Parent with young kids choosing a home](/docs/reference/personas/#parent-with-young-kids-choosing-a-home), [Agent or host staging a home virtually](/docs/reference/personas/#agent-or-host-staging-a-home-virtually), [Wheelchair user looking for a home](/docs/reference/personas/#wheelchair-user-looking-for-a-home), [Wheelchair user](/docs/reference/personas/#wheelchair-user).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `scan` | string | yes |  | Scan id. Filled from the selected building. |
| `question` | string |  |  | What the person asked, in their words. It decides which findings the tour stops at. |
| `findings` | array |  |  | Leave this out. The page fills it with the workspace's findings on this scan; without it the tour gathers them from the tools that suit the question. |
| `min_width_m` | number (m) |  | `0.813` | Clear width a door must give, used when the tour gathers findings itself. Saved preference `access.door_width_m`. Range: more than 0.3, at most 2. |
| `standard` | string |  |  | The standard the person's doors are judged by. It also tells a fire pre-plan from an access check when the question does not. Saved preference `access.door_standard`. |
| `max_stops` | integer |  | `6` | Most stops. Range: at least 2, at most 10. |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Rooms | `matterport.rooms` | required | The verdict is `unknown`, with the reason. |
| Doors and windows | `matterport.openings` | optional | stops in order of importance, no walking path |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Draws on the building: a route with its narrow points.
- Panel blocks: `VerdictHeader`, `EvidenceStrip`, `StepLog`.
- Speed: fast. Read-only.

## How it works

Tour: answers a question by showing. Turns the findings on one scan into a camera tour: from the way in, along the walking route, to each piece of evidence, with one line to say at each stop.

## Reliability

Sources this tool gave on the test home:

| Where it came from | Layer | Method | Reliability | Note |
|---|---|---|---|---|
| Looked up in a model | `model` | `lookup` | medium | A tour of findings other tools made; each stop keeps its own finding's words |
| Measured from the scan | `matterport` | `geometry` | medium | Shortest walkable route over the wall graph in empty rooms; furniture is not counted |
| Measured from the scan | `matterport` | `geometry` | medium | Matterport wall graph, empty rooms; door widths are the opening in the wall |
| Measured from the scan | `matterport` | `geometry` | medium | Opening width in the wall graph; a hinged door's leaf takes a few centimetres off it |
| Seen in a model | `model` | `vision` | low | Nothing found in one panorama: an alarm on a wall, behind a fan or outside the photo is missed |

The tool sets the label for each value. A model never does. The tools give a scan's wall graph the layer `matterport` whichever device made the scan, so a phone scan's geometry carries that label too.

## Limits

- Needs: rooms. On a scan without it, the verdict is `unknown` and says why.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

<p class="verdict"><span class="st fail">Fail</span> A tour of 6 findings on this scan, from the way in. Play it from the building's toolbar; each stop reads its finding's own words.</p>

| Value | Result | Where it came from | Reliability |
|---|---|---|---|
| Stops | <span class="num">6</span> | Looked up in a model | medium |
| Findings considered | <span class="num">20</span> | Looked up in a model | medium |

Findings: 1 warn, 4 fail, 1 unknown.

What it reported while it ran:

1. Egress routes: 10 findings
1. Door widths: 4 findings
1. Smoke alarm census: 2 findings
1. Step-free route: 4 findings
1. Chose 6 stops from 20 placed findings, in walking order from the way in

## Run it

```sh
threshold run tour --scan <scan-id>
curl -X POST http://127.0.0.1:8787/api/tools/tour/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `tour`. See [MCP server and CLI](/docs/mcp/).
