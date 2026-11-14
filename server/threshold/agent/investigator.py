"""Investigator: the agent loop on LangChain `deepagents`.

The main agent plans with `write_todos` (streamed as `plan.set`), hands each building to a `building` subagent,
then points the camera at what matters and shortlists. Every enabled tool becomes an agent tool whose result
goes straight into the workspace (`run.start`, `run.finish`, `finding.add`, `overlay.upsert`, `panel.upsert`,
`camera.focus`); the model sees only a compact summary and ids. Subagents keep case notes in the deepagents
virtual filesystem (/notes/<scan>.md), saved next to the workspace as <id>.casefile.json.
"""
from __future__ import annotations

import inspect
import json
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from pydantic import Field, create_model

from ..tools import Check, Metric, Place, PropertyScope, Source, ToolContext, ToolError, ToolResult, Verdict, run_tool
from ..tools.places import default_site
from ..tools.registry import REGISTRY, default_plan, load
from . import prefs
from .budget import Budget, BudgetSpent
from .catalog import catalog, personas, resolve
from .workspace import (
    MEASURE,
    ActionBar,
    AssumptionChips,
    BriefSet,
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
    RunProgress,
    Scope,
    RunStart,
    Session,
    ShortlistAdd,
    StepLog,
    VerdictHeader,
    WsFinding,
    WsOverlay,
    clean,
    known_sids,
    new_id,
)

RANK = {"fail": 0, "warn": 1, "unknown": 2, "pass": 3}


SENTENCE_END = re.compile(r"(?<![0-9])[.!?](?=\s|$)")  # "1." of a list is not a sentence end


def short(text: str, n: int = 280) -> str:
    """Fit a Note: plain text, the first paragraph, whole sentences up to n characters, else a hard cut."""
    text = text.replace("**", "").strip().split("\n\n")[0].strip()
    if len(text) <= n:
        return text
    ends = [m.end() for m in SENTENCE_END.finditer(text[:n])]
    return text[:ends[-1]] if ends else text[:n - 1] + "…"


def as_tool(fn: Callable, name: str, description: str, skip: tuple = ()):
    """A LangChain tool whose arguments come from `fn`'s signature and whose reply is JSON."""
    from langchain_core.tools import StructuredTool
    fields = {n: (Any if p.annotation is inspect.Parameter.empty else p.annotation,
                  Field(... if p.default is inspect.Parameter.empty else p.default))
              for n, p in inspect.signature(fn, eval_str=True).parameters.items()
              if n not in skip and p.kind not in (p.VAR_KEYWORD, p.VAR_POSITIONAL)}
    return StructuredTool.from_function(func=lambda **kw: json.dumps(fn(**kw), default=str), name=name,
                                        description=description, args_schema=create_model(f"{name}_args", **fields))


def target(run: Run) -> str:
    """What a run looked at, as a key: its scan id, else its place's key."""
    return run.sid or (run.place.key() if run.place else "")


def default_place(doc) -> dict | None:
    """The workspace's one place when there is exactly one (a scan or a place), else None: the model must say."""
    options = [{"scan": s} for s in doc.brief.scope.sids] + [p.model_dump(exclude_none=True) for p in doc.brief.scope.places]
    return options[0] if len(options) == 1 else None


def in_scope(place: Place, doc) -> bool:
    if place.scan:
        return place.scan in known_sids(doc)
    return any(p.key() == place.key() or (place.property_id is not None and p.property_id == place.property_id)
               for p in doc.brief.scope.places)


def attach(session: Session, plans: Callable[[str], dict] = default_plan) -> Session:
    """Give a session what the validator needs: a plan loader and the tool ids that exist."""
    session.plans = plans
    session.tools = set(catalog())
    session.siblings = session.siblings or sibling_scans
    return session


def sibling_scans(sid: str) -> list[str]:
    """Other scans of the same CoStar property, for corrections that spread."""
    from ..sources import costar
    try:
        pid = costar.property_id_of(sid)
        return [s for s in costar.scans_of_property(pid) if s != sid] if pid else []
    except Exception:
        return []


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
    return Panel(id=f"panel:{m.id}:{target(run)}", title=m.title, blocks=blocks, tool=m.id, run=run.id)


