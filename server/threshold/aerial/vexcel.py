"""Vexcel v2 client: header auth, a disk cache of every response, and at most about 3 requests a second.

Everyone at the event shares the key, so a response is fetched once and then read from
`$THRESHOLD_DATA_DIR/cache/vexcel/`. Errors are not cached.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time

import httpx

from ..config import CACHE, env

BASE = "https://api.vexcelgroup.com/v2"
DIR = CACHE / "vexcel"
MIN_GAP_S = 0.34  # about 3 requests a second across all threads
_lock = threading.Lock()
_last = [0.0]


class VexcelError(LookupError):
    def __init__(self, status: int, message: str):
        super().__init__(f"Vexcel {status}: {message[:300]}")
        self.status = status


def _key(method: str, path: str, params: dict | None, body: dict | None) -> str:
    raw = json.dumps([method, path, params or {}, body or {}], sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def _throttle() -> None:
    with _lock:
        wait = _last[0] + MIN_GAP_S - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.monotonic()


def call(method: str, path: str, params: dict | None = None, body: dict | None = None,
         timeout: float = 120) -> tuple[bytes, str]:
    """Raw bytes and content type for one request, from the cache when we have it."""
    k = _key(method, path, params, body)
    f, meta = DIR / path.strip("/").replace("/", "_") / k, None
    meta = f.with_suffix(".type")
    if f.exists() and meta.exists():
        return f.read_bytes(), meta.read_text()
    _throttle()
    r = httpx.request(method, f"{BASE}/{path.strip('/')}", params=params, json=body, timeout=timeout,
                      headers={"X-API-KEY": env()["VEXCEL_API_KEY"]})
    if r.status_code != 200:
        raise VexcelError(r.status_code, r.text)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(r.content)
    meta.write_text(r.headers.get("content-type", ""))
    return r.content, r.headers.get("content-type", "")


def get_json(path: str, **params) -> dict:
    return json.loads(call("GET", path, params=params)[0])


def post_json(path: str, body: dict) -> dict:
    return json.loads(call("POST", path, body=body)[0])
