---
title: "Field check"
description: "Lists what the scan could not settle and a person on site can, and records what they found: confirmed, contradicted or measured."
sidebar: {"label": "Field check"}
---

Lists what the scan could not settle and a person on site can, and records what they found: confirmed, contradicted or measured.

## What it answers

- What should I check when I visit?
- What did the visit change?

For the agent, the tool is described as: The on-site checks a scan's results call for (clear door widths, steps, smoke alarms not seen, the floor height for flood, window facing) and the outcome of each one a person has done with the phone app: confirmed, contradicted or measured, with the capture as evidence. Run from the phone link; by hand it only explains how to start.

## Who it is for

[Apartment manager](/docs/reference/personas/#apartment-manager), [Fire captain](/docs/reference/personas/#fire-captain), [Houston homeowner before a storm](/docs/reference/personas/#houston-homeowner-before-a-storm), [Los Angeles household preparing for an earthquake](/docs/reference/personas/#los-angeles-household-preparing-for-an-earthquake), [Older adult or family](/docs/reference/personas/#older-adult-or-family), [Wheelchair user](/docs/reference/personas/#wheelchair-user).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `scan` | string | yes |  | Scan id. Filled from the selected building. |
| `tasks` | array |  |  | The scan's phone tasks with their outcomes, from the capture routes. Missing when run by hand: then it explains how to start. |
| `offer_phone` | boolean |  | `false` | Set by the server: no phone has sent anything to this workspace yet, so the verdict says how to start one. Never set on the phone. |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Capture | `phone.capture` | required | The verdict is `unknown`, with the reason. |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Draws on the building: pins on what it found.
- Panel blocks: `VerdictHeader`, `MetricRow`, `CheckList`, `EvidenceStrip`, `FloorPlanMini`, `StepLog`.
- Speed: fast. Read-only.

## How it works

Field check: the on-site list. Other tools end in "measure on site", "too close to call" and "not seen"; this turns those into things to do with a phone in the building, and when a capture comes back it reports what the site says about the scan's result: confirmed, contradicted, or measured for the first time.

## Reliability

Every metric and finding carries its layer, its method and a high, medium or low label, set by the tool for each value. See [findings and reliability](/docs/concepts/findings-and-reliability/).

## Limits

- Needs: phone.capture. On a scan without it, the verdict is `unknown` and says why.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

<p class="verdict"><span class="st unknown">Unknown</span> Open this workspace on a phone (Continue on phone) to get the on-site checks for this building. They come from the other tools' results, so run those first.</p>


## Run it

```sh
threshold run field_check --scan <scan-id>
curl -X POST http://127.0.0.1:8787/api/tools/field_check/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `field_check`. See [MCP server and CLI](/docs/mcp/).
