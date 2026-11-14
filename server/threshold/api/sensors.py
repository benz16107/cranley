"""Phone readings of a workspace as a timeline, from the MongoDB time series collection (`store/mongo.py`):
`GET /api/workspace/{id}/sensors?scan=&every=minute`. 404 when the workspaces are not in MongoDB."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException

from ..store import connect, use_mongo

router = APIRouter(prefix="/api")


@router.get("/workspace/{workspace}/sensors")
def sensors(workspace: str, scan: str | None = None, every: Literal["second", "minute", "hour"] = "minute") -> dict:
    if not use_mongo():
        raise HTTPException(404, "Phone readings are kept as a time series only when workspaces are in MongoDB")
    store = connect()
    store.record_sensors(workspace)  # captures since the last save
    return {"workspace": workspace, "every": every, "series": store.sensor_series(workspace, scan, every)}
