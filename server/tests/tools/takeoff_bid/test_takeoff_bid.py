import pytest

from threshold.tools import ToolContext, run_tool
from threshold.tools.room_labeller import store

from ..conftest import OFFICE, make_plan

FT2 = 10.7639


def with_finishes(p, finish="carpet"):
    store.save({"sid": p["sid"], "rooms": {}, "corrections": [],
                "finishes": {r["id"]: {"finish": finish, "shares": {finish: 1.0}, "confidence": "high",
                                       "evidence": {"sid": p["sid"], "pano": f"p_{r['id']}", "face": 5}} for r in p["rooms"]}})


def test_cleaning_hours_follow_the_rates(office_plan, monkeypatch):
    from threshold.tools import takeoff_bid
    monkeypatch.setattr(takeoff_bid, "fixtures", lambda plan, rooms: {"wc": {"counts": {"toilet": 1, "sink": 1}, "evidence": None}})
    with_finishes(office_plan)
    res = run_tool("takeoff_bid", {"scan": "toffice", "trade": "cleaning", "label_with_vision": False},
                   ToolContext(plans=lambda sid: office_plan))
    m = {x.id: x.value for x in res.metrics}
    clean_m2 = sum((x1 - x0) * (y1 - y0) for i, x0, y0, x1, y1, lab in OFFICE if lab != "storage")
    assert m["cleanable"] == round(clean_m2 * FT2)
    assert m["hours_per_visit"] == round(clean_m2 * FT2 / 3500, 2)  # carpet everywhere, at the default rate
    assert m["fixtures"] == 0  # label_with_vision off: fixtures are not read


def test_unit_turn_needs_walls():
    p = make_plan("tnw", [("a", 0, 0, 4, 4, "Bedroom")], walls=False)
    res = run_tool("takeoff_bid", {"scan": "tnw", "trade": "unit_turn", "label_with_vision": False}, ToolContext(plans=lambda sid: p))
    assert res.verdict.status == "unknown" and "No wall graph" in res.verdict.text


def test_fit_out_prices_are_quantities_times_rates(office_plan):
    with_finishes(office_plan, "vinyl or linoleum")
    res = run_tool("takeoff_bid", {"scan": "toffice", "trade": "fit_out", "add_offices": 2, "label_with_vision": False,
                                   "contingency": 0}, ToolContext(plans=lambda sid: office_plan))
    m = {x.id: x.value for x in res.metrics}
    floor = m["floor_area"]
    assert m["cost.Flooring"] == pytest.approx(floor * 4.5, abs=5)
    assert m["cost.New_doors"] == 2800
    assert "every price is your assumption" in res.verdict.text
