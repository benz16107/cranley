from threshold.scanplan import normalize

RAW = {"id": "t", "name": "square", "floors": [{"id": "f", "label": "1", "sequence": 0,
       "vertices": [{"id": v, "position": {"x": x, "y": y}} for v, x, y in [("a", 0, 0), ("b", 4, 0), ("c", 4, 3), ("d", 0, 3)]],
       "edges": [{"id": "ab", "type": "wall", "thickness": 0.1, "vertices": [{"id": "a"}, {"id": "b"}],
                  "openings": [{"id": "o", "type": "doorway", "width": 0.9, "height": 2.0, "lowerElevation": 0, "relativeCenter": 0.25}]},
                 {"id": "bc", "type": "wall", "vertices": [{"id": "b"}, {"id": "c"}]},
                 {"id": "cd", "type": "wall", "vertices": [{"id": "c"}, {"id": "d"}]},
                 {"id": "da", "type": "wall", "vertices": [{"id": "d"}, {"id": "a"}]}]}],
       "rooms": [{"id": "r", "floor": {"id": "f"}, "classifications": [{"label": "Other", "confidence": 1}],
                  "boundary": {"edges": [{"id": e} for e in ("ab", "cd", "bc", "da")]}}]}


def test_room_polygon_door_position_and_unknown_label():
    plan = normalize(RAW)
    room, door = plan["rooms"][0], plan["openings"][0]
    assert len(room["polygon"]) == 4 and room["area"] == 12  # edges given out of order still chain
    assert room["label"] is None                              # "Other" means unlabelled
    assert door["center"] == [1.0, 0.0] and door["rooms"] == ["r"]
