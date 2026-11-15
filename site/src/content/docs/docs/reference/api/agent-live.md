---
title: "Agent, live view"
description: "HTTP API: agent, live view."
sidebar: {"label": "Agent, live view"}
---

The agents at work, live: `GET /api/agent/&#123;workspace}/live` streams the main agent and one lane per subagent (what it was asked, the tool it is running, waiting for an approval, done) as server-sent `lanes` events, a full snapshot each time something changes. The agent panel shows it beside the plan.

Generated from FastAPI's OpenAPI schema for `server/threshold/api/agent_live.py`.

## `GET /api/agent/{workspace}/live`

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `workspace` | path | string | yes |  |  |

Returns: `application/json`.

## `GET /api/agent/{workspace}/lanes`

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `workspace` | path | string | yes |  |  |

Returns: `application/json`.
