"""Sun by room on a hand-made house in Houston: one room, a south window and a north window, scan axes on east/north."""
import datetime as dt

import numpy as np
import pytest

from threshold import sun
from threshold.tools import ToolContext, run_tool

LAT, LON = 29.76, -95.37
DEC = dt.date(2026, 12, 21)


def plan(sid="s1"):
    def wall(id, a, b):
        return {"id": id, "floor": "f1", "a": a, "b": b, "type": "wall", "thickness": 0.1, "length": 4.0,
                "rooms": ["r1"], "openings": []}

    def op(id, w, t, c, sill):
        return {"id": id, "wall": w, "floor": "f1", "type": t, "width": 1.0, "height": 1.2 if t == "window" else 2.0,
                "sill": sill, "center": c, "rooms": ["r1"]}
    return {"schema": "scanplan/1", "sid": sid, "name": "Test", "has": {"room_labels": True, "openings": True},
            "geo": {"lat": LAT, "lon": LON, "altitude": 0, "yaw_deg": 0.0, "translation": {"x": 0, "y": 0}},
            "quality": {"georef": True}, "floors": [{"id": "f1", "label": "1", "sequence": 0, "elevation": 0}],
            "walls": [wall("ws", [0, 0], [4, 0]), wall("we", [4, 0], [4, 4]), wall("wn", [4, 4], [0, 4]),
                      wall("ww", [0, 4], [0, 0])],
            "rooms": [{"id": "r1", "floor": "f1", "label": "Bedroom", "label_confidence": 1, "label_source": "matterport",
                       "polygon": [[0, 0], [4, 0], [4, 4], [0, 4]], "area": 16.0, "height": 2.5, "walls": ["ws", "we", "wn", "ww"],
                       "holes": []}],
            "openings": [op("south", "ws", "window", [2, 0], 0.9), op("north", "wn", "window", [2, 4], 0.9),
                         op("door", "we", "doorway", [4, 2], 0.0)],
            "panos": []}


def tower_south(height=30.0):
    """A flat grid with a wall of buildings 10 to 20 m south of the house."""
    n, half = 240, 60.0
    h = np.zeros((n, n), np.float32)
    north = half - (np.arange(n) + 0.5) * 2 * half / n
    h[(north < -10) & (north > -20), :] = height
    return {"heights": h, "bounds_enu": (-half, -half, half, half), "ground_m": 0.0}


def test_south_window_gets_winter_sun_north_does_not():
    t = sun.window_sun(plan(), [DEC])
    by = {w["opening"]: w for w in t["windows"]}
    assert by["south"]["compass"] == "S" and by["north"]["compass"] == "N"
    assert by["south"]["days"][DEC.isoformat()]["hours"] > 9  # all day: sunrise to sunset is about 10.3 h
    assert by["north"]["days"][DEC.isoformat()]["hours"] == 0
    assert by["south"]["above_ground_m"] == pytest.approx(0.2 + 0.9 + 0.6)


def test_a_tall_neighbour_to_the_south_takes_the_winter_sun():
    t = sun.window_sun(plan(), [DEC], tower_south())
    d = {w["opening"]: w for w in t["windows"]}["south"]["days"][DEC.isoformat()]
    assert d["hours"] < 1 and d["blocked_hours"] > 8


def test_horizon_sees_the_tower_only_to_the_south():
    hzn = sun.horizon.horizon(tower_south(), 0, 0, 1.5)
    b = sun.horizon.bins()
    south = hzn[np.abs(b - 180) < 10]
    north = hzn[np.abs((b + 180) % 360 - 180) < 10]
    assert south.min() > 60 and north.max() == 0


def test_key_days_put_the_given_day_first_and_keep_it_once():
    assert [k for k, _, _ in sun.key_days(dt.date(2026, 11, 14))][0] == "day"
    days = sun.key_days(dt.date(2026, 6, 21))
    assert [k for k, _, _ in days] == ["june_solstice", "march_equinox", "september_equinox", "december_solstice"]


def test_tool_picks_rooms_and_draws_lens_and_window_pins(monkeypatch):
    monkeypatch.setattr(sun.horizon, "grid", lambda lat, lon: tower_south(height=4.0))
    ctx = ToolContext(plans=lambda sid: plan(sid))
    r = run_tool("sun_rooms", {"scan": "s1", "date": "2026-12-21"}, ctx)
    assert r.verdict.status == "pass"
    ids = {f.id for f in r.findings}
    assert {"sun_rooms:s1:plants", "sun_rooms:s1:office", "sun_rooms:s1:bedroom"} <= ids
    lens = next(o for o in r.overlays if o.kind == "lens")
    assert lens.values["r1"] > 0
    pins = next(o for o in r.overlays if o.kind == "pins").pins
    assert {p.anchor.opening for p in pins} == {"south", "north"}
    assert next(p for p in pins if p.anchor.opening == "north").status == "unknown"


def test_no_geocoordinates_is_unknown():
    p = plan()
    p["geo"] = None
    r = run_tool("sun_rooms", {"scan": "s1"}, ToolContext(plans=lambda sid: p))
    assert r.verdict.status == "unknown"
