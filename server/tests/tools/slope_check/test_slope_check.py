"""slope_check: the phone as a level, against the ADA limits, with its error carried."""
import math

import pytest

from threshold.tools import ToolContext, run_tool
from threshold.tools.slope_check import CROSS_MAX, RAMP_MAX, grade, settle


def deg(g):
    return math.degrees(math.atan(g))


def run(**inputs):
    return run_tool("slope_check", inputs, ToolContext())


def test_turning_the_phone_end_for_end_cancels_its_offset():
    # a 3 degree slope read by a phone whose sensor and camera bump add 0.7: 3.7 one way, -2.3 the other
    angle, err, cancelled = settle(3.7, -2.3, 0.0)
    assert angle == pytest.approx(3.0) and cancelled and err == pytest.approx(0.3)
    assert settle(3.7, None, 0.0) == (3.7, 1.0, False)               # one reading keeps the offset and a wider error
    assert settle(3.0, -3.0, 0.4)[1] == pytest.approx(0.5)           # a phone that would not lie still is less sure


def test_ramp_limits_are_the_ada_ones():
    assert RAMP_MAX == pytest.approx(0.0833, abs=1e-4) and CROSS_MAX == pytest.approx(0.0208, abs=1e-4)
    ok = run(mode="ramp", reading_deg=deg(0.06), flipped_deg=-deg(0.06))
    assert ok.verdict.status == "pass" and ok.checks[0].threshold == 8.33 and "405.2" in ok.checks[0].standard
    assert next(m for m in ok.metrics if m.id == "slope_pct").value == pytest.approx(6.0, abs=0.01)
    steep = run(mode="ramp", reading_deg=deg(0.11), flipped_deg=-deg(0.11))
    assert steep.verdict.status == "fail" and steep.findings[0].source.layer == "phone" and steep.findings[0].source.method == "sensor"
    close = run(mode="ramp", reading_deg=deg(0.082), flipped_deg=-deg(0.082))
    assert close.verdict.status == "warn" and "check it with a level" in close.verdict.text   # within the phone's error
    single = run(mode="ramp", reading_deg=deg(0.07))
    assert single.verdict.status == "warn" and single.findings[0].source.confidence == "low"  # 4.0 +/- 1.0 straddles 4.76


def test_cross_slope_fails_a_ramp_that_passes_its_running_slope():
    r = run(mode="ramp", reading_deg=deg(0.05), flipped_deg=-deg(0.05), cross_deg=deg(0.04), cross_flipped_deg=-deg(0.04))
    cross = next(c for c in r.checks if c.id == "cross")
    assert cross.status == "fail" and "405.3" in cross.standard and r.verdict.status == "fail"
    assert next(c for c in r.checks if c.id == "is_ramp").status == "warn"       # 5% is right at the 1:20 line


def test_threshold_bevel_and_plumb():
    assert run(mode="threshold", reading_deg=20.0, flipped_deg=-20.0).verdict.status == "pass"      # 36% against 1:2
    assert run(mode="threshold", reading_deg=35.0, flipped_deg=-35.0).verdict.status == "fail"
    lean = run(mode="plumb", reading_deg=1.5, flipped_deg=-1.5, scan="home", opening="E", capture="cap_1")
    assert lean.verdict.status == "warn" and "26 mm in each metre" in lean.verdict.text and not lean.checks
    assert lean.findings[0].anchor.opening == "E" and lean.findings[0].media[0].ref == "cap_1" and lean.scope.sid == "home"
    assert run(mode="plumb", reading_deg=0.2, flipped_deg=-0.1).verdict.status == "pass"
    assert grade(45) == pytest.approx(1.0)
