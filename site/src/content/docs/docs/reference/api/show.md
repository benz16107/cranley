---
title: "Flood and smoke shows"
description: "HTTP API: flood and smoke shows."
sidebar: {"label": "Flood and smoke shows"}
---

Show routes: a real storm and a modelled fire as timelines the scene plays on the building. Owned by the show workstream. The numbers are the flood and smoke tools' own; see world/storm.py and world/smoke.py.

Generated from FastAPI's OpenAPI schema for `server/threshold/api/show.py`.

## `GET /api/show/{sid}/storm`

Hurricane Harvey at this house: a water level for every half hour, when each room takes water, and sources.

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `sid` | path | string | yes |  |  |

Returns: `application/json`.

## `GET /api/show/{sid}/storm/belongings`

What the water reaches, item by item, and the loss range at every step. Minutes the first time (vision).

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `sid` | path | string | yes |  |  |

Returns: `application/json`.

## `GET /api/show/{sid}/smoke`

The Smoke clock's CFAST run as a per-room timeline. Reads a finished run; never starts one.

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `sid` | path | string | yes |  |  |
| `doors` | query | string |  | `"open"` |  |
| `fire_room` | query | string |  |  |  |

Returns: `application/json`.
