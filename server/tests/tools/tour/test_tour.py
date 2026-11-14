"""Tour: stops are chosen and ordered by code, and every line is a finding's own words."""
from tests.agent.conftest import make_plan
from threshold.tools import ToolContext, run_tool
from threshold.tools.tour import Evidence, build, sentences


def ev(id, status, detail, anchor, title="Finding"):
    return Evidence(id=id, title=title, status=status, detail=detail, anchor=anchor, tool="door_widths")


def test_sentences_cut_at_a_sentence_and_change_nothing():
    text = "Clear width 0.70 m against 0.81 m. It is the only door to the bedroom. " + "More. " * 60
    out = sentences(text, 75)
    assert out == "Clear width 0.70 m against 0.81 m. It is the only door to the bedroom."
    assert sentences("One sentence with no end", 10) == "One sentence with no end"


def test_the_way_in_comes_first_then_the_worst_finding_at_each_place():
    plan = make_plan()
    found = [ev("a", "pass", "Wide enough.", {"sid": "t1", "opening": "o3"}),
             ev("b", "fail", "Clear width 0.65 m against 0.81 m.", {"sid": "t1", "opening": "o1"}),
             ev("c", "warn", "Close to the limit.", {"sid": "t1", "room": "r2"}),
             ev("d", "fail", "On the map, not in the building.", {"geo": [-95.0, 29.7]}),
             ev("e", "warn", "A shorter note on the same door.", {"sid": "t1", "opening": "o1"})]
    t = build(plan, "can a wheelchair get through the doors", found, 6)
    got = [s["from"] for s in t["stops"]]
    assert got[0] == "a"                    # the way in opens the tour, even when it passes
    assert set(got[1:]) == {"b", "c"}       # then the worst finding at each place; the map finding has no place here
    assert all(s["line"] in {f.detail for f in found} for s in t["stops"])  # nothing written, only quoted
    assert t["considered"] == 4


def test_the_tool_returns_stops_as_findings_in_order():
    plan = make_plan()
    found = [{"id": "x", "title": "Narrow door", "status": "fail", "detail": "Clear width 0.65 m against 0.81 m.",
              "anchor": {"sid": "t1", "opening": "o1"}, "tool": "door_widths"}]
    r = run_tool("tour", {"scan": "t1", "findings": found, "question": "doors"}, ToolContext(plans=lambda s: plan))
    assert [f.id for f in r.findings] == ["tour:t1:00"]
    assert r.findings[0].detail == "Clear width 0.65 m against 0.81 m."
    assert r.verdict.status == "fail"


def test_nothing_to_tour_says_so():
    r = run_tool("tour", {"scan": "t1", "findings": []}, ToolContext(plans=lambda s: make_plan()))
    assert r.verdict.status == "unknown" and not r.findings


def test_each_kind_of_evidence_before_one_repeats():
    plan = make_plan()
    doors = [Evidence(id=f"d{i}", title="Narrow door", status="fail", detail="Too narrow.", anchor={"sid": "t1", "point": [i, 0, 0]},
                      tool="door_widths") for i in range(5)]
    alarm = Evidence(id="s", title="No alarm seen", status="warn", detail="Not seen.", anchor={"sid": "t1", "room": "r1"},
                     tool="life_safety_census")
    got = {s["from"] for s in build(plan, None, doors + [alarm], 3)["stops"]}
    assert "s" in got and len(got) == 3


def test_the_door_standard_picks_the_tools_when_the_question_does_not():
    import re

    from threshold.tools.tour import TOPICS
    topic = lambda text: [k for k, (pat, _) in TOPICS.items() if re.search(pat, text.lower())]
    assert topic("Can I live in this house? ADA 2010 404.2.3, 32 in clear") == ["access"]
    assert topic("Show me what matters. IBC 2021 1010.1.1, 32 in clear egress") == ["fire"]
    assert topic("Walk me through this house") == []
