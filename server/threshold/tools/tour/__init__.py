"""Tour: answers a question by showing. Turns the findings on one scan into a camera tour: from the way in, along
the walking route, to each piece of evidence, with one line to say at each stop.

Every line is a finding's own words (its first sentences), so the narration can only read text and numbers a tool
measured. This tool chooses and orders; it writes nothing of its own."""
from __future__ import annotations

import re

from pydantic import BaseModel, TypeAdapter

from ...geometry._plan import floor_z, rooms_by_id
from .. import (
    Finding,
    Metric,
    ScanScope,
    Source,
    ToolError,
    ToolResult,
    Verdict,
    field,
    tool,
)
from ..registry import REGISTRY, load, run_tool
from ..types import Anchor, Media, RouteOverlay, Status

ANCHOR = TypeAdapter(Anchor)

RANK = {"fail": 3, "warn": 2, "unknown": 1, "pass": 0}
LINE_MAX = 170
SRC = Source(layer="model", method="lookup", confidence="medium",
             note="A tour of findings other tools made; each stop keeps its own finding's words")
# Tools whose findings a tour is made of when none are handed in, by what the question is about. Fast ones only:
# a tour must not start a fire simulation.
TOPICS = {
    "fire": (r"fire|smoke|egress|escape|alarm|captain|pre-?plan|hose|crew", ["egress_routes", "life_safety_census", "door_widths"]),
    "access": (r"wheel|step|access|ramp|door|bathroom|turn|walker|stroller", ["door_widths", "step_free_route", "turning_space", "bathroom_clearance"]),
}
EVERY = ["egress_routes", "door_widths", "life_safety_census", "step_free_route"]


class Evidence(BaseModel):
    """One finding already in the workspace."""
    id: str
    title: str
    status: Status
    detail: str = ""
    anchor: dict | None = None
    tool: str | None = None
    source: dict | None = None
    media: list[dict] = []


class Inputs(BaseModel):
    scan: str = field(source="selection.scan", description="Scan id")
    question: str | None = field(None, description="What the person asked, in their words. It decides which findings "
                                                     "the tour stops at.")
    findings: list[Evidence] | None = field(None, description="Leave this out. The page fills it with the workspace's "
                                                               "findings on this scan; without it the tour gathers "
                                                               "them from the tools that suit the question.")
    min_width_m: float = field(0.813, pref="access.door_width_m", unit="m", gt=0.3, le=2,
                               description="Clear width a door must give, used when the tour gathers findings itself")
    max_stops: int = field(6, ge=2, le=10, description="Most stops")


def sentences(text: str, limit: int = LINE_MAX) -> str:
    """The first sentences of a finding's detail that fit in `limit` characters, unchanged."""
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", " ".join(text.split()))
    out = ""
    for p in parts:
        if out and len(out) + 1 + len(p) > limit:
            break
        out = f"{out} {p}".strip()
    return out


def gather(ctx, sid: str, question: str | None, min_width_m: float) -> list[Evidence]:
    """Findings from the tools that suit the question, run with the person's door width."""
    load()
    q = (question or "").lower()
    ids = [t for _, (pat, tools) in TOPICS.items() if re.search(pat, q) for t in tools] or EVERY
    if "egress_routes" in ids:
        try:  # the smoke clock only when its fire model has already run on this scan
            from ...world import smoke
            if smoke.timeline(ctx.plan(sid)).get("available"):
                ids.append("smoke_clock")
        except Exception:  # noqa: BLE001, S110 - an extra, never a reason to fail the tour
            pass
    out: list[Evidence] = []
    for tid in dict.fromkeys(ids):
        t = REGISTRY.get(tid)
        if t is None:
            continue
        given = {"scan": sid}
        for name, f in t.inputs.model_fields.items():
            if (f.json_schema_extra or {}).get("x-pref") == "access.door_width_m":
                given[name] = min_width_m
        try:
            r = run_tool(tid, given)
        except ToolError as e:
            ctx.step(f"{t.manifest.title} gave nothing: {str(e)[:120]}")
            continue
        ctx.step(f"{t.manifest.title}: {len(r.findings)} findings")
        out += [Evidence(**f.model_dump(mode="json"), tool=tid) for f in r.findings]
    return out


