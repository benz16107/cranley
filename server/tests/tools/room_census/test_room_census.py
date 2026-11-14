from threshold.tools import ToolContext, run_tool

from ..conftest import make_plan


def test_a_yard_with_no_walls_is_not_floor_area():
    p = make_plan("yard", [("lr", 0, 0, 5, 4, "Living Room"), ("cl", 5, 0, 6, 2, "Closet")])
    p["rooms"].append({"id": "yard", "floor": "f1", "label": None, "polygon": [], "area": 1348.5, "walls": [], "holes": []})
    ctx = ToolContext(plans=lambda sid: p)
    census = run_tool("room_census", {"scan": "yard"}, ctx)
    assert {m.id: m.value for m in census.metrics}["area_total"] == 22
    assert "1 area with no walls (outdoor or unscanned) is left out" in census.verdict.text
    store = run_tool("storage_space", {"scan": "yard", "label_with_vision": False}, ctx)
    assert {m.id: m.value for m in store.metrics}["storage_share"] == round(100 * 2 / 22, 1)
