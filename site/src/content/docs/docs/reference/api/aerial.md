---
title: "Aerial"
description: "HTTP API: aerial."
sidebar: {"label": "Aerial"}
---

Aerial routes (Contract 2): ortho, property facts, elevation, detection. Owned by perception.

Generated from FastAPI's OpenAPI schema for `server/threshold/api/aerial.py`.

## `GET /api/aerial/ortho`

JPEG, north up. Headers carry the pixel transform: bounds (west,south,east,north) in Web Mercator, linear.

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `lat` | query | number | yes |  |  |
| `lon` | query | number | yes |  |  |
| `size_m` | query | number |  | `60` |  |
| `px` | query | integer |  | `1024` |  |

Returns: `application/json`.

## `GET /api/aerial/property`

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `lat` | query | number | yes |  |  |
| `lon` | query | number | yes |  |  |

Returns: `application/json`.

## `GET /api/aerial/elevation`

Ground and surface at a point; with to_lat and to_lon, a profile along the line.

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `lat` | query | number | yes |  |  |
| `lon` | query | number | yes |  |  |
| `to_lat` | query | number |  |  |  |
| `to_lon` | query | number |  |  |  |
| `n` | query | integer |  | `50` |  |

Returns: `application/json`.

## `POST /api/aerial/detect`

Body (`application/json`): `DetectIn`

| Field | Type | Required | Notes |
|---|---|---|---|
| `lat` | number | yes |  |
| `lon` | number | yes |  |
| `size_m` | number |  |  |
| `labels` | list of string |  |  |
| `obliques` | boolean |  |  |
| `threshold` | number |  |  |
| `method` | string |  |  |

Returns: `application/json`.
