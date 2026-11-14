"""Investigator: the agent loop on LangChain `deepagents`.

The main agent plans with `write_todos` (streamed as `plan.set`), hands each building to a `building` subagent,
then points the camera at what matters and shortlists. Every enabled tool becomes an agent tool whose result
goes straight into the workspace (`run.start`, `run.finish`, `finding.add`, `overlay.upsert`, `panel.upsert`,
`camera.focus`); the model sees only a compact summary and ids. Subagents keep case notes in the deepagents
virtual filesystem (/notes/<scan>.md), saved next to the workspace as <id>.casefile.json.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from pydantic import Field, create_model

from ..tools import ToolContext, ToolError, run_tool
from ..tools.registry import REGISTRY, default_plan, load
from . import prefs
from .catalog import catalog, personas, resolve
from .workspace import (
    ActionBar,
    AssumptionChips,
    CameraFocus,
    CheckList,
    Control,
    Controls,
    EvidenceStrip,
    FindingAdd,
    FloorPlanMini,
    MetricRow,
    MiniChart,
    Note,
    OverlayUpsert,
    Panel,
    PanelUpsert,
    PlanSet,
    PlanStep,
    RankedColumn,
    RankedTable,
    Rejected,
    Run,
    RunFinish,
    RunStart,
    Session,
    ShortlistAdd,
    StepLog,
    VerdictHeader,
    WsFinding,
    WsOverlay,
    new_id,
)

RANK = {"fail": 0, "warn": 1, "unknown": 2, "pass": 3}


def attach(session: Session, plans: Callable[[str], dict] = default_plan) -> Session:
    """Give a session what the validator needs: a plan loader and the tool ids that exist."""
    session.plans = plans
    session.tools = set(catalog())
    return session


def panel_for(m, run: Run, overlay_ids: list[str]) -> Panel:
    """The tool's panel, built from the blocks its manifest declares, bound to the run. No model involved."""
    r = run.result
    head = [x.id for x in r.metrics if "." not in x.id][:4]
    series = [x.id for x in r.metrics if "." in x.id]  # dotted ids (area.Bedroom) are one series
    controls = [Control(input=k, pref=s["x-pref"], label=s.get("description") or s.get("title", k), kind="slider",
                        min=s.get("minimum", s.get("exclusiveMinimum")), max=s.get("maximum"), step=0.01,
                        unit=s.get("x-unit"))
                for k, s in m.inputs.get("properties", {}).items() if s.get("x-pref") and s.get("type") == "number"]
    make = {"VerdictHeader": lambda: VerdictHeader(run=run.id),
            "MetricRow": lambda: MetricRow(run=run.id, metrics=head) if head else None,
            "CheckList": lambda: CheckList(run=run.id) if r.checks else None,
            "EvidenceStrip": lambda: EvidenceStrip(findings=[f.id for f in r.findings]) if r.findings else None,
            "MiniChart": lambda: MiniChart(run=run.id, title=m.title, metrics=series) if series else None,
            "FloorPlanMini": lambda: FloorPlanMini(sid=run.sid, overlays=overlay_ids) if run.sid else None,
            "Controls": lambda: Controls(tool=m.id, controls=controls) if controls else None,
            "AssumptionChips": lambda: AssumptionChips(run=run.id) if r.assumptions else None,
            "StepLog": lambda: StepLog(run=run.id),
            "ActionBar": lambda: ActionBar(run=run.id) if r.actions else None}
    blocks = [b for b in (make[name]() for name in m.blocks if name in make) if b]
    return Panel(id=f"panel:{m.id}:{run.sid}", title=m.title, blocks=blocks, tool=m.id, run=run.id)


