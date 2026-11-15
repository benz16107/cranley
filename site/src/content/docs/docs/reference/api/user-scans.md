---
title: "Your own scans"
description: "HTTP API: your own scans."
sidebar: {"label": "Your own scans"}
---

Scans of people's own homes from the iPhone app. The plan itself is served by GET /api/scan/&#123;sid}/plan like any other scan, and every tool takes the sid.

Generated from FastAPI's OpenAPI schema for `server/threshold/api/user_scans.py`.

## `POST /api/scans/user`

Returns: `application/json`.

## `GET /api/scans/user`

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `workspace` | query | string |  |  |  |

Returns: `application/json`.
