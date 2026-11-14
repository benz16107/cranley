"""What the MCP server and the CLI share: running tools, searching, a building's facts, workspaces and agent turns.

Everything here returns plain JSON-ready dicts, and every text summary is built from result fields, never from
model text. Lists are capped (rule 1: results are for the person running this locally, not a bulk export).
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from typing import Any

from ..tools import ToolContext, ToolError, load, run_tool

MAX_LIST = 25      # rows a search or a list returns at most
MAX_ROOMS = 40     # rooms listed in a plan summary
MAX_FINDINGS = 50


def tools(write: bool = False) -> dict:
    """Registered tools that are built; write tools only when asked for."""
    return {k: t for k, t in load().items()
            if t.manifest.status == "ready" and (write or t.manifest.annotations.read_only)}


def _num(v: Any) -> str:
    if isinstance(v, float):
        return f"{v:.2f}".rstrip("0").rstrip(".")
    return "?" if v is None else str(v)


def summary(r: dict) -> str:
    """A few lines a person can read, from the ToolResult's own fields."""
    v = r["verdict"]
    lines = [f"{r['tool']}: {v['status'].upper()}. {v['text']}"]
    for m in r.get("metrics", [])[:8]:
        val = "not measured" if m["value"] is None else f"{_num(m['value'])} {m['unit']}".rstrip()
        lines.append(f"  {m['label']}: {val}  [{m['source']['confidence']}]")
    checks = r.get("checks", [])
    if checks:
        n = Counter(c["status"] for c in checks)
        lines.append("Checks: " + ", ".join(f"{k} {n[k]}" for k in ("fail", "warn", "pass", "unknown") if n[k]))
        for c in [c for c in checks if c["status"] in ("fail", "warn")][:6]:
            lines.append(f"  {c['status']}: {c['rule']} (measured {_num(c['measured'])}, limit {_num(c['threshold'])} {c['unit']})")
    if r.get("findings"):
        lines.append(f"Findings ({len(r['findings'])}):")
        lines += [f"  {f['status']}: {f['title']}" for f in r["findings"][:5]]
    if r.get("assumptions"):
        lines.append("Assumptions: " + "; ".join(f"{a['label']} {_num(a['value'])} {a['unit'] or ''}".strip()
                                                 for a in r["assumptions"][:6]))
    return "\n".join(lines)


def run(tool_id: str, inputs: dict, on_step: Callable[[str], None] | None = None) -> dict:
    """Run one registered tool; the ToolResult as JSON. Raises ToolError with a message safe to show."""
    return run_tool(tool_id, inputs, ToolContext(on_step=on_step)).model_dump(mode="json")


def search(query: str | None = None, address: str | None = None, city: str | None = None, kind: str | None = None,
           where: list[str] | None = None, limit: int = 10) -> dict:
    """Scans by words, address, city and kind; with `where` ("bath_route_door>=0.81"), by what is measured inside."""
    limit = max(1, min(limit, MAX_LIST))
    if where:
        from ..tools.measure_search import table
        out = table.search([table.parse(w) for w in where], city=city, kind=kind, limit=limit)
        keep = ("pool", "answerable", "matches", "engine")  # not the SQL or its parameters
        return {k: out[k] for k in keep if k in out} | {"scans": out.get("rows", [])[:limit]}
    from ..sources import index
    if kind and kind not in index.KINDS:
        raise ToolError("kind is one of " + ", ".join(index.KINDS))
    total, rows = index.search(query, address, city, None, kind, limit=limit)
    return {"total": total, "scans": rows}


def plan_summary(plan: dict) -> dict:
    """The ScanPlan without geometry: counts, quality, floors, rooms by label and the narrowest doorway."""
    rooms, openings = plan.get("rooms", []), plan.get("openings", [])
    doors = [o["width"] for o in openings if o.get("type") == "doorway" and o.get("width")]
    areas = [r["area"] for r in rooms if r.get("area")]
    q = plan.get("quality") or {}
    return {
        "sid": plan.get("sid"), "name": plan.get("name"), "address": plan.get("address"), "city": plan.get("city"),
        "segment": plan.get("segment"), "has": plan.get("has"),
        "quality": {k: q.get(k) for k in ("walls", "polygons", "openings", "labels", "georef", "notes") if k in q},
        "floors": [{k: f.get(k) for k in ("id", "label", "elevation")} for f in plan.get("floors", [])],
        "rooms": {"count": len(rooms), "total_area_m2": round(sum(areas), 1) if areas else None,
                  "by_label": dict(Counter(r.get("label") or "unlabelled" for r in rooms).most_common()),
                  "list": [{"id": r["id"], "label": r.get("label"), "floor": r.get("floor"),
                            "area_m2": round(r["area"], 1) if r.get("area") else None} for r in rooms[:MAX_ROOMS]]},
        "openings": {"doorways": len(doors), "windows": sum(o.get("type") == "window" for o in openings),
                     "narrowest_doorway_m": round(min(doors), 3) if doors else None},
        "panos": len(plan.get("panos", [])),
    }


def building(sid: str) -> dict:
    """One scan's index row, its plan summary and the record's checkable claims (when the CoStar kit is set up)."""
    from ..sources import costar, index
    from ..tools.registry import default_plan
    row = index.rows().get(sid)
    if not row:
        raise ToolError(f"No scan {sid}")
    out = {"scan": index.public(row)}
    try:
        out["plan"] = plan_summary(default_plan(sid))
    except Exception as e:  # a scan the loader cannot reach still has its index row
        out["plan"] = {"error": f"{type(e).__name__}: plan unavailable"}
    try:
        claims = costar.record(sid, False).get("claims") or {}
        out["record_claims"] = dict(list(claims.items())[:20])
    except Exception:
        out["record_claims"] = None
    return out


