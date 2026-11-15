---
title: "Map layers"
description: "HTTP API: map layers."
sidebar: {"label": "Map layers"}
---

Map layer routes for the world explorer: the catalogue, each layer's GeoJSON (a whole city, or one tile of the layer's own grid), the weather now, and Vexcel's orthophoto and 3D city mesh for the map. Owned by the explorer workstream.

Generated from FastAPI's OpenAPI schema for `server/threshold/api/layers.py`.

## `GET /api/layers`

Every layer: what it is, who publishes it, how far to trust it, and the day our copy was fetched.

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `city` | query | string |  | `"hou"` |  |

Returns: `application/json`.

## `GET /api/layers/weather`

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `city` | query | string |  | `"hou"` |  |

Returns: `application/json`.

## `GET /api/layers/ortho/{z}/{x}/{y}.jpg`

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `z` | path | integer | yes |  |  |
| `x` | path | integer | yes |  |  |
| `y` | path | integer | yes |  |  |

Returns: `application/json`.

## `GET /api/layers/city3d`

The 3D city mesh tiles round a point, or round a scan (then the near tiles are the building scene's own).

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `lat` | query | number |  |  |  |
| `lon` | query | number |  |  |  |
| `sid` | query | string |  |  |  |

Returns: `application/json`.

## `GET /api/layers/{layer}/geojson`

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `layer` | path | string | yes |  |  |
| `city` | query | string |  | `"hou"` |  |

Returns: `application/json`.

## `GET /api/layers/{layer}/tile/{z}/{x}/{y}`

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `layer` | path | string | yes |  |  |
| `z` | path | integer | yes |  |  |
| `x` | path | integer | yes |  |  |
| `y` | path | integer | yes |  |  |

Returns: `application/json`.
