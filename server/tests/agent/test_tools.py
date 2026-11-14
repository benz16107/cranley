import pytest

from threshold.tools import ToolContext, ToolError, manifests, run_tool
from threshold.tools.types import ToolResult

from .conftest import plans


def ctx():
    return ToolContext(plans=plans)


def test_registry_finds_reference_tools_with_ask_and_pref():
    ms = {m.id: m for m in manifests()}
    assert {"door_widths", "room_census"} <= set(ms)
    w = ms["door_widths"].inputs["properties"]["min_width_m"]
    assert w["x-pref"] == "access.door_width_m" and "x-ask" in w
    assert "min_width_m" in ms["door_widths"].inputs["required"]
    assert ms["door_widths"].inputs["properties"]["scan"]["x-source"] == "selection.scan"


def test_bad_inputs_and_unknown_tool_raise_tool_error():
    with pytest.raises(ToolError, match="min_width_m"):
        run_tool("door_widths", {"scan": "t1"}, ctx())
    with pytest.raises(ToolError, match="Unknown"):
        run_tool("nope", {}, ctx())
    with pytest.raises(ToolError, match="No scan"):
        run_tool("room_census", {"scan": "missing"}, ctx())


def test_door_widths_statuses_pins_and_rules():
    c = ctx()
    r = run_tool("door_widths", {"scan": "t1", "min_width_m": 0.8}, c)
    assert isinstance(r, ToolResult) and r.tool == "door_widths"
    status = {ch.id: ch.status for ch in r.checks}
    assert status == {"o1": "fail", "o2": "warn", "o3": "pass"}  # the window is not a doorway
    assert r.verdict.status == "fail" and "1 of 3" in r.verdict.text
    assert [f.status for f in r.findings] == ["fail", "warn"]
    assert r.findings[0].title == "Doorway, Bedroom to unlabelled room"
    pins = next(o for o in r.overlays if o.kind == "pins")
    assert len(pins.pins) == 3
    assert {o.style for o in r.overlays if o.kind == "rule"} == {"pass", "warn", "fail"}
    assert c.steps and r.metrics[1].value == 0.7


def test_door_widths_all_pass_and_no_doors():
    r = run_tool("door_widths", {"scan": "t1", "min_width_m": 0.5}, ctx())
    assert r.verdict.status == "pass" and not r.findings
    import copy
    p = copy.deepcopy(plans("t1")); p["openings"] = []
    r = run_tool("door_widths", {"scan": "x", "min_width_m": 0.8}, ToolContext(plans=lambda s: p))
    assert r.verdict.status == "unknown"


def test_room_census_groups_by_type_and_skips_void():
    r = run_tool("room_census", {"scan": "t1"}, ctx())
    m = {x.id: x.value for x in r.metrics}
    assert m["rooms"] == 3 and m["area_total"] == 36.0
    assert m["area.Unlabelled"] == 20.0 and m["area.Bedroom"] == 12.0
    lens = r.overlays[0]
    assert lens.kind == "lens" and set(lens.values) == {"r1", "r2", "r3"}
    assert r.verdict.status == "pass"  # two of three rooms have a type
