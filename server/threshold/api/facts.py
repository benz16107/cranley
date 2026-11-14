"""The building facts database (Tiger Data) over HTTP: city rollups, fact history, similar rooms, flood runs, usage
and read-only SQL. Every route answers 503 when no database is configured.

    GET  /api/facts/status                       row counts, compression, extensions
    GET  /api/facts/census?preset=wheelchair_homes | ?field=area_gap&by=property_type&stat=median&city=&kind=
    GET  /api/facts/census/presets
    GET  /api/facts/fields                       fields with values, scans per field
    GET  /api/facts/history/{sid}?field=         every recorded value, newest first
    GET  /api/facts/rooms/similar?q=sunlit kitchen with an island&label=Kitchen&city=Houston&min_area=12&words=0.3
    GET  /api/facts/rooms/similar?sid=&room=     rooms like this one
    GET  /api/facts/flood/wet?levels=0.5,1,1.5&city=Houston
    GET  /api/facts/flood/runs?sid=              stored runs
    GET  /api/facts/flood/run/{run}              replay: depth per room at each time step
    GET  /api/facts/ops?hours=24                 workspace operations per hour (usage)
    POST /api/facts/sql  {"sql": "SELECT ..."}   one read-only query, run as threshold_reader
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..facts import db

router = APIRouter(prefix="/api/facts")


def _need() -> None:
    if not db.available():
        raise HTTPException(503, "The facts database is not configured (TIGER_DATABASE_URL) or not reachable")


@router.get("/status")
def status() -> dict:
    _need()
    from ..facts import stats
    return stats.stats()


@router.get("/census/presets")
def presets() -> dict:
    from ..facts.census import PRESETS
    return PRESETS


@router.get("/census")
def census(preset: str | None = None, field: str | None = None, by: str | None = None, stat: str | None = None,
           city: str | None = None, kind: str | None = None, min_scans: int = Query(3, ge=1),
           limit: int = Query(50, ge=1, le=500)) -> dict:
    _need()
    from ..facts import census as cs
    try:
        if preset:
            if preset not in cs.PRESETS:
                raise ValueError(f"unknown preset; one of {', '.join(cs.PRESETS)}")
            kw = {k: v for k, v in {"by": by, "stat": stat}.items() if v}
            return cs.preset(preset, city=city, kind=kind, min_scans=min_scans, limit=limit, **kw)
        if not field:
            raise ValueError("give a preset or a field")
        return cs.census(field, by=by or "zip", stat=stat or "share", city=city, kind=kind, min_scans=min_scans,
                         limit=limit)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None


@router.get("/fields")
def fields() -> list[dict]:
    _need()
    from ..facts import census as cs
    return cs.fields()


@router.get("/history/{sid}")
def history(sid: str, field: str | None = None, limit: int = Query(200, ge=1, le=2000)) -> list[dict]:
    _need()
    from ..facts import census as cs
    return cs.history(sid, field, limit)


@router.get("/rooms/similar")
def similar(q: str | None = None, sid: str | None = None, room: str | None = None, label: str | None = None,
            city: str | None = None, kind: str | None = None, min_area: float | None = None,
            min_turn: float | None = None, words: float = Query(0.0, ge=0, le=1),
            limit: int = Query(10, ge=1, le=50)) -> dict:
    _need()
    from ..facts import rooms
    try:
        return rooms.similar(q, like=(sid, room) if sid and room else None, label=label, city=city, kind=kind,
                             min_area=min_area, min_turn=min_turn, words=words, limit=limit)
    except LookupError as e:
        raise HTTPException(404, str(e).strip("'\"")) from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from None


@router.get("/flood/wet")
def flood_wet(levels: str = "0.5,1,1.5", city: str | None = None) -> list[dict]:
    _need()
    from ..facts import flood
    try:
        lv = [float(x) for x in levels.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(400, "levels are metres, comma separated") from None
    return flood.wet_at(lv, city=city)


@router.get("/flood/runs")
def flood_runs(sid: str | None = None, limit: int = Query(50, ge=1, le=1000)) -> list[dict]:
    _need()
    return db.rows("SELECT * FROM flood_run WHERE (CAST(:sid AS text) IS NULL OR sid = CAST(:sid AS text)) "
                   "ORDER BY started DESC, sid LIMIT :n", sid=sid, n=limit)


@router.get("/flood/run/{run}")
def flood_run(run: str) -> dict:
    _need()
    meta = db.rows("SELECT * FROM flood_run WHERE run = :r", r=run)
    if not meta:
        raise HTTPException(404, f"no flood run {run}")
    steps = db.rows("SELECT ts, level_m, json_object_agg(room, depth_m) AS depth, "
                    "count(*) FILTER (WHERE depth_m > 0) AS rooms_wet, sum(wet_area_m2) AS wet_area_m2 "
                    "FROM flood_depth WHERE run = :r GROUP BY ts, level_m ORDER BY ts", r=run)
    return {**meta[0], "steps": steps}


@router.get("/ops")
def ops(hours: int = Query(24, ge=1, le=24 * 90)) -> list[dict]:
    _need()
    return db.rows("SELECT hour, op, by_whom, tool, ops, workspaces FROM ops_hourly "
                   "WHERE hour > now() - make_interval(hours => :h) ORDER BY hour DESC, ops DESC", h=hours)


class Sql(BaseModel):
    sql: str


@router.post("/sql")
def sql(body: Sql) -> dict:
    _need()
    from ..facts import ask
    try:
        return ask.run(body.sql)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
