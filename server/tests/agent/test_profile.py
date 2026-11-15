"""The person profile across investigations: what an answer, a removal and feedback teach, where it comes back, and
what is measured. Hand-made plans, a scripted composer, no network."""
from threshold.agent import prefs, profile
from threshold.agent.composer import compose
from threshold.agent.investigator import Investigation, attach
from threshold.agent.workspace import BriefSet, QuestionAsk, Scope, Session, ToolEnable
from threshold.store import FileStore

from .conftest import plans
from .test_composer import Fake


def new(tmp_path, sid="t1"):
    s = attach(Session.create("maya", root=tmp_path), plans)
    s.submit(BriefSet(by="user", scope=Scope(sids=[sid])))
    return s


def composed(s, model, text="Will it work for me?"):
    for op in compose(text, s.doc, model):
        s.submit(op)
    return [q for q in s.doc.questions if not q.answered]


def test_an_answer_is_asked_once_and_says_where_it_came_from(tmp_path):
    a = new(tmp_path)
    (q,) = composed(a, Fake("furniture_mover", ["door_widths"]), "Moving a wide chair in")
    entries = a.submit({"op": "question.answer", "id": q.id, "value": 0.7}, by="user")
    kept = a.doc.prefs["access.door_width_m"]
    assert entries[1].cause == entries[0].seq and kept.value == 0.7 and kept.origin.how == "answer"
    assert kept.origin.workspace == a.doc.id and kept.origin.investigation == "A person."

    b = new(tmp_path, "t2")  # the next investigation, another building
    assert composed(b, Fake("furniture_mover", ["door_widths"])) == []
    assert b.doc.prefs["access.door_width_m"].origin.workspace == a.doc.id  # the origin travels with the fact
    Investigation(b).run("door_widths", {"scan": "t2"})
    notes = {n["kind"]: n for n in profile.because(b.doc)["notes"]}
    assert notes["input"]["text"] == "Using your doorway width: 0.7 m" and notes["input"]["carried"]
    assert notes["input"]["why"].startswith("you told me on ") and "“A person.”" in notes["input"]["why"]
    assert notes["not_asked"]["key"] == "access.door_width_m"
    m = profile.measure(b.doc, b.log)
    assert (m["questions_asked"], m["questions_not_asked"], m["inputs_from_profile"], m["tool_runs"]) == (0, 1, 1, 1)
    assert profile.measure(a.doc, a.log)["questions_asked"] == 1

    a.undo(entries[0].seq)  # taking the answer back forgets the fact, in the profile too
    assert "access.door_width_m" not in a.doc.prefs
    assert composed(new(tmp_path), Fake("furniture_mover", ["door_widths"]))


def test_an_answer_about_one_storm_is_not_a_fact_about_the_person(tmp_path):
    assert profile.standing("kids.youngest_age") and not profile.standing("storm.hours_left")
    assert not profile.standing("flood.depth_m") and not profile.standing("approval.approve:t:i:0")
    a = new(tmp_path)
    a.submit(QuestionAsk(question={"id": "q1", "key": "storm.hours_left", "text": "How long?", "tools": [], "input": {"type": "number"}}))
    a.submit({"op": "question.answer", "id": "q1", "value": 6}, by="user")
    assert "storm.hours_left" not in a.doc.prefs


class Stating(Fake):
    def structured(self, system, user, schema):
        self.seen = (user, schema)
        return schema(persona=self.persona, summary="A person.", tools=[{"id": t, "reason": "x"} for t in self.tools],
                      stated=[{"key": "access.door_width_m", "quote": "70 cm wide"}])


def test_a_size_the_person_stated_beats_the_persona_default(tmp_path):
    a = new(tmp_path)
    (q,) = composed(a, Stating("wheelchair_user", ["door_widths"]), "I use a wheelchair, my chair is 70 cm wide")
    assert q.key == "access.door_width_m" and q.answer == 0.7 and not q.answered  # offered in their words, to confirm


