---
title: "Sponsor integrations"
description: "What each LangChain, MongoDB Atlas, Tiger Data and Photon feature is used for."
---

Each sponsor feature below does a job in the product. The rule for this list: a feature is used only where it does one. The tables are generated from the tracks in `docs/story.md`.

## LangChain: deepagents, LangGraph and LangSmith

The investigator is one deep agent with subagents. See [the agent](/docs/concepts/agent/).

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

### Left out, and why

| Feature | Why not |
|---|---|
| `memory=` (AGENTS.md files) | The person's preferences already go into the prompt, so a static file would repeat it. |
| Background subagents | They need an Agent Protocol server. Slow tools already run in the background, and subagents run in parallel. |
| Sandboxes and a shell | The agent runs no shell. Every action is a typed tool, and a shell would only add risk. |
| Per-model harness profiles | There is one model, so there is nothing to tune per model. |

The track page: [LangChain](/tracks/langchain/).

## Tiger Cloud

Tiger Cloud is the building facts database: what was measured, when, and how it changed.

| Feature | Why it is a real use |
|---|---|
| Hypertables for facts, flood simulations and the op log | Facts are measured again as tools improve; the history is time series by nature. |
| Columnstore compression | 234 MB to 58 MB on the cloud service. |
| Continuous aggregates, real-time, plus a hierarchical one | The Insights page reads daily rollups that include a fact measured a second ago, and a neighbourhood rollup built on them. |
| `percentile_agg` hyperfunction | Medians that roll up across days and areas. |
| PostGIS | Distance filters in search by measurement. |
| pgvector + pgvectorscale StreamingDiskANN with label filters, BM25 | Similar-room search filtered by room type inside the index, blended with words. |
| pgai vectorizer | Room descriptions embed themselves inside the database when they change (Ollama, nomic-embed-text). |
| TimescaleDB job | Rebuilds the room-search graphs hourly, because a graph grown row by row had recall@10 of 0.0. |
| Retention policy | The analytics copy of the op log deletes itself after the event, as CoStar's terms require. |
| Read-only role for the agent's SQL | The agent can ask its own questions of the facts and cannot write. |
| Database forks | City-wide what-if on a zero-copy fork, ready in about 31 s on the free plan, deleted after. |

### Left out, and why

| Feature | Why not |
|---|---|
| Tiger MCP server | It runs with the service owner's credentials. The agent's own read-only SQL role, with a 5 second timeout, is stricter. |
| Tiered storage, read replicas, high availability | Paid or operations features with no use at this size. |
| Gapfill and time-weighted hyperfunctions | No view plots a gap-filled or time-weighted series yet. |
| Chunk skipping | The columnstore policies already compress older chunks. |

The track page: [Tiger Cloud](/tracks/tiger-data/).

## MongoDB Atlas

Atlas holds the people side: workspaces, their operation logs, live sync, memory and search over past work.

| Feature | Why it is a real use |
|---|---|
| Documents with a unique (workspace, seq) index | An optimistic lock: two writers cannot both append operation n. |
| Multi-document transactions | A person's operation and what it taught the agent land together. |
| Change streams | Live sync between server processes, browsers and the phone: a door width typed on the phone reaches the desktop in about a second. |
| `$jsonSchema` validation | The append-only log refuses a malformed entry. |
| TTL index | Read-only share links delete themselves. |
| Atlas Search (fuzzy, facets, highlights) | Search past investigations with counts by tool, status and city. |
| Vector Search with filters, automated embedding (voyage-4) | Recall similar past needs per persona, with no embedding key in the app. |
| Hybrid search with `$rankFusion` | "Could not roll a chair into the toilet" finds "No ADA clearance at the toilet". |
| Time series collection | Every phone reading (GPS, altitude, tilt, sound) as one measurement; the timeline groups by minute with `$dateTrunc`. |
| 2dsphere and `$geoNear` | Shortlisted buildings near a point. |
| LangGraph checkpointer and store | Paused agent turns and long-term memory next to the workspaces. |
| MongoDB MCP server (read-only, guarded) | The agent counts and groups over the person's own past work. |

### Left out, and why

| Feature | Why not |
|---|---|
| Atlas Triggers | They need App Services keys. Change streams already react to inserts inside the server. |
| Stream Processing, Online Archive, Data Federation | Paid tiers, and no stream or archive need at a weekend's volume. |
| Queryable Encryption | No field is more sensitive than the documents as a whole, and it would need a key service. |
| Atlas Charts | The app draws its own panels from the result objects. |

The track page: [MongoDB Atlas](/tracks/mongodb/).

## Photon

A messaging agent over Photon is being built on its own branch: ask Cranley by text message and get the same tool results back. It was not merged when these docs were built, so nothing here is a claim that it works. It uses the same tool registry and the same workspace document as every other way in. The track page: [Photon](/tracks/photon/).
