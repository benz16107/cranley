---
title: "Person"
description: "HTTP API: person."
sidebar: {"label": "Person"}
---

The person's side of the agent: what is known about them across investigations, where a workspace used it, and feedback on a check.

Generated from FastAPI's OpenAPI schema for `server/threshold/api/person.py`.

## `GET /api/person/{id}`

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `id` | path | string | yes |  |  |
| `workspace` | query | string |  |  |  |
| `sessions` | query | boolean |  | `true` |  |

Returns: `application/json`.

## `GET /api/workspace/{id}/because`

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `id` | path | string | yes |  |  |

Returns: `application/json`.

## `POST /api/workspace/{id}/feedback`

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `id` | path | string | yes |  |  |

Body (`application/json`): `FeedbackIn`

| Field | Type | Required | Notes |
|---|---|---|---|
| `finding` | string | yes |  |
| `verdict` | string | yes |  |

Returns: `application/json`.
