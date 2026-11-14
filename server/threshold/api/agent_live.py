"""The agents at work, live: `GET /api/agent/{workspace}/live` streams the main agent and one lane per subagent (what
it was asked, the tool it is running, waiting for an approval, done) as server-sent `lanes` events, a full snapshot
each time something changes. The agent panel shows it beside the plan."""
from __future__ import annotations

import json
import queue

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from ..agent import live

router = APIRouter(prefix="/api")


@router.get("/agent/{workspace}/live")
def agent_live(workspace: str) -> StreamingResponse:
    def stream():
        q = live.subscribe(workspace)
        try:
            while True:
                try:
                    snap = q.get(timeout=15)
                except queue.Empty:
                    yield ": keep-alive\n\n"  # notices a closed client and keeps proxies from timing out
                    continue
                yield f"event: lanes\ndata: {json.dumps(snap, default=str)}\n\n"
        finally:
            live.unsubscribe(workspace, q)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@router.get("/agent/{workspace}/lanes")
def agent_lanes(workspace: str) -> dict:
    return live.snapshot(workspace)
