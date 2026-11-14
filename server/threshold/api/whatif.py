"""What-if renovations for the App. The renovated plan itself is GET /api/scan/{w_sid}/plan like any other scan, and
every tool takes the w_ sid.

    GET  /api/whatif/goals          goals and the JSON Schema of an edit
    POST /api/whatif                {scan, goal, edits?, city?} -> the whole run (whatif/renovate.py)
    GET  /api/whatif/{sid}          a stored what-if scan: base, edits, diff
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from ..tools.registry import ToolContext, ToolError
from ..whatif import EDITS, AnyEdit, EditError, compare, renovate, store

router = APIRouter(prefix="/api/whatif")


class Run(BaseModel):
    scan: str = Field(max_length=64, pattern=r"^[A-Za-z0-9_]+$")
    goal: str = Field("wheelchair_ready", max_length=40)
    edits: list[AnyEdit] | None = Field(None, max_length=20)
    city: bool = False


@router.get("/goals")
def goals() -> dict:
    return {"goals": [{"id": k, "title": g["title"], "tools": list(g["tools"])} for k, g in compare.GOALS.items()],
            "edit_schema": EDITS.json_schema()}


@router.post("")
async def run(body: Run) -> dict:
    try:  # seconds of shapely and four tools per edit: off the event loop
        return await run_in_threadpool(renovate.run, ToolContext(), body.scan, body.goal, body.edits, None, body.city)
    except ToolError as e:
        raise HTTPException(404, str(e)) from None
    except (EditError, ValueError) as e:
        raise HTTPException(422, str(e)) from None


@router.get("/{sid}")
def one(sid: str) -> dict:
    try:
        rec = store.record(sid)
        diff = store.plan(sid)["whatif"]["diff"]
    except LookupError as e:
        raise HTTPException(404, str(e)) from None
    except EditError as e:
        raise HTTPException(409, f"The edits no longer fit the base plan: {e}") from None
    return {**rec, "diff": diff, "plan": f"/api/scan/{sid}/plan"}
