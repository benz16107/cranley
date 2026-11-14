"""What the agents are doing right now, per workspace: the main agent and one lane per subagent task, each with the
tool it is running. Middleware on every agent feeds it; `/api/agent/{id}/live` streams it to the agent panel.

Kept in memory only: it describes the turn in progress, while the workspace log keeps everything that lasts (plan,
runs, findings, approvals)."""
from __future__ import annotations

import contextvars
import queue
import threading
import time
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langgraph.errors import GraphInterrupt

_lane: contextvars.ContextVar[str | None] = contextvars.ContextVar("lane", default=None)
_lock = threading.Lock()
_state: dict[str, dict] = {}  # workspace -> {"turn", "status", "lanes": {id: lane}}
_subs: dict[str, list[queue.Queue]] = {}
HIDDEN = {"write_todos", "write_file", "read_file", "edit_file", "ls", "glob", "grep"}  # bookkeeping, not work


def snapshot(ws: str) -> dict:
    with _lock:
        s = _state.get(ws) or {"turn": None, "status": "idle", "lanes": {}}
        return {"turn": s["turn"], "status": s["status"], "lanes": sorted(s["lanes"].values(), key=lambda x: x["started"])}


def _publish(ws: str) -> None:
    snap = snapshot(ws)
    for q in list(_subs.get(ws, [])):
        q.put(snap)


def subscribe(ws: str) -> queue.Queue:
    q: queue.Queue = queue.Queue()
    with _lock:
        _subs.setdefault(ws, []).append(q)
    q.put(snapshot(ws))
    return q


def unsubscribe(ws: str, q: queue.Queue) -> None:
    with _lock:
        if q in _subs.get(ws, []):
            _subs[ws].remove(q)


def begin(ws: str, turn: str, resumed: bool = False) -> None:
    with _lock:
        s = _state.get(ws)
        if not (resumed and s and s["turn"] == turn):
            s = _state[ws] = {"turn": turn, "status": "running", "lanes": {}}
        s["status"] = "running"
        for lane in s["lanes"].values():
            if lane["status"] == "waiting":
                lane["status"] = "running"
    _publish(ws)


def end(ws: str, status: str) -> None:
    """status: done, waiting (paused for an approval) or stopped."""
    with _lock:
        s = _state.get(ws)
        if not s:
            return
        s["status"] = status
        for lane in s["lanes"].values():
            if lane["status"] == "running":
                lane["status"] = "waiting" if status == "waiting" else "done"
                lane["tool"] = None
                if status != "waiting":
                    lane["finished"] = time.time()
    _publish(ws)


def _update(ws: str, lane_id: str, **kw: Any) -> None:
    with _lock:
        s = _state.get(ws)
        if not s:
            return
        lane = s["lanes"].setdefault(lane_id, {"id": lane_id, "agent": "investigator", "task": "", "status": "running",
                                               "tool": None, "tools": [], "started": time.time(), "finished": None})
        tool = kw.pop("tool", "keep")
        if tool != "keep":
            lane["tool"] = tool
            if tool and tool not in lane["tools"]:
                lane["tools"].append(tool)
        lane.update(kw)
    _publish(ws)


class Watch(AgentMiddleware):
    """Reports each tool call of one agent to the live view. On the main agent a `task` call opens a lane for the
    subagent it starts; on a subagent each call names the tool its lane is running."""

    def __init__(self, ws: str, main: bool):
        super().__init__()
        self.ws, self.main = ws, main

    @property
    def name(self) -> str:  # one instance per agent; names must be unique within an agent's stack
        return "LiveWatch"

    def wrap_tool_call(self, request, handler):
        call = request.tool_call
        if self.main and call["name"] == "task":
            lane = call.get("id") or call["args"].get("description", "")[:40]
            args = call["args"]
            _update(self.ws, lane, agent=args.get("subagent_type", "subagent"), task=args.get("description", "")[:200],
                    status="running", finished=None)
            token = _lane.set(lane)
            try:
                out = handler(request)
            except GraphInterrupt:  # the subagent paused for an approval; it resumes in a later request
                _update(self.ws, lane, status="waiting", tool=None)
                raise
            except Exception:
                _update(self.ws, lane, status="failed", tool=None, finished=time.time())
                raise
            finally:
                _lane.reset(token)
            _update(self.ws, lane, status="done", tool=None, finished=time.time())
            return out
        lane = _lane.get() if not self.main else "main"
        hidden = call["name"] in HIDDEN
        if lane and not hidden:
            _update(self.ws, lane, tool=call["name"])
        try:
            return handler(request)
        finally:
            if lane and not hidden:
                _update(self.ws, lane, tool=None)
