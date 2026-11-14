"""Past work, from MongoDB Atlas (THRESHOLD_STORE=mongo; 501 otherwise).

GET /api/history/search     full-text search over briefs, findings, notes, removed tools and shortlisted scans, with
                            facet counts (tool, status, city, kind, feedback). Needs profile or workspace.
GET /api/history/similar    past needs most like a sentence (vector search), optionally one persona's.
GET /api/history/shortlist  shortlisted scans of a profile or workspace, nearest first and within km of a point.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/history")


def mongo_store():
    from ..store import connect, use_mongo
    if not use_mongo():
        raise HTTPException(501, "Past work needs the MongoDB store (THRESHOLD_STORE=mongo)")
    return connect()


def point(near: str | None) -> tuple[float | None, float | None]:
    if not near:
        return None, None
    try:
        lon, lat = (float(x) for x in near.split(","))
    except ValueError:
        raise HTTPException(422, "near is lon,lat") from None
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        raise HTTPException(422, "near is out of range")
    return lon, lat


@router.get("/search")
def search(q: str | None = None, profile: str | None = None, workspace: str | None = None, tool: str | None = None,
           status: str | None = None, city: str | None = None, kind: str | None = None, feedback: str | None = None,
           sid: str | None = None, limit: int = Query(10, ge=1, le=50)) -> dict:
    if not (profile or workspace):
        raise HTTPException(422, "Say whose past work: profile or workspace")
    return mongo_store().search(q, limit, profile=profile, workspace=workspace, tool=tool, status=status, city=city,
                                kind=kind, feedback=feedback, sid=sid)


@router.get("/similar")
def similar(text: str, persona: str | None = None, k: int = Query(3, ge=1, le=10)) -> list[dict]:
    return mongo_store().recall(text, persona=persona, k=k)


@router.get("/shortlist")
def shortlist(profile: str | None = None, workspace: str | None = None, near: str | None = None,
              km: float | None = Query(None, gt=0, le=500)) -> list[dict]:
    if not (profile or workspace):
        raise HTTPException(422, "Say whose shortlist: profile or workspace")
    return mongo_store().shortlist_near(*point(near), km=km, profile=profile, workspace=workspace)
