"""Agent routes (Contract 2): tools, agent turns as server-sent events of workspace ops, and workspaces."""
from __future__ import annotations

import json
import queue
import threading
from typing import Any

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..agent import prefs
from ..agent.catalog import catalog
from ..agent.investigator import Investigation, attach, turn
from ..agent.workspace import Rejected, Session
from ..tools import ToolError, run_tool

router = APIRouter(prefix="/api")
_sessions: dict[str, Session] = {}
_lock = threading.Lock()


def session(id: str) -> Session:
    with _lock:
        if id not in _sessions:
            try:
                _sessions[id] = attach(Session.load(id))
            except LookupError as e:
                raise HTTPException(404, str(e)) from None
        return _sessions[id]


def view(s: Session, log: bool = False) -> dict:
    out = {"doc": s.doc.model_dump(mode="json", by_alias=True), "learned": prefs.learned(s.doc),
           "seq": len(s.log)}
    if log:
        out["log"] = [e.model_dump(mode="json", by_alias=True) for e in s.log]
    return out


@router.get("/tools")
def tools() -> list[dict]:
    return [m.model_dump(mode="json") for m in catalog().values()]


@router.post("/tools/{tool_id}/run")
def tool_run(tool_id: str, inputs: dict[str, Any] = Body(default={}), workspace: str | None = None) -> dict:
    """Run a tool. With ?workspace=<id> the run goes into that workspace (inputs left out come from its
    preferences) and the reply is the run summary; without it, the bare ToolResult."""
    if tool_id not in catalog():
        raise HTTPException(404, f"Unknown tool {tool_id}")
    if workspace:
        return Investigation(session(workspace)).run(tool_id, inputs)
    try:
        return run_tool(tool_id, inputs).model_dump(mode="json")
    except ToolError as e:
        raise HTTPException(400, str(e)) from None


class TurnIn(BaseModel):
    workspace: str | None = None
    text: str | None = None
    sids: list[str] | None = None
    profile: str = "default"


def _sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


@router.post("/agent/turn")
def agent_turn(body: TurnIn) -> StreamingResponse:
    """Events: `workspace` {id} first, then one `op` per log entry as it applies, then `done` or `error`."""
    if body.workspace:
        s = session(body.workspace)
    else:
        s = attach(Session.create(body.profile))
        with _lock:
            _sessions[s.base.id] = s
    q: queue.Queue = queue.Queue()
    listener = lambda e: q.put(("op", e.model_dump(mode="json", by_alias=True)))

    def work():
        try:
            q.put(("done", turn(s, body.text, body.sids)))
        except Exception as e:  # the stream must end with a reason, whatever failed
            q.put(("error", {"message": f"{type(e).__name__}: {e}"}))

    def stream():
        s.listeners.append(listener)
        threading.Thread(target=work, daemon=True).start()
        try:
            yield _sse("workspace", {"id": s.base.id})
            while True:
                kind, data = q.get()
                yield _sse(kind, data)
                if kind in ("done", "error"):
                    return
        finally:
            s.listeners.remove(listener)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@router.post("/workspace")
def workspace_create(profile: str = "default") -> dict:
    s = attach(Session.create(profile))
    with _lock:
        _sessions[s.base.id] = s
    return view(s)


@router.get("/workspace/{id}")
def workspace_get(id: str, log: bool = False) -> dict:
    return view(session(id), log)


@router.post("/workspace/{id}/ops")
def workspace_ops(id: str, ops: dict | list[dict] = Body(...)) -> dict:
    """User ops, one or a list, in the same vocabulary as the agent's. `by` is forced to "user"."""
    s = session(id)
    entries = []
    try:
        for op in ops if isinstance(ops, list) else [ops]:
            entries += s.submit(op, by="user")
    except Rejected as e:
        raise HTTPException(422, str(e)) from None
    return {"applied": [e.model_dump(mode="json", by_alias=True) for e in entries], **view(s)}


@router.post("/workspace/{id}/undo")
def workspace_undo(id: str, seq: int | None = Body(default=None, embed=True)) -> dict:
    s = session(id)
    try:
        e = s.undo(seq)
    except LookupError as err:
        raise HTTPException(409, str(err)) from None
    return {"undone": e.undo, **view(s)}
