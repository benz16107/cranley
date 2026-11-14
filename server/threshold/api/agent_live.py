"""The agents at work, live: `GET /api/agent/{workspace}/live` streams the main agent and one lane per subagent (what
it was asked, the tool it is running, waiting for an approval, done) as server-sent `lanes` events, a full snapshot
each time something changes. The agent panel shows it beside the plan."""
from __future__ import annotations

import asyncio
import json
import queue

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from ..agent import live

router = APIRouter(prefix="/api")


@router.get("/agent/{workspace}/live")
async def agent_live(workspace: str) -> StreamingResponse:
    async def stream():  # async and polling, so an open panel holds no threadpool worker
        q = live.subscribe(workspace)
        idle = 0.0
        try:
            while True:
                try:
                    snap = q.get_nowait()
                except queue.Empty:
                    await asyncio.sleep(0.25)
                    idle += 0.25
                    if idle >= 15:  # notices a closed client and keeps proxies from timing out
                        idle = 0.0
                        yield ": keep-alive\n\n"
                    continue
                idle = 0.0
                yield f"event: lanes\ndata: {json.dumps(snap, default=str)}\n\n"
        finally:
            live.unsubscribe(workspace, q)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@router.get("/agent/{workspace}/lanes")
def agent_lanes(workspace: str) -> dict:
    return live.snapshot(workspace)
