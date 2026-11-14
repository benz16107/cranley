"""window_check: a compass heading at a window against the scan's facing, and the sun hours that follow."""
import datetime as dt

import pytest

from tests.tools.conftest import plans as bare_plans
from tests.tools.truth_fixtures import make_home
from threshold.tools import ToolContext, run_tool
from threshold.tools.window_check import apart, declination, sun_hours

CTX = ToolContext(plans=lambda sid: make_home())       # Los Angeles; the living room window w1 faces south (180)


def run(heading, room="L", ctx=CTX, **more):
    return run_tool("window_check", {"scan": "home1", "room": room, "heading_deg": heading, "date": "2026-06-21", **more}, ctx)


def test_helpers():
    assert apart(350, 10) == 20 and apart(10, 350) == 20 and apart(180, 0) == 180
    assert declination(34.0, -118.3) == (11.2, "Los Angeles") and declination(29.7, -95.4)[1] == "Houston"
    assert declination(51.5, 0.0) == (0.0, None) and declination(None, None) == (0.0, None)
    # midsummer in Los Angeles: a south window sees less direct sun than an east one sees in the morning plus noon
    assert sun_hours(180, 34.0, -118.3, dt.date(2026, 6, 21)) < sun_hours(90, 34.0, -118.3, dt.date(2026, 6, 21)) + 4
    assert sun_hours(0, 34.0, -118.3, dt.date(2026, 12, 21)) == 0     # a north window in winter gets none


def test_a_heading_that_agrees_confirms_the_scan():
    r = run(170.0)                                                    # magnetic 170 + 11.2 declination = 181 true
    assert r.verdict.status == "pass" and "agrees with the scan (S)" in r.verdict.text
    assert next(m for m in r.metrics if m.id == "heading_deg").value == 181
    assert next(m for m in r.metrics if m.id == "difference_deg").value == 1
    assert next(m for m in r.metrics if m.id == "sun_phone_h").value == pytest.approx(next(m for m in r.metrics if m.id == "sun_scan_h").value, abs=0.2)
    assert r.findings[0].anchor.opening == "w1" and r.findings[0].source.layer == "phone" and r.findings[0].source.method == "sensor"


def test_a_heading_that_cannot_agree_contradicts_it_and_changes_the_sun_hours():
    r = run(80.0)                                                     # about east
    assert r.verdict.status == "fail" and "cannot both be right" in r.verdict.text
    sun = next(c for c in r.checks if c.id == "sun")
    assert sun.kind == "claim" and sun.measured != sun.threshold      # hours by the phone against hours by the scan
    mid = run(140.0)
    assert mid.verdict.status == "warn" and "read it again away from metal" in mid.verdict.text


def test_true_heading_and_a_room_or_scan_with_nothing_to_compare():
    assert next(m for m in run(181.0, magnetic=False).metrics if m.id == "heading_deg").value == 181
    none = run(90.0, room="B2")                                       # the second bedroom has no window in the scan
    assert none.verdict.status == "unknown" and "marks no window in this room" in none.verdict.text and none.checks == []
    nogeo = run_tool("window_check", {"scan": "home", "room": "L", "heading_deg": 90.0, "lat": 29.76, "lon": -95.37},
                     ToolContext(plans=bare_plans))
    assert nogeo.verdict.status == "unknown" and "no compass rotation" in nogeo.verdict.text
    assert next(m for m in nogeo.metrics if m.id == "sun_phone_h").value is not None   # the phone's own fix gives the sun hours


def test_a_direction_picked_by_hand_is_manual_and_true_north(tmp_path, monkeypatch):
    from threshold.capture import store
    monkeypatch.setattr(store, "ROOT", tmp_path)
    cap = store.save("ws_t", store.Meta(kind="reading", scan="home1", values={"magnetic": False}), None)["id"]
    r = run(180.0, capture=cap)                                       # "S" picked: no declination added
    assert next(m for m in r.metrics if m.id == "heading_deg").value == 180
    assert {f.source.method for f in r.findings} == {"manual"} and "picked by hand" in r.findings[0].source.note
    assert run(170.0).findings[0].source.method == "sensor"
