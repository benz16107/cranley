---
title: "MLH: Best Use of Tiger Data"
---

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

**Scripted flow:** `web/src/skins/app/demo/flows/tiger.json`, "A renovation what-if on a database fork".

**Demo path.** Search by measurement (one query, a ranked table), then renovate: widen a door, re-run city-wide on a
fork, compare Now and After, the fork deleted.