def relevance(question: str | None, e: Evidence) -> int:
    words = {w[:6] for w in re.findall(r"[a-z]{4,}", (question or "").lower())}
    text = f"{e.title} {e.detail} {e.tool or ''}".lower()
    return min(3, sum(1 for w in words if w in text))


def look_at(plan: dict, e: Evidence) -> dict | None:
    """Where to stand and look for evidence a vision model found in a panorama: at its box, or up at the ceiling when
    the finding is that nothing was seen there."""
    m = next((m for m in e.media if m.get("kind") == "pano"), None)
    if not m or m["ref"].count("/") != 2:
        return None
    sid, pano_id, face = m["ref"].split("/")
    pano = next((p for p in plan.get("panos") or [] if p["id"] == pano_id), None)
    if pano is None or sid != plan["sid"]:
        return None
    if m.get("box"):
        try:
            from ...vision import locate as loc
            from ...vision.reader import FACE_PX
            a = loc.locate(plan, pano, int(face), [v * FACE_PX for v in m["box"]], FACE_PX)["anchor"]
            return {"sid": sid, "pano": pano_id, "yaw_deg": a["yaw_deg"], "pitch_deg": a["pitch_deg"]}
        except Exception:  # noqa: BLE001 - fall back to the finding's own anchor
            return None
    return {"sid": sid, "pano": pano_id, "yaw_deg": 0.0, "pitch_deg": 62.0} if face == "0" else None


def _rooms(plan: dict, anchor: dict | None) -> list[str]:
    if not anchor:
        return []
    if "room" in anchor:
        return [anchor["room"]]
    if "opening" in anchor:
        o = next((o for o in plan.get("openings") or [] if o["id"] == anchor["opening"]), None)
        return list(o.get("rooms") or []) if o else []
    if "pano" in anchor:
        p = next((p for p in plan.get("panos") or [] if p["id"] == anchor["pano"]), None)
        return [p["room"]] if p and p.get("room") else []
    return []


def build(plan: dict, question: str | None, evidence: list[Evidence], max_stops: int, step=lambda _t: None) -> dict:
    """The stops, in walking order from the way in, and the path between them. Pure but for the route engine."""
    sid = plan["sid"]
    here = [e for e in evidence if e.anchor and e.anchor.get("sid", sid) == sid and "geo" not in e.anchor
            and (e.tool or "") != "tour" and not e.id.startswith("tour:")]
    best: dict[str, Evidence] = {}
    score = lambda e: (RANK[e.status] * 2 + relevance(question, e), len(e.detail))
    for e in here:   # one stop per place: the worst finding there
        key = str(sorted((k, str(v)) for k, v in e.anchor.items() if k != "sid"))
        if key not in best or score(e) > score(best[key]):
            best[key] = e
    ranked = sorted(best.values(), key=score, reverse=True)
    worth = [e for e in ranked if e.status != "pass"] or ranked
    # one stop from each tool before a second from any: a tour shows each kind of evidence (a narrow door, a bedroom
    # with no alarm seen, a room lost to smoke) before it repeats one. Tools go in order of their worst finding.
    by_tool: dict[str | None, list[Evidence]] = {}
    for e in worth:
        by_tool.setdefault(e.tool, []).append(e)
    rounds = [[g[i] for g in by_tool.values() if i < len(g)] for i in range(max(map(len, by_tool.values()), default=0))]
    chosen = [e for r in rounds for e in r][:max_stops]
    # walking order: distance of each stop's room from the way in, entry floor first
    dist: dict[str, float] = {}
    exit_opening, routes = None, {}
    try:
        from ..egress_routes import Inputs as EgressInputs
        from ..egress_routes import analyse
        a = analyse(plan, EgressInputs.model_fields["min_width_m"].default)
        routes = {k: v for k, v in a["routes"].items() if v["available"]}
        dist = {k: v["length_m"] for k, v in routes.items()}
        if a["exits"]:
            exit_opening = max(a["exits"], key=lambda e: e.get("width") or 0)
    except Exception as ex:  # noqa: BLE001 - no wall graph: the tour keeps the order of importance
        step(f"No walking routes for this scan ({str(ex)[:80]}); stops are in order of importance")
    z, rooms = floor_z(plan), rooms_by_id(plan)

    def order(e: Evidence):
        rs = _rooms(plan, e.anchor)
        fl = min((z.get(rooms[r]["floor"], 0.0) for r in rs if r in rooms), default=0.0)
        return (round(fl, 1), min((dist.get(r, 1e6) for r in rs), default=1e6))
    chosen.sort(key=order)
    # the way in comes first when a finding is about it
    if exit_opening is not None:
        door = next((e for e in here if e.anchor.get("opening") == exit_opening["id"]), None)
        if door is not None:
            chosen = [door] + [e for e in chosen if e is not door][:max_stops - 1]
    stops = []
    for i, e in enumerate(chosen):
        stops.append({"id": f"tour:{sid}:{i:02d}", "title": e.title, "status": e.status,
                      "line": sentences(e.detail) or e.title, "anchor": look_at(plan, e) or e.anchor,
                      "from": e.id, "tool": e.tool, "source": e.source, "media": e.media, "rooms": _rooms(plan, e.anchor)})
    # the path walked: the egress engine's own route from the farthest stop's room to the way in
    legs = []
    far = max((r for s in stops for r in s["rooms"] if r in routes), key=lambda r: dist[r], default=None)
    if far is not None:
        legs = [leg["overlay"] for leg in routes[far]["legs"] if not leg.get("stairs") and len(leg["overlay"]["points"]) > 1]
    return {"stops": stops, "legs": legs, "considered": len(here)}


