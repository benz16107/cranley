---
title: "Interior splats"
description: "HTTP API: interior splats."
sidebar: {"label": "Interior splats"}
---

Interior Gaussian splats trained from a scan's panoramas (threshold.splat). 404 until one has been trained.

Generated from FastAPI's OpenAPI schema for `server/threshold/api/interior_splat.py`.

## `GET /api/scan/{sid}/interior-splat.json`

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `sid` | path | string | yes |  |  |

Returns: `application/json`.

## `GET /api/scan/{sid}/interior-splat`

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `sid` | path | string | yes |  |  |
| `format` | query | string |  | `"spz"` |  |

Returns: `application/json`.
