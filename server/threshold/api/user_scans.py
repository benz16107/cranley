"""Scans of people's own homes from the iPhone app. The plan itself is served by GET /api/scan/{sid}/plan like any
other scan, and every tool takes the sid."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from ..roomplan import ExportError
from ..sources import user_scans

router = APIRouter(prefix="/api")
MAX_BYTES = 25_000_000  # a whole-house CapturedStructure is a few MB


class Geo(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    altitude: float | None = None
    accuracy_m: float | None = None
    heading_deg: float | None = Field(None, ge=0, lt=360, description="Compass heading of camera_forward, true north")
    heading_accuracy_deg: float | None = None
    camera_forward: list[float] | None = Field(None, min_length=2, max_length=2, description="RoomPlan world X, Z")
    camera_position: list[float] | None = Field(None, min_length=2, max_length=2, description="RoomPlan world X, Z")


class Upload(BaseModel):
    export: dict = Field(description="JSONEncoder output of RoomPlan's CapturedRoom or CapturedStructure")
    name: str = Field("My home", max_length=120)
    kind: str | None = Field(None, max_length=40, description="house, apartment_unit, office... (door exteriors)")
    address: str | None = Field(None, max_length=200)
    city: str | None = Field(None, max_length=80)
    notes: str | None = Field(None, max_length=2000)
    geo: Geo | None = None
    workspace: str | None = Field(None, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")


@router.post("/scans/user")
async def upload(request: Request) -> dict:
    from .capture import _body
    body = await _body(request, MAX_BYTES)  # refused as it streams in, not after the whole body is in memory
    try:
        up = Upload.model_validate_json(body)
    except ValueError as e:
        raise HTTPException(422, str(e)[:500]) from None
    meta = up.model_dump(exclude={"export"}, exclude_none=True)
    try:
        plan = await run_in_threadpool(user_scans.save, up.export, meta)  # seconds of shapely: off the event loop
    except ExportError as e:
        raise HTTPException(422, str(e)) from None
    q = plan["quality"]
    return {"sid": plan["sid"], "name": plan["name"], "plan": f"/api/scan/{plan['sid']}/plan",
            "rooms": [{"id": r["id"], "label": r["label"], "area": r["area"]} for r in plan["rooms"]],
            "counts": q["counts"], "quality": {k: q[k] for k in ("walls", "polygons", "openings", "labels", "georef")},
            "notes": q["notes"]}


@router.get("/scans/user")
def listing(workspace: str | None = None) -> list[dict]:
    return user_scans.rows(workspace)
