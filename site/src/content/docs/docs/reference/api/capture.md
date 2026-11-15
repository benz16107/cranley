---
title: "Phone captures"
description: "HTTP API: phone captures."
sidebar: {"label": "Phone captures"}
---

Phone captures and pairing. Used by the mobile web app (/m) and the native app alike.

Generated from FastAPI's OpenAPI schema for `server/threshold/api/capture.py`.

## `POST /api/workspace/{id}/pair`

A link for a phone, and the same link as a QR code (SVG). `origin` is the address the desktop page is open at; THRESHOLD_PHONE_ORIGIN, when set, wins: the HTTPS address a phone can reach (camera and sensors need HTTPS).

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `id` | path | string | yes |  |  |

Body (`application/json`): `Body_pair_phone_api_workspace__id__pair_post`

| Field | Type | Required | Notes |
|---|---|---|---|
| `hours` | number |  |  |
| `origin` | string |  |  |

Returns: `application/json`.

## `GET /api/workspace/{id}/captures`

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `id` | path | string | yes |  |  |

Returns: `application/json`.

## `POST /api/phone/start`

Returns: `application/json`.

## `GET /api/phone/{token}`

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `token` | path | string | yes |  |  |

Returns: `application/json`.

## `POST /api/phone/{token}/capture`

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `token` | path | string | yes |  |  |
| `meta` | query | string | yes |  |  |

Returns: `application/json`.

## `POST /api/phone/{token}/locate`

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `token` | path | string | yes |  |  |

Body (`application/json`): `Body_phone_locate_api_phone__token__locate_post`

| Field | Type | Required | Notes |
|---|---|---|---|
| `lat` | number | yes |  |
| `lon` | number | yes |  |
| `accuracy_m` | number |  |  |

Returns: `application/json`.

## `POST /api/phone/{token}/place`

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `token` | path | string | yes |  |  |

Body (`application/json`): `Body_phone_place_api_phone__token__place_post`

| Field | Type | Required | Notes |
|---|---|---|---|
| `sid` | string | yes |  |

Returns: `application/json`.

## `POST /api/phone/{token}/brief`

Start (or continue) an agent turn in the background. The phone reads the view until `busy` is false.

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `token` | path | string | yes |  |  |

Body (`application/json`): `Body_phone_brief_api_phone__token__brief_post`

| Field | Type | Required | Notes |
|---|---|---|---|
| `text` | string |  |  |
| `sid` | string |  |  |

Returns: `application/json`.

## `POST /api/phone/{token}/answer`

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `token` | path | string | yes |  |  |

Body (`application/json`): `Body_phone_answer_api_phone__token__answer_post`

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | string | yes |  |
| `value` | any | yes |  |

Returns: `application/json`.

## `POST /api/phone/{token}/run/{tool}`

Run a tool from the phone. Slow ones (the aerial tools read photos) carry on in the background.

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `token` | path | string | yes |  |  |
| `tool` | path | string | yes |  |  |

Body (`application/json`): object

Returns: `application/json`.

## `GET /api/capture/{id}`

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `id` | path | string | yes |  |  |

Returns: `application/json`.

## `GET /api/capture/{id}/file`

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `id` | path | string | yes |  |  |

Returns: `application/json`.

## `GET /api/capture/{id}/frame/{n}.jpg`

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `id` | path | string | yes |  |  |
| `n` | path | integer | yes |  |  |

Returns: `application/json`.
