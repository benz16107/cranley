import pytest

from threshold.geometry import turning_space
from threshold.tools import run_tool
from threshold.whatif import EditError, apply, compare, cost, propose, renovate


def _room(plan, rid):
    return next((r for r in plan["rooms"] if r["id"] == rid), None)


def _open(plan, oid):
    return next(o for o in plan["openings"] if o["id"] == oid)


def test_widen_door_edits_a_copy_with_a_stable_id(flat):
    after, diff = apply(flat, [{"op": "widen_door", "opening": "LT", "width_m": 0.915}])
    assert _open(after, "LT")["width"] == 0.915 and _open(flat, "LT")["width"] == 0.75
    assert after["sid"].startswith("w_") and len(after["sid"]) == 14
    assert after["sid"] == apply(flat, [{"op": "widen_door", "opening": "LT", "width_m": 0.915}])[0]["sid"]
    assert after["whatif"]["base"] == "flat" and diff[0]["width"] == [0.75, 0.915]


@pytest.mark.parametrize("edit,why", [
    ({"op": "widen_door", "opening": "LT", "width_m": 0.7}, "already"),
    ({"op": "widen_door", "opening": "LK", "width_m": 1.8}, "does not fit"),
    ({"op": "widen_door", "opening": "nope", "width_m": 0.9}, "no opening"),
    ({"op": "move_wall", "wall": "l1", "offset_m": 0.2}, "two scanned rooms"),
    ({"op": "add_ramp", "opening": "E"}, "no ramp needed"),
    ({"op": "door_swing", "opening": "LK", "swing": "pocket"}, "no door"),
])
def test_edits_that_do_not_fit_say_why(flat, edit, why):
    with pytest.raises(EditError, match=why):
        apply(flat, [edit])


def test_widen_slides_the_door_along_its_wall_when_it_must(flat):
    _open(flat, "LT")["center"] = [5, 0.2]  # near the corner: a 0.915 m door does not fit centred there
    after, diff = apply(flat, [{"op": "widen_door", "opening": "LT", "width_m": 0.915}])
    assert diff[0]["shift_m"] > 0.1 and _open(after, "LT")["center"][1] >= 0.915 / 2 + 0.05 - 1e-9


def test_move_wall_grows_the_bathroom_and_shrinks_the_closet(flat):
    after, diff = apply(flat, [{"op": "move_wall", "wall": "tc", "offset_m": 0.3, "grow": "T"}])
    assert _room(after, "T")["area"] == pytest.approx(1.7 * 2.5) and _room(after, "C")["area"] == pytest.approx(0.7 * 2.5)
    assert set(diff[0]["stretched"]) == {"t1", "c1", "tk", "ck"}
    assert turning_space(after, "T")["diameter"] > turning_space(flat, "T")["diameter"] + 0.25


def test_remove_wall_merges_the_closet_into_the_bathroom(flat):
    after, diff = apply(flat, [{"op": "remove_wall", "wall": "tc"}])
    assert _room(after, "C") is None and _room(after, "T")["area"] == pytest.approx(2.4 * 2.5)
    assert _open(after, "CK")["rooms"] == ["T", "K"] and diff[0]["merged_into"] == "T"
    assert turning_space(after, "T")["diameter"] >= 1.55


def test_ramp_levels_the_sill(flat):
    _open(flat, "E")["sill"] = 0.1
    after, diff = apply(flat, [{"op": "add_ramp", "opening": "E"}])
    assert diff[0]["run_m"] == pytest.approx(1.2)
    assert cost.line(diff[0], after)["total"] == round(1.2 * 3.28084 * 185)


def test_proposals_for_the_bathroom(flat):
    turn = [c["edit"].op for c in propose(flat, "bathroom_turn")]
    assert "move_wall" in turn and "remove_wall" in turn
    route = [c["edit"].model_dump() for c in propose(flat, "bathroom_route")]
    assert {"op": "widen_door", "opening": "LT", "width_m": 0.915} in route


def test_flips_show_the_route_and_the_circle(flat, ctx):
    after, _ = apply(flat, [{"op": "widen_door", "opening": "LT", "width_m": 0.915},
                            {"op": "remove_wall", "wall": "tc"}])
    c = compare.context({after["sid"]: after}, ctx)
    fl = {f["key"]: f["change"] for f in compare.flips(compare.run(flat, "wheelchair_ready", ctx),
                                                       compare.run(after, "wheelchair_ready", c))}
    assert fl["step_free_route:route.T"] == "fixed" and fl["turning_space:turn.T"] == "fixed"
    assert fl["door_widths:LT"] == "fixed"


def test_renovate_with_only_a_goal(ctx):
    r = run_tool("renovate", {"scan": "flat", "goal": "wheelchair_ready"}, ctx)
    m = {x.id: x.value for x in r.metrics}
    assert m["failing_after"] == 1 and m["fixed"] >= 4 and m["total_cost"] > 1000
    assert "Closet to Kitchen" in r.verdict.text  # closet doors are left out of the proposals, and the verdict says so
    # moving the wall wins over taking it out: the closet door would then open into the bathroom and fail
    assert {c.rule.split(" (")[0] for c in r.checks if c.status == "fail"} == set()
    sid = next(a.inputs["scan"] for a in r.actions)
    # the saved what-if scan rebuilds from its record and runs any tool
    from threshold.whatif import store
    assert store.record(sid)["base"] == "flat"


def test_your_edits_apply_together_or_say_why(ctx):
    # the second only fits once the first is in: tried alone it fails, together they go through
    r = renovate.run(ctx, "flat", "door_widths", [{"op": "move_wall", "wall": "tc", "offset_m": 0.25, "grow": "C"},
                                                  {"op": "widen_door", "opening": "CK", "width_m": 1.1}])
    assert len(r["package"]) == 2
    with pytest.raises(EditError, match="already"):
        renovate.run(ctx, "flat", "bathroom_turn", [{"op": "widen_door", "opening": "LT", "width_m": 0.7}])


def test_a_wall_cannot_move_past_the_end_of_one_that_meets_it(flat):
    with pytest.raises(EditError, match="shrink away"):
        apply(flat, [{"op": "move_wall", "wall": "tc", "offset_m": 1.2, "grow": "T"}])  # the closet is 1.0 m wide


def test_renovate_your_own_edits_rank_by_effect(ctx):
    r = renovate.run(ctx, "flat", "bathroom_route", [{"op": "door_swing", "opening": "LT", "swing": "swing_out"},
                                                     {"op": "widen_door", "opening": "LT", "width_m": 0.915}])
    first, second = r["candidates"]
    assert first["edit"]["op"] == "widen_door" and first["fixed"] > 0 and second["fixed"] == 0
    assert r["total_cost"] == 1200 + 250
    assert all(a["reliability"] == "low" and a["source"] for a in r["assumptions"])


def test_no_wall_graph_is_said_plainly(ctx, flat):
    flat["quality"]["walls"] = False
    with pytest.raises(EditError, match="no wall graph"):
        apply(flat, [{"op": "remove_wall", "wall": "tc"}])


def test_a_bathroom_merged_with_a_bigger_room_stays_a_bathroom(flat):
    after, diff = apply(flat, [{"op": "remove_wall", "wall": "tk"}])  # bathroom (3.5 m2) and kitchen (5.1 m2)
    assert diff[0]["merged_into"] == "T" and _room(after, "K") is None and _room(after, "T")["label"] == "Bathroom"
