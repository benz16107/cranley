"""Show routes: a real storm and a modelled fire as timelines the scene plays on the building. Owned by the show
workstream. The numbers are the flood and smoke tools' own; see world/storm.py and world/smoke.py."""
from __future__ import annotations

import functools

from fastapi import APIRouter, HTTPException

from ..tools import ToolError
from ..tools.registry import default_plan
from ..world import smoke, storm

router = APIRouter(prefix="/api/show")


def _plan(sid: str) -> dict:
    try:
        return default_plan(sid)
    except (LookupError, ToolError) as e:
        raise HTTPException(404, f"No scan {sid}: {e}") from None


@functools.lru_cache(maxsize=32)
def _storm(sid: str) -> dict:
    return storm.timeline(_plan(sid))


@functools.lru_cache(maxsize=32)
def _belongings(sid: str) -> dict:
    return storm.belongings(_plan(sid))


@router.get("/{sid}/storm")
def scan_storm(sid: str) -> dict:
    """Hurricane Harvey at this house: a water level for every half hour, when each room takes water, and sources."""
    return _storm(sid)


@router.get("/{sid}/storm/belongings")
def scan_belongings(sid: str) -> dict:
    """What the water reaches, item by item, and the loss range at every step. Minutes the first time (vision)."""
    return _belongings(sid)


@router.get("/{sid}/smoke")
def scan_smoke(sid: str, doors: str = "open", fire_room: str | None = None) -> dict:
    """The Smoke clock's CFAST run as a per-room timeline. Reads a finished run; never starts one."""
    try:
        return smoke.timeline(_plan(sid), closed=doors == "closed", fire_room=fire_room)
    except ToolError as e:
        return {"sid": sid, "available": False, "reason": str(e)}
