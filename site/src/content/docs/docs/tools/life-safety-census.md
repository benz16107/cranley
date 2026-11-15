---
title: "Smoke alarm census"
description: "Checks every bedroom's ceiling photo for a smoke alarm and lists where none was seen, as leads to check."
sidebar: {"label": "Smoke alarm census"}
---

Checks every bedroom's ceiling photo for a smoke alarm and lists where none was seen, as leads to check.

## What it answers

- Do the bedrooms in this complex have smoke alarms?
- Which units should the install crew visit?

For the agent, the tool is described as: For one scan or every scan of a property: each bedroom (and each hallway serving two or more bedrooms, and each level) read for a smoke alarm in its panorama. Each is 'seen' with the photo crop, 'not seen' (a lead, not a violation) or 'could not see'. Cites Texas Property Code 92.255 or California law by the scan's city.

## Who it is for

[Apartment manager](/docs/reference/personas/#apartment-manager), [Community risk reduction officer](/docs/reference/personas/#community-risk-reduction-officer), [Fire captain](/docs/reference/personas/#fire-captain), [Renter checking a listing](/docs/reference/personas/#renter-checking-a-listing).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `scan` | string |  |  | Scan id. Filled from the selected building. |
| `whole_property` | boolean |  | `false` | Check every scan of the selected scan's CoStar property. |
| `property_id` | integer |  |  | CoStar property id; checks all its scans. |
| `read_panoramas` | boolean |  | `true` | Send unread panoramas to the vision model. |
| `max_scans_read` | integer |  | `3` | At most this many unread scans go to the vision model in one run; scans read before are free. Range: at least 0, at most 12. |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| 360° photos | `matterport.panoramas` | required | The verdict is `unknown`, with the reason. |
| Room names | `matterport.room_labels` | required | The verdict is `unknown`, with the reason. |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Draws on the building: doors, walls or rooms coloured by status; pins on what it found.
- Panel blocks: `VerdictHeader`, `MetricRow`, `CheckList`, `EvidenceStrip`, `FloorPlanMini`, `StepLog`, `Note`.
- Speed: slow. Read-only.

## How it works

Life-safety census: every sleeping room checked for a smoke alarm seen in its panorama, with the photo as evidence. Results are leads to check on site: "not seen" is never "absent".

## Reliability

Sources this tool gave on the test cafe:

| Where it came from | Layer | Method | Reliability | Note |
|---|---|---|---|---|
| Seen in a model | `model` | `vision` | medium | Vision model on the room's central panorama, all six faces (face 0 is the ceiling) |
| Seen in a model | `model` | `vision` | low | Nothing found in one panorama: an alarm on a wall, behind a fan or outside the photo is missed |

The tool sets the label for each value. A model never does. The tools give a scan's wall graph the layer `matterport` whichever device made the scan, so a phone scan's geometry carries that label too.

## Limits

- Needs: 360° photos, room names. On a scan without them, the verdict is `unknown` and says why.
- The agent asks before running it, because it reads every bedroom's ceiling panorama with the vision model.
- It is slow: progress steps reach the workspace while it runs.
- A result is a planning aid, not an inspection.

## On the made-up test cafe

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

<p class="verdict"><span class="st unknown">Unknown</span> No bedrooms with a room type in this scan.</p>

| Value | Result | Where it came from | Reliability |
|---|---|---|---|
| Bedrooms | <span class="num">0</span> | Seen in a model | medium |
| Alarm seen | <span class="num">0</span> | Seen in a model | medium |
| Not seen | <span class="num">0</span> | Seen in a model | low |
| Could not see | <span class="num">0</span> | Seen in a model | low |

What it reported while it ran:

1. Sent 0 new scans to the vision model

## Run it

```sh
threshold run life_safety_census --scan <scan-id>
curl -X POST http://127.0.0.1:8787/api/tools/life_safety_census/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `life_safety_census`. See [MCP server and CLI](/docs/mcp/).
