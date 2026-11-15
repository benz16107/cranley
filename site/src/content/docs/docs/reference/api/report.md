---
title: "Reports"
description: "HTTP API: reports."
sidebar: {"label": "Reports"}
---

Site reports. A field visit from the iPhone app (scan sent, place and business named, report kind chosen) becomes a workspace whose tools run in the background; any workspace, visit or not, prints as a PDF a business can keep.

Generated from FastAPI's OpenAPI schema for `server/threshold/api/report.py`.

## `POST /api/report/visit`

A new workspace for this visit with the scan in scope, the kind's tools running in the background, and a pairing token so the phone's measurements and photos join the same visit.

Body (`application/json`): `Visit`

| Field | Type | Required | Notes |
|---|---|---|---|
| `sid` | string | yes |  |
| `kind` | string |  |  |
| `business` | string |  |  |
| `place` | string |  |  |
| `address` | string |  |  |
| `contact` | string |  | Who the report is for |

Returns: `application/json`.

## `GET /api/report/kinds`

Returns: `application/json`.

## `GET /api/report/{workspace}/status`

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `workspace` | path | string | yes |  |  |

Returns: `application/json`.

## `GET /api/report/{workspace}.html`

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `workspace` | path | string | yes |  |  |
| `kind` | query | string |  |  |  |
| `sid` | query | string |  |  |  |

Returns: `text/html`.

## `GET /api/report/{workspace}.pdf`

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `workspace` | path | string | yes |  |  |
| `kind` | query | string |  |  |  |
| `sid` | query | string |  |  |  |

Returns: `application/json`.
