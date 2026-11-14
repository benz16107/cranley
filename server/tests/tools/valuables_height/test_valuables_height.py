"""valuables_height with a fake vision reader on the hand-made house."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "flood_rehearsal"))
from flood_house import house

from threshold.tools.flood_rehearsal import scenario
from threshold.tools.flood_rehearsal.scenario import FloodInputs
from threshold.tools.valuables_height import Inputs, inventory, losses, result


def item(name, room, z, cost, size, fixture=False, count=1):
    anchor = {"sid": "house", "point": [2.0, 2.0, z]} if z is not None else \
        {"sid": "house", "pano": "l1", "yaw_deg": 10.0, "pitch_deg": -5.0}
    return {"name": name, "category": "furniture", "count": count, "size_class": size, "cost_class": cost,
            "fixture": fixture, "confidence": "high", "anchor": anchor,
            "media": [{"kind": "pano", "ref": f"house/{room.lower()}1/2", "box": [0.1, 0.1, 0.2, 0.2]}]}


def fake_contents(plan, room):
    items = {"L": [item("Sofa", "L", 0.0, "$500 to $2,000", "two people carry"),
                   item("Television", "L", 0.6, "$500 to $2,000", "one person carries"),
                   item("Lamp", "L", None, "$100 to $500", "hand-held"),
                   item("Built-in shelves", "L", 0.0, "$500 to $2,000", "needs a mover or is built in", fixture=True)]}
    return {"room": room, "pano": {"L": "l1", "K": "k1", "R": "r1", "G": "g1"}[room], "items": items.get(room, []),
            "defurnished_used": False}


def fake_objects(plan, labels, panos, max_panos):
    def f(label, z):
        return {"label": label, "room": "L", "pano_anchor": {"sid": "house", "pano": "l1", "yaw_deg": 0, "pitch_deg": -20},
                "finding": {"anchor": {"sid": "house", "point": [1.0, 4.9, z]}, "source": {"confidence": "medium"},
                            "media": [{"kind": "pano", "ref": "house/l1/1", "box": [0.4, 0.6, 0.45, 0.65]}]}}
    return [f("outlet near the floor", 0.3), f("electrical panel", 1.2)]


@pytest.fixture
def flood(monkeypatch):
    monkeypatch.setattr(scenario, "_site", lambda *a: (_ for _ in ()).throw(RuntimeError("offline")))
    p = house()
    return p, scenario.run(p, FloodInputs(scan="house", depth_m=0.5), lambda s: None)


def test_inventory_heights_and_wetness(flood):
    p, fl = flood
    inv = inventory(p, fl, 8, lambda s: None, contents=fake_contents, find_objects=fake_objects)
    by = {x["name"]: x for x in inv["items"]}
    assert by["Sofa"]["height_m"] == 0.0 and by["Sofa"]["wet_mid"]
    assert by["Television"]["height_m"] == pytest.approx(0.6) and not by["Television"]["wet_hi"]
    assert by["Lamp"]["height_m"] is None and not by["Lamp"]["wet_lo"] and by["Lamp"]["wet_hi"]
    util = {u["label"]: u for u in inv["utilities"]}
    assert util["outlet near the floor"]["wet_hi"] is False or util["outlet near the floor"]["height_m"] == pytest.approx(0.3)
    assert not util["electrical panel"]["wet_hi"]
    assert inv["rooms_read"][0] == "G"                          # the deepest room is read first


def test_losses_are_ranges(flood):
    p, fl = flood
    inv = inventory(p, fl, 8, lambda s: None, contents=fake_contents, find_objects=fake_objects)
    loss = losses(inv["items"])
    assert loss["belongings"] == (500, 2000 + 500)               # sofa sure; lamp (unknown height) only at the top
    assert loss["fixtures"] == (500, 2000)


def test_result_pins_every_item_on_plan_and_panorama(flood):
    p, fl = flood
    inv = inventory(p, fl, 8, lambda s: None, contents=fake_contents, find_objects=fake_objects)
    r = result("house", p, Inputs(scan="house", depth_m=0.5), fl, inv)
    pins = next(o for o in r.overlays if o.kind == "pins").pins
    assert {"item:L:0", "item:L:0:pano", "util:u1", "util:u1:pano"} <= {x.id for x in pins}
    assert r.verdict.status == "fail" and "$500 and $2,500" in r.verdict.text
    assert {c.rule.split(" above")[0] for c in r.checks} == {"Low outlet", "Electrical panel"}
    assert any(f.id.endswith(":staging") for f in r.findings)
