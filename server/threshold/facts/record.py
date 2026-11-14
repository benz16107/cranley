"""Record what tools compute and what the agent does, into the fact and op_log hypertables.

`record_result` turns a ToolResult into fact rows: each numeric metric, each check with a measured value (the record
value and path ride along when the check compares with a record), and each room value of a lens overlay. `record_op`
appends a workspace log entry. Both queue the rows and return at once; one background thread writes them. With no
database configured they do nothing, and a write that fails is dropped with a log line, never raised into a run.
"""
from __future__ import annotations

import json
import logging
import queue
import re
import threading
from datetime import UTC, datetime

from . import db
from .load import FACT_COLS, copy

log = logging.getLogger(__name__)
_q: queue.Queue = queue.Queue(maxsize=10_000)
_thread: threading.Thread | None = None
_lock = threading.Lock()
OP_COLS = ["at", "workspace", "seq", "op", "by_whom", "tool", "undo", "cause", "body"]


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")[:60]


def _now() -> str:
    return datetime.now(UTC).isoformat()


def fact_rows(tool: str, result: dict, run: str | None = None, at: str | None = None) -> list[list]:
    """Fact rows for one ToolResult (as a dict). Only results about one scan become facts: a search over many scans
    states no fact about any one of them."""
    sid = (result.get("scope") or {}).get("sid")
    if not sid:
        return []
    at = at or _now()
    out = []
    src = lambda s: ((s or {}).get("layer"), (s or {}).get("method"), (s or {}).get("confidence"))  # noqa: E731
    finding_room = {f["id"]: (f.get("anchor") or {}).get("room") for f in result.get("findings") or []}
    finding_src = {f["id"]: f.get("source") for f in result.get("findings") or []}
    for m in result.get("metrics") or []:
        if isinstance(m.get("value"), (int, float)):
            out.append([at, sid, None, f"{tool}.{m['id']}", float(m["value"]), m.get("label"), m.get("unit") or None,
                        *src(m.get("source")), tool, run, json.dumps({"note": (m.get("source") or {}).get("note")}),
                        None, None])
    for c in result.get("checks") or []:
        if not isinstance(c.get("measured"), (int, float)):
            continue
        fid = next(iter(c.get("findings") or []), None)
        out.append([at, sid, finding_room.get(fid), f"{tool}.check.{c['id']}", float(c["measured"]), c.get("status"),
                    c.get("unit") or None, *src(finding_src.get(fid)), tool, run,
                    json.dumps({"rule": c.get("rule"), "finding": fid}),
                    None if c.get("threshold") is None else str(c["threshold"]), c.get("standard")])
    for o in result.get("overlays") or []:
        if o.get("kind") != "lens":
            continue
        leg = o.get("legend") or {}
        name = f"{tool}.lens.{_slug(leg.get('title') or 'value')}"
        for room, v in (o.get("values") or {}).items():
            if isinstance(v, (int, float)):
                out.append([at, sid, room, name, float(v), leg.get("title"), leg.get("unit") or None, None, None, None,
                            tool, run, None, None, None])
    return out


def _worker() -> None:
    while True:
        batch = [_q.get()]
        while len(batch) < 500:
            try:
                batch.append(_q.get_nowait())
            except queue.Empty:
                break
        facts = [r for kind, rows in batch if kind == "fact" for r in rows]
        ops = [r for kind, rows in batch if kind == "op" for r in rows]
        try:
            with db.transaction() as c:
                copy(c, "fact", FACT_COLS, facts)
                copy(c, "op_log", OP_COLS, ops)
        except Exception as e:  # noqa: BLE001 - recording is best effort; the tool run already succeeded
            log.warning("facts: dropped %d facts and %d ops: %s", len(facts), len(ops), str(e)[:200])
        finally:
            for _ in batch:
                _q.task_done()


def _put(kind: str, rows: list[list]) -> None:
    global _thread
    if not rows or not db.available():
        return
    with _lock:
        if _thread is None:
            _thread = threading.Thread(target=_worker, name="facts-writer", daemon=True)
            _thread.start()
    try:
        _q.put_nowait((kind, rows))
    except queue.Full:
        log.warning("facts: queue full, dropped %d rows", len(rows))


def record_result(tool: str, result, run: str | None = None) -> None:
    try:
        d = result.model_dump(mode="json") if hasattr(result, "model_dump") else result
        _put("fact", fact_rows(tool, d, run))
    except Exception as e:  # noqa: BLE001
        log.warning("facts: could not record %s: %s", tool, str(e)[:200])


def op_row(workspace: str, entry) -> list:
    """One op_log row for a workspace LogEntry."""
    e = entry.model_dump(mode="json", by_alias=True) if hasattr(entry, "model_dump") else entry
    body = e.get("op") or {}
    tool = body.get("tool") or (body.get("record") or {}).get("tool") or (body.get("result") or {}).get("tool")
    return [datetime.fromtimestamp(e["at"], UTC).isoformat(), workspace, e["seq"],
            body.get("op") or ("undo" if e.get("undo") is not None else None), body.get("by"), tool, e.get("undo"),
            e.get("cause"), json.dumps(body)]


def record_op(workspace: str, entry) -> None:
    try:
        _put("op", [op_row(workspace, entry)])
    except Exception as e:  # noqa: BLE001
        log.warning("facts: could not record op: %s", str(e)[:200])


def flush(timeout: float = 10.0) -> None:
    """Wait until queued rows are written (tests and batch jobs)."""
    if _thread is not None:
        _q.join()
