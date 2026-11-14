"""daylight: windows per room, sun hours, low-confidence wording, scans with no windows."""
import datetime as dt

from tests.tools.truth_fixtures import make_home
from threshold.tools import ToolContext, run_tool
from threshold.tools.daylight import per_room


def test_per_room_counts_and_sun():
    d = per_room(make_home(), dt.date(2026, 6, 21))
    assert d["available"] and d["sun"]
    assert d["rooms"]["L"]["windows"] == 1 and round(d["rooms"]["L"]["glazed_m2"], 2) == 3.0
    assert d["rooms"]["B2"]["windows"] == 0
    assert d["rooms"]["L"]["hours"] > 0 and d["rooms"]["L"]["directions"]


def test_result_flags_dark_bedroom_and_hedges_direction():
    def unchecked(sid):  # a scan whose placement was not verified against its footprint (plan.quality.georef)
        p = make_home()
        p["quality"]["georef"] = False
        return p
    r = run_tool("daylight", {"scan": "home1", "date": "2026-06-21"}, ToolContext(plans=unchecked))
    assert r.verdict.status == "warn"
    assert any(f.title == "Bedroom has no window" for f in r.findings)
    sunny = next(f for f in r.findings if f.title.startswith("Sunniest"))
    assert sunny.detail.startswith("If the scan's compass rotation is right") and sunny.source.confidence == "low"
    checked = run_tool("daylight", {"scan": "home1", "date": "2026-06-21"}, ToolContext(plans=lambda sid: make_home()))
    sunny = next(f for f in checked.findings if f.title.startswith("Sunniest"))
    assert not sunny.detail.startswith("If") and sunny.source.confidence != "low"  # a verified scan states it plainly
    assert r.overlays[0].kind == "lens" and r.overlays[0].legend.unit == "h"


def test_no_windows_recorded_is_unknown():
    r = run_tool("daylight", {"scan": "home1"}, ToolContext(plans=lambda sid: make_home(windows=False)))
    assert r.verdict.status == "unknown" and "no windows" in r.verdict.text


def test_no_geocoordinates_says_sun_hours_cannot_be_traced():
    def phone(sid):
        p = make_home()
        p["geo"] = None
        return p
    r = run_tool("daylight", {"scan": "home1"}, ToolContext(plans=phone))
    assert "Hours of sun cannot be traced" in r.verdict.text and r.overlays[0].legend.unit == "m²"
