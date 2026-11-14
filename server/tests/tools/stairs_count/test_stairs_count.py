from threshold.tools import run_tool


def test_levels_steps_and_estimate(ctx):
    r = run_tool("stairs_count", {"scan": "home", "read_panoramas": False}, ctx)
    m = {x.id: x.value for x in r.metrics}
    assert m["floors"] == 2 and m["steps_max"] == round(2.8 / 0.178) and m["door_steps"] == 1
    assert r.verdict.status == "warn"                   # bed and bath are on the entrance floor
    assert "stairs_count:home:step:LK" in {f.id for f in r.findings}
    assert run_tool("stairs_count", {"scan": "home", "riser_m": 0.2, "read_panoramas": False}, ctx) \
        .metrics[1].value == 14
