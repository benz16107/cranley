"""Phone captures and pairing. Used by the mobile web app (/m) and the native app alike.

Desktop, by workspace id:
POST /api/workspace/{id}/pair            {token, expires, path}: a link that lets a phone add captures to this workspace
GET  /api/workspace/{id}/captures        the workspace's captures, newest first

Phone, by pairing token (the token never shows the workspace id and opens none of the workspace's own routes):
POST /api/phone/start                    a new workspace for a phone used by itself: {token, expires}
GET  /api/phone/{token}                  the phone view: buildings, tasks, captures, results, open questions
POST /api/phone/{token}/capture?meta=    the file as the raw request body (none for a reading), `meta` as JSON in the
                                         query (capture.store.Meta). Replies with what the capture settled.
POST /api/phone/{token}/locate           {lat, lon, accuracy_m}: runs where_am_i, lists the scanned buildings here
POST /api/phone/{token}/place            {sid}: this is the building the visit is about
POST /api/phone/{token}/brief            {text, sid?}: the person's brief, spoken or typed; the agent works in the background
POST /api/phone/{token}/answer           {id, value}: answer one of the agent's questions
POST /api/phone/{token}/run/{tool}       inputs: a phone tool, or a tool the phone offered (aerial tools at a fix)

Files (a capture id is 64 random bits and is the only key):
GET  /api/capture/{id}                   the record
GET  /api/capture/{id}/file              the photo, video or audio, with Range
GET  /api/capture/{id}/frame/{n}.jpg     a still from a walk-through video
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import logging
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from pydantic import ValidationError

from ..agent.budget import Budget
from ..agent.investigator import attach, turn
from ..agent.workspace import QuestionAnswer, Rejected, Session
from ..capture import apply, frames, pair, store
from ..config import env
from ..tools.where_am_i import AERIAL_ONLY, nearest
from .agent import _lock, _sessions, session

router = APIRouter(prefix="/api")
_work = concurrent.futures.ThreadPoolExecutor(max_workers=3, thread_name_prefix="phone")  # turns and slow tools
_jobs: dict[str, list[concurrent.futures.Future]] = {}
RUNNABLE = {*apply.PHONE_TOOLS, *(t for t, _ in AERIAL_ONLY), "flood_rehearsal"}
PHONE_TURN = {"model_calls": 16, "tool_runs": 10, "parallel": 3}  # a turn started from a phone is a small one
# identity: the gzip middleware leaves a response alone when it names an encoding, and Range needs the raw bytes
RAW = {"Content-Encoding": "identity", "Cache-Control": "private, max-age=3600"}


def paired(token: str) -> Session:
    try:
        return session(pair.check(token))
    except LookupError as e:
        raise HTTPException(401, str(e)) from None


def busy(ws: str) -> bool:
    _jobs[ws] = [j for j in _jobs.get(ws, []) if not j.done()]
    return bool(_jobs[ws])


def background(ws: str, fn, *args) -> None:
    _jobs.setdefault(ws, []).append(_work.submit(fn, *args))


def phone_view(s: Session) -> dict:
    """What the phone shows. No workspace id: the token is the phone's only handle."""
    doc, plans = s.doc, apply.plans_of(s)
    buildings = []
    for sid in doc.brief.scope.sids[-6:]:
        try:
            p = plans(sid)
        except Exception:  # noqa: BLE001 - a scan that will not load is listed without its rooms
            buildings.append({"sid": sid, "name": sid, "address": None, "rooms": [], "walls": False})
            continue
        g = p.get("geo") or {}
        buildings.append({"sid": sid, "name": p.get("name") or sid, "address": p.get("address"), "lat": g.get("lat"),
                          "lon": g.get("lon"), "walls": bool((p.get("quality") or {}).get("walls", p.get("walls"))),
                          "rooms": [{"id": r["id"], "label": r.get("label") or "Unlabelled room", "floor": r.get("floor")}
                                    for r in p.get("rooms") or [] if r.get("label") != "Void"]})
    results, seen = [], set()
    for r in reversed(doc.runs):
        key = (r.tool, r.sid, r.place.key() if r.place else None)
        if key in seen or r.status == "skipped":
            continue
        seen.add(key)
        res = r.result
        results.append({"run": r.id, "tool": r.tool, "sid": r.sid, "status": r.status, "at": r.finished or r.started,
                        "phone": r.tool in apply.PHONE_TOOLS,
                        "verdict": res.verdict.model_dump() if res else None, "error": r.error,
                        "step": r.steps[-1] if r.status == "running" and r.steps else None,
                        "metrics": [m.model_dump(mode="json") for m in res.metrics[:4]] if res else [],
                        "checks": [c.model_dump(mode="json") for c in res.checks[:12]] if res else [],
                        "findings": [f.model_dump(mode="json") for f in res.findings[:12]] if res else [],
                        "actions": [a.model_dump(mode="json") for a in res.actions] if res else []})
    return {"brief": doc.brief.text or None, "summary": doc.brief.summary or None, "buildings": buildings,
            "questions": [{"id": q.id, "text": q.text, "input": q.input} for q in doc.questions if not q.answered],
            "tasks": apply.phone_tasks(s), "captures": [store.public(c) for c in store.listing(doc.id)[-40:]][::-1],
            "results": results[:30], "busy": busy(doc.id) or any(r.status == "running" for r in doc.runs),
            "plan": [{"text": p.text, "status": p.status} for p in doc.plan], "seq": len(s.log)}


