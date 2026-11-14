import pytest

from threshold.geometry import evaluate_pack, list_packs, load_pack
from threshold.geometry.rules import MEASURES

FIELDS = {"id", "text", "standard", "measure", "threshold", "unit", "severity", "compare"}


def test_every_pack_is_complete_data():
    ids = [p["id"] for p in list_packs()]
    assert {"wheelchair", "aging_in_place", "furniture_path", "robot_fit", "stretcher"} <= set(ids)
    for pid in ids:
        pack = load_pack(pid)
        for rule in pack["rules"]:
            assert FIELDS <= set(rule), (pid, rule["id"])
            assert rule["measure"] in MEASURES
            assert rule["severity"] in ("required", "advisory") and rule["compare"] in ("at_least", "at_most")
            for v in [rule["threshold"], *rule.get("box", [])]:
                assert not isinstance(v, str) or v[1:] in pack["params"]


def test_wheelchair_pack_finds_the_narrow_bathroom_door(plan):
    r = evaluate_pack(plan, "wheelchair")
    checks = {c["id"]: c for c in r["checks"]}
    door = checks["wheelchair.door_clear_width"]
    assert door["result"] == "likely fail" and door["measured"] == pytest.approx(0.65)
    assert door["standard"].startswith("ADA 2010")
    f = next(f for f in r["findings"] if f["id"] in door["findings"])
    assert f["anchor"] == {"sid": "test", "opening": "BC"} and f["status"] == "fail"
    assert checks["wheelchair.turning_space"]["result"] == "likely pass"   # living 3.9 m, bath 1.9 m
    assert r["verdict"]["status"] == "fail"
    assert r["overlays"][0]["kind"] == "pins"


def test_thresholds_flag_the_step_into_the_bathroom(plan):
    check = next(c for c in evaluate_pack(plan, "wheelchair")["checks"] if c["id"] == "wheelchair.thresholds")
    assert check["measured"] == pytest.approx(0.2) and check["result"] == "likely fail"


def test_parameters_change_the_answer(plan):
    small = evaluate_pack(plan, "robot_fit", {"body_width": 0.4, "step_height": 0.25})
    big = evaluate_pack(plan, "robot_fit", {"body_width": 0.9})
    reach = lambda r: next(c for c in r["checks"] if c["id"] == "robot_fit.reach")["result"]
    assert reach(small) == "likely pass" and reach(big) == "likely fail"
    assert {a["id"]: a["value"] for a in small["assumptions"]}["body_width"] == 0.4


def test_no_walls_gives_unknown_not_an_error(no_walls):
    for p in list_packs():
        r = evaluate_pack(no_walls, p["id"])
        assert r["verdict"]["status"] in ("unknown", "warn", "fail", "pass")
    assert evaluate_pack(no_walls, "wheelchair")["verdict"]["status"] == "unknown"
