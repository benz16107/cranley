"""Search homes by what is measured inside them (the access workstream's measures table), for the map.

    GET /api/search/measures?where=bath_route_door>=0.81&where=floors==1&city=Houston&kind=house&sort=&limit=50
        &near=29.76,-95.37&within_km=2&room=Kitchen:area>=12,turn_diameter>=1.5   (the last three need the facts database)
    GET /api/search/measures/fields      the measures that can be searched, with labels and units
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..tools.measure_search import table

router = APIRouter(prefix="/api/search")


@router.get("/measures/fields")
def fields() -> dict:
    return {k: {"label": v[0], "unit": v[1], "kind": v[2], "description": v[3]} for k, v in table.FIELDS.items()}


@router.get("/measures")
def measures(where: list[str] = Query(default=[]), city: str | None = None, kind: str | None = None,
             sort: str | None = None, limit: int = Query(50, ge=1, le=500), near: str | None = None,
             within_km: float | None = Query(None, gt=0, le=200), room: list[str] = Query(default=[])) -> dict:
    from ..facts import db as facts_db
    if not table.DB.exists() and not facts_db.available():
        raise HTTPException(503, "The measures table has not been built yet")
    try:
        pt = tuple(float(x) for x in near.split(",")) if near else None
        if pt is not None and len(pt) != 2:
            raise ValueError("near is lat,lon")
        rooms = [{"label": r.split(":", 1)[0], "where": [_room_parse(w) for w in r.split(":", 1)[1].split(",") if w]}
                 if ":" in r else {"label": r, "where": []} for r in room]
        return table.search([table.parse(w) for w in where], city=city, kind=kind, sort=sort, limit=limit, near=pt,
                            within_m=within_km * 1000 if within_km else None, rooms=rooms)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None


def _room_parse(expr: str) -> dict:
    from ..facts.search import ROOM_MEASURES
    for op in (">=", "<=", "==", "!=", ">", "<"):
        if op in expr:
            m, v = (x.strip() for x in expr.split(op, 1))
            if m not in ROOM_MEASURES:
                raise ValueError(f"unknown room measure {m!r}; one of {', '.join(ROOM_MEASURES)}")
            return {"measure": m, "op": op, "value": float(v)}
    raise ValueError(f"no comparison in {expr!r}; write e.g. area>=12")
