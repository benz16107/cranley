---
title: "Live sync"
description: "HTTP API: live sync."
sidebar: {"label": "Live sync"}
---

Live workspaces and read-only share links.

Generated from FastAPI's OpenAPI schema for `server/threshold/api/live.py`.

## `GET /api/workspace/{id}/live`

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `id` | path | string | yes |  |  |
| `after` | query | integer |  | `0` |  |

Returns: `application/json`.

## `POST /api/workspace/{id}/share`

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `id` | path | string | yes |  |  |

Body (`application/json`): `Body_share_api_workspace__id__share_post`

| Field | Type | Required | Notes |
|---|---|---|---|
| `days` | number |  |  |

Returns: `application/json`.

## `GET /api/shared/{token}`

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `token` | path | string | yes |  |  |

Returns: `application/json`.

## `GET /api/shared/{token}/live`

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `token` | path | string | yes |  |  |
| `after` | query | integer |  | `0` |  |

Returns: `application/json`.

## `GET /api/shared/{token}/shortlist`

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `token` | path | string | yes |  |  |
| `near` | query | string |  |  |  |
| `km` | query | number |  |  |  |

Returns: `application/json`.

## `DELETE /api/workspace/{id}/share/{token}`

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `id` | path | string | yes |  |  |
| `token` | path | string | yes |  |  |

Returns: `application/json`.
