---
title: "Past work"
description: "HTTP API: past work."
sidebar: {"label": "Past work"}
---

Past work, from MongoDB Atlas (THRESHOLD_STORE=mongo; 501 otherwise).

Generated from FastAPI's OpenAPI schema for `server/threshold/api/history.py`.

## `GET /api/history/search`

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `q` | query | string |  |  |  |
| `profile` | query | string |  |  |  |
| `workspace` | query | string |  |  |  |
| `tool` | query | string |  |  |  |
| `status` | query | string |  |  |  |
| `city` | query | string |  |  |  |
| `kind` | query | string |  |  |  |
| `feedback` | query | string |  |  |  |
| `sid` | query | string |  |  |  |
| `limit` | query | integer |  | `10` |  |

Returns: `application/json`.

## `GET /api/history/similar`

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `text` | query | string | yes |  |  |
| `persona` | query | string |  |  |  |
| `k` | query | integer |  | `3` |  |

Returns: `application/json`.

## `GET /api/history/shortlist`

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `profile` | query | string |  |  |  |
| `workspace` | query | string |  |  |  |
| `near` | query | string |  |  |  |
| `km` | query | number |  |  |  |

Returns: `application/json`.