class Investigation:
    """One agent turn over one workspace. Tool calls from the main agent and subagents land here."""

    def __init__(self, session: Session, turn: str | None = None):
        self.s = attach(session, session.plans or default_plan)
        self.turn = turn or new_id("turn")
        self.step: str | None = None  # the plan step in progress
        self.notes: list[str] = []
        self.files: dict[str, Any] = {}

    def emit(self, op) -> bool:
        op.run = op.run or self.turn
        try:
            self.s.submit(op)
            return True
        except Rejected:
            return False

    # ---- running a tool into the workspace ----
    def run(self, tool_id: str, given: dict) -> dict:
        m = catalog().get(tool_id)
        doc = self.s.doc
        if m is None:
            return {"error": f"unknown tool {tool_id}"}
        inputs, used, missing = resolve(m, doc, given)
        rec = Run(id=new_id("run"), tool=tool_id, sid=inputs.get("scan") or given.get("scan"), inputs=inputs,
                  inputs_from=used, plan_step=self.step)
        if rec.sid and rec.sid not in doc.brief.scope.sids:
            return {"error": f"scan {rec.sid} is not in this workspace; use one of {doc.brief.scope.sids}"}
        self.emit(RunStart(record=rec, run=rec.id))
        if m.status == "planned":
            self.emit(RunFinish(id=rec.id, status="skipped", summary=f"{m.title} is planned, not built yet", run=rec.id))
            return {"run": rec.id, "skipped": "planned tool, not built yet"}
        if missing:
            need = ", ".join(n for n, _ in missing)
            self.emit(RunFinish(id=rec.id, status="error", error=f"needs {need}", run=rec.id))
            return {"run": rec.id, "error": f"missing inputs the person has not given: {need}"}
        ctx = ToolContext(plans=prefs.with_labels(self.s.plans, doc))
        try:
            result = run_tool(tool_id, inputs, ctx)
        except ToolError as e:
            self.emit(RunFinish(id=rec.id, status="error", error=str(e), steps=ctx.steps, run=rec.id))
            return {"run": rec.id, "error": str(e)}
        self.emit(RunFinish(id=rec.id, status="done", summary=result.verdict.text, steps=ctx.steps, result=result,
                            run=rec.id))
        hidden = prefs.muted(self.s.doc)
        shown = [f for f in result.findings if f.id not in hidden]
        for f in shown:
            self.emit(FindingAdd(finding=WsFinding(**f.model_dump(), run=rec.id, tool=tool_id), run=rec.id))
        ids = [f"{tool_id}:{rec.sid}:{i}" for i in range(len(result.overlays))]
        for oid, o in zip(ids, result.overlays):
            self.emit(OverlayUpsert(overlay=WsOverlay(id=oid, sid=rec.sid, overlay=o, tool=tool_id, run=rec.id),
                                    run=rec.id))
        for old in self.s.doc.overlays:  # a re-run with fewer overlays hides the leftovers
            if old.tool == tool_id and old.sid == rec.sid and old.id not in ids and old.visible:
                self.emit(OverlayUpsert(overlay=old.model_copy(update={"visible": False, "run": rec.id}), run=rec.id))
        done = next(r for r in self.s.doc.runs if r.id == rec.id)
        self.emit(PanelUpsert(panel=panel_for(m, done, ids), run=rec.id))
        worst = min((f for f in shown if f.anchor), key=lambda f: RANK[f.status], default=None)
        if worst and worst.status != "pass":
            self.emit(CameraFocus(anchor=worst.anchor, reason=worst.title, run=rec.id))
        return {"run": rec.id, "tool": tool_id, "scan": rec.sid, "verdict": result.verdict.status,
                "summary": result.verdict.text,
                "findings": [{"id": f.id, "status": f.status, "title": f.title} for f in
                             sorted(shown, key=lambda f: RANK[f.status])[:8]],
                "more_findings": max(0, len(shown) - 8), "hidden_because_rejected": len(result.findings) - len(shown),
                "inputs_from_preferences": used}

    def compare(self) -> None:
        """When several buildings ran the same tool, one RankedTable compares them."""
        by_tool: dict[str, list[Run]] = {}
        for r in self.s.doc.runs:
            if r.status == "done" and r.result and r.sid:
                by_tool.setdefault(r.tool, []).append(r)
        for tool_id, runs in by_tool.items():
            latest = list({r.sid: r for r in runs}.values())
            if len(latest) < 2:
                continue
            cols = [RankedColumn(metric=x.id, label=x.label, better="lower" if x.id in ("too_narrow",) else "higher")
                    for x in latest[0].result.metrics if "." not in x.id][:4]
            self.emit(PanelUpsert(panel=Panel(id=f"compare:{tool_id}", title=f"{catalog()[tool_id].title}: compare",
                                              tool=tool_id, blocks=[RankedTable(title="Buildings", columns=cols,
                                                                                rows=[r.id for r in latest])])))

    # ---- small agent actions ----
    def focus(self, finding_id: str, reason: str = "") -> str:
        f = next((f for f in self.s.doc.findings if f.id == finding_id), None)
        if not f or not f.anchor:
            return f"no anchored finding {finding_id}"
        return "ok" if self.emit(CameraFocus(anchor=f.anchor, reason=reason or f.title)) else "rejected"

    def shortlist(self, scan: str, note: str = "") -> str:
        return "ok" if self.emit(ShortlistAdd(sid=scan, note=note)) else f"unknown scan {scan}"

    def note(self, text: str) -> str:
        self.notes = (self.notes + [text])[-5:]
        ok = self.emit(PanelUpsert(panel=Panel(id="agent:notes", title="Notes", blocks=[Note(text=t[:280])
                                                                                          for t in self.notes])))
        if not ok:
            self.notes.pop()
            return "rejected: notes may not state measurements; point to finding ids instead"
        return "ok"

    def plan(self, todos: list[dict]) -> None:
        steps = [PlanStep(id=f"s{i + 1}", text=t.get("content", ""), status=t.get("status", "pending"))
                 for i, t in enumerate(todos)]
        self.step = next((s.id for s in steps if s.status == "in_progress"), self.step)
        self.emit(PlanSet(steps=steps))

    def observe(self, chunk: dict) -> None:
        """Turn one deepagents stream update into ops: todos become plan.set, files become the case file."""
        if chunk.get("type") != "updates":
            return
        for data in (chunk.get("data") or {}).values():
            if not isinstance(data, dict):
                continue
            todos = data.get("todos")
            if isinstance(todos, list):
                self.plan([t if isinstance(t, dict) else dict(t) for t in todos])
            files = data.get("files")
            if isinstance(files, dict):
                self.files.update(files)

    # ---- the agent ----
    def agent_tools(self) -> list:
        from langchain_core.tools import StructuredTool
        load()
        out = []
        for t in self.s.doc.tools:
            m = catalog().get(t.id)
            if not t.enabled or not m or m.status != "ready":
                continue
            fields = {n: (f.annotation if n == "scan" else f.annotation | None,
                          Field(... if n == "scan" else None, description=f.description or m.inputs["properties"][n]
                                .get("x-ask", n)))
                      for n, f in REGISTRY[t.id].inputs.model_fields.items()}
            out.append(StructuredTool.from_function(
                func=(lambda tid: lambda **kw: json.dumps(self.run(tid, {k: v for k, v in kw.items() if v is not None})))(t.id),
                name=t.id, args_schema=create_model(f"{t.id}_args", **fields),
                description=m.model_description + " Leave out inputs you were not told: the person's preferences fill them."))
        return out

    def small_tools(self) -> list:
        from langchain_core.tools import StructuredTool
        return [StructuredTool.from_function(self.focus, name="focus",
                                             description="Point the person's camera at one finding by id."),
                StructuredTool.from_function(self.shortlist, name="shortlist",
                                             description="Add a scan that meets the need to the person's shortlist."),
                StructuredTool.from_function(self.note, name="note",
                                             description="Add one short note (under 280 characters) for the person. "
                                                         "No measurements or numbers with units.")]

    def prompt(self, request: str | None) -> str:
        d = self.s.doc
        p = personas().get(d.brief.persona or "")
        enabled = [t for t in d.tools if t.enabled]
        return "\n".join([
            f"Person: {d.brief.summary or d.brief.text}", f"They said: {d.brief.text}",
            f"Persona: {p.title if p else 'none'}", f"Now: {request or 'Investigate these buildings for them.'}",
            f"Buildings (scan ids): {', '.join(d.brief.scope.sids)}",
            "Ready tools: " + ", ".join(f"{t.id} ({t.reason})" for t in enabled if t.status == "ready"),
            "Planned tools, not built, already marked skipped: " +
            (", ".join(t.id for t in enabled if t.status == "planned") or "none"),
            "What the person has taught you:", prefs.as_text(d)])

    def build(self, model=None):
        from deepagents import create_deep_agent
        from langchain.agents.middleware import TodoListMiddleware

        from .llm import chat
        tools = self.agent_tools()
        building = {"name": "building", "description": "Investigates one building (one scan id) with the ready tools.",
                    "system_prompt": BUILDING, "tools": tools + [self.small_tools()[2]]}
        return create_deep_agent(model=model or chat(2048), tools=self.small_tools(), system_prompt=MAIN,
                                 subagents=[building], middleware=[TodoListMiddleware()], name="investigator")

    def go(self, request: str | None = None, model=None) -> str:
        """Run one investigation turn. Returns the agent's closing sentence."""
        d = self.s.doc
        for t in d.tools:  # planned tools show as skipped instead of silently missing
            if t.enabled and t.status == "planned" and not any(r.tool == t.id for r in d.runs):
                self.run(t.id, {})
        agent = self.build(model)
        last = ""
        for chunk in agent.stream({"messages": [{"role": "user", "content": self.prompt(request)}]},
                                  stream_mode="updates", subgraphs=True, version="v2"):
            self.observe(chunk)
            if not chunk.get("ns"):
                for data in (chunk.get("data") or {}).values():
                    for msg in (data.get("messages") or []) if isinstance(data, dict) else []:
                        if getattr(msg, "type", "") == "ai" and not getattr(msg, "tool_calls", None) and msg.text:
                            last = msg.text
        self.compare()
        if last and not self.emit(PanelUpsert(panel=Panel(id="agent:summary", title="Where to look first",
                                                          blocks=[Note(text=last[:280])]))):
            last = ""
        if self.files:
            (self.s.root / f"{self.s.base.id}.casefile.json").write_text(json.dumps(self.files, default=str))
        return last


