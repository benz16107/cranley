"""Shared plumbing for every upstream call: one rate limit for the whole process, retry with backoff on 429 and
5xx, one-flight locks so identical requests are made once, and an atomic disk cache under $THRESHOLD_DATA_DIR/cache.

Everyone shares the sponsors' keys, so the limit is about 4 requests a second (THRESHOLD_RPS to change it).
"""
from __future__ import annotations

import os
import random
import re
import threading
import time
from collections import defaultdict
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path

import httpx

from ..config import CACHE, env

RETRY_STATUS = {429, 500, 502, 503, 504}
_gate = threading.Lock()
_next_slot = 0.0
_client = httpx.Client(timeout=httpx.Timeout(90, connect=20), follow_redirects=True,
                       limits=httpx.Limits(max_connections=32, max_keepalive_connections=16))


def _rate() -> float:
    return float(env().get("THRESHOLD_RPS") or 4)


def _wait_for_slot() -> None:
    """Block until this request's turn. Turns are 1/rate seconds apart across all threads."""
    global _next_slot
    with _gate:
        now = time.monotonic()
        slot = max(now, _next_slot)
        _next_slot = slot + 1 / _rate()
    if slot > now:
        time.sleep(slot - now)


def _backoff(attempt: int, r: httpx.Response | None) -> float:
    retry_after = (r.headers.get("retry-after") or "") if r is not None else ""
    base = float(retry_after) if retry_after.isdigit() else min(30.0, 2.0 ** attempt)
    return base + random.uniform(0, 0.5)


def send(method: str, url: str, *, stream: bool = False, retries: int = 5, auth=None, **kw) -> httpx.Response:
    """One upstream request, rate limited, retried on 429, 5xx and dropped connections. Raises on a final failure.
    With stream=True the caller must close the response; only opening the response is retried."""
    for attempt in range(retries + 1):
        _wait_for_slot()
        try:
            r = _client.send(_client.build_request(method, url, **kw), stream=stream, **({"auth": auth} if auth else {}))
        except httpx.TransportError:
            if attempt == retries:
                raise
            time.sleep(_backoff(attempt, None))
            continue
        if r.status_code in RETRY_STATUS and attempt < retries:
            wait = _backoff(attempt, r)
            r.close()
            time.sleep(wait)
            continue
        return r.raise_for_status() if r.status_code >= 400 else r
    raise AssertionError("unreachable")


# --- one-flight locks: the web view asks for six cube faces at once, and they share one upstream lookup ---
_locks: defaultdict[str, threading.Lock] = defaultdict(threading.Lock)
_locks_guard = threading.Lock()


@contextmanager
def one_flight(key: str):
    with _locks_guard:
        lock = _locks[key]
    with lock:
        yield


# --- disk cache ---
def cache_path(*parts: str) -> Path:
    return CACHE.joinpath(*parts)


def write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def cached(path: Path, make: Callable[[], bytes]) -> bytes:
    """Bytes at `path`, made (once, even under concurrency) and stored when missing."""
    try:
        return path.read_bytes()
    except FileNotFoundError:
        pass
    with one_flight(str(path)):
        try:
            return path.read_bytes()
        except FileNotFoundError:
            data = make()
            write_atomic(path, data)
            return data


# --- names that reach the file system or an upstream query must be plain ---
_SID = re.compile(r"^[A-Za-z0-9]{6,20}$")
_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_FILE = re.compile(r"^[A-Za-z0-9_.-]{1,96}$")


def check(value: str, kind: str = "id") -> str:
    """Return value when it is a plain scan id ("sid"), id ("id") or file name ("file"); else raise LookupError (a 404)."""
    ok = {"sid": _SID, "id": _ID, "file": _FILE}[kind].match(value) and ".." not in value
    if not ok:
        raise LookupError(f"no such {kind}: {value[:40]!r}")
    return value
