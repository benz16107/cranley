import pytest
from pydantic import ValidationError

from threshold.agent.catalog import catalog, personas
from threshold.agent.composer import compose, prompt, schema
from threshold.agent.workspace import (
    BriefSet,
    PrefSet,
    QuestionAsk,
    ToolEnable,
    Workspace,
    apply,
)


class Fake:
    """Answers the composer's one call with a fixed choice and records what it was asked."""
    def __init__(self, persona, tools):
        self.persona, self.tools, self.seen = persona, tools, None

    def structured(self, system, user, schema):
        self.seen = (user, schema)
        return schema(persona=self.persona, summary="A person.",
                      tools=[{"id": t, "reason": f"because {t}"} for t in self.tools])


def test_presets_exist_and_name_known_tools():
    assert len(personas()) >= 11  # tool workstreams add presets as new files
    for p in personas().values():
        assert set(p.tools) <= set(catalog()), p.id
    assert catalog()["flood_rehearsal"].status == "planned" and catalog()["door_widths"].status == "ready"


def test_schema_is_an_enum():
    S = schema(["door_widths", "room_census"], ["wheelchair_user"])
    with pytest.raises(ValidationError):
        S(persona="wheelchair_user", summary="x", tools=[{"id": "teleporter", "reason": "x"}])
    with pytest.raises(ValidationError):
        S(persona="pirate", summary="x", tools=[{"id": "door_widths", "reason": "x"}])


def test_wheelchair_preset_fills_threshold_so_no_question():
    ops = compose("I use a wheelchair", Workspace(id="w"), Fake("wheelchair_user", ["door_widths", "room_census",
                                                                                   "step_free_route"]))
    assert isinstance(ops[0], BriefSet) and ops[0].persona == "wheelchair_user"
    enabled = {o.tool: o.status for o in ops if isinstance(o, ToolEnable)}
    assert enabled == {"door_widths": "ready", "room_census": "ready", "step_free_route": "planned"}
    assert not [o for o in ops if isinstance(o, QuestionAsk)]


def test_mover_gets_asked_the_width_once():
    ops = compose("Will my sofa fit?", Workspace(id="w"), Fake("furniture_mover", ["door_widths", "door_widths"]))
    qs = [o.question for o in ops if isinstance(o, QuestionAsk)]
    assert len(qs) == 1 and qs[0].key == "access.door_width_m" and qs[0].input["type"] == "number"
    assert sum(isinstance(o, ToolEnable) for o in ops) == 1


def test_a_saved_preference_answers_the_question():
    d = apply(Workspace(id="w"), PrefSet(key="access.door_width_m", value=0.9))
    ops = compose("sofa", d, Fake("furniture_mover", ["door_widths"]))
    assert not [o for o in ops if isinstance(o, QuestionAsk)]


def test_removed_tools_leave_the_enum():
    d = apply(Workspace(id="w"), PrefSet(key="tool.off.room_census", value=True))
    user, ids = prompt("x", d)
    assert "room_census" not in ids and "removed these before" in user