class Investigation:
    """One agent turn over one workspace. Tool calls from the main agent and subagents land here."""

    def __init__(self, session: Session, turn: str | None = None, budget: Budget | None = None):
        self.s = attach(session, session.plans or default_plan)
        self.turn = turn or new_id("turn")
        self.budget = budget or Budget()
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
        if "place" in m.inputs.get("properties", {}):
            given = {**given, "place": given.get("place") or default_place(doc)}
            if given["place"] is None:
                return {"error": "this tool needs a place: a scan, property_id, address or geo [lon, lat]"}
            try:
                place = Place.model_validate(given["place"])
            except ValueError as e:
                return {"error": f"bad place: {e}"}
            if not in_scope(place, doc):
                return {"error": f"place {place.key()} is not in this workspace; add it with consider first"}
            given["place"] = place.model_dump(exclude_none=True)
        inputs, used, missing = resolve(m, doc, given)
        place = Place.model_validate(inputs["place"]) if inputs.get("place") else None
        rec = Run(id=new_id("run"), tool=tool_id, sid=inputs.get("scan") or given.get("scan") or (place.scan if place else None),
                  place=place if place and not place.scan else None, inputs=inputs, inputs_from=used, plan_step=self.step)
        if rec.sid and rec.sid not in known_sids(doc):
            return {"error": f"scan {rec.sid} is not in this workspace; use one of {doc.brief.scope.sids}"}
        if m.status == "ready" and not missing and not self.budget.take_run():
            return {"error": "this turn's tool-run budget is spent; finish with what you have"}
        self.emit(RunStart(record=rec, run=rec.id))
        if m.status == "planned":
            self.emit(RunFinish(id=rec.id, status="skipped", summary=f"{m.title} is planned, not built yet", run=rec.id))
            return {"run": rec.id, "skipped": "planned tool, not built yet"}
        if missing:
            need = ", ".join(n for n, _ in missing)
            self.emit(RunFinish(id=rec.id, status="error", error=f"needs {need}", run=rec.id))
            return {"run": rec.id, "error": f"missing inputs the person has not given: {need}"}
        ctx = ToolContext(plans=prefs.with_labels(self.s.plans, doc),
                          on_step=lambda text: self.emit(RunProgress(id=rec.id, step=short(text, 200), run=rec.id)))
        if self.s.sites:
            ctx.sites = self.s.sites
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
        target_of = {r.id: target(r) for r in self.s.doc.runs}
        kept = {f.id for f in shown}
        for old in self.s.doc.findings:  # a re-run retires what it no longer reports
            if (old.tool == tool_id and old.run != rec.id and target_of.get(old.run) == target(rec) and old.id not in kept
                    and not old.superseded_by):
                self.emit(FindingAdd(finding=old.model_copy(update={"superseded_by": rec.id}), run=rec.id))
        ids = [f"{tool_id}:{target(rec)}:{i}" for i in range(len(result.overlays))]
        for oid, o in zip(ids, result.overlays):
            self.emit(OverlayUpsert(overlay=WsOverlay(id=oid, sid=rec.sid, overlay=o, tool=tool_id, run=rec.id),
                                    run=rec.id))
        for old in self.s.doc.overlays:  # a re-run with fewer overlays hides the leftovers
            if old.tool == tool_id and old.id.startswith(f"{tool_id}:{target(rec)}:") and old.id not in ids and old.visible:
                self.emit(OverlayUpsert(overlay=old.model_copy(update={"visible": False, "run": rec.id}), run=rec.id))
        done = next(r for r in self.s.doc.runs if r.id == rec.id)
        self.emit(PanelUpsert(panel=panel_for(m, done, ids), run=rec.id))
        worst = min((f for f in shown if f.anchor), key=lambda f: RANK[f.status], default=None)
        if worst and worst.status != "pass":
            self.emit(CameraFocus(anchor=worst.anchor, reason=worst.title, run=rec.id))
        return {"run": rec.id, "tool": tool_id, "scan": rec.sid, "place": rec.place and rec.place.key(),
                "verdict": result.verdict.status,
                "summary": result.verdict.text,
                "findings": [{"id": f.id, "status": f.status, "title": f.title} for f in
                             sorted(shown, key=lambda f: RANK[f.status])[:8]],
                "more_findings": max(0, len(shown) - 8), "hidden_because_rejected": len(result.findings) - len(shown),
                # the person's own answers and edits apart from the persona's defaults, so the model never calls
                # an answer the person just gave a "saved setting"
                "inputs_the_person_gave": [k for k, v in used.items() if v in self.s.doc.prefs or v in self.s.doc.brief.facts],
                "inputs_from_persona_defaults": [k for k, v in used.items()
                                                 if v not in self.s.doc.prefs and v not in self.s.doc.brief.facts]}

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
        ok = self.emit(PanelUpsert(panel=Panel(id="agent:notes", title="Notes", blocks=[Note(text=short(t))
                                                                                          for t in self.notes])))
        if not ok:
            self.notes.pop()
            return "rejected: notes may not state measurements; point to finding ids instead"
        return "ok"

    # ---- finding buildings ----
    def _exists(self, sid: str) -> bool:
        from ..sources import index
        if sid in index.rows():
            return True
        try:
            self.s.plans(sid)
            return True
        except Exception:
            return False

    def consider(self, scans: list[str] | None = None, property_ids: list[int] | None = None,
                 addresses: list[str] | None = None, points: list[list[float]] | None = None) -> dict:
        """Add buildings found by search to the workspace so tools may run on them."""
        with self.s.lock:  # parallel subagents may add at once; read and write the scope as one step
            out = self._consider(scans, property_ids, addresses, points)
        with ThreadPoolExecutor(max_workers=self.budget.parallel) as ex:
            out["new_scans_can_answer"] = dict(zip(out["new"], ex.map(self.can_answer, out.pop("new"))))
        return out

    def _consider(self, scans, property_ids, addresses, points) -> dict:
        sc = self.s.doc.brief.scope
        sids, places, problems = list(sc.sids), list(sc.places), []
        for sid in scans or []:
            if sid in sids:
                continue
            (sids.append(sid) if self._exists(sid) else problems.append(f"no scan {sid}"))
        wanted = [Place(property_id=p) for p in property_ids or []] + [Place(address=a) for a in addresses or []]
        for pt in points or []:
            try:
                wanted.append(Place(geo=tuple(pt)))
            except ValueError as e:
                problems.append(f"bad point {pt}: {e}")
        have = {p.key() for p in places}
        for p in wanted:
            if p.key() in have:
                continue
            try:
                ToolContext(sites=self.s.sites or default_site).site(p)
                places.append(p)
                have.add(p.key())
            except ToolError as e:
                problems.append(str(e))
        new = [s for s in sids if s not in sc.sids]
        if new or len(places) != len(sc.places):
            self.emit(BriefSet(scope=Scope(sids=sids, address=sc.address, places=places)))
        return {"scans_in_workspace": len(sids), "places": [p.key() for p in places], "problems": problems, "new": new}

    def can_answer(self, sid: str) -> dict:
        """What a scan's plan holds, so the agent can swap a candidate that cannot answer: walls, doorways, labels."""
        try:
            p = self.s.plans(sid)
        except Exception as e:
            return {"error": f"plan unavailable: {type(e).__name__}"}
        q = p.get("quality") or {}
        has = p.get("has") or {}
        return {"walls": q.get("walls", bool(p.get("walls"))), "doorways": q.get("openings", bool(has.get("openings"))),
                "room_labels": q.get("labels", bool(has.get("room_labels")))}

    def scans_of(self, property_id: int) -> list[dict]:
        return ToolContext(sites=self.s.sites or default_site).site(Place(property_id=property_id)).scans

    def property_scans(self, property_id: int) -> dict:
        """The scans of one property, grouped by kind."""
        try:
            scans = self.scans_of(property_id)
        except ToolError as e:
            return {"error": str(e)}
        kinds: dict[str, list] = {}
        for s in scans:
            kinds.setdefault(s["kind"], []).append({"sid": s["sid"], "name": s["name"]})
        return {"property_id": property_id, "count": len(scans),
                "by_kind": {k: {"count": len(v), "first": v[:12]} for k, v in kinds.items()}}

    def fan_out(self, tool_id: str, property_id: int, kinds: list[str] | None = None,
                scans: list[str] | None = None, max_scans: int | None = None) -> dict:
        """Run one scan tool over a property's scans not yet checked with it, at most `parallel` at once and
        `max_fan_out` per call, then upsert one property-level run over every scan of the property checked so far."""
        m = catalog().get(tool_id)
        if not m or m.status != "ready" or "scan" not in m.inputs.get("properties", {}):
            return {"error": f"{tool_id} is not a ready tool that runs on a scan"}
        try:
            all_scans = self.scans_of(property_id)
        except ToolError as e:
            return {"error": str(e)}

        def latest() -> dict[str, Run]:
            ids = {s["sid"] for s in all_scans}
            return {r.sid: r for r in self.s.doc.runs if r.tool == tool_id and r.sid in ids and r.status != "running"}
        before = latest()
        pool = [s for s in all_scans if (not kinds or s["kind"] in kinds)
                and (s["sid"] in scans if scans else s["sid"] not in before)]
        pick = pool[:max(1, min(max_scans or self.budget.max_fan_out, self.budget.max_fan_out))]
        if pick:
            self.consider(scans=[s["sid"] for s in pick], property_ids=[property_id])
            with ThreadPoolExecutor(max_workers=self.budget.parallel) as ex:
                list(ex.map(lambda s: self.run(tool_id, {"scan": s["sid"]}), pick))
        elif not before:
            return {"error": f"no scans of property {property_id} match kinds {kinds}"}
        done = latest()
        name = {s["sid"]: s for s in all_scans}
        checks, counts = [], {k: 0 for k in RANK}
        for sid, r in done.items():
            st = r.result.verdict.status if r.result else "unknown"
            counts[st] += 1
            checks.append(Check(id=f"scan.{sid}", rule=f"{name[sid]['name'] or sid} ({name[sid]['kind']})", measured=None,
                                threshold=None, unit="", status=st, standard=r.error or (r.summary if r.status == "skipped" else None),
                                findings=[f.id for f in self.s.doc.findings if f.run == r.id and not f.superseded_by]))
        worst = min((c.status for c in checks), key=lambda x: RANK[x])
        left = len(all_scans) - len(done)
        src = Source(layer="matterport", method="geometry", confidence="medium",
                     note=f"Aggregate of {m.title} over the property's scans")
        text = (f"{m.title} on {len(done)} of {len(all_scans)} scans: {counts['fail']} fail, {counts['warn']} warn, "
                f"{counts['pass']} pass, {counts['unknown']} unknown." + (f" {left} scans not checked yet." if left else ""))
        result = ToolResult(tool=tool_id, scope=PropertyScope(property_id=property_id, sids=list(done)),
                            verdict=Verdict(status=worst, text=text),
                            metrics=[Metric(id="scans_checked", label="Scans checked", value=len(done), unit="", source=src),
                                     Metric(id="scans_not_checked", label="Not checked", value=left, unit="", source=src),
                                     *[Metric(id=f"verdicts.{k}", label=k, value=v, unit="scans", source=src)
                                       for k, v in counts.items()]],
                            checks=sorted(checks, key=lambda c: RANK[c.status]))
        place = Place(property_id=property_id)
        rec = Run(id=new_id("run"), tool=tool_id, place=place, plan_step=self.step,
                  inputs={"place": place.model_dump(exclude_none=True), "scans": list(done)})
        steps = [f"Ran {m.title} on {len(pick)} more scans, {self.budget.parallel} at a time",
                 f"{len(done)} of {len(all_scans)} scans of the property checked so far"]
        self.emit(RunStart(record=rec, run=rec.id))
        self.emit(RunFinish(id=rec.id, status="done", summary=text, steps=steps, result=result, run=rec.id))
        self.emit(PanelUpsert(panel=Panel(id=f"panel:{tool_id}:{place.key()}", title=f"{m.title}: whole property",
                                          tool=tool_id, run=rec.id,
                                          blocks=[VerdictHeader(run=rec.id), MetricRow(run=rec.id, metrics=["scans_checked", "scans_not_checked"]),
                                                  MiniChart(run=rec.id, title="Scans by verdict",
                                                            metrics=[f"verdicts.{k}" for k in RANK]),
                                                  CheckList(run=rec.id), StepLog(run=rec.id)]), run=rec.id))
        return {"run": rec.id, "property_id": property_id, "verdict": worst, "summary": text, "ran_now": len(pick),
                "worst_scans": [{"scan": c.id[5:], "status": c.status, "findings": c.findings[:4]}
                                for c in result.checks[:6]]}

    def rank(self, candidates: list[str], reasons: list[str]) -> dict:
        """A ranked comparison panel: the candidates in the given order, one RankedTable over their latest runs of
        the tool most of them ran, and one reason each. Candidates are scan ids or p<property id>."""
        latest: dict[str, dict[str, Run]] = {}
        for r in self.s.doc.runs:
            if r.status == "done" and r.result:
                latest.setdefault(target(r), {})[r.tool] = r
        tools = [t for c in candidates for t in latest.get(c, {})]
        if not tools:
            return {"error": "none of these candidates has a finished run; investigate them first"}
        lead = personas().get(self.s.doc.brief.persona or "")
        lead = lead.layout.lead_tool if lead and lead.layout.lead_tool in tools else max(set(tools), key=tools.count)
        rows = [latest[c][lead] for c in candidates if lead in latest.get(c, {})]
        cols = [RankedColumn(metric=x.id, label=x.label, better="lower" if "too" in x.id or "fail" in x.id else "higher")
                for x in rows[0].result.metrics if "." not in x.id][:4]
        notes, dropped = [], []
        for i, (c, why) in enumerate(zip(candidates, reasons + [""] * len(candidates))):
            if MEASURE.search(why):
                dropped.append(c)
            else:
                notes.append(Note(text=short(f"{i + 1}. {self.label(c)}: {why}")))
        blocks = [RankedTable(title=f"Ranked by {catalog()[lead].title}", columns=cols, rows=[r.id for r in rows]), *notes]
        ok = self.emit(PanelUpsert(panel=Panel(id="agent:ranked", title="Ranked for you", blocks=blocks)))
        return {"ok": ok, "ranked_by": lead, "rows": len(rows),
                "reasons_dropped_for_measurements": dropped}

    def label(self, key: str) -> str:
        from ..sources import index
        r = index.rows().get(key)
        if r:
            return r["name"] or r["address"] or key
        if key.startswith("p") and key[1:].isdigit():
            try:
                return ToolContext(sites=self.s.sites or default_site).site(Place(property_id=int(key[1:]))).address or key
            except ToolError:
                return key
        return key

    def compose_panel(self, title: str, blocks: list[dict]) -> dict:
        """A custom panel from the block catalog, bound to runs, findings and overlays already in the workspace."""
        slug = "-".join(re.findall(r"[a-z0-9]+", title.lower()))[:40] or "panel"
        raw = {"op": "panel.upsert", "by": "agent", "run": self.turn,
               "panel": {"id": f"custom:{slug}", "title": title[:80], "blocks": blocks}}
        try:
            op, notes = clean(self.s.doc, raw, self.s.plans or default_plan, self.s.tools or set(catalog()))
        except Rejected as e:
            return {"error": str(e)}
        ok = self.emit(op)
        return {"panel": op.panel.id if ok else None, "blocks": [b.type for b in op.panel.blocks], "dropped": notes}

    def plan(self, todos: list[dict]) -> None:
        steps = [PlanStep(id=f"s{i + 1}", text=t.get("content", ""), status=t.get("status", "pending"))
                 for i, t in enumerate(todos)]
        self.step = next((s.id for s in steps if s.status == "in_progress"), self.step)
        self.emit(PlanSet(steps=steps))

    def observe(self, chunk: dict) -> None:
        """Turn one deepagents stream update into ops: the main agent's todos become plan.set, files from any agent
        become the case file."""
        if chunk.get("type") != "updates":
            return
        for data in (chunk.get("data") or {}).values():
            if not isinstance(data, dict):
                continue
            todos = data.get("todos")
            if isinstance(todos, list) and not chunk.get("ns"):  # a subagent's own todo list is not the plan
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
            fields = {}
            for n, f in REGISTRY[t.id].inputs.model_fields.items():
                where = n in ("scan", "place")
                desc = (PLACE_HELP if n == "place" else f.description or m.inputs["properties"][n].get("x-ask", n))
                fields[n] = ((dict if n == "place" else f.annotation) if where else f.annotation | None,
                             Field(... if where else None, description=desc))
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
                                             description="Add a scan that meets the need to the person's shortlist "
                                                         "(shortlist.add), with a short note why, without numbers."),
                StructuredTool.from_function(self.note, name="note",
                                             description="Add one short note (under 280 characters) for the person. "
                                                         "No measurements or numbers with units.")]

    def search_tools(self) -> list:
        from langchain_core.tools import StructuredTool

        from . import search
        out = [as_tool(search.find_scans, "find_scans", (search.find_scans.__doc__ or "") + " text: words in the name or "
                       "address. drone: a drone capture exists. empty_room_view: a defurnished view exists. At most 25 rows."),
               as_tool(search.find_properties, "find_properties", (search.find_properties.__doc__ or "") + " Rows carry record "
                       "facts (units, elevators, walk-up, year built, rent range): use them to choose, never quote them.",
                       skip=("rows",)),
               as_tool(self.consider, "consider", "Add found buildings to the workspace before investigating them: "
                       "scan ids, CoStar property ids, addresses, or points [lon, lat]."),
               as_tool(self.rank, "rank", "Show the ranked comparison: candidates (scan ids or p<property id>) best "
                       "first, and one plain reason each, without numbers."),
               as_tool(self.compose_panel, "compose_panel", PANEL_HELP)]
        if hasattr(self.s.store, "search"):
            out.append(as_tool(self.history, "search_history", "Search this person's past workspaces (briefs, findings, "
                               "notes, tools they removed, buildings they shortlisted). feedback \"rejected\" finds what "
                               "they turned down and why: skip those buildings, or check that reason first. kind: brief, "
                               "finding, note, tool_removed, shortlist. Never quote numbers from it."))
        route = search.measures_route()
        if route:
            out.append(StructuredTool.from_function(
                lambda **kw: json.dumps(search.find_by_measure(route, kw.get("params") or kw), default=str),
                name="find_by_measure", args_schema=create_model("find_by_measure_args", params=(dict, Field(
                    description=f"Query parameters of GET {search.MEASURES}: {search.measures_params(route)}"))),
                description="Search scans by measured facts (door widths, step-free routes, turning space) "
                            "from the access workstream's prefetched measurements."))
        return out

    def property_tools(self) -> list:
        return [as_tool(self.property_scans, "property_scans", "List one property's scans grouped by kind."),
                as_tool(self.fan_out, "run_on_property", "Run one ready scan tool over a property's scans (filter by "
                        "kinds, e.g. apartment_unit or amenity, or by scan ids). Runs a few at a time, at most "
                        f"{self.budget.max_fan_out} scans, and adds one property-level result."),
                as_tool(self.coverage, "coverage", "Which floor plans and shared spaces of the property no scan covers.")]

    def coverage(self, property_id: int) -> dict:
        return self.run("property_coverage", {"place": {"property_id": property_id}})

    def prompt(self, request: str | None) -> str:
        d = self.s.doc
        p = personas().get(d.brief.persona or "")
        enabled = [t for t in d.tools if t.enabled]
        places = [x.key() for x in d.brief.scope.places]
        return "\n".join([
            f"Person: {d.brief.summary or d.brief.text}", f"They said: {d.brief.text}",
            f"Persona: {p.title if p else 'none'}", f"Now: {request or 'Investigate for them.'}",
            f"Buildings (scan ids): {', '.join(d.brief.scope.sids) or 'none yet: find them with search'}",
            f"Places (properties p<id>, addresses, points): {', '.join(places) or 'none'}",
            "Ready tools: " + ", ".join(f"{t.id} ({t.reason})" for t in enabled if t.status == "ready"),
            "Planned tools, not built, already marked skipped: " +
            (", ".join(t.id for t in enabled if t.status == "planned") or "none"),
            *([f"What the composer said it cannot do: {'; '.join(d.brief.limits)}"] if d.brief.limits else []),
            f"Budget this turn: {self.budget.model_calls} model calls in all agents, {self.budget.tool_runs} tool runs. "
            "Investigate at most five candidates.",
            "What the person has taught you:", prefs.as_text(d), *self.lessons()])

    def lessons(self) -> list[str]:
        """What earlier people with the same persona and a similar need taught (the store's memory)."""
        from ..store import recall_lines
        d = self.s.doc
        got = recall_lines(self.s.store, d.brief.text, persona=d.brief.persona or "none", exclude=d.id)
        return ["Earlier people with this persona and a similar need (search_history finds their findings):", *got] if got else []

    def history(self, text: str | None = None, kind: str | None = None, tool: str | None = None,
                status: str | None = None, feedback: str | None = None, city: str | None = None) -> dict:
        """The person's past work across their workspaces."""
        res = self.s.store.search(text, 12, profile=self.s.base.profile, kind=kind, tool=tool, status=status,
                                  feedback=feedback, city=city)
        keep = ("workspace", "kind", "sid", "address", "city", "tool", "status", "title", "feedback", "reason", "finding")
        return {"total": res["total"], "facets": res["facets"],
                "hits": [{**{k: h.get(k) for k in keep if h.get(k) is not None}, "here": h["workspace"] == self.s.base.id}
                         for h in res["hits"]]}

    def build(self, model=None):
        from deepagents import create_deep_agent
        from langchain.agents.middleware import ModelCallLimitMiddleware, TodoListMiddleware

        from .llm import chat
        b = self.budget
        tools = self.agent_tools()
        note = self.small_tools()[2]
        building = {"name": "building", "description": "Investigates one building (one scan id) with the ready tools.",
                    "system_prompt": BUILDING, "tools": tools + [note],
                    "middleware": [ModelCallLimitMiddleware(run_limit=b.subagent_calls)]}
        prop = {"name": "property", "description": "Investigates a whole property (CoStar property id) across its "
                                                   "scans: units, amenities, lobby. Say which tools and kinds of scan.",
                "system_prompt": PROPERTY, "tools": self.property_tools() + [note],
                "middleware": [ModelCallLimitMiddleware(run_limit=b.property_calls)]}
        return create_deep_agent(model=model or chat(2048), tools=self.small_tools() + self.search_tools(),
                                 system_prompt=MAIN, subagents=[building, prop],
                                 middleware=[TodoListMiddleware(), ModelCallLimitMiddleware(run_limit=b.main_calls)],
                                 name="investigator")

    def go(self, request: str | None = None, model=None) -> str:
        """Run one investigation turn. Returns the agent's closing sentence; `self.budget` says what it spent."""
        d = self.s.doc
        for t in d.tools:  # planned tools show as skipped instead of silently missing
            if t.enabled and t.status == "planned" and not any(r.tool == t.id for r in d.runs):
                self.run(t.id, {})
        agent = self.build(model)
        last = ""
        config = {"callbacks": [self.budget.callback()], "max_concurrency": self.budget.parallel, "recursion_limit": 120}
        try:
            for chunk in agent.stream({"messages": [{"role": "user", "content": self.prompt(request)}]}, config,
                                      stream_mode="updates", subgraphs=True, version="v2"):
                self.observe(chunk)
                if not chunk.get("ns"):
                    for data in (chunk.get("data") or {}).values():
                        for msg in (data.get("messages") or []) if isinstance(data, dict) else []:
                            if getattr(msg, "type", "") == "ai" and not getattr(msg, "tool_calls", None) and msg.text:
                                last = msg.text
        except BudgetSpent:
            last = last or "I stopped at this turn's budget; the results so far are in your workspace."
        self.compare()
        if last and not self.emit(PanelUpsert(panel=Panel(id="agent:summary", title="Where to look first",
                                                          blocks=[Note(text=short(last))]))):
            last = ""
        (self.s.root / f"{self.s.base.id}.casefile.json").write_text(
            json.dumps({"files": self.files, "budget": self.budget.report()}, default=str))
        return last


