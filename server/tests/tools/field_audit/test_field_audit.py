"""field_audit: severity, the pick of disagreements, the summary and the judgement, over hand-made scans."""
import copy

from tests.tools.conftest import HOME_RECORD, make_home
from threshold.tools.field_audit import (
    judge,
    pick,
    run_audit,
    severity,
    summary,
    to_result,
)
from threshold.tools.record_vs_reality import gather


def row(sid, field, key, rv, mv, ratio=None, conf="medium", kind="home"):
    return {"sid": sid, "name": sid, "kind": kind, "scope": "home", "field": field, "claim_key": key,
            "record_value": rv, "measured_value": mv, "ratio": ratio, "verdict": "contradicted", "confidence": conf,
            "severity": severity({"verdict": "contradicted", "confidence": conf, "ratio": ratio,
                                  "claim": {"value": rv}, "measured": {"value": mv}}),
            "reason": "", "record_path": "x", "evidence": ""}


def test_severity_and_pick_skip_partial_scans_and_repeat_scans():
    rows = [row("a", "area", "living_area", 1000, 300, ratio=0.3), row("b", "area", "living_area", 1000, 1500, ratio=1.5),
            row("b", "bedrooms", "beds", 3, 2), row("c", "bedrooms", "beds", 4, 2), row("d", "stories", "stories", 2, 1, conf="low")]
    got = [(r["sid"], r["field"]) for r in pick(rows, 3)]
    assert ("a", "area") not in got  # a partial scan teaches nothing about the record
    assert got[0] == ("c", "bedrooms") and ("b", "area") in got  # half the bedrooms missing outranks +50% area
    assert len({s for s, _ in got}) == len(got)  # one row per scan


def test_judge_bedrooms_with_panorama_labels():
    r = row("x", "bedrooms", "beds", 3, 2)
    deep = {"comparisons": [], "evidence": {}}
    labels = [{"label": "Bedroom"}] * 3
    assert judge(r, make_home(), deep, labels)[0] == "measurement"
    assert judge(r, make_home(), deep, [{"label": "Bedroom"}] * 2)[0] == "record"


def test_run_audit_end_to_end(monkeypatch):
    big = copy.deepcopy(HOME_RECORD)
    big["claims"]["living_area"]["value"] = 480  # the scan measures 143% of it
    big["claims"]["stories"]["value"] = 1
    recs = {"h1": HOME_RECORD, "h2": big}
    monkeypatch.setitem(gather.SOURCES, "record", recs.get)
    monkeypatch.setitem(gather.SOURCES, "site", lambda lat, lon: {"lat": lat, "lon": lon, "facts": [], "parcel": None})
    monkeypatch.setitem(gather.SOURCES, "ortho", lambda *a: (_ for _ in ()).throw(RuntimeError("offline")))
    monkeypatch.setitem(gather.SOURCES, "objects", lambda plan, labels, panos: [])
    out = run_audit([("h1", "home"), ("h2", "home")], lambda sid: make_home(), deep_top=2)
    s = {x["field"]: x for x in summary(out["rows"])}
    assert s["area"]["contradicted"] == 1 and s["area"]["over_10pct"] == 1
    assert out["top"] and out["top"][0]["sid"] == "h2" and out["top"][0]["judgement"] in ("record", "unclear")
    r = to_result(out)
    assert r.scope.sids == ["h1", "h2"] and any(m.id == "disagree.area" for m in r.metrics)
    assert all(f.id.startswith("field_audit:") for f in r.findings)