def test_not_relevant_hides_the_kind_now_and_next_time(tmp_path):
    a = new(tmp_path)
    a.submit(ToolEnable(tool="door_widths"))
    Investigation(a).run("door_widths", {"scan": "t1", "min_width_m": 0.9})
    seen = [f for f in a.doc.findings]
    assert len(seen) >= 2
    entries = a.submit({"op": "finding.add", "finding": {**seen[0].model_dump(), "feedback": {
        "verdict": "rejected", "reason": prefs.NOT_RELEVANT}}}, by="user")
    key = prefs.kind("door_widths", seen[0].title)[0]
    assert key in prefs.less(a.doc)
    assert all(f.feedback and f.feedback.verdict == "rejected" for f in a.doc.findings)  # the others like it went too
    assert len(entries) == 2 + len(seen)  # the op, its mute, the kind, and one entry per similar finding

    b = new(tmp_path, "t2")
    out = Investigation(b).run("door_widths", {"scan": "t2", "min_width_m": 0.9})
    assert out["findings"] == [] and out["kept_back_as_not_relevant_to_them"] == len(seen)
    (note,) = [n for n in profile.because(b.doc)["notes"] if n["kind"] == "kept_back"]
    assert note["count"] == len(seen) and note["text"].startswith(f"Kept back {len(seen)} “Doorway” checks")
    assert profile.measure(b.doc, b.log)["checks_kept_back"] == len(seen)

    a.undo(entries[0].seq)  # one undo brings them all back
    assert not prefs.less(a.doc) and not any(f.feedback for f in a.doc.findings)


def test_a_plain_rejection_mutes_one_finding_only(tmp_path):
    a = new(tmp_path)
    Investigation(a).run("door_widths", {"scan": "t1", "min_width_m": 0.9})
    f = a.doc.findings[0]
    a.submit({"op": "finding.add", "finding": {**f.model_dump(), "feedback": {"verdict": "rejected", "reason": "wrong"}}}, by="user")
    assert not prefs.less(a.doc) and sum(1 for x in a.doc.findings if x.feedback) == 1


def test_useful_checks_come_first_and_their_tool_leads_the_ranking(tmp_path):
    a = new(tmp_path)
    a.submit(BriefSet(by="user", scope=Scope(sids=["t1", "t2"]), persona="wheelchair_user"))
    inv = Investigation(a)
    for sid in ("t1", "t2"):
        inv.run("door_widths", {"scan": sid, "min_width_m": 0.9})
        inv.run("room_census", {"scan": sid})
    assert inv.rank(["t1", "t2"], ["a", "b"])["ranked_by"] == "door_widths"
    f = a.doc.findings[0]
    a.submit({"op": "finding.add", "finding": {**f.model_dump(), "feedback": {"verdict": "confirmed"}}}, by="user")
    assert prefs.favourite(a.doc) == "door_widths" and prefs.more(a.doc) == {prefs.kind("door_widths", f.title)[0]: 1}
    assert inv.rank(["t1", "t2"], ["a", "b"])["ranked_by"] == "door_widths"
    ranked = next(p for p in a.doc.panels if p.id == "agent:ranked")
    assert any(getattr(b, "text", "").startswith("Ranked by Door widths because you marked") for b in ranked.blocks)
    (first,) = [n for n in profile.because(a.doc)["notes"] if n["kind"] == "first"]
    assert f.id in first["findings"]


