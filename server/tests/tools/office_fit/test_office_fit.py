from threshold.tools import ToolContext, run_tool
from threshold.tools.office_fit import Inputs, fit

from ..conftest import OFFICE, make_plan


def rooms(spec=OFFICE):
    return [{"id": i, "label": lab, "area": (x1 - x0) * (y1 - y0), "windows": 1} for i, x0, y0, x1, y1, lab in spec]


def prog(**k):
    return Inputs(scan="t", **{"headcount": 10, "private_offices": 2, "meeting_rooms": 1, "meeting_seats": 6, **k})


def test_fits_as_built():
    f = fit(rooms(), prog())
    # 80 m2 open / 6.5 = 12 desks; offices 10.5, 12, 16 m2: two for the program, the 16 m2 one seats two more
    assert (f["desks"], f["need_desks"], f["status"]) == (14, 8, "pass")
    assert f["roles"]["o1"]["role"] == "office" and f["roles"]["o3"]["seats"] == 2
    assert f["roles"]["conf"]["seats"] == 8  # 20 m2 / 2.3


def test_short_of_offices_converts_a_spare_meeting_room():
    spec = OFFICE + [("conf2", 20, 2, 23, 6, "conference room")]
    f = fit(rooms(spec), prog(private_offices=4))
    conv = [k for k, v in f["roles"].items() if v.get("convert")]
    assert conv == ["conf2"] and f["status"] == "warn"


def test_shell_space_suggests_building_offices():
    spec = [("open", 0, 0, 30, 20, "open office")]
    f = fit(rooms(spec), prog(headcount=40, private_offices=3, meeting_rooms=0))
    assert f["status"] == "warn" and f["changes"][0]["kind"] == "build" and f["changes"][0]["offices"] == 3


def test_too_small_fails_with_a_space_change():
    f = fit(rooms(), prog(headcount=40))
    assert f["status"] == "fail" and any(c["kind"] in ("space", "density") for c in f["changes"])


def test_tool_runs_without_a_record(office_plan):
    res = run_tool("office_fit", {"scan": "toffice", "headcount": 10, "private_offices": 2, "label_with_vision": False},
                   ToolContext(plans=lambda sid: office_plan))
    assert res.verdict.status == "pass"
    kinds = [o.kind for o in res.overlays]
    assert "lens" in kinds and "pins" in kinds
    assert {a.id for a in res.assumptions} >= {"office.desk_m2", "office.meeting_seat_m2"}


def test_no_walls_says_what_it_cannot_do(office_plan):
    p = make_plan("tnw", OFFICE, walls=False)
    res = run_tool("office_fit", {"scan": "tnw", "headcount": 8, "label_with_vision": False}, ToolContext(plans=lambda sid: p))
    assert "No wall graph" in res.verdict.text