PLACE_HELP = ("Where to run: {\"scan\": id} or {\"property_id\": id} or {\"address\": text} or {\"geo\": [lon, lat]}. "
              "It must be in the workspace (consider adds it).")

PANEL_HELP = ("Only when no tool's panel answers the person's question: build one panel from blocks bound to what is "
              "already in the workspace. Blocks: VerdictHeader{run}, MetricRow{run, metrics[<=4 metric ids]}, "
              "CheckList{run, checks?, status?}, EvidenceStrip{findings[ids]}, RankedTable{title, columns[{metric, "
              "label, better}], rows[run ids]}, MiniChart{run, title, metrics[ids]}, FloorPlanMini{sid, overlays[ids]}, "
              "AssumptionChips{run}, StepLog{run}, Note{text}, ActionBar{run}. Each block has \"type\". Bind by id; "
              "never type a number. Blocks that name something missing are dropped.")

MAIN = """You are the investigator in Threshold. You do not chat: the person sees your plan, searches, tool runs,
findings and camera in their workspace, not your words.
1. First call write_todos with a short plan. Mark steps in_progress before and completed after.
2. If no buildings are given, find them: find_properties for record facts (city, type, units, elevators, rent,
   tenants), find_scans for scans (city, kind, address, drone capture, empty-room view), find_by_measure when present.
   Pick at most five candidates that fit the person, then call consider with them. consider says what each new scan's
   plan holds; if one cannot answer the person's need (no doorways for a door question), swap it for another once.
3. For each candidate unit or house, call task with subagent_type "building", naming the scan id and what to check.
   For a whole property (many scans: units, lobby, gym), use subagent_type "property" with the property id. Several
   task calls in one message run in parallel.
4. Tool results go into the workspace by themselves. You see summaries and finding ids. Never restate a measurement
   or invent a number; refer to findings by id.
5. With two or more candidates, call rank once with all of them, best first, and one plain reason each. Shortlist the
   ones that meet the need, each with a short note. Call focus on the one finding that matters most.
6. Use compose_panel only when no tool's panel answers a question the person asked.
7. Finish with at most three short sentences, plain text, no lists and no numbers at all (no measurements, counts,
   times or money; the panels show those): what you found and where the person should look first. Say that something is missing or could not be checked only when a tool's summary says
   so. Stay inside the budget."""

