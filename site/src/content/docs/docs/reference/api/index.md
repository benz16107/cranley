---
title: "HTTP API"
description: "The 97 operations of the FastAPI server, by router."
sidebar: {"label": "Overview", "order": 0}
---

The server (`server/threshold/api/app.py`) includes one router per file. These pages are generated from its OpenAPI schema: 97 operations in 19 groups. With the server running, the same schema is at `/openapi.json` and an interactive copy at `/docs`.

The API has no login and serves the data in your data folder, so keep it on your own machine or network. Signed scan links never reach the browser: the server fetches, caches and serves.

| Group | File | Operations |
|---|---|---|
| [Aerial](/docs/reference/api/aerial/) | `api/aerial.py` | 4 |
| [Agent and workspace](/docs/reference/api/agent/) | `api/agent.py` | 7 |
| [Agent, live view](/docs/reference/api/agent-live/) | `api/agent_live.py` | 2 |
| [Phone captures](/docs/reference/api/capture/) | `api/capture.py` | 13 |
| [Scans and buildings](/docs/reference/api/data/) | `api/data.py` | 12 |
| [Facts database](/docs/reference/api/facts/) | `api/facts.py` | 11 |
| [Past work](/docs/reference/api/history/) | `api/history.py` | 3 |
| [Interior splats](/docs/reference/api/interior-splat/) | `api/interior_splat.py` | 2 |
| [Map layers](/docs/reference/api/layers/) | `api/layers.py` | 6 |
| [Live sync](/docs/reference/api/live/) | `api/live.py` | 6 |
| [photon](/docs/reference/api/photon/) | `api/photon.py` | 4 |
| [Reports](/docs/reference/api/report/) | `api/report.py` | 5 |
| [Search](/docs/reference/api/search/) | `api/search.py` | 2 |
| [Phone sensors](/docs/reference/api/sensors/) | `api/sensors.py` | 1 |
| [Flood and smoke shows](/docs/reference/api/show/) | `api/show.py` | 3 |
| [Site media](/docs/reference/api/site-media/) | `api/site_media.py` | 2 |
| [Your own scans](/docs/reference/api/user-scans/) | `api/user_scans.py` | 2 |
| [What-if renovations](/docs/reference/api/whatif/) | `api/whatif.py` | 3 |
| [3D city and terrain](/docs/reference/api/world/) | `api/world.py` | 9 |