@tool(id="tour", title="Tour", icon="walk",
      summary="Answers by showing: a camera tour from the way in to each piece of evidence the other tools found, "
              "with one spoken line at each stop.",
      model_description="Call this last on a scan, after the other tools have run there. It turns their findings into a "
                        "camera tour that answers the person's question by showing: from the way in, along the route, "
                        "stopping at each finding that matters (a narrow door, a bedroom with no smoke alarm seen, a "
                        "room that floods). Pass the person's question. Suits a fire captain's pre-plan and a wheelchair "
                        "user's check of a home. Returns the stops in order; each is a finding id.",
      personas=["fire_captain", "wheelchair_user", "wheelchair_home_search", "fire_training_officer"],
      requires=[{"layer": "matterport.rooms"}, {"layer": "matterport.openings", "need": "optional",
                                                "fallback": "stops in order of importance, no walking path"}],
      blocks=["VerdictHeader", "EvidenceStrip", "StepLog"], overlays=["route"],
      examples=["Show me what matters for a fire crew in this house", "Walk me through what a wheelchair user would hit"])
def run(ctx, inputs: Inputs) -> ToolResult:
    sid = inputs.scan
    plan = ctx.plan(sid)
    evidence = inputs.findings
    if evidence is None:
        evidence = gather(ctx, sid, inputs.question, inputs.min_width_m)
    else:
        ctx.step(f"Took {len(evidence)} findings from the workspace")
    t = build(plan, inputs.question, evidence, inputs.max_stops, ctx.step)
    stops = t["stops"]
    scope = ScanScope(sid=sid)
    if not stops:
        return ToolResult(scope=scope, verdict=Verdict(status="unknown", text=(
            "There is nothing to tour yet: no finding on this scan has a place in the building. Run the tools that "
            "answer the question first, then the tour.")))
    ctx.step(f"Chose {len(stops)} stops from {t['considered']} placed findings, in walking order from the way in")
    findings = []
    for s in stops:
        anchor = ANCHOR.validate_python({"sid": sid, **s["anchor"]})
        src = Source(**s["source"]) if s["source"] else SRC
        findings.append(Finding(id=s["id"], title=s["title"], status=s["status"], detail=s["line"], anchor=anchor,
                                source=src, media=[Media(**m) for m in s["media"] if m.get("kind") in ("pano", "ortho", "drone", "phone")]))
    worst = max(stops, key=lambda s: RANK[s["status"]])["status"]
    overlays = [RouteOverlay(floor=leg["floor"], points=leg["points"], chokes=[], label="Tour") for leg in t["legs"]]
    return ToolResult(
        scope=scope,
        verdict=Verdict(status=worst, text=f"A tour of {len(stops)} findings on this scan, from the way in. Play it "
                                           "from the building's toolbar; each stop reads its finding's own words."),
        metrics=[Metric(id="stops", label="Stops", value=len(stops), unit="", source=SRC),
                 Metric(id="considered", label="Findings considered", value=t["considered"], unit="", source=SRC)],
        findings=findings, overlays=overlays)
