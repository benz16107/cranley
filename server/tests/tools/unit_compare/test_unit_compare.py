from threshold.tools import ToolContext, run_tool
from threshold.tools import unit_compare as uc

from ..conftest import make_plan


def test_title_layout():
    assert uc._title_layout("2BR, 2BA - 1,052SF") == (2, 2.0, 1052.0)
    assert uc._title_layout("Studio - 396SF") == (0, None, 396.0)
    assert uc._title_layout("1BR, 1BA, 747 SF") == (1, 1.0, 747.0)


def test_rent_from_matching_floor_plan(monkeypatch):
    lst = [{"apartmentModels": [{"numBeds": 1, "numBaths": 1, "minSquareFeet": 700, "minRent": 1400, "maxRent": 1600},
                                {"numBeds": 1, "numBaths": 1, "minSquareFeet": 900, "minRent": 2000, "maxRent": 2000},
                                {"numBeds": 2, "numBaths": 2, "minSquareFeet": 1000, "minRent": 0}]}]
    monkeypatch.setattr(uc.costar, "by_property", lambda ds, pid: lst)
    assert uc.apartment_rent(1, 1, 1.0, 705)[0] == 1500
    assert uc.apartment_rent(1, 2, 2.0, 1000) == (None, "the listing gives no rent for this floor plan")


def test_ranks_by_area_without_rent(monkeypatch):
    from threshold.tools.room_labeller import facts
    monkeypatch.setattr(facts, "scan_kind", lambda sid: "apartment_unit")
    plans = {"u1": make_plan("u1", [("b", 0, 0, 4, 4, "Bedroom"), ("k", 4, 0, 8, 3, "Kitchen")]),
             "u2": make_plan("u2", [("b", 0, 0, 5, 5, "Bedroom"), ("c", 5, 0, 6, 2, "Closet"), ("k", 6, 0, 10, 4, "Kitchen")])}
    res = run_tool("unit_compare", {"scans": ["u1", "u2"]}, ToolContext(plans=plans.__getitem__))
    assert [f.title for f in res.findings] == ["1. u2", "2. u1"]
    assert res.scope.sids == ["u2", "u1"]


def test_a_scan_with_no_property_is_not_applicable_rather_than_an_error():
    from threshold.tools import ToolContext, run_tool
    res = run_tool("unit_compare", {"scan": "lonely"}, ToolContext(plans=lambda sid: {}))
    assert res.verdict.status == "unknown" and "no sibling units" in res.verdict.text
    assert res.scope.sid == "lonely" and not res.findings
