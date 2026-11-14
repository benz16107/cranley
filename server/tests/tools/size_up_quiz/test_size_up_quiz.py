from threshold.tools.fire_preplan.site import side_of, sides
from threshold.tools.size_up_quiz import score

LAT, LON = 29.76, -95.37
M_LON = 1 / (111320.0 * 0.8682)  # degrees of longitude per metre at 29.76 N


def test_sides_go_clockwise_from_the_address_side():
    assert sides("S") == {"A": "S", "B": "W", "C": "N", "D": "E"}
    assert side_of(270, "S") == "B"   # west of the building when A faces south
    assert side_of(10, "N") == "A"


def test_score_choice_count_and_points():
    qs = [{"id": "side", "kind": "choice", "answer": "B", "accept": ["C"], "points": 1},
          {"id": "beds", "kind": "count", "answer": 3, "points": 1},
          {"id": "where", "kind": "points", "answer": [[LON, LAT], [LON + 20 * M_LON, LAT]], "points": 2}]
    perfect = score(qs, {"side": "b", "beds": 3, "where": [[LON, LAT], [LON + 20 * M_LON, LAT]]})
    assert perfect["total"] == perfect["max"] == 4
    off = score(qs, {"side": "C", "beds": 2, "where": [[LON + 6.5 * M_LON, LAT]]})
    q = {x["id"]: x for x in off["questions"]}
    assert q["side"]["points"] == 1                       # an accepted corner answer
    assert round(q["beds"]["points"], 2) == 0.67          # one off out of three
    assert q["where"]["points"] == 0.5                    # 6.5 m off scores half of one point, the other missed
    extra = score(qs[2:], {"where": [[LON, LAT], [LON + 20 * M_LON, LAT], [LON + 40 * M_LON, LAT]]})
    assert extra["total"] == 1.5                          # an extra mark costs half of one bedroom
    assert score(qs, {})["total"] == 0