def test_the_person_document_lists_facts_and_measures_each_investigation(tmp_path):
    a = new(tmp_path)
    (q,) = composed(a, Fake("furniture_mover", ["door_widths", "room_census"]), "Moving a wide chair in")
    a.submit({"op": "question.answer", "id": q.id, "value": 0.7}, by="user")
    Investigation(a).run("door_widths", {"scan": "t1"})
    a.submit({"op": "tool.disable", "tool": "room_census", "reason": "not for me"}, by="user")
    b = new(tmp_path, "t2")
    composed(b, Fake("furniture_mover", ["door_widths"]))
    Investigation(b).run("door_widths", {"scan": "t2"})
    b.save()

    doc = profile.person(FileStore(tmp_path), "maya", here=b.doc.id)
    by_key = {f["key"]: f for f in doc["facts"]}
    assert by_key["access.door_width_m"]["shown"] == "0.7" and by_key["access.door_width_m"]["unit"] == "m"
    assert by_key["access.door_width_m"]["group"] == "about" and by_key["access.door_width_m"]["edit"]["type"] == "number"
    assert by_key["tool.off.room_census"]["group"] == "matters" and by_key["tool.off.room_census"]["shown"] == "Room census"
    assert by_key["tool.off.room_census"]["undo"] == {"op": "pref.set", "key": "tool.off.room_census", "value": None, "by": "user"}
    assert [m["workspace"] for m in doc["sessions"]] == [a.doc.id, b.doc.id] and doc["investigations"] == 2
    rows = {r["id"]: r["values"] for r in doc["adapted"]}
    assert rows["questions_asked"] == [1, 0] and rows["questions_not_asked"] == [0, 1] and rows["inputs_from_profile"] == [0, 1]
    assert not any(k.startswith("session.") for k in b.doc.prefs)  # the list of investigations is not a preference
    left = [n for n in profile.because(b.doc)["notes"] if n["kind"] == "left_out"]
    assert left and left[0]["text"] == "Left out Room census" and "you removed it on" in left[0]["why"]


def test_a_returning_person_is_named_to_the_composer_and_a_new_one_is_not(tmp_path):
    a = new(tmp_path)
    m = Fake("furniture_mover", ["door_widths"])
    (q,) = composed(a, m, "Moving a wide chair in")
    assert "What you already know about this person" not in m.seen[0]
    assert prefs.as_text(a.doc) == "- nothing yet"
    a.submit({"op": "question.answer", "id": q.id, "value": 0.7}, by="user")
    assert prefs.as_text(a.doc) == "- nothing yet"  # an answer given here is in the inputs, not in the prompt
    b = new(tmp_path, "t2")
    composed(b, m)
    assert "What you already know about this person" in m.seen[0] and "Doorway width you need: 0.7 m (you told me on" in m.seen[0]
    assert "you told me on" in prefs.as_text(b.doc)


def test_a_value_the_agent_repeats_is_still_the_persons(tmp_path):
    """The agent may pass the person's own number back as a tool input. It is marked as theirs, and a different
    number (a what-if) is not."""
    a = new(tmp_path)
    a.submit({"op": "pref.set", "key": "access.door_width_m", "value": 0.7}, by="user")
    inv = Investigation(a)
    same, other = inv.run("door_widths", {"scan": "t1", "min_width_m": 0.7}), inv.run("door_widths", {"scan": "t1", "min_width_m": 0.9})
    runs = {r.id: r for r in a.doc.runs}
    assert runs[same["run"]].inputs_from == {"min_width_m": "access.door_width_m"} and runs[other["run"]].inputs_from == {}


def test_an_answer_counts_as_reused_even_where_a_persona_has_a_default(tmp_path):
    a = new(tmp_path)
    (q,) = composed(a, Stating("wheelchair_user", ["door_widths"]), "I use a wheelchair, my chair is 70 cm wide")
    a.submit({"op": "question.answer", "id": q.id, "value": 0.7}, by="user")
    b = new(tmp_path, "t2")
    assert composed(b, Fake("wheelchair_user", ["door_widths"])) == []
    Investigation(b).run("door_widths", {"scan": "t2"})
    m = profile.measure(b.doc, b.log)
    assert (m["questions_asked"], m["questions_not_asked"], m["inputs_from_profile"]) == (0, 1, 1)