@router.post("/workspace/{id}/pair")
def pair_phone(id: str, hours: float = Body(pair.HOURS, gt=0, le=72), origin: str | None = Body(None, max_length=200)) -> dict:
    """A link for a phone, and the same link as a QR code (SVG). `origin` is the address the desktop page is open at;
    THRESHOLD_PHONE_ORIGIN, when set, wins: the HTTPS address a phone can reach (camera and sensors need HTTPS)."""
    import io

    import segno
    session(id)  # 404 for an unknown workspace
    out = pair.issue(id, hours)
    base = (env().get("THRESHOLD_PHONE_ORIGIN") or origin or "").rstrip("/")
    if not base.startswith(("https://", "http://")):
        base = ""
    url = f"{base}/m?t={out['token']}"
    svg = io.BytesIO()
    segno.make(url, error="m").save(svg, kind="svg", border=2, xmldecl=False, svgns=True, nl=False, omitsize=True)
    return {**out, "path": f"/m?t={out['token']}", "url": url, "secure": base.startswith("https://"), "qr": svg.getvalue().decode()}


@router.get("/workspace/{id}/captures")
def workspace_captures(id: str) -> list[dict]:
    session(id)
    return [store.public(c) for c in store.listing(id)][::-1]


@router.post("/phone/start")
def phone_start(profile: str = Body("phone", embed=True, max_length=40)) -> dict:
    s = attach(Session.create(profile))
    with _lock:
        _sessions[s.base.id] = s
    return pair.issue(s.base.id, hours=72)


@router.get("/phone/{token}")
def phone_get(token: str) -> dict:
    return phone_view(paired(token))


async def _body(request: Request, limit: int) -> bytes:
    """The request body, refused as soon as it passes `limit` bytes."""
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        raise HTTPException(413, "That file is too large.")
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            raise HTTPException(413, "That file is too large.")
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/phone/{token}/capture")
async def phone_capture(token: str, request: Request, meta: str = Query(..., max_length=store.META_LIMIT)) -> dict:
    s = paired(token)
    try:
        m = store.Meta.model_validate_json(meta)
    except ValidationError as e:
        raise HTTPException(422, f"Bad capture record: {e.errors()[0]['msg']} at {e.errors()[0]['loc']}") from None
    data = await _body(request, store.LIMIT_MB.get(m.kind, 0) * 1_000_000 + 1024)
    try:
        cap = store.save(s.base.id, m, data or None)
    except store.Rejected as e:
        raise HTTPException(415, str(e)) from None
    try:
        did = await asyncio.to_thread(apply.handle, s, cap)
    except Exception as e:  # noqa: BLE001 - the capture is saved; say that, and keep the cause for the server's log
        logging.getLogger("threshold.capture").exception("capture %s: what it feeds failed", cap["id"])
        did = {"problem": f"The capture is saved, but the step after it failed on the server ({type(e).__name__}). Try again; "
                          "if it keeps failing, type the value instead."}
    return {"capture": store.public(store.get(cap["id"])), **did, "view": phone_view(s)}


