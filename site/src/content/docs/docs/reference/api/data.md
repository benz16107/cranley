---
title: "Scans and buildings"
description: "HTTP API: scans and buildings."
sidebar: {"label": "Scans and buildings"}
---

Scan data routes (Contract 2 in docs/ARCHITECTURE.md): the scan index and buildings, the ScanPlan, panoramas, floor plans, the splat, drone photos and the CoStar record. Every upstream response is cached on disk.

Generated from FastAPI's OpenAPI schema for `server/threshold/api/data.py`.

## `GET /api/scans`

Index rows. `q` needs every word in the name, address, ids or postal code; `address` is a substring.

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `q` | query | string |  |  |  |
| `address` | query | string |  |  |  |
| `city` | query | string |  |  |  |
| `segment` | query | string |  |  |  |
| `kind` | query | string |  |  | house, apartment_unit, amenity, office, warehouse, retail or other |
| `splat` | query | boolean |  |  |  |
| `defurnished` | query | boolean |  |  |  |
| `rooms_min` | query | integer |  |  |  |
| `rooms_max` | query | integer |  |  |  |
| `floors_min` | query | integer |  |  |  |
| `limit` | query | integer |  | `50` |  |
| `offset` | query | integer |  | `0` |  |

Returns: `application/json`.

## `GET /api/buildings`

GeoJSON, one point per building (scans that share a CoStar property id, else an address, else a spot). properties: id, property_id, address, city, segment, count (scans), splat, defurnished, kinds, scans (compact rows [sid, name, kind, rooms, panos]). Gzipped by the app, about 400 kB for all of them.

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `segment` | query | string |  |  |  |
| `city` | query | string |  |  |  |
| `splat` | query | boolean |  |  |  |
| `bbox` | query | string |  |  | west,south,east,north |

Returns: `application/json`.

## `GET /api/property/{property_id}/scans`

Every scan of one CoStar property.

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `property_id` | path | integer | yes |  |  |

Returns: `application/json`.

## `GET /api/scan/{sid}/plan`

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `sid` | path | string | yes |  |  |

Returns: `application/json`.

## `GET /api/scan/{sid}/record`

The CoStar property or listing record for a scan, with its listings, tenancies, sales and `claims` (the checkable facts and where in the record each came from). Trimmed unless full=1. 404 until the kit is configured.

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `sid` | path | string | yes |  |  |
| `full` | query | boolean |  | `false` |  |

Returns: `application/json`.

## `GET /api/scan/{sid}/pano/{pano}/equirect.jpg`

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `sid` | path | string | yes |  |  |
| `pano` | path | string | yes |  |  |
| `w` | query | integer |  | `2048` |  |
| `view` | query | string |  | `"furnished"` |  |

Returns: `application/json`.

## `GET /api/scan/{sid}/pano/{pano}/{face}.jpg`

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `sid` | path | string | yes |  |  |
| `pano` | path | string | yes |  |  |
| `face` | path | integer | yes |  |  |
| `res` | query | string |  | `"2k"` |  |
| `view` | query | string |  | `"furnished"` |  |

Returns: `application/json`.

## `GET /api/scan/{sid}/floorplan/{floor}.{fmt}`

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `sid` | path | string | yes |  |  |
| `floor` | path | string | yes |  |  |
| `fmt` | path | string | yes |  |  |
| `flags` | query | string |  | `"photogramy"` |  |

Returns: `application/json`.

## `GET /api/scan/{sid}/splat`

splat.ply, with Range. The first request starts a download into the cache (70 to 660 MB); ranges are served as the bytes arrive, so asking for the first 60 MB answers once 60 MB are in.

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `sid` | path | string | yes |  |  |

Returns: `application/json`.

## `GET /api/scan/{sid}/splat/envmap/{face}.jpg`

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `sid` | path | string | yes |  |  |
| `face` | path | string | yes |  |  |

Returns: `application/json`.

## `GET /api/scan/{sid}/drone`

Drone photos with GPS, height above take-off and gimbal angles, read from each photo's XMP block. The first call for a scan reads n small ranges (about n/4 seconds); later calls come from the cache.

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `sid` | path | string | yes |  |  |
| `n` | query | integer |  | `60` | photos to describe, spread through the flight; 0 is all |

Returns: `application/json`.

## `GET /api/scan/{sid}/drone/{name}`

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `sid` | path | string | yes |  |  |
| `name` | path | string | yes |  |  |
| `w` | query | integer |  | `1600` |  |

Returns: `application/json`.