BUILDING = """You investigate one building (one scan id) for a person. Run each ready tool that serves their need on
this scan, once each. Leave out inputs you were not told; the person's preferences fill them. If a tool reports
missing inputs, do not guess them; say so in your reply. Write a short case note with write_file to
/notes/<scan id>.md: which finding ids matter for this person and why, without measurements. Use note only if
something needs explaining to the person. Reply in two lines: the finding ids that matter most, and why. Inputs a run lists under inputs_the_person_gave are the
person's own answers; never call them saved settings or defaults."""

PROPERTY = """You investigate one whole property (a CoStar property id) for a person. Call property_scans first. Then
call run_on_property once per useful tool, choosing the kinds of scan that matter (units, amenities). Then call
coverage to learn which floor plans and shared spaces no scan covers. Do not run tools one scan at a time. Write a
short case note with write_file to /notes/p<property id>.md without measurements. Reply in three lines: the run ids
that matter, the scans that need attention, and what no scan covers."""


def turn(session: Session, text: str | None = None, sids: list[str] | None = None, composer=None,
         agent_model=None, places: list[dict] | None = None, budget: Budget | None = None) -> dict:
    """One agent turn: set the scope, compose the workspace if it has none, stop at unanswered questions,
    otherwise investigate (searching for buildings when none are given). Ops stream to the session's listeners."""
    from .composer import compose
    from .llm import Claude
    attach(session, session.plans or default_plan)
    t = new_id("turn")
    sc = session.doc.brief.scope
    if sids or places:
        session.submit(BriefSet(by="user", run=t, scope=Scope(sids=sids or sc.sids, address=sc.address,
                                                             places=[Place.model_validate(p) for p in places] if places else sc.places)))
    if text and not (session.doc.brief.persona or session.doc.brief.summary):  # not composed yet
        from ..store import recall_lines
        for op in compose(text, session.doc, composer or Claude(), run=t,
                          recalled=recall_lines(session.store, text, exclude=session.base.id)):
            try:
                session.submit(op)
            except Rejected:
                pass
        text = None
    open_qs = [q for q in session.doc.questions if not q.answered]
    if open_qs:
        return {"status": "questions", "questions": [q.id for q in open_qs]}
    sc = session.doc.brief.scope
    if not sc.sids and not sc.places and not session.doc.brief.text:
        return {"status": "needs_scope", "message": "Pick a building or say what you are looking for"}
    inv = Investigation(session, t, budget)
    summary = inv.go(text, agent_model)
    return {"status": "done", "summary": summary, "budget": inv.budget.report()}
