---
title: "Ask the facts database"
description: "Answers questions across every scanned building that no fixed tool covers, with the SQL shown."
sidebar: {"label": "Ask the facts database"}
---

Answers questions across every scanned building that no fixed tool covers, with the SQL shown.

## What it answers

- Which property type has the worst listed-versus-measured area gap?
- How many Houston houses take water in more than half their rooms at 0.5 m?

For the agent, the tool is described as: Run one read-only SQL query over the building facts database (Postgres with TimescaleDB, PostGIS and pgvector) to answer an analytic question across many buildings: comparisons by property type, zip or city, distributions, record-versus-measured disagreements, flood exposure, usage. Write the SQL yourself from the schema in the `sql` input's description. Returns the rows (each as a check, first numeric column as the value) and the SQL. Prefer measure_search, city_census or similar_rooms when they fit.

## Who it is for

[Commercial property underwriter](/docs/reference/personas/#commercial-property-underwriter), [CoStar research lead](/docs/reference/personas/#costar-research-lead), [CoStar researcher](/docs/reference/personas/#costar-researcher), [Insurance underwriter](/docs/reference/personas/#insurance-underwriter).

## Inputs

| Input | Type | Required | Default | Notes |
|---|---|---|---|---|
| `question` | string | yes |  | The question in plain words, shown with the answer. |
| `sql` | string | yes |  | One PostgreSQL SELECT (or WITH ... SELECT) over schema threshold. Aggregate in SQL; at most 200 rows come back. Schema threshold (Postgres with TimescaleDB, PostGIS, pgvector). Units: metres, m2, ft2 where named. scan(sid, building_id, name, kind[house\|apartment_unit\|office\|amenity\|warehouse\|retail\|other], segment, city, zip, address, geom geography(Point), walls bool, polygons bool, labels bool, panos, floors, created) building(id, property_id, address, city, zip, property_type, listed_area_ft2, geom geography(Point), footprint geography(Polygon)) measures(sid, floor_area, rooms, bedrooms, bathrooms, kitchens, floors, entrances, entrance_width, doors, narrowest_door, median_door, bath_route_door, bath_route_m, bed_route_door_min, kitchen_route_door, bath_turn, kitchen_turn, bed_turn, largest_turn, longest_wall, bed_wall, living_wall, ceiling_median, windows, glazed_area, glazing_ratio, level_changes, max_sill_step, step_free_bath 0/1, wheelchair_bath 0/1, wheelchair_rooms_share %, error) room(sid, room, floor, label, area, width, depth, height, doors, widest_door, narrowest_door, turn_diameter, windows, glazed_area) door(sid, opening, kind, width, implausible, step, floor) fact(at, sid, building_id, room, field, value_num, value_text, unit, layer, method, confidence, tool, run, evidence jsonb, record_value, record_path, city, zip, kind, property_type) -- hypertable; history of every computed field fact_daily(day, sid, room, field, value_num, value_text, unit, method, confidence, record_value, building_id, city, zip, kind, property_type, at, observations) -- continuous aggregate: latest value per scan, room, field and day fields include every measures column, area_gap (measured/listed - 1), vs_record.&lt;claim> (value_text is the verdict: confirmed\|contradicted\|cannot verify; record_value is the record's), room.area, room.turn_diameter, &lt;tool>.&lt;metric> flood_run(run, sid, scenario, datum, step_m, step_s, started); flood_depth(ts, run, sid, room, label, level_m, depth_m, wet_area_m2) flood_by_level(bucket, run, sid, level_m, rooms_wet, rooms, wet_area_m2, max_depth_m) -- continuous aggregate ops_hourly(hour, op, by_whom, tool, ops, workspaces) -- agent operations per hour, counts only room_text(sid, room, pano, description, features text[], embedding vector(384), labels smallint[]); room_type(id, label). |

An input that nothing fills (the selected building, a saved preference, a persona's preset) becomes a question to the person. The agent asks only for those.

## Data used

| Layer | Id | Needed | If it is missing |
|---|---|---|---|
| Facts database | `threshold.facts` | required | The verdict is `unknown`, with the reason. |

## What it returns

A [tool result](/docs/reference/result-format/): a verdict (pass, warn, fail or unknown), metrics, checks and findings, each with its source.

- Panel blocks: `VerdictHeader`, `CheckList`, `StepLog`.
- Speed: fast. Read-only.

## How it works

Facts query: the investigator answers an analytic question the fixed tools do not cover with one read-only SQL query over the facts database. The SQL and every returned number are the evidence; the model chooses the query, the database computes the values.

## Reliability

Every metric and finding carries its layer, its method and a high, medium or low label, set by the tool for each value. See [findings and reliability](/docs/concepts/findings-and-reliability/).

## Limits

- Needs: facts database. On a scan without it, the verdict is `unknown` and says why.
- A result is a planning aid, not an inspection.

## On the made-up test home

This section was written by running the tool when the docs were built, on a hand-made RoomPlan export (no real place was scanned), with no sponsor keys and the network switched off.

Not run: it needs `question`, `sql`, which only a person or a phone on site can give.

## Run it

```sh
threshold run facts_query
curl -X POST http://127.0.0.1:8787/api/tools/facts_query/run -H 'content-type: application/json' -d '{...inputs}'
```

Over MCP the tool is named `facts_query`. See [MCP server and CLI](/docs/mcp/).
