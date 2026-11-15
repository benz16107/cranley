---
title: "Commute fit"
description: "Estimated drive time from where your people live to each candidate office: the median, who gets a long commute, and transit nearby."
sidebar: {"label": "Commute fit"}
---

Estimated drive time from where your people live to each candidate office: the median, who gets a long commute, and transit nearby.

## What it answers

- Our people live in these zip codes; which office keeps commutes short?

For the agent, the tool is described as: For an office relocation: given employees' home zip codes (or points) and 1 to 10 candidate buildings, estimates each person's one-way drive (straight line x detour, a low-reliability estimate), the head-weighted median per candidate, who would commute longer than a limit or lose time against the current office, and bus and rail stops near each candidate.

## Who it is for

[Office relocation lead](/docs/reference/personas/#office-relocation-lead), [Office tenant](/docs/reference/personas/#office-tenant).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `candidates` | array | yes |  | Candidate offices: scans, CoStar properties, addresses or points. Asked as: "Which buildings are you choosing between?" |
| `employees` | array | yes |  | Asked as: "Where do your employees live? Zip codes, with a head count after a colon (77002:12), or lon,lat points." Saved preference `commute.employees`. |
| `current` | Place |  |  | Where the office is now, to show who gains or loses time. |
| `long_min` | number (min) |  | `45` | A one-way commute longer than this counts as long. Saved preference `commute.long_min`. Range: at least 10, at most 180. |
| `worse_min` | number (min) |  | `15` | A move that adds this much to someone's commute is flagged. Saved preference `commute.worse_min`. Range: at least 1, at most 120. |
| `detour` | number |  | `1.3` | Road distance over straight-line distance. Saved preference `commute.detour`. Range: at least 1.0, at most 2.5. |
| `check_transit` | boolean |  | `true` | Count bus stops and rail stations near each candidate (OpenStreetMap). |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Osm | `osm` | optional | no transit count |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Panel blocks: `VerdictHeader`, `MetricRow`, `RankedTable`, `MiniChart`, `CheckList`, `EvidenceStrip`, `StepLog`.
- Its own ranked table: Median min, Long commutes %, Longest min, Transit stops 800 m.
- Speed: fast. Read-only.

## How it works

Commute fit: how long employees would drive to each candidate office, from where they live (zip codes or points).

## Reliability

Every metric and finding carries its layer, its method and a high, medium or low label, set by the tool for each value. See [findings and reliability](/docs/concepts/findings-and-reliability/).

## Limits

- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

Not run: it needs `candidates`, `employees`, which only a person or a phone on site can give.

## Run it

```sh
threshold run commute_fit
curl -X POST http://127.0.0.1:8787/api/tools/commute_fit/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `commute_fit`. See [MCP server and CLI](/docs/mcp/).
