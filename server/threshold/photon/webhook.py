"""The only Cranley process the internet can reach (through Tailscale Funnel). It answers two paths and nothing else:

    POST /photon/webhook    a Photon event: Standard Webhooks signature checked (PHOTON_WEBHOOK_SECRET), then forwarded
    POST /voice/tool/{name} an ElevenLabs agent's tool call: shared secret header checked (VOICE_TOOL_SECRET)

Both forward to the private API on 127.0.0.1 (PHOTON_API_ORIGIN, default http://127.0.0.1:8911) with the internal token.
Everything else is 404. No sponsor data passes through here: it only relays events in and small JSON answers out.

    uv run python -m threshold.photon.webhook --port 8912
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import time

import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from ..config import env

TOLERANCE_S = 300   # Standard Webhooks: reject timestamps more than five minutes off
MAX_BODY = 1_000_000


def verify(secret: str, msg_id: str, timestamp: str, body: bytes, signatures: str, now: float | None = None) -> bool:
    """Standard Webhooks: HMAC-SHA256 over "id.timestamp.body" with the base64 key after "whsec_"."""
    try:
        ts = int(timestamp)
    except ValueError:
        return False
    if abs((now or time.time()) - ts) > TOLERANCE_S:
        return False
    key = base64.b64decode(secret.removeprefix("whsec_"))
    want = base64.b64encode(hmac.new(key, f"{msg_id}.{timestamp}.".encode() + body, hashlib.sha256).digest()).decode()
    return any(hmac.compare_digest(want, s.split(",", 1)[1]) for s in signatures.split() if s.startswith("v1,"))


def _origin() -> str:
    return env().get("PHOTON_API_ORIGIN", "http://127.0.0.1:8911")


def _forward(path: str, body: bytes) -> Response:
    try:
        r = httpx.post(_origin() + path, content=body, timeout=25,
                       headers={"content-type": "application/json", "x-cranley-internal": env().get("PHOTON_INTERNAL_TOKEN", "")})
    except httpx.HTTPError:
        return Response(status_code=503)  # Photon retries 5xx
    return Response(r.content, status_code=r.status_code, media_type="application/json")


async def photon_event(req: Request) -> Response:
    body = await req.body()
    if len(body) > MAX_BODY:
        return Response(status_code=413)
    secret = env().get("PHOTON_WEBHOOK_SECRET")
    h = req.headers
    if not secret or not verify(secret, h.get("webhook-id", ""), h.get("webhook-timestamp", ""), body, h.get("webhook-signature", "")):
        return Response(status_code=400)
    return _forward("/api/photon/event", body)


async def voice_tool(req: Request) -> Response:
    want = env().get("VOICE_TOOL_SECRET")
    got = req.headers.get("x-cranley-tool-secret", "")
    if not want or not hmac.compare_digest(got, want):
        return Response(status_code=401)
    body = await req.body()
    if len(body) > MAX_BODY:
        return Response(status_code=413)
    name = req.path_params["name"]
    if not name.isidentifier():
        return Response(status_code=404)
    return _forward(f"/api/photon/tool/{name}", body or b"{}")


async def health(_: Request) -> Response:
    return JSONResponse({"ok": True})


app = Starlette(routes=[Route("/photon/webhook", photon_event, methods=["POST"]),
                        Route("/voice/tool/{name}", voice_tool, methods=["POST"]),
                        Route("/photon/health", health, methods=["GET"])])


def main() -> None:
    import uvicorn
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=8912)
    a = p.parse_args()
    uvicorn.run(app, host="127.0.0.1", port=a.port, log_level="info")


if __name__ == "__main__":
    main()
