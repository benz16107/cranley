---
title: "Agent and workspace"
description: "HTTP API: agent and workspace."
sidebar: {"label": "Agent and workspace"}
---

Agent routes (Contract 2): tools, agent turns as server-sent events of workspace ops, and workspaces.

Generated from FastAPI's OpenAPI schema for `server/threshold/api/agent.py`.

## `GET /api/tools`

Returns: `application/json`.

## `POST /api/tools/{tool_id}/run`

Run a tool. With ?workspace=&lt;id> the run goes into that workspace (inputs left out come from its preferences) and the reply is the run summary; without it, the bare ToolResult. With ?workspace and ?wait=&lt;seconds> a slow tool (a smoke simulation takes minutes) does not hold the request open: when the run has not finished in that time the reply is `&#123;"status": "running", "run": &lt;id>}` and the run carries on in the background. Its `run.start`, `run.progress` and `run.finish` ops, findings, overlays and panel reach the workspace exactly as they do for a fast tool, so a client follows it by reading the workspace until the run's id leaves the view's `busy` list (the run reads "done" a few seconds before its panel is written).

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `tool_id` | path | string | yes |  |  |
| `workspace` | query | string |  |  |  |
| `wait` | query | number |  |  | seconds to wait before answering |

Body (`application/json`): object

Returns: `application/json`.

## `POST /api/agent/turn`

Events: `workspace` &#123;id} first, then one `op` per log entry as it applies (tool steps arrive as `run.progress` while a tool runs), then `done` (with the turn's `budget`: limits, what it used, what stopped it) or `error`.

Body (`application/json`): `TurnIn`

| Field | Type | Required | Notes |
|---|---|---|---|
| `workspace` | string |  |  |
| `text` | string |  |  |
| `sids` | list of string |  |  |
| `places` | list of Place |  | Properties, addresses or points to look at without a scan |
| `profile` | string |  |  |
| `budget` | BudgetIn |  |  |

Returns: `application/json`.

## `POST /api/workspace`

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `profile` | query | string |  | `"default"` |  |

Returns: `application/json`.

## `GET /api/workspace/{id}`

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `id` | path | string | yes |  |  |
| `log` | query | boolean |  | `false` |  |

Returns: `application/json`.

## `POST /api/workspace/{id}/ops`

User ops, one or a list, in the same vocabulary as the agent's. `by` is forced to "user".

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `id` | path | string | yes |  |  |

Body (`application/json`): object or list of object

Returns: `application/json`.

## `POST /api/workspace/{id}/undo`

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `id` | path | string | yes |  |  |

Body (`application/json`): `Body_workspace_undo_api_workspace__id__undo_post`

| Field | Type | Required | Notes |
|---|---|---|---|
| `seq` | integer |  |  |

Returns: `application/json`.
