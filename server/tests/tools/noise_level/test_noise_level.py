"""noise_level: an uncalibrated level per room; only what survives the microphone's error is called."""
from tests.tools.conftest import plans
from threshold.tools import ToolContext, run_tool
from threshold.tools.noise_level import ABS_ERR_DB, judge


def run(readings, scan="home"):
    return run_tool("noise_level", {"readings": readings, "scan": scan}, ToolContext(plans=plans))


def test_judge_never_fails_from_an_uncalibrated_microphone():
    assert judge(18, 30) == "pass" and judge(42, 30) == "warn" and judge(33, 30) == "unknown" and judge(80, 35) == "warn"
    assert ABS_ERR_DB == 10


def test_rooms_are_compared_and_drawn_as_a_lens():
    r = run([{"room": "R", "leq_dba": 31.0, "seconds": 15, "capture": "cap_a"}, {"room": "L", "leq_dba": 52.0, "lmax_dba": 68, "seconds": 15},
             {"room": "R", "leq_dba": 29.0, "seconds": 15}])                       # the bedroom measured twice: the later one stands
    assert r.overlays[0].kind == "lens" and r.overlays[0].values == {"R": 29.0, "L": 52.0} and r.overlays[0].legend.unit == "dBA"
    assert r.verdict.text.startswith("The bedroom is the quietest and the living room the loudest of 2 places measured.")
    assert "uncalibrated" in r.verdict.text and r.verdict.status == "warn"
    bed, living = (next(c for c in r.checks if c.id == k) for k in ("R", "L"))
    assert bed.threshold == 30 and bed.status == "unknown" and living.threshold == 35 and living.status == "warn"
    assert "WHO" in bed.standard and all(f.source.layer == "phone" and f.source.confidence == "low" for f in r.findings)
    assert next(m for m in r.metrics if m.id == "gap").value == 23.0
    assert next(f for f in r.findings if f.id == "noise_level:home:L").anchor.room == "L"


def test_no_real_difference_one_room_and_no_scan():
    assert "no real difference" in run([{"room": "R", "leq_dba": 40, "seconds": 15}, {"room": "L", "leq_dba": 42, "seconds": 15}]).verdict.text
    one = run([{"room": "R", "leq_dba": 40, "seconds": 5}])
    assert one.verdict.status == "unknown" and "shorter than 10 s" in one.verdict.text
    bare = run_tool("noise_level", {"readings": [{"label": "Front room", "leq_dba": 45, "seconds": 20}]}, ToolContext())
    assert bare.overlays == [] and bare.scope.sids == [] and bare.findings[0].anchor is None
