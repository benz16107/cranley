---
title: "Phone sensors"
description: "HTTP API: phone sensors."
sidebar: {"label": "Phone sensors"}
---

Phone readings of a workspace as a timeline, from the MongoDB time series collection (`store/mongo.py`): `GET /api/workspace/&#123;id}/sensors?scan=&every=minute`. 404 when the workspaces are not in MongoDB.

Generated from FastAPI's OpenAPI schema for `server/threshold/api/sensors.py`.

## `GET /api/workspace/{workspace}/sensors`

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `workspace` | path | string | yes |  |  |
| `scan` | query | string |  |  |  |
| `every` | query | string |  | `"minute"` |  |

Returns: `application/json`.
