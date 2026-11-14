"""pet_fit on the hand-made two-storey test home (tests/tools/conftest.py) and hand-made evidence: no sponsor data."""
from shapely.geometry import Point

from tests.tools.conftest import make_home
from threshold.tools import ToolContext, run_tool
from threshold.tools.pet_fit import Pet, fence_state, home, policy, rules, unit_floor


def test_spots_in_the_test_home():
    plan = make_home()
    c = home.crate_spot(plan, "large")
    assert c and c["label"] in home.CRATE_ROOMS
    lt = home.litter_spot(plan)
    assert lt and lt["food_m"] >= home.LITTER_FROM_FOOD_M
    kitchen = next(r for r in plan["rooms"] if r["label"] == "Kitchen")
    from shapely.geometry import Polygon
    assert Polygon(kitchen["polygon"]).distance(Point(lt["center"][:2])) >= 3.0
    assert c["center"][2] > 0  # placed above the floor at scan z


def test_stairs_and_fall_windows():
    plan = make_home()
    st = home.stairs(plan)
    assert st["floors"] == 2 and st["steps_max"] == round(2.8 / 0.178) and st["bedroom_on_entry"]
    assert home.fall_windows(plan)["windows"] == []           # the only window is downstairs
    plan["openings"].append({"id": "W2", "wall": "u1", "floor": "f2", "type": "window", "width": 1.0, "height": 1.2,
                             "sill": 3.6, "center": [2, 0], "rooms": ["U"]})
    w = home.fall_windows(plan)["windows"]
    assert [x["id"] for x in w] == ["W2"] and w[0]["drop_m"] >= 2.8


def apt(**kw):
    base = {"property_id": 1, "no_pets": False, "negotiable": None, "walkup": False, "elevators": 2, "path": "p",
            "policies": [{"petType": 3, "type": "dog", "weight": 50, "numPets": 2}, {"petType": 2, "type": "cat"}]}
    return {**base, **kw}


def statuses(pet, E):
    return {r[0]: r[5] for r in rules(pet, E, "k")}


def test_policy_weight_limit_and_no_pets():
    E = {"apt": apt(), "apartment": True, "site": None}
    assert statuses(Pet(kind="dog", weight_lb=60), E)["policy"] == "fail"
    assert statuses(Pet(kind="dog", weight_lb=40), E)["policy"] == "pass"
    assert statuses(Pet(kind="small"), E)["policy"] == "fail"       # the record names dogs and cats only
    assert statuses(Pet(kind="cat"), {**E, "apt": apt(no_pets=True)})["policy"] == "fail"
    assert statuses(Pet(kind="cat"), {**E, "apt": apt(policies=[])})["policy"] == "unknown"


def test_pool_fence_road_and_stairs_rules():
    E = {"apartment": False, "site": object(), "pool": {"pool": True, "enclosed": False},
         "listing": {"fence": ["Back Yard Fenced"]}, "road": {"m": 20.0, "name": "X", "highway": "primary"},
         "stairs": {"steps_max": 16, "bedroom_on_entry": False, "floors": 2}}
    s = statuses(Pet(kind="dog", weight_lb=70, age="senior"), E)
    assert s["pool"] == "fail" and s["fence"] == "pass" and s["stairs"] == "fail"
    assert s["road"] == "pass"                       # close to a busy road, but the yard is fenced
    s = statuses(Pet(kind="cat", outdoor=True), {**E, "listing": {}})
    assert s["road"] == "warn" and s["fence"] == "unknown" and "pool" not in s


def test_fence_and_unit_floor_readers():
    assert policy.fenced({"fence": ["Fence Around Pool"]}) is None
    assert policy.fenced({"fence": ["Partially Fenced Property"]}) == "partial"
    assert fence_state({"fence_photo": {"back_yard_fenced": "yes", "gaps": "yes"}}) == "partial"
    assert unit_floor("1 A St, PH7, Los Angeles, CA, 90024, US") == (None, "penthouse")
    assert unit_floor("1 A St, 1204, Houston, TX, 77077, US")[0] == 12


def test_whole_tool_indoors_only(monkeypatch):
    from threshold.sources import index
    monkeypatch.setattr(index, "rows", dict)
    monkeypatch.setattr(policy, "bundle", lambda sid, pid: {})
    plan = make_home()
    r = run_tool("pet_fit", {"scan": "home", "use_vision": False, "nearby": False,
                             "pets": [{"kind": "dog", "weight_lb": 95, "age": "senior"}, {"kind": "cat"}]},
                 ToolContext(plans=lambda sid: plan))
    ids = {c.id for c in r.checks}
    assert {"pet1.stairs", "pet1.crate", "pet1.outdoor", "pet2.litter"} <= ids
    assert "not checked" in r.verdict.text and r.verdict.status in ("warn", "fail")
    assert any(o.kind == "box" for o in r.overlays)
