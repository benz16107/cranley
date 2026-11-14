"""room_sizes on the feng_shui test house (hand-made, no sponsor data)."""
from threshold.tools import ToolContext, run_tool

from ..feng_shui.test_feng_shui import house


def test_sizes_ranked_with_assumed_heights():
    p = house()
    p["rooms"][0]["height"] = None  # the living room has no height: the median of the others (2.5 m)
    res = run_tool("room_sizes", {"scan": "fs", "min_area_m2": 10}, ToolContext(plans=lambda sid: p))
    m = {x.id: x for x in res.metrics}
    assert m["largest"].value == 27 and "Living Room" in m["largest"].label
    assert (m["L/width"].value, m["L/depth"].value, m["L/height"].value) == (9, 3, 2.5)
    assert m["L/height"].source.confidence == "low" and m["R/height"].source.confidence == "medium"
    assert {c.id for c in res.checks if c.status == "fail"} == {"area:H", "area:T", "area:H2"}
    assert "1 room has no ceiling" in res.verdict.text
