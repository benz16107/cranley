"""Read-only SQL for the investigator: analytic questions the fixed tools do not cover, answered by one SELECT the
agent writes, with the SQL shown as evidence.

Safety, in layers: the statement must be a single SELECT or WITH; it runs on a separate connection logged in as
`threshold_reader`, a role that can only SELECT from schema `threshold`, whose transactions are read only, with a
5 s statement timeout; at most MAX_ROWS rows come back. The reader's password is random per process and lives only
in memory (it is reset on the role each time this process connects), so nothing secret is stored.

Tiger Data's own MCP server (`tiger mcp start`, tool `db_query`, with `read_only` set to `all`) gives a coding agent
the same kind of access to a Tiger Cloud service; this module is the product's in-app equivalent.
"""
from __future__ import annotations

import re
import secrets
import threading
import time

import pg8000.native

from . import db

MAX_ROWS = 200
SCHEMA_DOC = """Schema threshold (Postgres with TimescaleDB, PostGIS, pgvector). Units: metres, m2, ft2 where named.
scan(sid, building_id, name, kind[house|apartment_unit|office|amenity|warehouse|retail|other], segment, city, zip,
     address, geom geography(Point), walls bool, polygons bool, labels bool, panos, floors, created)
building(id, property_id, address, city, zip, property_type, listed_area_ft2, geom geography(Point), footprint geography(Polygon))
measures(sid, floor_area, rooms, bedrooms, bathrooms, kitchens, floors, entrances, entrance_width, doors, narrowest_door,
     median_door, bath_route_door, bath_route_m, bed_route_door_min, kitchen_route_door, bath_turn, kitchen_turn,
     bed_turn, largest_turn, longest_wall, bed_wall, living_wall, ceiling_median, windows, glazed_area, glazing_ratio,
     level_changes, max_sill_step, step_free_bath 0/1, wheelchair_bath 0/1, wheelchair_rooms_share %, error)
room(sid, room, floor, label, area, width, depth, height, doors, widest_door, narrowest_door, turn_diameter, windows, glazed_area)
door(sid, opening, kind, width, implausible, step, floor)
fact(at, sid, building_id, room, field, value_num, value_text, unit, layer, method, confidence, tool, run, evidence jsonb,
     record_value, record_path, city, zip, kind, property_type)  -- hypertable; history of every computed field
fact_daily(day, sid, room, field, value_num, value_text, unit, method, confidence, record_value, building_id, city, zip,
     kind, property_type, at, observations)  -- continuous aggregate: latest value per scan, room, field and day
  fields include every measures column, area_gap (measured/listed - 1), vs_record.<claim> (value_text is the verdict:
  confirmed|contradicted|cannot verify; record_value is the record's), room.area, room.turn_diameter, <tool>.<metric>
flood_run(run, sid, scenario, datum, step_m, step_s, started); flood_depth(ts, run, sid, room, label, level_m, depth_m, wet_area_m2)
flood_by_level(bucket, run, sid, level_m, rooms_wet, rooms, wet_area_m2, max_depth_m)  -- continuous aggregate
ops_hourly(hour, op, by_whom, tool, ops, workspaces)  -- agent operations per hour, counts only
room_text(sid, room, pano, description, features text[], embedding vector(384), labels smallint[]); room_type(id, label)"""
_FORBIDDEN = re.compile(r"\b(insert|update|delete|merge|truncate|alter|create|drop|grant|revoke|copy|call|do|vacuum|"
                        r"analyze|refresh|set|reset|lock|listen|notify|prepare|execute|comment|security|set_config|"
                        r"pg_sleep|dblink|lo_\w+|pg_read\w*|pg_ls\w*|op_log|_timescaledb_\w+|_hyper_\w+)\b", re.IGNORECASE)
_lock = threading.Lock()
_reader: dict = {}


def check(sql: str) -> str:
    """The statement, trimmed, if it is one read-only query; ValueError with a reason otherwise."""
    s = re.sub(r"--[^\n]*", " ", sql).strip().rstrip(";").strip()
    if ";" in s:
        raise ValueError("one statement only")
    if not re.match(r"(?is)^\s*(select|with)\b", s):
        raise ValueError("only SELECT or WITH queries")
    bad = _FORBIDDEN.search(re.sub(r"'(?:[^']|'')*'", "''", s))  # ignore words inside string literals
    if bad:
        raise ValueError(f"'{bad.group(0)}' is not allowed in a read-only query")
    return s


def _connect() -> pg8000.native.Connection:
    """A connection as threshold_reader with a fresh random password set by the owner connection."""
    pw = secrets.token_urlsafe(24)
    owner = db.con()
    owner.run(f"ALTER ROLE {db.READER} LOGIN PASSWORD '{pw}'")  # token_urlsafe has no quote characters
    p = db._params(db.url())
    c = pg8000.native.Connection(**{**p, "user": db.READER, "password": pw, "application_name": "threshold-reader"},
                                 timeout=10)
    c.run("SET search_path = threshold, public")
    return c


def run(sql: str, limit: int = MAX_ROWS) -> dict:
    """Run one read-only query as threshold_reader. Returns columns, rows (at most `limit`), time and the SQL."""
    s = check(sql)
    with _lock:
        c = _reader.get("con")
        for attempt in (0, 1):
            try:
                if c is None:
                    c = _reader["con"] = _connect()
                t0 = time.perf_counter()
                c.run("BEGIN READ ONLY")
                try:
                    out = c.run(s)
                    cols = [d["name"] for d in c.columns or []]
                finally:
                    c.run("ROLLBACK")
                break
            except pg8000.native.InterfaceError:
                c = _reader["con"] = None  # dropped connection: reconnect once
                if attempt:
                    raise
            except pg8000.native.DatabaseError as e:
                msg = e.args[0].get("M") if e.args and isinstance(e.args[0], dict) else str(e)
                raise ValueError(f"the database refused the query: {msg}") from None
    rows = out or []
    return {"sql": s, "columns": cols, "rows": [[_plain(v) for v in r] for r in rows[:limit]], "row_count": len(rows),
            "truncated": len(rows) > limit, "ms": round((time.perf_counter() - t0) * 1000, 1), "role": db.READER}


def _plain(v):
    from datetime import date, datetime
    from decimal import Decimal
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, str) and len(v) > 500:
        return v[:500] + "…"
    if isinstance(v, (bytes, memoryview)):
        return None
    return v
