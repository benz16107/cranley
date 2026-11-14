"""Row counts, sizes, columnstore compression and query timings for the facts database."""
from __future__ import annotations

import json
import statistics
import time

from . import db

HYPERTABLES = ("fact", "flood_depth", "op_log")
TABLES = ("building", "scan", "measures", "room", "door", "room_text", "flood_run") + HYPERTABLES


def compress() -> dict:
    """Convert every chunk of each hypertable to the columnstore now (the policy would do it after a day)."""
    c = db.con()
    for h in HYPERTABLES:
        for (ch,) in c.run(f"SELECT show_chunks('threshold.{h}')") or []:
            c.run(f"CALL convert_to_columnstore('{ch}', if_not_columnstore => true)")
    return compression()


def compression() -> dict:
    out = {}
    for h in HYPERTABLES:
        r = db.rows("SELECT sum(before_compression_total_bytes) AS before, sum(after_compression_total_bytes) AS after, "
                    "count(*) AS chunks FROM hypertable_columnstore_stats(CAST(:h AS regclass))", h=f"threshold.{h}")[0]
        b, a = (int(x) if x is not None else None for x in (r["before"], r["after"]))
        out[h] = {"chunks": r["chunks"], "before_bytes": b, "after_bytes": a,
                  "ratio": round(b / a, 1) if a else None, "saved": f"{100 * (1 - a / b):.1f}%" if a and b else None}
    return out


def stats() -> dict:
    rows = {t: db.rows(f"SELECT count(*) AS n FROM {t}")[0]["n"] for t in TABLES}
    size = {t: db.rows("SELECT CASE WHEN EXISTS (SELECT 1 FROM timescaledb_information.hypertables WHERE "
                       "hypertable_schema = 'threshold' AND hypertable_name = :t) THEN hypertable_size(CAST(:q AS regclass)) "
                       "ELSE pg_total_relation_size(CAST(:q AS regclass)) END AS b", t=t, q=f"threshold.{t}")[0]["b"]
            for t in TABLES}
    caggs = {r["view_name"]: r["n"] for r in db.rows(
        "SELECT view_name, 0 AS n FROM timescaledb_information.continuous_aggregates WHERE view_schema = 'threshold'")}
    for v in caggs:
        caggs[v] = db.rows(f"SELECT count(*) AS n FROM {v}")[0]["n"]
    ext = {r["extname"]: r["extversion"] for r in db.rows(
        "SELECT extname, extversion FROM pg_extension WHERE extname IN ('timescaledb', 'timescaledb_toolkit', 'postgis', "
        "'vector', 'vectorscale', 'pg_textsearch')")}
    return {"rows": rows, "bytes": size, "continuous_aggregates": caggs, "compression": compression(), "extensions": ext}


def _time(sql: str, args: dict, n: int = 7, off: bool = False) -> tuple[float, list[str]]:
    """Median server execution time in ms of `sql` over n runs (EXPLAIN ANALYZE, after one warm-up; network round
    trips left out, so a cloud service and a local one compare fairly), and the plan's scan node types.
    `off` disables index, bitmap and index-only scans for the run, so the planner must read the table."""
    c = db.con()
    c.run("BEGIN")
    try:
        if off:
            for k in ("enable_indexscan", "enable_bitmapscan", "enable_indexonlyscan"):
                c.run(f"SET LOCAL {k} = off")
        ts, nodes = [], set()

        def walk(p):
            if "Scan" in p["Node Type"]:
                nodes.add(p["Node Type"] + (f" {p['Index Name']}" if p.get("Index Name") else "") +
                          (f" on {p['Relation Name']}" if p.get("Relation Name") else ""))
            for ch in p.get("Plans") or []:
                walk(ch)
        for i in range(n + 1):
            plan = c.run("EXPLAIN (ANALYZE, FORMAT JSON) " + sql, **args)[0][0]
            plan = (json.loads(plan) if isinstance(plan, str) else plan)[0]
            if i:
                ts.append(plan["Execution Time"] + plan["Planning Time"])
            else:
                walk(plan["Plan"])
    finally:
        c.run("ROLLBACK")
    return round(statistics.median(ts), 2), sorted(nodes)


def round_trip_ms(n: int = 7) -> float:
    c = db.con()
    ts = []
    for _ in range(n):
        t0 = time.perf_counter()
        c.run("SELECT 1")
        ts.append((time.perf_counter() - t0) * 1000)
    return round(statistics.median(ts), 2)


