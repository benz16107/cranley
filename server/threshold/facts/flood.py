"""Flood rehearsal runs as time series: water rising past a house in steps, the geometry engine's water depth per
room at each step, one `flood_depth` row per (time, room). A run can be replayed, compared with other houses, and
aggregated across many ("how many rooms across these 200 Houston houses are wet at 0.5 m, 1 m, 1.5 m").

Level 0 is the lowest scanned floor (the scan's own frame). Height above the street needs the floor height the
flood_rehearsal tool measures from aerial and drone data; these runs do not call those APIs, and say so in `datum`.
"""
from __future__ import annotations

import time
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime, timedelta

from . import db
from .load import cached_plan, copy

STEP_M, STEP_S, TOP_M = 0.05, 900, 2.0  # 5 cm every 15 minutes up to 2 m: a ten-hour rise
DATUM = "lowest scanned floor"
SCENARIO = "rise 5 cm per 15 min"


def simulate(plan: dict, started: datetime, step_m: float = STEP_M, step_s: int = STEP_S, top_m: float = TOP_M) -> list[list]:
    """flood_depth rows [ts, run, sid, room, label, level_m, depth_m, wet_area_m2] for one plan."""
    from ..geometry import water
    run = f"{plan['sid']}:{started:%Y%m%dT%H%M}"
    first = water(plan, 0.0)
    if not first["available"]:
        return []
    ground = first["level"] - first["level_above_lowest_floor"]
    rows = []
    for i in range(round(top_m / step_m) + 1):
        level = round(i * step_m, 3)
        w = water(plan, ground + level)
        ts = (started + timedelta(seconds=i * step_s)).isoformat()
        rows += [[ts, run, plan["sid"], r["room"], r["label"], level, round(r["depth"], 3),
                  round(r["wetted_floor_area"], 2)] for r in w["rooms"]]
    return rows


def _one(args) -> tuple[str, list[list], str | None]:
    sid, started = args
    try:
        plan = cached_plan(sid)
        return sid, simulate(plan, started) if plan else [], None
    except Exception as e:  # noqa: BLE001 - one odd plan must not stop the batch
        return sid, [], f"{type(e).__name__}: {e}"[:200]


def run_many(city: str = "Houston", kind: str = "house", limit: int = 200, workers: int = 8,
             sids: list[str] | None = None) -> dict:
    """Simulate and store one run per scan: by default the first `limit` walled scans of `kind` in `city`."""
    t0 = time.time()
    if sids is None:
        sids = [r["sid"] for r in db.rows("SELECT sid FROM scan WHERE walls AND kind = :k AND city ILIKE :c "
                                          "ORDER BY sid LIMIT :n", k=kind, c=f"%{city}%", n=limit)]
    started = datetime.now(UTC).replace(second=0, microsecond=0)
    with ProcessPoolExecutor(workers) as ex:
        res = list(ex.map(_one, [(s, started) for s in sids], chunksize=4))
    rows = [r for _, rs, _ in res for r in rs]
    runs = sorted({r[1]: r[2] for r in rows}.items())
    with db.transaction() as c:
        copy(c, "flood_run", ["run", "sid", "scenario", "datum", "step_m", "step_s", "started", "note"],
             [[run, sid, SCENARIO, DATUM, STEP_M, STEP_S, started.isoformat(),
               "Still water through openings by sill height (threshold.geometry.water)"] for run, sid in runs])
        copy(c, "flood_depth", ["ts", "run", "sid", "room", "label", "level_m", "depth_m", "wet_area_m2"], rows)
    db.con().run("CALL refresh_continuous_aggregate('flood_by_level', NULL, NULL)")
    return {"scans": len(sids), "runs": len(runs), "rows": len(rows), "errors": [e for _, _, e in res if e][:5],
            "seconds": round(time.time() - t0, 1)}


def wet_at(levels: list[float], city: str | None = None, run_like: str | None = None) -> list[dict]:
    """Across the latest stored run of each house: houses and rooms wet at each level, from the flood_by_level
    continuous aggregate."""
    return db.rows(
        "SELECT l.level AS level_m, count(DISTINCT f.sid) AS houses, sum(f.rooms) AS rooms, "
        "sum(f.rooms_wet) AS rooms_wet, count(DISTINCT f.sid) FILTER (WHERE f.rooms_wet > 0) AS houses_wet, "
        "round(sum(f.wet_area_m2)::numeric, 1) AS wet_area_m2 "
        "FROM unnest(CAST(:levels AS real[])) AS l(level) "
        "JOIN flood_by_level f ON abs(f.level_m - l.level) < 0.001 "
        "JOIN (SELECT DISTINCT ON (sid) run FROM flood_run ORDER BY sid, started DESC) latest ON latest.run = f.run "
        "JOIN scan s ON s.sid = f.sid "
        "WHERE (CAST(:city AS text) IS NULL OR s.city ILIKE CAST(:city AS text)) "
        "AND (CAST(:run AS text) IS NULL OR f.run LIKE CAST(:run AS text)) "
        "GROUP BY l.level ORDER BY l.level",
        levels=levels, city=f"%{city}%" if city else None, run=run_like)
