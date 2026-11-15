---
title: "Site media"
description: "HTTP API: site media."
sidebar: {"label": "Site media"}
---

Media the site tools point at: oblique crops (evidence for dock doors) and printable sheets (risk_sheet). Owned by the site tools workstream; app.py includes this router by itself.

Generated from FastAPI's OpenAPI schema for `server/threshold/api/site_media.py`.

## `GET /api/site/oblique`

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `lat` | query | number | yes |  |  |
| `lon` | query | number | yes |  |  |
| `size_m` | query | number |  | `120` |  |
| `direction` | query | string |  | `"oblique-north"` |  |

Returns: `application/json`.

## `GET /api/site/sheet/{name}.html`

| Parameter | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `name` | path | string | yes |  |  |

Returns: `text/html`.
