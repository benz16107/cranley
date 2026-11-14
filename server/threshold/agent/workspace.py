"""Contract 5: the workspace document, its sixteen operations, a pure reducer, the validator that cleans agent
ops, an append-only log with undo, and JSON persistence under $THRESHOLD_DATA_DIR/workspaces/.

The agent and the user change a workspace only through `Session.submit(op)`. The web app renders `doc`.
"""
from __future__ import annotations

import json
import re
import threading
import time
import uuid
from collections.abc import Callable
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from ..config import DATA
from ..tools.types import (
    Anchor,
    Finding,
    GeoAnchor,
    LensOverlay,
    OpeningAnchor,
    Overlay,
    PanoAnchor,
    PinsOverlay,
    PointAnchor,
    RoomAnchor,
    Status,
    ToolResult,
    WallAnchor,
)

SCHEMA = "workspace/1"
STORE = DATA / "workspaces"
By = Literal["agent", "user", "system"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


# ---- Panel blocks: the only twelve things a panel may contain. Blocks bind to runs and findings by id. ----

class VerdictHeader(Strict):
    type: Literal["VerdictHeader"] = "VerdictHeader"
    run: str = Field(description="Run id; shows result.verdict")


class MetricRow(Strict):
    type: Literal["MetricRow"] = "MetricRow"
    run: str
    metrics: list[str] = Field(max_length=4, description="Metric ids in result.metrics, each shown with its source")


class CheckList(Strict):
    type: Literal["CheckList"] = "CheckList"
    run: str
    checks: list[str] | None = Field(None, description="Check ids; null means all, worst first")
    status: list[Status] | None = Field(None, description="Show only these statuses; null means all")


class EvidenceStrip(Strict):
    type: Literal["EvidenceStrip"] = "EvidenceStrip"
    findings: list[str] = Field(description="Workspace finding ids; each thumbnail flies to its anchor")


class RankedColumn(Strict):
    metric: str = Field(description="Metric id read from each row's run result")
    label: str
    better: Literal["higher", "lower"]


class RankedTable(Strict):
    type: Literal["RankedTable"] = "RankedTable"
    title: str
    columns: list[RankedColumn] = Field(max_length=6)
    rows: list[str] = Field(description="Run ids, one per candidate building")


class MiniChart(Strict):
    type: Literal["MiniChart"] = "MiniChart"
    run: str
    title: str
    metrics: list[str] = Field(description="Metric ids; one bar each, label and unit from the metric")


class FloorPlanMini(Strict):
    type: Literal["FloorPlanMini"] = "FloorPlanMini"
    sid: str
    floor: str | None = None
    overlays: list[str] = Field(default=[], description="Workspace overlay ids drawn on the plan")


class Control(Strict):
    input: str = Field(description="Tool input name")
    pref: str | None = Field(None, description="Preference key an edit sets (pref.set), which re-runs the tool")
    label: str
    kind: Literal["slider", "select", "toggle"]
    min: float | None = None
    max: float | None = None
    step: float | None = None
    options: list[str] | None = None
    unit: str | None = None


class Controls(Strict):
    type: Literal["Controls"] = "Controls"
    tool: str
    controls: list[Control]


class AssumptionChips(Strict):
    type: Literal["AssumptionChips"] = "AssumptionChips"
    run: str = Field(description="Shows result.assumptions; an editable chip sends pref.set with key = assumption id")


class StepLog(Strict):
    type: Literal["StepLog"] = "StepLog"
    run: str = Field(description="Shows the run's steps")


class Note(Strict):
    type: Literal["Note"] = "Note"
    text: str = Field(max_length=280)


class ActionBar(Strict):
    type: Literal["ActionBar"] = "ActionBar"
    run: str = Field(description="Shows result.actions; each runs its tool with its inputs")


Block = Annotated[VerdictHeader | MetricRow | CheckList | EvidenceStrip | RankedTable | MiniChart | FloorPlanMini
                  | Controls | AssumptionChips | StepLog | Note | ActionBar, Field(discriminator="type")]
BLOCK = TypeAdapter(Block)
MapBlock = Literal["PinSet", "ParcelFill", "Extrusion", "ReachRing", "RouteLine", "OrthoPatch", "HexDensity", "Callout"]


# ---- The document ----

class Scope(Strict):
    sids: list[str] = []
    address: str | None = None


class Brief(Strict):
    text: str = Field("", description="What the person said, in their words")
    summary: str = Field("", description="One line: who they are and what they need")
    persona: str | None = None
    scope: Scope = Scope()
    facts: dict[str, Any] = Field(default={}, description="Answers keyed by preference key (x-pref)")


class Question(Strict):
    id: str
    key: str = Field(description="Preference key the answer fills")
    text: str
    tools: list[str]
    input: dict[str, Any] = Field(description="JSON Schema of the answer (type, minimum, maximum, x-unit)")
    answer: Any = None
    answered: bool = False


class ToolEntry(Strict):
    id: str
    enabled: bool = True
    reason: str = ""
    by: By = "agent"
    status: Literal["ready", "planned"] = "ready"


class Run(Strict):
    id: str
    tool: str
    sid: str | None = None
    inputs: dict[str, Any] = {}
    inputs_from: dict[str, str] = Field(default={}, description="input -> preference key it came from")
    plan_step: str | None = None
    status: Literal["running", "done", "error", "skipped"] = "running"
    started: float | None = None
    finished: float | None = None
    steps: list[str] = []
    summary: str = ""
    error: str | None = None
    result: ToolResult | None = None
    stale: bool = Field(False, description="A preference this run used changed after it finished")


class Feedback(Strict):
    verdict: Literal["rejected", "confirmed"]
    reason: str | None = None


class WsFinding(Finding):
    run: str | None = None
    tool: str | None = None
    feedback: Feedback | None = None
    superseded_by: str | None = Field(None, description="A later run of the same tool on the same scan that no "
                                                        "longer reports this finding; hide it")


class Layer(Strict):
    id: str
    block: MapBlock
    data_ref: str = Field(description="A back-end route, never data")
    label: str = ""
    tool: str | None = None
    run: str | None = None
    visible: bool = True


class WsOverlay(Strict):
    id: str
    sid: str
    overlay: Overlay
    tool: str | None = None
    run: str | None = None
    visible: bool = True


class Panel(Strict):
    id: str
    title: str
    blocks: list[Block]
    tool: str | None = None
    run: str | None = None


class Camera(Strict):
    anchor: Anchor
    reason: str = ""
    at: float | None = None


class PlanStep(Strict):
    id: str
    text: str
    status: Literal["pending", "in_progress", "completed"] = "pending"


class Pref(Strict):
    key: str
    value: Any
    reason: str = Field("", description="The event it came from, said to the person")
    cause: int | None = Field(None, description="Log seq of the op it was learned from")
    by: By = "user"
    at: float | None = None


class ShortlistItem(Strict):
    sid: str
    note: str = ""
    by: By = "user"


class Workspace(Strict):
    schema_: Literal["workspace/1"] = Field(SCHEMA, alias="schema")
    id: str
    profile: str = "default"
    created: float = 0
    updated: float = 0
    brief: Brief = Brief()
    questions: list[Question] = []
    tools: list[ToolEntry] = []
    runs: list[Run] = []
    findings: list[WsFinding] = []
    layers: list[Layer] = []
    overlays: list[WsOverlay] = []
    panels: list[Panel] = []
    camera: Camera | None = None
    plan: list[PlanStep] = []
    prefs: dict[str, Pref] = {}
    shortlist: list[ShortlistItem] = []
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


# ---- The sixteen operations ----

class OpBase(Strict):
    by: By = "agent"
    run: str | None = Field(None, description="Agent turn or tool run this op belongs to")


class BriefSet(OpBase):
    op: Literal["brief.set"] = "brief.set"
    text: str | None = None
    summary: str | None = None
    persona: str | None = None
    scope: Scope | None = None
    facts: dict[str, Any] | None = None


class QuestionAsk(OpBase):
    op: Literal["question.ask"] = "question.ask"
    question: Question


class QuestionAnswer(OpBase):
    op: Literal["question.answer"] = "question.answer"
    id: str
    value: Any


class ToolEnable(OpBase):
    op: Literal["tool.enable"] = "tool.enable"
    tool: str
    reason: str = ""
    status: Literal["ready", "planned"] = "ready"


class ToolDisable(OpBase):
    op: Literal["tool.disable"] = "tool.disable"
    tool: str
    reason: str = ""


class RunStart(OpBase):
    op: Literal["run.start"] = "run.start"
    record: Run


class RunFinish(OpBase):
    op: Literal["run.finish"] = "run.finish"
    id: str
    status: Literal["done", "error", "skipped"]
    summary: str = ""
    steps: list[str] = []
    error: str | None = None
    result: ToolResult | None = None


class FindingAdd(OpBase):
    op: Literal["finding.add"] = "finding.add"
    finding: WsFinding


class LayerUpsert(OpBase):
    op: Literal["layer.upsert"] = "layer.upsert"
    layer: Layer


class OverlayUpsert(OpBase):
    op: Literal["overlay.upsert"] = "overlay.upsert"
    overlay: WsOverlay


class PanelUpsert(OpBase):
    op: Literal["panel.upsert"] = "panel.upsert"
    panel: Panel


class CameraFocus(OpBase):
    op: Literal["camera.focus"] = "camera.focus"
    anchor: Anchor
    reason: str = ""


class PlanSet(OpBase):
    op: Literal["plan.set"] = "plan.set"
    steps: list[PlanStep]


class PrefSet(OpBase):
    op: Literal["pref.set"] = "pref.set"
    key: str
    value: Any = Field(description="null removes the preference")
    reason: str = ""
    cause: int | None = None


class ShortlistAdd(OpBase):
    op: Literal["shortlist.add"] = "shortlist.add"
    sid: str
    note: str = ""


class ShortlistRemove(OpBase):
    op: Literal["shortlist.remove"] = "shortlist.remove"
    sid: str


OP_TYPES = (BriefSet, QuestionAsk, QuestionAnswer, ToolEnable, ToolDisable, RunStart, RunFinish, FindingAdd, LayerUpsert,
            OverlayUpsert, PanelUpsert, CameraFocus, PlanSet, PrefSet, ShortlistAdd, ShortlistRemove)
Op = Annotated[Union[OP_TYPES], Field(discriminator="op")]  # a tuple needs Union[]
OP = TypeAdapter(Op)
OP_NAMES = [t.model_fields["op"].default for t in OP_TYPES]


class LogEntry(Strict):
    seq: int
    at: float
    op: Op | None = None
    undo: int | None = Field(None, description="Seq of the entry this one undoes")
    cause: int | None = Field(None, description="Seq of the user op this entry was learned from")


# ---- Reducer ----

def _upsert(items: list, item, key: str = "id") -> None:
    for i, x in enumerate(items):
        if getattr(x, key) == getattr(item, key):
            items[i] = item  # in place: nothing the user placed moves
            return
    items.append(item)


def apply(doc: Workspace, op: BaseModel, at: float | None = None) -> Workspace:
    """Pure: returns a new document with `op` applied."""
    d = doc.model_copy(deep=True)
    at = at if at is not None else time.time()
    d.updated = at
    match op:
        case BriefSet():
            for k in ("text", "summary", "persona", "scope"):
                if getattr(op, k) is not None:
                    setattr(d.brief, k, getattr(op, k))
            if op.facts:
                d.brief.facts = {**d.brief.facts, **op.facts}
        case QuestionAsk():
            _upsert(d.questions, op.question)
        case QuestionAnswer():
            for q in d.questions:
                if q.id == op.id:
                    q.answer, q.answered = op.value, True
                    d.brief.facts = {**d.brief.facts, q.key: op.value}
        case ToolEnable():
            _upsert(d.tools, ToolEntry(id=op.tool, reason=op.reason, by=op.by, status=op.status))
        case ToolDisable():
            for t in d.tools:
                if t.id == op.tool:
                    t.enabled = False
                    t.by = op.by
                    t.reason = op.reason or t.reason
        case RunStart():
            _upsert(d.runs, op.record.model_copy(update={"started": op.record.started or at}))
        case RunFinish():
            for r in d.runs:
                if r.id == op.id:
                    r.status, r.summary, r.error, r.result, r.finished = op.status, op.summary, op.error, op.result, at
                    r.steps = op.steps or r.steps
        case FindingAdd():
            _upsert(d.findings, op.finding)
        case LayerUpsert():
            _upsert(d.layers, op.layer)
        case OverlayUpsert():
            _upsert(d.overlays, op.overlay)
        case PanelUpsert():
            _upsert(d.panels, op.panel)
        case CameraFocus():
            d.camera = Camera(anchor=op.anchor, reason=op.reason, at=at)
        case PlanSet():
            d.plan = op.steps
        case PrefSet():
            if op.value is None:
                d.prefs.pop(op.key, None)
            else:
                d.prefs[op.key] = Pref(key=op.key, value=op.value, reason=op.reason, cause=op.cause, by=op.by, at=at)
            for r in d.runs:
                if r.status == "done" and op.key in r.inputs_from.values():
                    r.stale = True
        case ShortlistAdd():
            _upsert(d.shortlist, ShortlistItem(sid=op.sid, note=op.note, by=op.by), key="sid")
        case ShortlistRemove():
            d.shortlist = [s for s in d.shortlist if s.sid != op.sid]
        case _:
            raise TypeError(f"not an op: {op!r}")
    return d


# ---- Validator: clean what the agent emits (the tldraw rule) ----

MEASURE = re.compile(r"\d+(?:[.,]\d+)?\s?(?:m²|m2|sq ?ft|sqft|cm|mm|m|in|inches|ft|feet|metres|meters|%)(?![A-Za-z])")


class Rejected(ValueError):
    pass


def known_sids(doc: Workspace) -> set[str]:
    return set(doc.brief.scope.sids) | {r.sid for r in doc.runs if r.sid}


def anchor_ok(a: Any, doc: Workspace, plans: Callable[[str], dict]) -> bool:
    if isinstance(a, GeoAnchor):
        return -180 <= a.geo[0] <= 180 and -90 <= a.geo[1] <= 90
    if a.sid not in known_sids(doc):
        return False
    try:
        p = plans(a.sid)
    except Exception:
        return False
    match a:
        case RoomAnchor():
            return any(r["id"] == a.room for r in p["rooms"])
        case OpeningAnchor():
            return any(o["id"] == a.opening for o in p["openings"])
        case WallAnchor():
            return any(w["id"] == a.wall for w in p["walls"])
        case PanoAnchor():
            return any(x["id"] == a.pano for x in p["panos"])
        case PointAnchor():
            return True
    return False


def _unique(existing: set[str], wanted: str) -> str:
    i, out = 2, wanted
    while out in existing:
        out, i = f"{wanted}~{i}", i + 1
    return out


def clean(doc: Workspace, raw: dict | BaseModel, plans: Callable[[str], dict], tools: set[str]) -> tuple[Any, list[str]]:
    """Validate one agent op. Returns (op, notes); raises Rejected when nothing usable is left.
    Drops unknown panel blocks and blocks that name missing runs, strips anchors that name a scan, room, opening,
    wall or panorama that does not exist, makes ids unique, rejects unknown tools and model-typed measurements."""
    notes: list[str] = []
    raw = raw.model_dump(by_alias=True) if isinstance(raw, BaseModel) else json.loads(json.dumps(raw))
    if raw.get("op") == "panel.upsert" and isinstance(raw.get("panel"), dict):
        runs = {r.id for r in doc.runs}
        kept = []
        for b in raw["panel"].get("blocks") or []:
            try:
                blk = BLOCK.validate_python(b)
            except ValidationError:
                notes.append(f"dropped block {b.get('type') if isinstance(b, dict) else b!r}")
                continue
            if getattr(blk, "run", None) and blk.run not in runs:
                notes.append(f"dropped {blk.type}: no run {blk.run}")
                continue
            if isinstance(blk, Note) and MEASURE.search(blk.text):
                notes.append("dropped Note: a measurement in model text")
                continue
            kept.append(blk.model_dump())
        if not kept:
            raise Rejected("panel has no valid blocks")
        raw["panel"]["blocks"] = kept
    try:
        op = OP.validate_python(raw)
    except ValidationError as e:
        raise Rejected(f"invalid op: {e.errors()[0]['msg']} at {e.errors()[0]['loc']}") from None

    match op:
        case ToolEnable() | ToolDisable() if op.tool not in tools:
            raise Rejected(f"unknown tool {op.tool}")
        case RunStart() if op.record.tool not in tools:
            raise Rejected(f"unknown tool {op.record.tool}")
        case FindingAdd():
            f = op.finding
            if f.anchor is not None and not anchor_ok(f.anchor, doc, plans):
                notes.append(f"stripped anchor of {f.id}")
                f.anchor = None  # shows as "unanchored"
            clash = next((x for x in doc.findings if x.id == f.id), None)
            if clash and clash.tool != f.tool:
                f.id = _unique({x.id for x in doc.findings}, f.id)
            if MEASURE.search(f.title) and f.tool is None:
                raise Rejected("finding title states a measurement the agent typed")
        case CameraFocus() if not anchor_ok(op.anchor, doc, plans):
            raise Rejected("camera anchor names something that does not exist")
        case OverlayUpsert():
            o = op.overlay
            if o.sid not in known_sids(doc):
                raise Rejected(f"overlay on unknown scan {o.sid}")
            if isinstance(o.overlay, PinsOverlay):
                o.overlay.pins = [p for p in o.overlay.pins if anchor_ok(p.anchor, doc, plans)]
            if isinstance(o.overlay, LensOverlay):
                rooms = {r["id"] for r in plans(o.sid)["rooms"]}
                o.overlay.values = {k: v for k, v in o.overlay.values.items() if k in rooms}
        case ShortlistAdd() if op.sid not in known_sids(doc):
            raise Rejected(f"unknown scan {op.sid}")
        case QuestionAsk():
            q = op.question
            prior = next((x for x in doc.questions if x.id == q.id), None)
            if prior and prior.key != q.key:
                q.id = _unique({x.id for x in doc.questions}, q.id)
        case PlanSet():
            seen: set[str] = set()
            for s in op.steps:
                s.id = _unique(seen, s.id)
                seen.add(s.id)
    return op, notes


# ---- Log, undo, persistence ----

def replay(base: Workspace, log: list[LogEntry]) -> Workspace:
    undone = {e.undo for e in log if e.undo is not None}
    changed = True
    while changed:  # an undone op takes the preferences learned from it along
        before = len(undone)
        undone |= {e.seq for e in log if e.cause in undone}
        changed = len(undone) != before
    doc = base
    for e in log:
        if e.op is not None and e.seq not in undone:
            doc = apply(doc, e.op, e.at)
    return doc


def _no_plans(sid: str) -> dict:
    raise LookupError(sid)


class Session:
    """One workspace: its log and the document it folds to. Thread-safe; subagents submit in parallel."""

    def __init__(self, id: str, profile: str = "default", created: float | None = None,
                 log: list[LogEntry] | None = None, root=None):
        self.root = root or STORE
        self.base = Workspace(id=id, profile=profile, created=created or time.time())
        self.log = log or []
        self.doc = replay(self.base, self.log)
        self.lock = threading.RLock()
        self.listeners: list[Callable[[LogEntry], None]] = []
        self.plans: Callable[[str], dict] | None = None  # set by the agent; used to check anchors
        self.tools: set[str] | None = None

    # persistence
    @property
    def path(self):
        return self.root / f"{self.base.id}.json"

    def save(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"id": self.base.id, "profile": self.base.profile, "created": self.base.created,
                                   "log": [e.model_dump(mode="json", by_alias=True) for e in self.log]}))
        tmp.replace(self.path)
        # shortcut: the profile is this workspace's prefs, last write wins; two live workspaces on one profile
        # overwrite each other. Merge by key with timestamps when there are real users.
        prof = self.root / "profiles" / f"{self.base.profile}.json"
        prof.parent.mkdir(exist_ok=True)
        prof.write_text(json.dumps({k: v.model_dump(mode="json") for k, v in self.doc.prefs.items()}))

    @classmethod
    def load(cls, id: str, root=None) -> Session:
        f = (root or STORE) / f"{id}.json"
        if not f.exists():
            raise LookupError(f"no workspace {id}")
        d = json.loads(f.read_text())
        return cls(d["id"], d["profile"], d["created"], [LogEntry.model_validate(e) for e in d["log"]], root)

    @classmethod
    def create(cls, profile: str = "default", root=None) -> Session:
        """A new workspace that starts with what this profile learned in earlier sessions."""
        s = cls(new_id("ws"), profile, root=root)
        prof = s.root / "profiles" / f"{profile}.json"
        for p in (json.loads(prof.read_text()).values() if prof.exists() else []):
            s.submit(PrefSet(by="system", key=p["key"], value=p["value"],
                             reason=p.get("reason") or "From an earlier session"))
        s.save()
        return s

    # changes
    def _append(self, op: BaseModel | None, undo: int | None = None, cause: int | None = None) -> LogEntry:
        e = LogEntry(seq=len(self.log) + 1, at=time.time(), op=op, undo=undo, cause=cause)
        self.log.append(e)
        if op is not None:
            self.doc = apply(self.doc, op, e.at)
        for fn in self.listeners:
            fn(e)
        return e

    def submit(self, op: dict | BaseModel, by: By | None = None, cause: int | None = None) -> list[LogEntry]:
        """Validate and apply one op, then learn from it if the user made it. Returns the entries appended."""
        from . import prefs  # prefs reads this module's types
        with self.lock:
            raw = op.model_dump(by_alias=True) if isinstance(op, BaseModel) else dict(op)
            if by:
                raw["by"] = by
            if raw.get("by", "agent") == "agent":
                parsed, _ = clean(self.doc, raw, self.plans or _no_plans,
                                  self.tools if self.tools is not None else {t.id for t in self.doc.tools})
            else:
                try:
                    parsed = OP.validate_python(raw)
                except ValidationError as e:
                    raise Rejected(str(e.errors()[0]["msg"]) + f" at {e.errors()[0]['loc']}") from None
            before = self.doc
            entries = [self._append(parsed, cause=cause)]
            if parsed.by == "user":
                for learned in prefs.derive(before, parsed):
                    entries.append(self._append(learned, cause=entries[0].seq))
            self.save()
            return entries

    def undo(self, seq: int | None = None) -> LogEntry:
        """Undo one entry (default: the user's latest op not yet undone) and what was learned from it."""
        with self.lock:
            undone = {e.undo for e in self.log if e.undo is not None}
            if seq is None:
                seq = next((e.seq for e in reversed(self.log)
                            if e.op is not None and e.op.by == "user" and e.seq not in undone), None)
            if seq is None or not any(e.seq == seq and e.op is not None for e in self.log) or seq in undone:
                raise LookupError("nothing to undo")
            e = self._append(None, undo=seq)
            self.doc = replay(self.base, self.log)
            self.save()
            return e
