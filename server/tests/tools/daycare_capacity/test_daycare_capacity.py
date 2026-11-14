from threshold.tools.daycare_capacity import RULES, capacities, indoor


def test_texas_and_california_rules():
    tx = capacities(RULES["TX"], 3000, 4000, 2, 3)
    assert tx == {"indoor": 100, "outdoor": 200, "toilets": 34, "sinks": 51}  # 4000 / (80 * 25%)
    ca = capacities(RULES["CA"], 3500, 3000, 2, 2)
    assert ca == {"indoor": 100, "outdoor": 40, "toilets": 15, "sinks": 15}    # one of each kept spare
    assert capacities(RULES["TX"], None, None, None, None) == {"indoor": None, "outdoor": None, "toilets": None, "sinks": None}


def test_indoor_rooms():
    rooms = [{"id": "a", "label": "Bedroom", "area": 12}, {"id": "b", "label": "Bathroom", "area": 5},
             {"id": "c", "label": None, "area": 30}, {"id": "d", "label": "Living Room", "area": 25},
             {"id": "e", "label": "Hallway", "area": 6}, {"id": "f", "label": "Closet", "area": 1}]
    counted, excluded, unknown = indoor({"rooms": rooms})
    assert [r["id"] for r in counted] == ["a", "d"] and [r["id"] for r in excluded] == ["b", "e"]
    assert [r["id"] for r in unknown] == ["c"]
