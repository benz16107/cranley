---
title: "Photon"
description: "HTTP API: photon."
sidebar: {"label": "Photon"}
---

Photon events, as forwarded by the webhook service (threshold/photon/webhook.py), which alone faces the internet.

Generated from FastAPI's OpenAPI schema for `server/threshold/api/photon.py`.

## `POST /api/photon/event`

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `x-cranley-internal` | header | string |  |  |  |

Body (`application/json`): object

## `POST /api/photon/tool/{name}`

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `name` | path | string | yes |  |  |
| `x-cranley-internal` | header | string |  |  |  |

Body (`application/json`): object

Returns: `application/json`.

## `POST /api/photon/alerts/check`

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `x-cranley-internal` | header | string |  |  |  |

Returns: `application/json`.

## `GET /api/photon/status`

Returns: `application/json`.
