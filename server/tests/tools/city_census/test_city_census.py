from types import SimpleNamespace

from threshold.agent.investigator import own_table
from threshold.facts import census, db
from threshold.tools import run_tool
from threshold.tools.registry import load


def test_groups_come_back_as_a_ranked_table(monkeypatch):
    monkeypatch.setattr(db, "available", lambda: True)
    monkeypatch.setattr(census, "preset", lambda name, **kw: {
        "source": "test", "ms": 1, "sql": "SELECT", "stat": "share", "by": "zip", "field": "wheelchair_bath",
        "label": "Wheelchair homes", "scans_with_field": 9,
        "rows": [{"grp": "77094", "scans": 6, "share": 0.5, "median": 1.0, "mean": 0.5},
                 {"grp": "77001", "scans": 3, "share": 0.33, "median": 0.0, "mean": 0.33}]})
    r = run_tool("city_census", {"preset": "wheelchair_homes"})
    assert not r.checks                                            # groups are rows, not "pass" checks
    m = {x.id: x for x in r.metrics}
    assert m["g0/share"].value == 50.0 and m["g0/share"].unit == "%" and m["g0/scans"].label == "zip 77094"
    t = own_table(load()["city_census"].manifest, SimpleNamespace(id="run_1", result=r))
    assert t.run == "run_1" and t.rows == ["g0", "g1"] and t.labels["g1"] == "zip 77001"
    assert [c.metric for c in t.columns] == ["share", "median", "mean", "scans"]
