---
title: "Search"
description: "HTTP API: search."
sidebar: {"label": "Search"}
---

Search homes by what is measured inside them (the access workstream's measures table), for the map.

Generated from FastAPI's OpenAPI schema for `server/threshold/api/search.py`.

## `GET /api/search/measures/fields`

Returns: `application/json`.

## `GET /api/search/measures`

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `where` | query | list of string |  | `[]` |  |
| `city` | query | string |  |  |  |
| `kind` | query | string |  |  |  |
| `sort` | query | string |  |  |  |
| `limit` | query | integer |  | `50` |  |
| `near` | query | string |  |  |  |
| `within_km` | query | number |  |  |  |
| `room` | query | list of string |  | `[]` |  |

Returns: `application/json`.
