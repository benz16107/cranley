import datetime as dt

import pytest

from threshold.geometry import (
    facing,
    from_latlon,
    georef,
    sun_on_windows,
    sun_position,
    to_enu,
    to_latlon,
)


def test_yaw_rotates_scan_axes(plan):
    assert to_enu(plan, 1.0, 0.0, yaw_sign=1) == pytest.approx((0.0, 1.0))   # yaw 90: scan +x is north
    assert to_enu(plan, 1.0, 0.0, yaw_sign=-1) == pytest.approx((0.0, -1.0))


def test_latlon_round_trip(plan):
    lat, lon = to_latlon(plan, 12.0, -7.0)
    assert from_latlon(plan, lat, lon) == pytest.approx((12.0, -7.0), abs=1e-6)
    lat2, _ = to_latlon(plan, 0.0, 111.0, yaw_sign=1, translation="scan")      # scan +y is west at yaw 90
    assert lat2 == pytest.approx(29.76, abs=1e-6)


def test_no_geo_is_none(plan):
    plan["geo"] = None
    assert to_latlon(plan, 0, 0) is None and not facing(plan)["available"]


def test_window_and_entrance_face_outward(plan):
    f = {o["opening"]: o for o in facing(plan)["openings"]}
    # outward is -y for the window and -x for the entrance; at yaw 90 that is east and south (sign +1)
    expect = {"W": 90.0, "E": 180.0} if georef.YAW_SIGN == 1 else {"W": 270.0, "E": 0.0}
    for oid, az in expect.items():
        assert f[oid]["azimuth_deg"] == pytest.approx(az, abs=1e-6)


def test_sun_position_houston_solstice():
    tz = dt.timezone(dt.timedelta(hours=-5))
    noon = max(sun_position(dt.datetime(2026, 6, 21, 12, m, tzinfo=tz) + dt.timedelta(hours=1), 29.76, -95.37)[1]
               for m in range(60))
    assert noon == pytest.approx(90 - 29.76 + 23.44, abs=0.3)
    morning_az, _ = sun_position(dt.datetime(2026, 6, 21, 8, 0, tzinfo=tz), 29.76, -95.37)
    assert 45 < morning_az < 110


def test_east_window_gets_morning_sun_only(plan):
    if georef.YAW_SIGN != 1:
        pytest.skip("expectation written for yaw sign +1")
    w = next(o for o in sun_on_windows(plan, dt.date(2026, 3, 20))["openings"] if o["opening"] == "W")
    assert w["sun"] and all(end <= "13:30" for _, end in w["sun"]) and 5 < w["hours"] < 7.5
