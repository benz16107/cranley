"""Pairing tokens. A token names one workspace and an expiry and is signed with a secret kept in the data folder,
so nothing is stored per token. Whoever holds it can add captures to that workspace and read the phone view of it
until it expires; it never shows the workspace id and opens none of the workspace's own routes."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time

from . import store

HOURS = 8.0  # one visit to a building; the desktop makes a new one with a click


def _key() -> bytes:
    f = store.ROOT / ".pairing-secret"
    if not f.exists():
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(secrets.token_bytes(32))
        f.chmod(0o600)
    return f.read_bytes()


def _sign(body: bytes) -> str:
    return base64.urlsafe_b64encode(hmac.new(_key(), body, hashlib.sha256).digest()[:16]).decode().rstrip("=")


def issue(workspace: str, hours: float = HOURS, now: float | None = None) -> dict:
    # shortcut: a token cannot be revoked before it expires; keep a deny list here if that is ever needed
    expires = int((now or time.time()) + hours * 3600)
    body = f"{workspace}.{expires}".encode()
    return {"token": base64.urlsafe_b64encode(body).decode().rstrip("=") + "." + _sign(body), "expires": expires}


def check(token: str, now: float | None = None) -> str:
    """The workspace a token opens. Raises LookupError for a forged, damaged or expired one."""
    try:
        b64, sig = token.split(".")
        body = base64.urlsafe_b64decode(b64 + "=" * (-len(b64) % 4))
        workspace, expires = body.decode().rsplit(".", 1)
        ok = hmac.compare_digest(sig, _sign(body)) and int(expires) > (now or time.time())
    except (ValueError, TypeError):  # damaged base64, a missing part, or characters no signature has
        ok = False
    if not ok:
        raise LookupError("This phone link has expired. Open a new one from the desktop.")
    return workspace
