from threshold.tools import ToolContext, run_tool

from ..conftest import make_plan


def test_closets_share_and_bedroom_without_closet():
    p = make_plan("tunit", [("b1", 0, 0, 4, 4, "Bedroom"), ("c1", 4, 0, 5, 2, "Closet"), ("b2", 0, 4, 4, 8, "Bedroom"),
                            ("lr", 5, 0, 10, 8, "Living Room"), ("pan", 4, 2, 5, 3, "Pantry")],
                  doors=[("b1", "c1", 0.7), ("b2", "lr", 0.8), ("pan", "lr", 0.6)])
    res = run_tool("storage_space", {"scan": "tunit", "label_with_vision": False}, ToolContext(plans=lambda sid: p))
    m = {x.id: x.value for x in res.metrics}
    assert m["storage_rooms"] == 2  # closet and pantry
    assert m["storage_share"] == round(100 * 3 / 75, 1)
    bad = [f for f in res.findings if f.title == "Bedroom without a closet room"]
    assert [f.anchor.room for f in bad] == ["b2"]
