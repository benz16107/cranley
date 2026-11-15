---
title: Tools
description: A tool is a manifest and a handler. The same manifest feeds the agent, the web app, the MCP server and the CLI.
---

A tool answers one kind of question about a building. It is a folder under `server/threshold/tools/` with two parts.

## The manifest

The manifest says what the tool is: its id, title and summary, who it is for, a JSON Schema of its inputs, the data layers it needs, the panel blocks it fills and what it draws. The registry finds every tool by itself, and the same manifest feeds four places:

- the agent, which reads it to choose tools
- the web app's tool list
- the [MCP server](/docs/mcp/)
- the `threshold` command line

A tool added once shows up in all four.

## Inputs fill themselves where they can

Each input can name where its value comes from:

- the selected building
- a saved preference, such as `access.door_width_m`
- a persona's preset
- its default

Only an input that nothing fills becomes a question to the person. That is why the agent asks for your chair's width and nothing else.

## The handler

The handler is a function, `run(ctx, inputs)`, that returns a [tool result](/docs/reference/result-format/): a verdict, metrics, checks, findings, overlays and assumptions. It gets the plan of a scan from `ctx.plan(sid)`, or the coordinates, address and record of any place from `ctx.site(place)`.

```python
@tool(id="ceiling_height", title="Ceiling height", summary="Rooms lower than you need.",
      model_description="Check every room's ceiling height in one scan against a minimum.",
      requires=[{"layer": "matterport.rooms"}], blocks=["VerdictHeader", "CheckList", "StepLog"])
def run(ctx, inputs: Inputs) -> ToolResult:
    rooms = [r for r in ctx.plan(inputs.scan)["rooms"] if r.get("height")]
    ctx.step(f"Read {len(rooms)} room heights")
    low = [r for r in rooms if r["height"] < inputs.min_height_m]
    ...
```

## Rules every tool follows

- **Numbers come from code.** Every measured value goes into a metric, a check, a finding or an overlay. The model sees only the verdict's words, finding ids, statuses and titles.
- **Fail softly.** Missing data is an `unknown` verdict with a sentence saying why. It is not an error.
- **Stable finding ids.** A re-run replaces a finding, and one the person rejected stays hidden.
- **Report progress.** Each `ctx.step("...")` reaches the person while the tool runs.
- **Test with a hand-made plan.** Never with sponsor data in the repository.

The engines are shared. Routes, clearance, fit, rule packs, takeoff, sun and water live in `threshold.geometry`. Room labels and objects from panoramas live in `threshold.vision`. Site facts from the air live in `threshold.aerial`. A tool calls them and never copies them.

See the [tool reference](/docs/tools/) for every tool.
