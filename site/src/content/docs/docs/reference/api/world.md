---
title: "3D city and terrain"
description: "HTTP API: 3d city and terrain."
sidebar: {"label": "3D city and terrain"}
---

World routes: a scan's surroundings (Vexcel 3D city mesh, surface model, orthophoto), Matterport's own scanned mesh with colour baked from the panoramas, and the drone splat's placement. Owned by the views workstream.

Generated from FastAPI's OpenAPI schema for `server/threshold/api/world.py`.

## `GET /api/world/3d/{name}`

Vexcel's 3D Tiles, passed through with our key: `tileset.json`, or `tile.glb` (Draco geometry, KTX2 texture).

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `name` | path | string | yes |  |  |

Returns: `application/json`.

## `GET /api/world/{sid}/site`

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `sid` | path | string | yes |  |  |

Returns: `application/json`.

## `GET /api/world/{sid}/tiles`

The 3D city mesh tiles round the scan, nearest first: fine near the building, coarser further out.

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `sid` | path | string | yes |  |  |

Returns: `application/json`.

## `GET /api/world/{sid}/terrain`

The surface model round the scan as a height grid, and where the two orthophotos that texture it sit.

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `sid` | path | string | yes |  |  |
| `size_m` | query | number |  | `360` |  |
| `n` | query | integer |  | `256` |  |

Returns: `application/json`.

## `GET /api/world/{sid}/mesh`

The scanned mesh as one binary block (see world/mesh.py `pack`).

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `sid` | path | string | yes |  |  |

Returns: `application/json`.

## `GET /api/world/{sid}/mesh/status`

Whether the colour atlas is baked; asking starts the bake (minutes the first time for a scan).

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `sid` | path | string | yes |  |  |
| `start` | query | boolean |  | `true` |  |

Returns: `application/json`.

## `GET /api/world/{sid}/mesh/atlas.jpg`

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `sid` | path | string | yes |  |  |

Returns: `application/json`.

## `GET /api/world/{sid}/interior`

&#123;splat: bool}: whether this scan has an interior splat that this server can serve. Always a 200, so a page can ask about every scan without a 404 in its console. The splat and its placing are the splat workstream's routes (`api/interior_splat.py`).

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `sid` | path | string | yes |  |  |

Returns: `application/json`.

## `GET /api/world/{sid}/splat-fit`

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `sid` | path | string | yes |  |  |

Returns: `application/json`.