@router.post("/phone/{token}/locate")
def phone_locate(token: str, lat: float = Body(...), lon: float = Body(...), accuracy_m: float | None = Body(None)) -> dict:
    s = paired(token)
    here = nearest(lon, lat)
    out, res = apply.run(s, "where_am_i", {"geo": [lon, lat], "accuracy_m": accuracy_m})
    return {"here": here, "verdict": res.verdict.model_dump() if res else None, "error": out.get("error"),
            "actions": [a.model_dump() for a in res.actions] if res else []}


@router.post("/phone/{token}/place")
def phone_place(token: str, sid: str = Body(..., embed=True, max_length=40)) -> dict:
    s = paired(token)
    try:
        apply.plans_of(s)(sid)
    except Exception:  # noqa: BLE001
        raise HTTPException(404, "That scan is not in the index.") from None
    apply.in_scope(s, sid)
    return phone_view(s)


@router.post("/phone/{token}/brief")
def phone_brief(token: str, text: str | None = Body(None, max_length=2000), sid: str | None = Body(None)) -> dict:
    """Start (or continue) an agent turn in the background. The phone reads the view until `busy` is false."""
    s = paired(token)
    if busy(s.base.id):
        raise HTTPException(409, "The agent is still working on the last thing you asked.")
    background(s.base.id, turn, s, text, [sid] if sid else None, None, None, None, Budget(**PHONE_TURN))
    return {"status": "running"}


@router.post("/phone/{token}/answer")
def phone_answer(token: str, id: str = Body(...), value: Any = Body(...)) -> dict:
    s = paired(token)
    try:
        s.submit(QuestionAnswer(id=id, value=value), by="user")
    except Rejected as e:
        raise HTTPException(422, str(e)) from None
    return phone_view(s)


@router.post("/phone/{token}/run/{tool}")
def phone_run(token: str, tool: str, inputs: dict[str, Any] = Body(default={})) -> dict:
    """Run a tool from the phone. Slow ones (the aerial tools read photos) carry on in the background."""
    s = paired(token)
    if tool not in RUNNABLE:
        raise HTTPException(403, "The phone link cannot run that tool.")
    place = inputs.get("place")
    if isinstance(place, dict) and place.get("geo"):  # an aerial tool at the phone's fix: the fix joins the workspace
        from ..agent.workspace import BriefSet, Scope
        from ..tools import Place
        sc, p = s.doc.brief.scope, Place.model_validate(place)
        if not any(x.key() == p.key() for x in sc.places):
            s.submit(BriefSet(scope=Scope(sids=sc.sids, address=sc.address, places=[*sc.places, p])), by="user")
    apply.in_scope(s, inputs.get("scan"))
    job = _work.submit(apply.run, s, tool, inputs)
    _jobs.setdefault(s.base.id, []).append(job)
    try:
        out, res = job.result(timeout=4)
    except concurrent.futures.TimeoutError:
        return {"status": "running", "view": phone_view(s)}
    return {"status": "done", "run": out.get("run"), "error": out.get("error"),
            "verdict": res.verdict.model_dump() if res else None, "view": phone_view(s)}


@router.get("/capture/{id}")
def capture_record(id: str) -> dict:
    try:
        return store.public(store.get(id))
    except LookupError:
        raise HTTPException(404, "No such capture") from None


@router.get("/capture/{id}/file")
def capture_file(id: str) -> FileResponse:
    try:
        rec, p = store.get(id), store.path(id)
    except LookupError:
        raise HTTPException(404, "No such capture") from None
    if p is None or not p.exists():
        raise HTTPException(404, "This capture is a reading; it has no file")
    return FileResponse(p, media_type=rec["mime"], headers=RAW)


@router.get("/capture/{id}/frame/{n}.jpg")
def capture_frame(id: str, n: int) -> Response:
    try:
        return Response(frames.frame(id, n), media_type="image/jpeg", headers=RAW)
    except LookupError:
        raise HTTPException(404, "No such frame") from None
