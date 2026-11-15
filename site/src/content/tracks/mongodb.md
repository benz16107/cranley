---
title: "MLH: Best Use of MongoDB Atlas"
---

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

**Demo path.** Pair the phone by QR, type a door width on the phone, watch it land on the desktop; Copy link opens a
read-only shared workspace; search past work for a phrase that is not in it word for word.
