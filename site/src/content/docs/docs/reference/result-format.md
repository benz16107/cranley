---
title: "Result format"
description: "The typed result every tool returns, its overlays, and the tool manifest."
---

Every tool returns the same typed result. A renderer ignores what it does not know, and a typo in a tool fails at the tool, because every model forbids unknown fields. Generated from `server/threshold/tools/types.py`.

## The result

### ToolResult



| Field | Type | Notes |
|---|---|---|
| `tool` | string |  |
| `scope` | ScanScope or AddressScope or ScansScope or PropertyScope or GeoScope |  |
| `verdict` | Verdict |  |
| `metrics` | list of Metric |  |
| `checks` | list of Check |  |
| `findings` | list of Finding |  |
| `overlays` | list of LensOverlay or RuleOverlay or PinsOverlay or RouteOverlay or WaterOverlay or BoxOverlay |  |
| `assumptions` | list of Assumption |  |
| `actions` | list of Action |  |

### Verdict



| Field | Type | Notes |
|---|---|---|
| `status` | `pass` or `warn` or `fail` or `unknown` |  |
| `text` | string |  |

### Metric



| Field | Type | Notes |
|---|---|---|
| `id` | string |  |
| `label` | string |  |
| `value` | number or null |  |
| `unit` | string |  |
| `source` | Source |  |

### Check



| Field | Type | Notes |
|---|---|---|
| `id` | string |  |
| `rule` | string |  |
| `measured` | number or null |  |
| `threshold` | number or null |  |
| `unit` | string |  |
| `status` | `pass` or `warn` or `fail` or `unknown` |  |
| `standard` | string or null |  |
| `findings` | list of string |  |
| `kind` | `limit` or `claim` | claim: `threshold` is what a record or a listing says, not a limit to meet |

### Finding



| Field | Type | Notes |
|---|---|---|
| `id` | string |  |
| `title` | string |  |
| `status` | `pass` or `warn` or `fail` or `unknown` |  |
| `detail` | string |  |
| `anchor` | PointAnchor or RoomAnchor or OpeningAnchor or WallAnchor or PanoAnchor or GeoAnchor or null |  |
| `source` | Source |  |
| `media` | list of Media |  |

### Source



| Field | Type | Notes |
|---|---|---|
| `layer` | `matterport` or `vexcel` or `costar` or `drone` or `model` or `phone` |  |
| `method` | `geometry` or `vision` or `lookup` or `simulation` or `sensor` or `manual` |  |
| `confidence` | `high` or `medium` or `low` |  |
| `note` | string or null |  |

### Media



| Field | Type | Notes |
|---|---|---|
| `kind` | `pano` or `ortho` or `drone` or `phone` |  |
| `ref` | string |  |
| `box` | array or null |  |

### Assumption



| Field | Type | Notes |
|---|---|---|
| `id` | string | For an editable assumption, the preference key (x-pref) that an edit sets |
| `label` | string |  |
| `value` | number or string or boolean or null |  |
| `unit` | string or null |  |
| `editable` | boolean |  |

### Action



| Field | Type | Notes |
|---|---|---|
| `id` | string |  |
| `label` | string |  |
| `tool` | string |  |
| `inputs` | object |  |

## Overlays

One overlay draws in every view that can show it: the 3D building, the plan, a panorama or the map.

### LensOverlay



| Field | Type | Notes |
|---|---|---|
| `kind` | string |  |
| `values` | object | room id -> value |
| `ramp` | `sequential` or `status` |  |
| `legend` | Legend |  |

### RuleOverlay



| Field | Type | Notes |
|---|---|---|
| `kind` | string |  |
| `select` | SelectRooms or SelectRoomLabels or SelectOpenings or SelectWalls |  |
| `style` | `solid` or `dim` or `hide` or `highlight` or `pass` or `warn` or `fail` |  |

### PinsOverlay



| Field | Type | Notes |
|---|---|---|
| `kind` | string |  |
| `pins` | list of Pin |  |

### RouteOverlay



| Field | Type | Notes |
|---|---|---|
| `kind` | string |  |
| `floor` | string |  |
| `points` | list of array |  |
| `chokes` | list of Choke |  |
| `label` | string |  |

### WaterOverlay



| Field | Type | Notes |
|---|---|---|
| `kind` | string |  |
| `level_m` | number |  |
| `datum` | string |  |

### BoxOverlay



| Field | Type | Notes |
|---|---|---|
| `kind` | string |  |
| `center` | list of |  |
| `size` | list of |  |
| `yaw_deg` | number |  |
| `label` | string |  |
| `status` | `pass` or `warn` or `fail` or `unknown` |  |
| `model` | string or null | Model class the scene draws stretched to exactly this box, such as vehicle/pickup or furniture/sofa; none draws the box alone |

## The manifest

One per tool. It feeds the agent, the web tool dock, the MCP server and the CLI.

### Manifest



| Field | Type | Notes |
|---|---|---|
| `id` | string |  |
| `title` | string |  |
| `summary` | string | For the person: tooltip and 'why this tool' |
| `model_description` | string | For the model: when to use it and what it returns |
| `icon` | string or null |  |
| `personas` | list of string |  |
| `requires` | list of Requirement |  |
| `inputs` | object | JSON Schema with x-ask, x-pref, x-source, x-unit |
| `blocks` | list of string |  |
| `overlays` | list of string |  |
| `annotations` | Annotations |  |
| `examples` | list of string |  |
| `status` | `ready` or `planned` |  |
| `table` | list of TableColumn | Columns of the run's own RankedTable: each row is a key k with metrics `k/&lt;column.metric>`; the first cell's label names the row |

### Requirement



| Field | Type | Notes |
|---|---|---|
| `layer` | string | e.g. matterport.rooms, matterport.openings, vexcel.ortho, costar.property |
| `need` | `required` or `optional` |  |
| `fallback` | string or null |  |

### Annotations



| Field | Type | Notes |
|---|---|---|
| `read_only` | boolean |  |
| `cost` | `fast` or `slow` |  |

### Place

Where a tool runs when it does not need a scan: a scan id, a CoStar property id (all its scans), an address, or a point. Give one; `ctx.site(place)` resolves it to coordinates, address, property and scans.

| Field | Type | Notes |
|---|---|---|
| `scan` | string or null |  |
| `property_id` | integer or null |  |
| `address` | string or null |  |
| `geo` | array or null | [lon, lat] |
