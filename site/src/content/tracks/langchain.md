---
title: "LangChain: Best use of deepagents"
---

Not on the Devpost prize list. Every feature below does a job in the product.md`.

| Feature | Why it is a real use |
|---|---|
| `create_deep_agent` with declarative subagents | One building or one whole property per subagent, each with its own context, so ten buildings do not crowd one context window. |
| Parallel subagents, shown live | Buildings are independent, so they are checked at the same time; middleware reports each tool call and the panel shows one lane per subagent. |
| Planning (`write_todos`) | The plan is the person's progress view, not hidden state. |
| Virtual filesystem and CompositeBackend | Case notes per building in state; `/memories/` in the store; `/skills/` read-only from disk. |
| StoreBackend on MongoDB (long-term memory) | A second investigation of a building starts from what the last one learned. |
| Skills (SKILL.md) | Procedures for fire pre-plan, storm prep, step-free home and record check load only when the need matches. |
| Human-in-the-loop (`interrupt_on`, `when` predicate) | A smoke simulation, a vision read of every panorama, a plan edit or a city rollup waits for "Run it / Skip it / Always run it here". |
| MongoDB checkpointer, `Command(resume=…)` | A paused turn resumes in any server process, even after a restart. |
| Rubric grader middleware | Catches the closing message stating numbers or claiming checks did not run; a real turn made that mistake before this existed. |
| MCP tools via langchain-mcp-adapters | The read-only MongoDB MCP server's tools, behind a guard, answer counts over the person's own past work. |
| LangSmith traces, datasets and experiments | Every turn is one trace tagged by persona; the composer's briefs are a dataset, and each prompt change is an experiment scored per check. |

**Demo path.** A fire captain's brief over two houses: the todo list appears, two lanes run in parallel, both pause
on the CFAST approval card, "Run it" resumes from the checkpoint, the rubric verdict and the LangSmith trace close it.
