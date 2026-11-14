"""Site reports. A field visit from the iPhone app (scan sent, place and business named, report kind chosen) becomes a
workspace whose tools run in the background; any workspace, visit or not, prints as a PDF a business can keep.

    POST /api/report/visit                 start a visit: {sid, kind, business, place, address, contact}
    GET  /api/report/{workspace}/status    which of the visit's tools have finished
    GET  /api/report/{workspace}.pdf       the report (?kind= to choose the tools, ?sid= one scan)
    GET  /api/report/{workspace}.html      the same report as a web page

Reports are printed on request and kept under $THRESHOLD_DATA_DIR/reports_out/ (outside the repo: a report of a
CoStar-backed scan carries CoStar data)."""
from __future__ import annotations

import concurrent.futures
import hashlib
import logging
import re

from fastapi import APIRouter, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field

from ..agent.investigator import Investigation, attach
from ..agent.workspace import BriefSet, Scope, Session, ToolEnable
from ..capture import pair, store
from ..config import DATA
from ..report import KINDS, build, pdf
from ..report.render import html_doc
from ..tools.registry import default_plan
from .agent import _lock, _sessions, session

router = APIRouter(prefix="/api/report")
OUT = DATA / "reports_out"
_pool = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="report-visit")
_visits: dict[str, concurrent.futures.Future] = {}
log = logging.getLogger("threshold.report")
Kind = re.compile("^(" + "|".join(KINDS) + ")$")


class Visit(BaseModel):
    sid: str = Field(max_length=40)
    kind: str = Field("accessibility", pattern=Kind.pattern)
    business: str = Field("", max_length=120)
    place: str = Field("", max_length=120)
    address: str = Field("", max_length=200)
    contact: str = Field("", max_length=120, description="Who the report is for")


def _inputs(tool: str, given: dict, sid: str) -> dict:
    out = {"scan": sid, **given}
    if not sid.startswith("u_"):  # a Matterport scan has panoramas; let the tool read them as it normally would
        out.pop("read_panoramas", None)
    return out


def _run_visit(s: Session, v: Visit) -> None:
    inv = Investigation(s)
    for tool, given in KINDS[v.kind]["tools"]:
        try:
            out = inv.run(tool, _inputs(tool, given, v.sid))
            if out.get("error"):
                log.warning("visit %s: %s did not run: %s", s.base.id, tool, out["error"])
        except Exception:
            log.exception("visit %s: %s failed", s.base.id, tool)


@router.post("/visit")
def visit(v: Visit) -> dict:
    """A new workspace for this visit with the scan in scope, the kind's tools running in the background, and a
    pairing token so the phone's measurements and photos join the same visit."""
    try:
        default_plan(v.sid)
    except Exception:  # noqa: BLE001
        raise HTTPException(404, f"No scan {v.sid[:40]!r} on this server.") from None
    s = attach(Session.create("phone"))  # the phone profile: a visit must not teach the desktop's learned profile
    with _lock:
        _sessions[s.base.id] = s
    spec = KINDS[v.kind]
    who = " at ".join(x for x in (v.business, v.place) if x)
    s.submit(BriefSet(text=f"{spec['title']}{' for ' + who if who else ''}", summary=spec["lede"],
                      scope=Scope(sids=[v.sid], address=v.address or None),
                      facts={"report": v.model_dump()}), by="user")
    for tool, _ in spec["tools"]:
        s.submit(ToolEnable(tool=tool, reason=f"Part of the {spec['title'].lower()}."), by="user")
    _visits[s.base.id] = _pool.submit(_run_visit, s, v)
    tok = pair.issue(s.base.id, hours=72)
    return {"workspace": s.base.id, "token": tok["token"], "kind": v.kind, "status": status(s.base.id)}


@router.get("/kinds")
def kinds() -> list[dict]:
    return [{"id": k, "title": v["title"], "lede": v["lede"], "tools": [t for t, _ in v["tools"]]} for k, v in KINDS.items()]


@router.get("/{workspace}/status")
def status(workspace: str) -> dict:
    s = session(workspace)
    doc = s.doc
    meta = (doc.brief.facts or {}).get("report") or {}
    spec = KINDS.get(meta.get("kind") or "")
    from ..report import _title
    tools = [t for t, _ in spec["tools"]] if spec else list(dict.fromkeys(r.tool for r in doc.runs))
    rows = []
    for t in tools:
        r = next((r for r in reversed(doc.runs) if r.tool == t), None)
        rows.append({"tool": t, "title": _title(t), "status": r.status if r else "waiting",
                     "verdict": r.result.verdict.model_dump() if r and r.result else None, "error": r.error if r else None})
    job = _visits.get(workspace)
    running = (job is not None and not job.done()) or any(r["status"] == "running" for r in rows)
    return {"workspace": workspace, "kind": meta.get("kind"), "business": meta.get("business"), "tools": rows,
            "done": not running, "pdf": f"/api/report/{workspace}.pdf", "html": f"/api/report/{workspace}.html"}


def _report(workspace: str, kind: str | None, sid: str | None, alarms: bool = True) -> tuple[dict, str]:
    s = session(workspace)
    if kind and kind not in KINDS:
        raise HTTPException(422, f"kind must be one of {', '.join(KINDS)}")
    plans = s.plans or default_plan
    caps = store.listing(workspace)
    from ..capture.apply import alarm_in_photo
    rep = build(s.doc, plans, caps, kind=kind, sid=sid, alarm=alarm_in_photo if alarms else None)
    return rep, html_doc(rep, photo=lambda cid: store.image(cid, 480))


def _name(rep: dict) -> str:
    base = re.sub(r"[^A-Za-z0-9]+", "-", f"{rep['business'] or rep['place'] or 'site'} {rep['title']}").strip("-").lower()
    return f"{base[:60] or 'report'}-{rep['date']}"


@router.get("/{workspace}.html", response_class=HTMLResponse)
async def report_html(workspace: str, kind: str | None = Query(None), sid: str | None = Query(None, max_length=40)) -> HTMLResponse:
    _, page = await run_in_threadpool(_report, workspace, kind, sid)
    return HTMLResponse(page)


@router.get("/{workspace}.pdf")
async def report_pdf(workspace: str, kind: str | None = Query(None), sid: str | None = Query(None, max_length=40)) -> Response:
    rep, page = await run_in_threadpool(_report, workspace, kind, sid)
    h = hashlib.sha1(page.split("<footer>")[0].encode()).hexdigest()[:10]  # the footer carries the clock
    f = OUT / workspace / f"{_name(rep)}-{h}.pdf"
    if not f.exists():
        try:
            data = await run_in_threadpool(pdf.from_html, page)
        except pdf.Unavailable as e:
            raise HTTPException(503, str(e)) from None
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(data)
    return Response(f.read_bytes(), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{f.stem[:-11]}.pdf"', "Content-Encoding": "identity",
                             "Cache-Control": "no-store"})
