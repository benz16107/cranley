"""Pairing tokens. A token names one workspace and an expiry, sealed (AES-GCM: encrypted and authenticated) with a
secret kept in the data folder, so nothing is stored per token. Whoever holds it can add captures to that workspace and
read the phone view of it until it expires; the workspace id cannot be read out of it, and it opens none of the
workspace's own routes."""
from __future__ import annotations

import base64
import os
import secrets
import time

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from . import store

HOURS = 8.0  # one visit to a building; the desktop makes a new one with a click


def _key() -> bytes:
    f = store.ROOT / ".pairing-secret"
    f.parent.mkdir(parents=True, exist_ok=True)
    try:  # O_EXCL: two first requests cannot each write a different key, and the file is never world-readable
        fd = os.open(f, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        pass
    else:
        with os.fdopen(fd, "wb") as out:
            out.write(secrets.token_bytes(32))
    key = f.read_bytes()
    if len(key) != 32:  # read while the first writer was still writing
        time.sleep(0.05)
        key = f.read_bytes()
    return key


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def issue(workspace: str, hours: float = HOURS, now: float | None = None) -> dict:
    # shortcut: a token cannot be revoked before it expires; keep a deny list here if that is ever needed
    expires = int((now or time.time()) + hours * 3600)
    nonce = secrets.token_bytes(12)
    sealed = AESGCM(_key()).encrypt(nonce, f"{workspace}.{expires}".encode(), None)
    return {"token": _b64(nonce + sealed), "expires": expires}


def check(token: str, now: float | None = None) -> str:
    """The workspace a token opens. Raises LookupError for a forged, damaged or expired one."""
    try:
        raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
        workspace, expires = AESGCM(_key()).decrypt(raw[:12], raw[12:], None).decode().rsplit(".", 1)
        ok = int(expires) > (now or time.time())
    except (ValueError, TypeError, InvalidTag):  # damaged base64, too short, forged, or not ours
        ok = False
    if not ok:
        raise LookupError("This phone link has expired. Open a new one from the desktop.")
    return workspace
