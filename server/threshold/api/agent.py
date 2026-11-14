"""Agent routes (Contract 2): tools, agent turns as server-sent events of workspace ops, and workspaces."""
from __future__ import annotations

import concurrent.futures
import json
import logging
import queue
import threading
import time
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..agent import prefs
from ..agent.budget import Budget
from ..agent.catalog import catalog
from ..agent.investigator import Investigation, attach, turn
from ..agent.workspace import Rejected, RunFinish, Session
from ..tools import Place, ToolError, run_tool

router = APIRouter(prefix="/api")
_sessions: dict[str, Session] = {}
_lock = threading.Lock()
_background = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="tool-run")  # runs that outlive their request
# workspace id -> run id -> its background job. A run reads "done" before its findings, panel and camera are written
# (each op is stored as it is emitted), so the view names the runs still writing in `busy`.
_jobs: dict[str, dict[str, concurrent.futures.Future]] = {}
ORPHAN_S = 3600  # no tool runs this long (a smoke simulation takes minutes), so a run still open is one a restart cut off


def session(id: str) -> Session:
    with _lock:
        if id not in _sessions:
            try:
                _sessions[id] = attach(Session.load(id))
            except LookupError as e:
                raise HTTPException(404, str(e)) from None
        s = _sessions[id]
    s.sync()  # another server process may have appended (MongoDB store); a no-op for files
    for r in [r for r in s.doc.runs if r.status == "running" and (r.started or 0) < time.time() - ORPHAN_S]:
        try:
            s.submit(RunFinish(id=r.id, status="error", error="The server stopped while this ran. Run it again."), by="system")
        except Rejected:
            pass
    return s


def view(s: Session, log: bool = False) -> dict:
    out = {"doc": s.doc.model_dump(mode="json", by_alias=True), "learned": prefs.learned(s.doc),
           "seq": len(s.log), "busy": [rid for rid, j in _jobs.get(s.doc.id, {}).items() if not j.done()]}
    if log:
        out["log"] = [e.model_dump(mode="json", by_alias=True) for e in s.log]
    return out


@router.get("/tools")
def tools() -> list[dict]:
    return [m.model_dump(mode="json") for m in catalog().values()]


@router.post("/tools/{tool_id}/run")
def tool_run(tool_id: str, inputs: dict[str, Any] = Body(default={}), workspace: str | None = None,
             wait: float | None = Query(None, ge=0, le=600, description="seconds to wait before answering")) -> dict:
    """Run a tool. With ?workspace=<id> the run goes into that workspace (inputs left out come from its
    preferences) and the reply is the run summary; without it, the bare ToolResult.

    With ?workspace and ?wait=<seconds> a slow tool (a smoke simulation takes minutes) does not hold the request
    open: when the run has not finished in that time the reply is `{"status": "running", "run": <id>}` and the run
    carries on in the background. Its `run.start`, `run.progress` and `run.finish` ops, findings, overlays and panel
    reach the workspace exactly as they do for a fast tool, so a client follows it by reading the workspace until
    the run's id leaves the view's `busy` list (the run reads "done" a few seconds before its panel is written)."""
    if tool_id not in catalog():
        raise HTTPException(404, f"Unknown tool {tool_id}")
    if workspace:
        s = session(workspace)
        if wait is None:
            return Investigation(s).run(tool_id, inputs)
        before = {r.id for r in s.doc.runs}
        job = _background.submit(Investigation(s).run, tool_id, inputs)
        try:
            return job.result(timeout=wait)
        except concurrent.futures.TimeoutError:
            started = next((r.id for r in reversed(s.doc.runs) if r.id not in before and r.tool == tool_id), None)
            if started:
                _jobs[workspace] = {k: j for k, j in _jobs.get(workspace, {}).items() if not j.done()} | {started: job}
            return {"status": "running", "run": started, "tool": tool_id}
    try:
        return run_tool(tool_id, inputs).model_dump(mode="json")
    except ToolError as e:
        raise HTTPException(400, str(e)) from None


class BudgetIn(BaseModel):
    model_calls: int = Field(40, ge=1, le=120)
    tool_runs: int = Field(40, ge=1, le=200)
    parallel: int = Field(4, ge=1, le=8)


class TurnIn(BaseModel):
    workspace: str | None = None
    text: str | None = None
    sids: list[str] | None = None
    places: list[Place] | None = Field(None, description="Properties, addresses or points to look at without a scan")
    profile: str = "default"
    budget: BudgetIn | None = None


QUIET = ("pymongo", "bson", "pg8000", "httpx", "httpcore", "anthropic", "langchain_anthropic", "openai")


def public_error(e: Exception) -> str:
    """What a client may read about a failure. Database and HTTP client errors name hosts (the Atlas cluster's address,
    an upstream URL), so those stay in the server's log."""
    if type(e).__module__.split(".")[0] in QUIET:
        return f"{type(e).__name__}: a database or upstream call failed; the server log has the details"
    return f"{type(e).__name__}: {e}"


def _sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


@router.post("/agent/turn")
def agent_turn(body: TurnIn) -> StreamingResponse:
    """Events: `workspace` {id} first, then one `op` per log entry as it applies (tool steps arrive as `run.progress`
    while a tool runs), then `done` (with the turn's `budget`: limits, what it used, what stopped it) or `error`."""
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
            b = Budget(**body.budget.model_dump()) if body.budget else None
            q.put(("done", turn(s, body.text, body.sids, places=[p.model_dump(exclude_none=True) for p in body.places]
                                if body.places else None, budget=b)))
        except Exception as e:  # the stream must end with a reason, whatever failed
            logging.getLogger("threshold.agent").exception("agent turn on %s failed", s.base.id)
            q.put(("error", {"message": public_error(e)}))

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
    entries, ops = [], ops if isinstance(ops, list) else [ops]
    for i, op in enumerate(ops):
        try:
            entries += s.submit(op, by="user")
        except Rejected as e:  # the ops before it are stored: say so, or a retry applies them twice
            raise HTTPException(422, f"{e} (op {i + 1} of {len(ops)}; the {i} before it were applied)" if i else str(e)) from None
    return {"applied": [e.model_dump(mode="json", by_alias=True) for e in entries], **view(s)}


@router.post("/workspace/{id}/undo")
def workspace_undo(id: str, seq: int | None = Body(default=None, embed=True)) -> dict:
    s = session(id)
    try:
        e = s.undo(seq)
    except LookupError as err:
        raise HTTPException(409, str(err)) from None
    return {"undone": e.undo, **view(s)}
