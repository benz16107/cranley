"""Scans people make of their own homes with the iPhone app (RoomPlan), stored outside the repo.

    $THRESHOLD_DATA_DIR/user_scans/<sid>/roomplan.json   the export exactly as the phone sent it
    $THRESHOLD_DATA_DIR/user_scans/<sid>/meta.json       name, kind, address, geo, workspace, created

The ScanPlan is converted from the export on read (cached), so a better converter needs no re-upload.
A user scan id is "u_" and 12 hex digits. Matterport ids are letters and digits only, so the two never collide.
"""
from __future__ import annotations

import datetime as dt
import functools
import json
import re
import secrets

from ..config import DATA
from ..roomplan import convert

ROOT = DATA / "user_scans"
SID = re.compile(r"u_[0-9a-f]{12}")


def owns(sid: str) -> bool:
    return bool(SID.fullmatch(sid or ""))  # match with $ let "u_...\n" through


def _dir(sid: str):
    if not owns(sid):
        raise LookupError(f"no such user scan: {sid[:40]!r}")
    d = ROOT / sid
    if not (d / "roomplan.json").exists():
        raise LookupError(f"no such user scan: {sid}")
    return d


def save(export: dict, meta: dict) -> dict:
    """Convert first (so a bad export stores nothing), then write. Returns the ScanPlan."""
    sid = "u_" + secrets.token_hex(6)
    meta = {**meta, "sid": sid, "created": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    plan = _convert(export, meta)
    d = ROOT / sid
    d.mkdir(parents=True, exist_ok=False)
    (d / "roomplan.json").write_text(json.dumps(export, separators=(",", ":")))
    (d / "meta.json").write_text(json.dumps(meta, indent=1))
    return plan


def _convert(export: dict, meta: dict) -> dict:
    return convert(export, meta["sid"], meta.get("name"), kind=meta.get("kind"), address=meta.get("address"),
                   city=meta.get("city"), geo=meta.get("geo"), created=meta.get("created"), notes=meta.get("notes"))


def meta(sid: str) -> dict:
    return json.loads((_dir(sid) / "meta.json").read_text())


@functools.lru_cache(maxsize=64)
def plan_json(sid: str) -> bytes:
    d = _dir(sid)
    plan = _convert(json.loads((d / "roomplan.json").read_text()), json.loads((d / "meta.json").read_text()))
    return json.dumps(plan, separators=(",", ":")).encode()


def plan(sid: str) -> dict:
    """The ScanPlan. A fresh dict each call, so callers may change it."""
    return json.loads(plan_json(sid))


def rows(workspace: str | None = None) -> list[dict]:
    """Every user scan, newest first, optionally only those sent from one workspace."""
    out = []
    for d in ROOT.glob("u_*/meta.json") if ROOT.exists() else ():
        m = json.loads(d.read_text())
        if workspace is None or m.get("workspace") == workspace:
            out.append({k: m.get(k) for k in ("sid", "name", "kind", "address", "city", "created", "workspace")})
    return sorted(out, key=lambda m: m["created"] or "", reverse=True)
