"""Every function over the real ScanPlan fixtures (skipped when the data folder is missing)."""
import time

import pytest

from threshold.geometry.survey import survey_plan

from .conftest import fixture_plans

PLANS = fixture_plans()


@pytest.mark.skipif(not PLANS, reason="ScanPlan fixtures not in $THRESHOLD_DATA_DIR")
@pytest.mark.parametrize("plan", PLANS, ids=[p["sid"] for p in PLANS])
def test_every_function_answers_or_says_why(plan):
    t0 = time.perf_counter()
    res = survey_plan(plan)
    assert time.perf_counter() - t0 < 2.0                      # all functions together, cold cache
    has_walls = bool(plan["walls"])
    for name in ("room_graph", "reach", "turning", "pack:wheelchair"):
        assert res[name][0] == has_walls, (name, res[name][1])
    for name in ("takeoff", "latlon", "water"):
        assert res[name][0], name