def bench() -> dict:
    """Each question timed with its indexes and with index scans switched off; aggregates against the raw tables."""
    from . import census, search
    pt = db.rows("SELECT ST_Y(geom::geometry) AS lat, ST_X(geom::geometry) AS lon FROM scan WHERE kind = 'apartment_unit' "
                 "AND city ILIKE '%Houston%' AND geom IS NOT NULL ORDER BY sid LIMIT 1")[0]
    s = search.search([{"measure": "bath_route_door", "op": ">=", "value": 0.81}], kind="apartment_unit",
                      near=(pt["lat"], pt["lon"]), within_m=2000)
    r = search.search([], city="Houston", rooms=[{"label": "Kitchen", "where": [
        {"measure": "area", "op": ">=", "value": 12}, {"measure": "turn_diameter", "op": ">=", "value": 1.5}]}])
    one = db.rows("SELECT sid FROM fact WHERE field = 'bath_route_door' ORDER BY sid LIMIT 1")[0]["sid"]
    cz = census.census("wheelchair_bath", by="zip")
    cr = census.census("wheelchair_bath", by="zip", source="fact")
    flood_raw = ("SELECT level_m, count(DISTINCT sid) AS houses, count(*) FILTER (WHERE depth_m > 0) AS rooms_wet "
                 "FROM flood_depth WHERE level_m IN (0.5, 1.0, 1.5) GROUP BY level_m")
    flood_agg = ("SELECT level_m, count(DISTINCT sid) AS houses, sum(rooms_wet) AS rooms_wet FROM flood_by_level "
                 "WHERE level_m IN (0.5, 1.0, 1.5) GROUP BY level_m")
    qs = {
        "apartments within 2 km, bathroom through 0.81 m doors": (s["sql"], s["params"]),
        "Houston homes with a kitchen of 12 m2 and a 1.5 m turning circle": (r["sql"], r["params"]),
        "one scan's history of one field": (("SELECT at, value_num, tool FROM fact WHERE sid = :sid AND field = :f "
                                             "ORDER BY at DESC"), {"sid": one, "f": "bath_route_door"}),
        "flood: rooms wet at 0.5, 1 and 1.5 m (raw rows)": (flood_raw, {}),
    }
    out = {}
    for name, (sql, args) in qs.items():
        on, nodes_on = _time(sql, args)
        off, nodes_off = _time(sql, args, off=True)
        out[name] = {"with_indexes_ms": on, "without_indexes_ms": off, "plan_with": nodes_on, "plan_without": nodes_off,
                     "rows": len(db.rows(sql, **args))}
    for name, (sql_raw, args_raw, sql_agg, args_agg) in {
        "census: wheelchair share by zip": (cr["sql"], {"field": "wheelchair_bath", "city": None, "kind": None,
                                                        "min": 3, "lim": 50},
                                           cz["sql"], {"field": "wheelchair_bath", "city": None, "kind": None,
                                                       "min": 3, "lim": 50}),
        "flood: rooms wet at 0.5, 1 and 1.5 m": (flood_raw, {}, flood_agg, {}),
    }.items():
        raw, _ = _time(sql_raw, args_raw)
        agg, nodes = _time(sql_agg, args_agg)
        out[name] = {"raw_table_ms": raw, "continuous_aggregate_ms": agg, "plan_aggregate": nodes}
    n = db.rows("SELECT count(*) AS n FROM room_text WHERE embedding IS NOT NULL")[0]["n"]
    if n:
        qs = [r["v"] for r in db.rows("SELECT embedding::text AS v FROM room_text ORDER BY sid, room")][::max(1, n // 20)][:20]
        sql = "SELECT sid, room FROM room_text ORDER BY embedding <=> CAST(:q AS vector) LIMIT 10"
        ann, nodes = _time(sql, {"q": qs[0]})
        exact, nodes_x = _time(sql, {"q": qs[0]}, off=True)
        c, rec = db.con(), []
        for q in qs:
            a = {tuple(x) for x in c.run(sql, q=q)}
            c.run("BEGIN")
            c.run("SET LOCAL enable_indexscan = off")
            e = {tuple(x) for x in c.run(sql, q=q)}
            c.run("ROLLBACK")
            rec.append(len(a & e) / max(len(e), 1))
        out["similar rooms, top 10 by embedding"] = {"diskann_ms": ann, "exact_ms": exact, "plan_with": nodes,
                                                     "plan_without": nodes_x, "recall_at_10": round(sum(rec) / len(rec), 3),
                                                     "queries": len(qs), "rooms": n}
    out["round_trip_ms"] = round_trip_ms()
    return out
