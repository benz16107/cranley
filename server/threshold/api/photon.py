"""Photon events, as forwarded by the webhook service (threshold/photon/webhook.py), which alone faces the internet.

    POST /api/photon/event     one verified event; needs the X-Cranley-Internal header (PHOTON_INTERNAL_TOKEN)
    POST /api/photon/tool/{n}  a voice-agent tool call (ask, run); same header
    GET  /api/photon/status    whether keys are set, and how many chats

Each chat's messages are handled one at a time, in arrival order, on a small pool: a webhook answers in milliseconds
while an agent turn can take minutes."""
from __future__ import annotations

import concurrent.futures
import hmac
import logging
import threading
from collections import defaultdict

from fastapi import APIRouter, Body, Header, HTTPException

from ..config import env
from ..photon import client
from ..photon import router as photon

router = APIRouter(prefix="/api/photon")
log = logging.getLogger("threshold.photon")
_pool = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="photon")
_chat_locks: dict[str, threading.Lock] = defaultdict(threading.Lock)


def _check(token: str | None) -> None:
    want = env().get("PHOTON_INTERNAL_TOKEN")
    if not want or not token or not hmac.compare_digest(token, want):
        raise HTTPException(401, "not from the webhook service")


def _space(event: dict) -> str:
    o = (event.get("data") or {}).get("object") or {}
    return (o.get("space") or {}).get("id") or o.get("id") or "call"


def _run(event: dict) -> None:
    with _chat_locks[_space(event)]:
        try:
            photon.handle(event)
        except Exception:
            log.exception("photon event %s", event.get("id"))


@router.post("/event", status_code=202)
def event(body: dict = Body(...), x_cranley_internal: str | None = Header(None)) -> dict:
    _check(x_cranley_internal)
    _pool.submit(_run, body)
    return {"queued": body.get("type")}


@router.post("/tool/{name}")
def tool(name: str, body: dict = Body(default={}), x_cranley_internal: str | None = Header(None)) -> dict:
    _check(x_cranley_internal)
    from ..photon import voice
    return voice.tool(name, body)


@router.post("/alerts/check")
def alerts_check(x_cranley_internal: str | None = Header(None)) -> dict:
    _check(x_cranley_internal)
    from ..photon import alerts
    return {"sent": alerts.check(photon.state())}


@router.get("/status")
def status() -> dict:
    return {"enabled": client.enabled(), "chats": len(photon.state().data["threads"])}
