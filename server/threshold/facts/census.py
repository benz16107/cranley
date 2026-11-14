"""City and neighbourhood rollups of the fact history, read from the `fact_daily` continuous aggregate (the latest
value of every field per scan and day, real time). Each scan counts once: its most recent value.

    census("wheelchair_bath", by="zip", city="Houston")        share of homes where a wheelchair reaches a bathroom
    census("area_gap", by="property_type", stat="median")      measured over listed area, minus one
"""
from __future__ import annotations

import time

from . import db

GROUPS = {"zip": "zip", "city": "city", "property_type": "property_type", "kind": "kind", "building": "building_id"}
PRESETS = {
    "wheelchair_homes": {"field": "wheelchair_bath", "by": "zip", "stat": "share",
                         "label": "Homes where a wheelchair reaches a bathroom from the entrance (0.815 m doors, no steps)"},
    "area_gap": {"field": "area_gap", "by": "property_type", "stat": "median",
                 "label": "Measured over listed area, minus one (negative: smaller than listed)"},
    "smoke_alarms": {"field": "risk_sheet.check.smoke_alarms", "by": "building", "stat": "share",
                     "label": "Scans where the panoramas show at least one smoke alarm"},
    "step_free_bath": {"field": "step_free_bath", "by": "zip", "stat": "share",
                       "label": "Homes with a step-free way to a bathroom"},
    "bath_route_door": {"field": "bath_route_door", "by": "city", "stat": "median",
                        "label": "Narrowest door on the way to the bathroom (m)"},
}


def census(field: str, *, by: str = "zip", stat: str = "share", city: str | None = None, kind: str | None = None,
           min_scans: int = 3, limit: int = 50, source: str = "fact_daily") -> dict:
    """Per group: scans with a value, the share above zero (for flags and counts), mean and median.
    `source` = "fact" reads the raw history instead of the continuous aggregate (for timing comparisons)."""
    if by not in GROUPS:
        raise ValueError(f"group by one of {', '.join(GROUPS)}")
    if stat not in ("share", "median", "mean"):
        raise ValueError("stat is share, median or mean")
    if source not in ("fact_daily", "fact"):
        raise ValueError("source is fact_daily or fact")
    g = GROUPS[by]
    order = {"share": "share", "median": "median", "mean": "mean"}[stat]
    sql = (f"WITH latest AS (SELECT DISTINCT ON (sid) sid, {g} AS grp, value_num FROM {source} "
           "WHERE field = :field AND room IS NULL AND value_num IS NOT NULL "
           "AND (CAST(:city AS text) IS NULL OR city ILIKE CAST(:city AS text)) "
           "AND (CAST(:kind AS text) IS NULL OR kind = CAST(:kind AS text)) "
           f"ORDER BY sid, {'day' if source == 'fact_daily' else 'at'} DESC) "
           "SELECT grp, count(*) AS scans, round(avg((value_num > 0)::int)::numeric, 3) AS share, "
           "round(avg(value_num)::numeric, 3) AS mean, "
           "round(percentile_cont(0.5) WITHIN GROUP (ORDER BY value_num)::numeric, 3) AS median "
           f"FROM latest GROUP BY grp HAVING count(*) >= :min ORDER BY {order} DESC NULLS LAST, scans DESC LIMIT :lim")
    t0 = time.perf_counter()
    rows = db.rows(sql, field=field, city=f"%{city}%" if city else None, kind=kind, min=min_scans, lim=limit)
    ms = round((time.perf_counter() - t0) * 1000, 1)
    tot = db.rows(f"SELECT count(DISTINCT sid) AS n FROM {source} WHERE field = :f AND room IS NULL", f=field)[0]["n"]
    return {"field": field, "by": by, "stat": stat, "rows": [{k: (float(v) if k in ("share", "mean", "median") and v is not None
                                                              else v) for k, v in r.items()} for r in rows],
            "scans_with_field": tot, "sql": sql, "ms": ms, "source": source}


def preset(name: str, **kw) -> dict:
    p = PRESETS[name]
    out = census(p["field"], by=kw.pop("by", p["by"]), stat=kw.pop("stat", p["stat"]), **kw)
    return {**out, "preset": name, "label": p["label"]}


def fields(limit: int = 200) -> list[dict]:
    """Fields with scan-level values, how many scans have each, and the tools that wrote them."""
    return db.rows("SELECT field, count(DISTINCT sid) AS scans, max(at) AS latest, "
                   "array_agg(DISTINCT method) FILTER (WHERE method IS NOT NULL) AS methods "
                   "FROM fact_daily WHERE room IS NULL GROUP BY field ORDER BY scans DESC LIMIT :n", n=limit)


def history(sid: str, field: str | None = None, limit: int = 200) -> list[dict]:
    """Every recorded value of a scan's facts, newest first: what changed, when, by which tool and method."""
    return db.rows("SELECT at, room, field, value_num, value_text, unit, layer, method, confidence, tool, run, "
                   "record_value, record_path, evidence FROM fact WHERE sid = :sid "
                   "AND (CAST(:field AS text) IS NULL OR field = CAST(:field AS text)) ORDER BY at DESC LIMIT :n",
                   sid=sid, field=field, n=limit)
