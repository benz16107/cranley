"""What-if scans on disk, served like phone scans: `w_<12 hex>` ids that every tool and GET /api/scan/{sid}/plan take.

    $THRESHOLD_DATA_DIR/whatif/<sid>.json   {sid, base, edits, created}

Only the base id and the edits are stored. The plan is rebuilt from the base plan on read (cached), so a better
normalizer reaches what-if scans too, and an edit that no longer fits the base plan says so instead of serving
stale geometry.
"""
from __future__ import annotations

import datetime as dt
import functools
import json
import re

from ..config import DATA
from .edits import apply, derived_sid, parse

ROOT = DATA / "whatif"
SID = re.compile(r"w_[0-9a-f]{12}")


def owns(sid: str) -> bool:
    return bool(SID.fullmatch(sid or ""))


def save(base: str, edits: list, base_plan: dict | None = None) -> tuple[dict, list[dict]]:
    """Apply, then write the record. Returns the edited plan and the diff. Idempotent: the same edits on the same
    base give the same sid and the same file."""
    from ..tools.registry import default_plan
    edits = parse(edits)
    plan, diff = apply(base_plan if base_plan is not None else default_plan(base), edits)
    ROOT.mkdir(parents=True, exist_ok=True)
    f = ROOT / f"{plan['sid']}.json"
    if not f.exists():
        f.write_text(json.dumps({"sid": plan["sid"], "base": base, "edits": [e.model_dump() for e in edits],
                                 "created": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}, indent=1))
    return plan, diff


def record(sid: str) -> dict:
    f = ROOT / f"{sid}.json"
    if not owns(sid) or not f.exists():
        raise LookupError(f"no such what-if scan: {sid[:40]!r}")
    return json.loads(f.read_text())


@functools.lru_cache(maxsize=64)
def plan_json(sid: str) -> bytes:
    from ..tools.registry import default_plan
    rec = record(sid)
    plan, diff = apply(default_plan(rec["base"]), rec["edits"])
    if plan["sid"] != sid or derived_sid(rec["base"], parse(rec["edits"])) != sid:
        raise LookupError(f"what-if scan {sid} does not match its record")
    plan["whatif"]["diff"] = diff
    return json.dumps(plan, separators=(",", ":")).encode()


def plan(sid: str) -> dict:
    return json.loads(plan_json(sid))
