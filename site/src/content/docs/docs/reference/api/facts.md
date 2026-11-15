---
title: "Facts database"
description: "HTTP API: facts database."
sidebar: {"label": "Facts database"}
---

The building facts database (Tiger Data) over HTTP: city rollups, fact history, similar rooms, flood runs, usage and read-only SQL. Every route answers 503 when no database is configured.

Generated from FastAPI's OpenAPI schema for `server/threshold/api/facts.py`.

## `GET /api/facts/status`

Returns: `application/json`.

## `GET /api/facts/census/presets`

Returns: `application/json`.

## `GET /api/facts/census`

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `preset` | query | string |  |  |  |
| `field` | query | string |  |  |  |
| `by` | query | string |  |  |  |
| `stat` | query | string |  |  |  |
| `city` | query | string |  |  |  |
| `kind` | query | string |  |  |  |
| `min_scans` | query | integer |  | `3` |  |
| `limit` | query | integer |  | `50` |  |

Returns: `application/json`.

## `GET /api/facts/fields`

Returns: `application/json`.

## `GET /api/facts/history/{sid}`

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `sid` | path | string | yes |  |  |
| `field` | query | string |  |  |  |
| `limit` | query | integer |  | `200` |  |

Returns: `application/json`.

## `GET /api/facts/rooms/similar`

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `q` | query | string |  |  |  |
| `sid` | query | string |  |  |  |
| `room` | query | string |  |  |  |
| `label` | query | string |  |  |  |
| `city` | query | string |  |  |  |
| `kind` | query | string |  |  |  |
| `min_area` | query | number |  |  |  |
| `min_turn` | query | number |  |  |  |
| `words` | query | number |  | `0.0` |  |
| `limit` | query | integer |  | `10` |  |

Returns: `application/json`.

## `GET /api/facts/flood/wet`

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `levels` | query | string |  | `"0.5,1,1.5"` |  |
| `city` | query | string |  |  |  |

Returns: `application/json`.

## `GET /api/facts/flood/runs`

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `sid` | query | string |  |  |  |
| `limit` | query | integer |  | `50` |  |

Returns: `application/json`.

## `GET /api/facts/flood/run/{run}`

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `run` | path | string | yes |  |  |

Returns: `application/json`.

## `GET /api/facts/ops`

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `hours` | query | integer |  | `24` |  |

Returns: `application/json`.

## `POST /api/facts/sql`

Body (`application/json`): `Sql`

| Field | Type | Required | Notes |
|---|---|---|---|
| `sql` | string | yes |  |

Returns: `application/json`.
