"""The composer evaluation (threshold/agent/evaluate.py) replayed with the recorded live answers: forty-one briefs,
every preset and several nobody planned for. Re-record with `uv run python -m threshold.agent.evaluate --live`."""
import json

from threshold.agent import evaluate


def test_every_brief_passes_with_the_recorded_model():
    briefs = json.loads(evaluate.BRIEFS.read_text())
    rows = evaluate.run(evaluate.Recorded(json.loads(evaluate.RECORDED.read_text())), parallel=1)
    failed = {r["id"]: [k for k, ok in r["checks"].items() if not ok] for r in rows if not r["ok"]}
    assert len(rows) == len(briefs) >= 40 and not failed, failed


def test_briefs_cover_every_preset_and_unplanned_needs():
    from threshold.agent.catalog import personas
    briefs = json.loads(evaluate.BRIEFS.read_text())
    named = {p for b in briefs for p in b["persona"]}
    assert set(personas()) <= named
    assert sum(bool(b.get("cannot")) for b in briefs) >= 5
