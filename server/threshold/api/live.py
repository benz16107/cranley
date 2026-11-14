"""Live workspaces and read-only share links.

GET    /api/workspace/{id}/live?after=<seq>   server-sent events in the agent turn's vocabulary: `workspace` {id}, then
                                              one `op` per log entry after `after`, as any writer appends it, from any
                                              server process or device. With MongoDB this is a change stream on the op
                                              log; with files, this process's own writes.
POST   /api/workspace/{id}/share {days}       a read-only link (MongoDB; it expires by a TTL index)
GET    /api/shared/{token}                    the workspace view, read-only
GET    /api/shared/{token}/live?after=<seq>   its live events
GET    /api/shared/{token}/shortlist?near=lon,lat&km=
DELETE /api/workspace/{id}/share/{token}    revoke a link (the owner's route, not the link's)

A watcher fetches the view (its `seq`), then opens live with after=seq. Each op event carries its seq as the SSE `id`,
so a browser's EventSource that reconnects (a dropped network, a change stream that ended) sends Last-Event-ID and
resumes after the last op it got, instead of replaying everything since the first `after`.
"""
from __future__ import annotations

import asyncio
import json
import logging
import queue
from collections.abc import Iterator

from fastapi import APIRouter, Body, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from ..agent.workspace import Session
from .agent import _sse, session, view
from .history import mongo_store, point

router = APIRouter(prefix="/api")
END = object()
SHARED = "shared"


def entries(s: Session, after: int) -> Iterator[dict | None]:
    """Log entries after `after`, then new ones as they land; None every second or so with nothing new."""
    if hasattr(s.store, "watch"):
        yield from s.store.watch(s.base.id, after)
        return
    q: queue.Queue = queue.Queue()
    s.listeners.append(q.put)  # before reading the log, so nothing falls between the two
    try:
        last = after
        for e in list(s.log)[after:]:
            last = e.seq
            yield e.model_dump(mode="json", by_alias=True)
        while True:
            try:
                e = q.get(timeout=1)
            except queue.Empty:
                yield None
                continue
            if e.seq > last:
                last = e.seq
                yield e.model_dump(mode="json", by_alias=True)
    finally:
        s.listeners.remove(q.put)


def masked(data, id: str | None):
    """`data` with the workspace id replaced: a link viewer who learned the id could write through the owner's
    routes, so read-only means never showing it."""
    return json.loads(json.dumps(data, default=str).replace(id, SHARED)) if id else data


def stream(request: Request, s: Session, after: int, hide: bool = False) -> StreamingResponse:
    hidden = s.base.id if hide else None
    resume = request.headers.get("last-event-id", "")
    after = max(after, int(resume)) if resume.isdigit() else after

    async def events():
        it = entries(s, after)
        try:
            yield _sse("workspace", masked({"id": s.base.id, "after": after}, hidden))
            while not await request.is_disconnected():
                try:
                    e = await asyncio.to_thread(next, it, END)
                except Exception:  # noqa: BLE001 - a change stream that failed: end, and the client resumes by its id
                    logging.getLogger("threshold.live").exception("live stream for %s failed", s.base.id)
                    return
                if e is END:
                    return
                yield ": keep-alive\n\n" if e is None else f"id: {e['seq']}\n" + _sse("op", masked(e, hidden))
        finally:
            try:
                it.close()  # closes the change stream
            except ValueError:
                pass  # still inside next() in its thread; it ends within a second and is collected

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/workspace/{id}/live")
def live(id: str, request: Request, after: int = Query(0, ge=0)) -> StreamingResponse:
    return stream(request, session(id), after)


def link(token: str) -> dict:
    found = mongo_store().shared(token)
    if not found:
        raise HTTPException(404, "This link has expired or was revoked")
    return found


@router.post("/workspace/{id}/share")
def share(id: str, days: float = Body(7, embed=True, gt=0, le=30)) -> dict:
    session(id)  # 404 for an unknown workspace
    return mongo_store().share(id, days)


@router.get("/shared/{token}")
def shared(token: str) -> dict:
    ln = link(token)
    s = session(ln["workspace"])
    s.sync()  # another server process may have written since this one loaded it
    return masked({**view(s), "share": {k: v for k, v in ln.items() if k != "workspace"}, "readonly": True}, s.base.id)


@router.get("/shared/{token}/live")
def shared_live(token: str, request: Request, after: int = Query(0, ge=0)) -> StreamingResponse:
    return stream(request, session(link(token)["workspace"]), after, hide=True)


@router.get("/shared/{token}/shortlist")
def shared_shortlist(token: str, near: str | None = None, km: float | None = Query(None, gt=0, le=500)) -> list[dict]:
    ws = link(token)["workspace"]
    return masked(mongo_store().shortlist_near(*point(near), km=km, workspace=ws), ws)


@router.delete("/workspace/{id}/share/{token}")
def unshare(id: str, token: str) -> dict:
    if link(token)["workspace"] != id:
        raise HTTPException(404, "No such link on this workspace")
    return {"revoked": mongo_store().unshare(token)}
