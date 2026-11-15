---
title: Findings and reliability
description: Every number carries its layer, its method and a reliability label. A model never states a measured value.
---

Cranley's rule is that a number goes from a calculation to a result object to the screen. It never passes through a model's text.

## What a result holds

| Part | What it is |
|---|---|
| Verdict | `pass`, `warn`, `fail` or `unknown`, with one sentence |
| Metrics | Measured values, each with a unit and a source |
| Checks | One rule each: what was measured, the threshold, and the status |
| Findings | The things worth a look, each anchored to a room, a doorway, a wall, a point in a panorama or a place on the map |
| Assumptions | What the tool assumed, and whether the person can edit it |

## The source on every value

Each metric and each finding carries a source with four parts.

| Part | Values |
|---|---|
| Layer | `matterport`, `vexcel`, `costar`, `drone`, `model` or `phone` |
| Method | `geometry`, `vision`, `lookup`, `simulation`, `sensor` or `manual` |
| Confidence | `high`, `medium` or `low` |
| Note | A sentence about what the value rests on |

The app says this in plain words: "Measured from the scan", "Seen in aerial photos", "From the property record", with a mark for how sure. The tool sets the label for each value. A model never does.

For example, the door widths tool labels a doorway's width as geometry with medium confidence, and its note says that a hinged door's leaf takes a few centimetres off the opening.

## Unknown is an answer

When a scan cannot answer, the tool says so. The verdict is `unknown`, and the sentence gives the reason: no wall graph, no door data, no location, unscanned space. Every plan carries a quality block that tools check first. In the app, `unknown` is hatched and never shown as a pass.

When we ran every tool on a 15-place demo set through the real API, 266 runs answered, 62 said "cannot answer here", 1 failed on a bad input and 0 were judged wrong.

## What the agent may say

The agent's closing message is graded before the person sees it. The grader checks that the message:

1. is at most three short sentences
2. contains no measurement, count, time, distance or money
3. says a check was skipped only when the transcript shows it
4. names where to look first

A real turn once claimed that none of the checks ran, after twelve runs. That mistake is why the grader exists.

## What waits for a yes

Slow or invasive steps wait for the person: a smoke simulation, a read of every panorama by the vision model, a plan edit, a roll-up of a whole city. The choices are "Run it", "Skip it" and "Always run it here".

## What was not checked

Every PDF report ends with a list of what was not checked. The fields are defined in the [result format](/docs/reference/result-format/).