# ---- workspaces and agent turns (these reuse the API's session cache, so the web app sees the same state) ----

def workspace_create(profile: str = "default") -> dict:
    from ..api import agent as api
    return compact(api.workspace_create(profile))


def workspace(id: str) -> dict:
    from ..api import agent as api
    return compact(api.view(api.session(id)))


def compact(view: dict) -> dict:
    """The workspace without panels, overlays and layers: brief, runs with verdicts, findings count, open questions."""
    d = view["doc"]
    runs = [{"id": r["id"], "tool": r["tool"], "sid": r.get("sid"), "status": r["status"],
             "verdict": (r.get("result") or {}).get("verdict"), "error": r.get("error")} for r in d["runs"]][-MAX_LIST:]
    return {"id": d["id"], "profile": d["profile"],
            "brief": {k: d["brief"].get(k) for k in ("text", "summary", "persona", "scope", "limits")},
            "tools": [t["id"] for t in d["tools"] if t["enabled"]],
            "runs": runs, "runs_total": len(d["runs"]), "busy": view.get("busy", []),
            "findings": len([f for f in d["findings"] if not f.get("superseded_by")]),
            "questions": [{"id": q["id"], "text": q["text"], "key": q["key"]} for q in d["questions"] if not q["answered"]],
            "shortlist": d["shortlist"], "prefs": {k: p["value"] for k, p in d["prefs"].items()}}


def findings(id: str, status: str | None = None, tool: str | None = None, limit: int = MAX_FINDINGS) -> dict:
    from ..api import agent as api
    fs = [f.model_dump(mode="json") for f in api.session(id).doc.findings if not f.superseded_by
          and (not status or f.status == status) and (not tool or f.tool == tool)]
    keep = ("id", "title", "status", "detail", "tool", "run", "anchor", "source", "feedback")
    return {"total": len(fs), "findings": [{k: f.get(k) for k in keep} for f in fs[:max(1, min(limit, MAX_FINDINGS))]]}


def apply_ops(id: str, ops: list[dict]) -> dict:
    from ..api import agent as api
    out = api.workspace_ops(id, ops)
    return {"applied": len(out["applied"]), "workspace": compact(out)}


def describe(entry: dict) -> str | None:
    """One progress line for a workspace op, or None for ops not worth a line."""
    op = entry.get("op") or {}
    kind = op.get("op", "")
    if kind == "run.start":
        r = op.get("record") or {}
        return f"running {r.get('tool', '?')}" + (f" on {r['sid']}" if r.get("sid") else "")
    if kind == "run.progress":
        return f"  {op.get('step', '')}"
    if kind == "run.finish":
        v = ((op.get("result") or {}).get("verdict") or {})
        return f"finished {op.get('id', '')}: {v.get('status', op.get('status', ''))}. {v.get('text', '')}".rstrip(". ")
    if kind == "finding.add":
        f = op.get("finding") or {}
        return f"finding ({f.get('status')}): {f.get('title')}"
    if kind == "question.ask":
        return f"question: {(op.get('question') or {}).get('text')}"
    if kind == "tool.enable":
        return f"enabled {op.get('tool')}"
    return None


def ask(brief: str, workspace_id: str | None = None, scans: list[str] | None = None, profile: str = "default",
        on_line: Callable[[str], None] | None = None) -> dict:
    """One agent turn on a brief. Progress lines go to `on_line` as ops apply; returns the turn's status, the
    workspace and its runs. The agent's own `note` is model text; verdicts and findings come from tool results."""
    from ..agent.investigator import attach, turn
    from ..agent.workspace import Session
    from ..api import agent as api
    if workspace_id:
        s = api.session(workspace_id)
    else:
        s = attach(Session.create(profile))
        with api._lock:
            api._sessions[s.base.id] = s
    seen = len(s.doc.runs)

    def listen(e):
        line = describe(e.model_dump(mode="json", by_alias=True))
        if line and on_line:
            on_line(line)
    s.listeners.append(listen)
    try:
        out = turn(s, brief, scans or None)
    finally:
        s.listeners.remove(listen)
    ws = compact(api.view(s))
    new = [r for r in s.doc.runs[seen:]]
    return {"workspace": s.base.id, "status": out.get("status"), "note": out.get("summary") or out.get("message"),
            "questions": out.get("questions"), "runs": [{"id": r.id, "tool": r.tool, "sid": r.sid, "status": r.status,
                                                        "verdict": r.result.verdict.model_dump() if r.result else None}
                                                       for r in new][:MAX_LIST],
            "findings": ws["findings"], "open_questions": ws["questions"]}


def ask_text(out: dict) -> str:
    lines = [f"Workspace {out['workspace']}: {out['status']}"]
    for r in out["runs"]:
        v = r["verdict"] or {}
        lines.append(f"  {r['tool']}" + (f" on {r['sid']}" if r["sid"] else "") + f": {v.get('status', r['status'])}. {v.get('text', '')}".rstrip(". "))
    lines += [f"  question {q['id']}: {q['text']}" for q in out["open_questions"]]
    if out.get("note"):
        lines.append(f"Agent's note (model text, not a measurement): {out['note']}")
    return "\n".join(lines)
