import pytest

from threshold.tools import run_tool
from threshold.tools.measure_search import table
from tests.tools.conftest import make_home, no_walls


def test_measures_of_the_hand_made_home():
    m = table.measure(make_home())
    assert m["floors"] == 2 and m["bedrooms"] == 2 and m["bathrooms"] == 1
    assert m["implausible_doors"] == 1 and m["level_changes"] == 1
    assert m["bath_route_door"] == pytest.approx(0.90)       # E 0.95 clear, HT 0.90 clear
    assert m["bed_route_door_min"] is None                    # the upstairs bedroom is not reachable
    assert m["bed_route_door_max"] == pytest.approx(0.65)
    assert m["step_free_bath"] == 1 and m["wheelchair_bath"] == 1
    assert m["bed_bath_entry_floor"] == 1 and m["windows"] == 1
    assert table.measure(no_walls())["bath_route_door"] is None


def test_search_ranks_and_explains(tmp_path, monkeypatch):
    rows = []
    for sid, plan in (("a", make_home("a")), ("b", no_walls("b"))):
        rows.append(({"sid": sid, "name": sid.upper(), "kind": "house", "city": "Houston", "lat": 29.7, "lon": -95.4,
                      "walls": int(bool(plan["walls"])), **table.measure(plan)}, table.doors_of(plan)))
    db = tmp_path / "m.sqlite"
    table.write(rows, {"scans": 2}, db)
    res = table.search([table.parse("bath_route_door>=0.81"), table.parse("bedrooms>=2")], path=db)
    assert res["pool"] == 2 and res["answerable"] == 1 and res["matches"] == 1
    assert res["rows"][0]["why"][0] == "Doors to the bathroom 0.90 m >= 0.81 m"
    monkeypatch.setattr(table, "DB", db)
    r = run_tool("measure_search", {"criteria": [{"measure": "bath_route_door", "op": ">=", "value": 0.81}]})
    assert r.scope.sid == "a" and r.checks[0].status == "pass" and r.findings[0].anchor.geo == (-95.4, 29.7)
    picked = run_tool("measure_search", {"need": "step_free_bath"})            # a need is a fixed list of criteria
    assert picked.verdict.status != "unknown" and "Step-free way to a bathroom" in picked.checks[0].rule
    assert run_tool("measure_search", {}).verdict.status == "unknown"           # nothing asked: says what to give
    from types import SimpleNamespace

    from threshold.agent.investigator import own_table
    from threshold.tools.registry import load
    t = own_table(load()["measure_search"].manifest, SimpleNamespace(id="run_9", result=r))
    assert t.run == "run_9" and t.rows == ["m0"] and t.labels["m0"] == "A"         # the one match, by name
    assert [(c.metric, c.label) for c in t.columns] == [("score", "Margin over the criteria"),
                                                        ("bath_route_door", "Doors to the bathroom")]
    assert {m.id: m.value for m in r.metrics}["m0/bath_route_door"] == 0.9


def test_parse_rejects_unknown_measures():
    assert table.parse("floors==1") == {"measure": "floors", "op": "==", "value": 1.0}
    with pytest.raises(ValueError):
        table.parse("nope>=1")
