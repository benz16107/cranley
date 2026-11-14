"""Search homes by what is measured inside them (the access workstream's measures table), for the map.

    GET /api/search/measures?where=bath_route_door>=0.81&where=floors==1&city=Houston&kind=house&sort=&limit=50
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
             sort: str | None = None, limit: int = Query(50, ge=1, le=500)) -> dict:
    if not table.DB.exists():
        raise HTTPException(503, "The measures table has not been built yet")
    try:
        return table.search([table.parse(w) for w in where], city=city, kind=kind, sort=sort, limit=limit)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
