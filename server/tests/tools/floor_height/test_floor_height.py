"""floor_height on the flood tools' hand-made house: steps, fixes and the before and after. No network."""
import pytest

from tests.tools.flood_rehearsal.flood_house import house, plans_of
from threshold.tools import ToolContext, run_tool
from threshold.tools import floor_height as fhgt
from threshold.tools.flood_rehearsal import public, scenario


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def no(*a, **k):
        raise RuntimeError("offline")
    monkeypatch.setattr(scenario, "_site", no)
    monkeypatch.setattr(public, "fema_zone", no)
    monkeypatch.setattr(fhgt, "_ground", lambda pts: [10.40, 10.00])     # the yard at the door is 0.40 m above the street


def run(**inputs):
    p = house()
    return run_tool("floor_height", {"scan": p["sid"], "depth_m": 0.4, **inputs}, ToolContext(plans=plans_of(p)))


def metric(r, mid):
    return next(m.value for m in r.metrics if m.id == mid)


DOOR = {"lat": 29.78, "lon": -95.2451, "altitude_m": 14.9, "altitude_accuracy_m": 4.0, "accuracy_m": 5}
STREET = {"lat": 29.78, "lon": -95.2454, "altitude_m": 14.2, "altitude_accuracy_m": 4.0, "accuracy_m": 5}


def test_estimates_from_what_the_phone_sent():
    est, info = fhgt.estimates(fhgt.Inputs(scan="house", steps=1, riser_m=0.16))
    assert est[0]["method"] == "phone_steps" and est[0]["value_m"] == pytest.approx(0.19) and est[0]["confidence"] == "high"
    assert est[0]["err_m"] == pytest.approx(0.022, abs=0.001)
    assumed, _ = fhgt.estimates(fhgt.Inputs(scan="house", steps=2))
    assert assumed[0]["value_m"] == pytest.approx(2 * 0.1778 + 0.03, abs=0.001) and assumed[0]["err_m"] > 0.06 and assumed[0]["confidence"] == "medium"
    gps, info = fhgt.estimates(fhgt.Inputs(scan="house", door=DOOR, street=STREET, baro_rise_m=0.62))
    by = {e["method"]: e for e in gps}
    assert info["grade_m"] == pytest.approx(0.40)
    assert by["phone_gps"]["value_m"] == pytest.approx(0.30) and by["phone_gps"]["err_m"] > 5 and by["phone_gps"]["confidence"] == "low"
    assert by["phone_baro"]["value_m"] == pytest.approx(0.22) and by["phone_baro"]["err_m"] == pytest.approx(0.335, abs=0.01)
    assert fhgt.estimates(fhgt.Inputs(scan="house"))[0] == []


def test_a_measured_riser_narrows_the_flood_range():
    r = run(steps=1, riser_m=0.20, capture="cap_door")                 # 0.23 m; the scan's outdoor panoramas say 0.25
    assert r.verdict.status == "pass" and "narrower than before" in r.verdict.text
    assert metric(r, "floor_height") == pytest.approx(0.23) and metric(r, "range_after") < metric(r, "range_before")
    assert metric(r, "shrink_pct") > 50 and metric(r, "floor_low") >= 0.15       # the door step stays a lower bound
    depth = next(c for c in r.checks if c.id == "depth_range")
    assert depth.measured < depth.threshold and depth.kind == "claim"            # water on the floor: range now against before
    f = r.findings[0]
    assert f.anchor.opening == "F" and f.media[0].ref == "cap_door" and f.source.layer == "phone" and f.source.method == "manual"
    assert r.actions[0].tool == "flood_rehearsal" and r.actions[0].inputs["floor_height_m"] == pytest.approx(0.23)


def test_gps_alone_is_reported_and_does_not_narrow():
    r = run(door=DOOR, street=STREET)
    assert r.verdict.status == "warn" and "did not narrow" in r.verdict.text
    assert metric(r, "range_after") == pytest.approx(metric(r, "range_before")) and metric(r, "grade") == 0.4
    assert "GPS altitude is good to metres" in r.findings[0].detail


def test_nothing_usable_and_a_disagreeing_count():
    assert run().verdict.status == "unknown" and "Count the steps" in run().verdict.text
    r = run(steps=4, riser_m=0.18)                                     # 0.75 m against the scan's 0.25: they cannot both be right
    assert "disagree" in r.verdict.text and metric(r, "floor_high") >= 0.7
