---
title: The agent
description: A composer that picks tools for a need, and an investigator that plans, checks buildings in parallel and asks before expensive steps.
---

Two parts turn a sentence into a workspace.

## The composer

One call with structured output turns the person's sentence into a persona or none, tools with a reason for each, what the tools cannot do for them, and up to four questions.

- Tool and persona ids are fixed lists, so the model cannot invent one.
- The model does not write the questions. They are the chosen tools' required inputs that nothing fills yet.
- A size the person already said, such as a 90 cm piano, is filled in for them to confirm.

## The investigator

The investigator is a deep agent built on LangChain's `deepagents`.

- **It plans.** Its todo list is streamed to the workspace as the plan the person watches.
- **It fans out.** Each building, or each whole property, goes to a subagent with its own context, so ten buildings do not crowd one context window. Buildings are independent, so they are checked at the same time, and the panel shows one lane per subagent.
- **Its tools are the tools.** Every enabled tool becomes an agent tool. The result goes straight into the workspace. The model sees a compact summary and ids, never the numbers.
- **It keeps notes.** Subagents write case notes per building. Long-term memory per building means a second investigation starts from what the last one learned.
- **It loads skills.** Procedures for a fire pre-plan, storm preparation, a step-free home and a record check load only when the need matches.
- **It asks first.** A smoke simulation, a vision read of every panorama, a plan edit or a city roll-up pauses the turn until the person answers. A paused turn is saved to a checkpoint and can resume in any server process, even after a restart.
- **It has a budget.** A turn is bounded by model calls, tool runs and how many subagents run at once. The defaults are 40, 40 and 4.
- **It is graded.** A rubric checks its closing message. See [findings and reliability](/docs/concepts/findings-and-reliability/).

## A turn over HTTP

`POST /api/agent/turn` streams server-sent events: the workspace id first, then one event per operation as it applies, then `done` with a status of `done`, `questions` or `needs_scope`. See [agent and workspace](/docs/reference/api/agent/).

## From other agents

The same tools work from Claude Code, Claude Desktop, Cursor or your own LangChain agent through the [MCP server](/docs/mcp/). With `--write`, the `agent_turn` tool runs a whole investigator turn.

What each LangChain feature does in the product is listed under [sponsor integrations](/docs/sponsor-integrations/).