MAIN = """You are the investigator in Threshold. You do not chat: the person sees your plan, tool runs, findings and
camera in their workspace, not your words.
1. First call write_todos with a short plan: one step per building, then one step to point out what matters.
2. For each building, call task with subagent_type "building", naming the scan id and what to check for this person.
   Mark the step in_progress before and completed after.
3. Tool results go into the workspace by themselves. You see summaries and finding ids. Never restate a measurement
   or invent a number; refer to findings by id.
4. Then call focus on the one finding that matters most to this person, and shortlist each building that meets the
   need.
5. Finish with one short sentence, without numbers, telling the person where to look first."""

BUILDING = """You investigate one building (one scan id) for a person. Run each ready tool that serves their need on
this scan, once each. Leave out inputs you were not told; the person's preferences fill them. If a tool reports
missing inputs, do not guess them; say so in your reply. Write a short case note with write_file to
/notes/<scan id>.md: which finding ids matter for this person and why, without measurements. Use note only if
something needs explaining to the person. Reply in two lines: the finding ids that matter most, and why."""


def turn(session: Session, text: str | None = None, sids: list[str] | None = None, composer=None,
         agent_model=None) -> dict:
    """One agent turn: set the scope, compose the workspace if it has none, stop at unanswered questions,
    otherwise investigate. Ops stream to the session's listeners as they apply."""
    from .composer import compose
    from .llm import Claude
    from .workspace import BriefSet, Scope
    attach(session, session.plans or default_plan)
    t = new_id("turn")
    if sids:
        session.submit(BriefSet(by="user", scope=Scope(sids=sids, address=session.doc.brief.scope.address), run=t))
    if text and not session.doc.brief.persona:
        for op in compose(text, session.doc, composer or Claude(), run=t):
            try:
                session.submit(op)
            except Rejected:
                pass
        text = None
    open_qs = [q for q in session.doc.questions if not q.answered]
    if open_qs:
        return {"status": "questions", "questions": [q.id for q in open_qs]}
    if not session.doc.brief.scope.sids:
        return {"status": "needs_scope", "message": "Pick a building first"}
    return {"status": "done", "summary": Investigation(session, t).go(text, agent_model)}
