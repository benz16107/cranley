"""Small hand-made plans; no sponsor data and no network."""
import pytest

from threshold.agent.catalog import catalog
from threshold.agent.investigator import attach
from threshold.agent.workspace import Session
from threshold.tools.types import Manifest

UNBUILT = "not_built_yet"  # a planned tool that stays planned, whatever real tools get built


@pytest.fixture(autouse=True, scope="session")
def planned_stub():
    catalog()[UNBUILT] = Manifest(id=UNBUILT, title="Not built yet", summary="A planned tool.",
                                  model_description="A planned tool.", status="planned")
    yield
    catalog().pop(UNBUILT, None)


def make_plan(sid="t1"):
    rooms = [{"id": "r1", "label": "Bedroom", "area": 12.0}, {"id": "r2", "label": "Bathroom", "area": 4.0},
             {"id": "r3", "label": None, "area": 20.0}, {"id": "r4", "label": "Void", "area": 1.0}]
    rooms = [{"floor": "f1", "label_confidence": 1, "label_source": "matterport", "polygon": [], "height": 2.5,
              "width": None, "depth": None, "walls": [], "holes": [], **r} for r in rooms]
    def door(id, w, rs, t="doorway"):
        return {"id": id, "wall": "w1", "floor": "f1", "type": t, "width": w, "height": 2.0, "sill": 0,
                "center": [0, 0], "rooms": rs}
    return {"schema": "scanplan/1", "sid": sid, "name": "Test", "has": {"room_labels": True, "openings": True},
            "floors": [{"id": "f1", "label": "1", "sequence": 0}],
            "walls": [{"id": "w1", "floor": "f1", "a": [0, 0], "b": [1, 0], "type": "wall", "thickness": 0.1,
                       "length": 1, "rooms": ["r1"], "openings": []}],
            "rooms": rooms,
            "openings": [door("o1", 0.70, ["r1", "r3"]), door("o2", 0.84, ["r2", "r3"]), door("o3", 0.95, ["r3"]),
                         door("o4", 1.2, ["r1"], "window")],
            "panos": [{"id": "p1", "label": "1", "position": [0, 0, 1.5], "rotation": None, "floor": "f1",
                       "room": "r1", "neighbors": []}]}


PLANS = {"t1": make_plan("t1"), "t2": make_plan("t2")}


def plans(sid):
    if sid not in PLANS:
        raise LookupError(sid)
    return PLANS[sid]


@pytest.fixture
def session(tmp_path):
    return attach(Session.create(root=tmp_path), plans)
