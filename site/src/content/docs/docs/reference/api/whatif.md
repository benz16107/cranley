---
title: "What-if renovations"
description: "HTTP API: what-if renovations."
sidebar: {"label": "What-if renovations"}
---

What-if renovations for the App. The renovated plan itself is GET /api/scan/&#123;w_sid}/plan like any other scan, and every tool takes the w_ sid.

Generated from FastAPI's OpenAPI schema for `server/threshold/api/whatif.py`.

## `GET /api/whatif/goals`

Returns: `application/json`.

## `POST /api/whatif`

Body (`application/json`): `Run`

| Field | Type | Required | Notes |
|---|---|---|---|
| `scan` | string | yes |  |
| `goal` | string |  |  |
| `edits` | list of any |  |  |
| `city` | boolean |  |  |

Returns: `application/json`.

## `GET /api/whatif/{sid}`

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `sid` | path | string | yes |  |  |

Returns: `application/json`.
