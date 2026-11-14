"""quiet_rooms with the noise map and OpenStreetMap stubbed: the bedroom facing away from the road ranks quieter."""
import pytest

from tests.tools.conftest import make_home
from threshold.signals import noise_map, osm_sources
from threshold.tools import ToolContext, run_tool

LAT, LON = 29.70, -95.40


def home():
    p = make_home()
    p["geo"] = {"lat": LAT, "lon": LON, "altitude": 0, "yaw_deg": 0.0, "translation": {"x": 0.0, "y": 0.0}, "source": "test"}
    return p


@pytest.fixture
def south_road(monkeypatch):
    lv = {"road": {"layer": "road", "low": 60.0, "high": 70, "below_floor": False},
          "aviation": {"layer": "aviation", "low": None, "high": None, "below_floor": True},
          "rail": {"layer": "rail", "low": None, "high": None, "below_floor": True}}
    road = {"kind": "major_road", "name": "Test Road", "ref": None, "distance_m": 60.0, "bearing_deg": 180.0,
            "lat": LAT - 60 / 110574.0, "lon": LON, "osm": "way/1"}
    monkeypatch.setattr(noise_map, "levels", lambda lat, lon: lv)
    monkeypatch.setattr(osm_sources, "nearest", lambda lat, lon: {"highway": None, "major_road": road, "rail": None, "airport": None})


def test_back_bedroom_is_quieter(south_road):
    r = run_tool("quiet_rooms", {"scan": "home"}, ToolContext(plans=lambda sid: home()))
    order = [c.id for c in r.checks]
    assert order == ["R", "U"]  # R faces west and north; U upstairs has a south wall facing the road
    est = {c.id: c.measured for c in r.checks}
    assert est["U"] - est["R"] == pytest.approx(3.0)  # R's west wall is side-on to the road: SIDE_DB
    assert est["U"] == pytest.approx(65.0 - 25.0)
    assert r.findings[0].title == "Quietest: Bedroom"
    assert any(o.kind == "pins" and o.pins[0].anchor.geo for o in r.overlays)


def test_open_window_is_louder(south_road):
    shut = run_tool("quiet_rooms", {"scan": "home"}, ToolContext(plans=lambda sid: home()))
    open_ = run_tool("quiet_rooms", {"scan": "home", "windows_open": True}, ToolContext(plans=lambda sid: home()))
    assert open_.checks[0].measured - shut.checks[0].measured == pytest.approx(10.0)


def test_no_geo_is_unknown():
    r = run_tool("quiet_rooms", {"scan": "home"}, ToolContext(plans=lambda sid: make_home()))
    assert r.verdict.status == "unknown"
