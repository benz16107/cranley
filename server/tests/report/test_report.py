"""Site reports on the hand-made test cafe (threshold/roomplan/demo.py): a workspace runs each kind's tools, then the
report is built, drawn and printed. No sponsor data, no network; files store in a temporary folder."""
import pytest

from threshold.agent.investigator import Investigation, attach
from threshold.agent.workspace import BriefSet, Scope, Session
from threshold.report import KINDS, build, occupancy
from threshold.report.render import html_doc
from threshold.roomplan import convert
from threshold.roomplan.demo import cafe

SID = "u_0000cafe0001"


@pytest.fixture(scope="module")
def plan():
    return convert(cafe(), SID, "Test cafe", kind="storefront")


def visit(tmp_path, plan, kind):
    s = attach(Session.create("phone", root=tmp_path), lambda sid: plan)
    s.submit(BriefSet(scope=Scope(sids=[SID]), facts={"report": {"kind": kind, "business": "Test Cafe"}}), by="user")
    inv = Investigation(s)
    for tool, given in KINDS[kind]["tools"]:
        inv.run(tool, {"scan": SID, **given})
    return s


def test_occupancy_from_room_areas(plan):
    o = occupancy(plan)
    rows = {r["room"]: r for r in o["rows"]}
    assert rows["Dining Room"]["load"] == 38      # 52.5 m2 = 565 ft2 at 15 ft2 net
    assert rows["Kitchen"]["load"] == 2           # 204 ft2 at 200 gross
    assert rows["Bathroom"]["load"] == 0          # accessory
    assert o["total"] == 41 and o["exits_needed"] == 1
    assert o["exits"] == 2 and o["status"] == "pass"  # the street door and the rear door


def test_accessibility_report(tmp_path, plan):
    s = visit(tmp_path, plan, "accessibility")
    rep = build(s.doc, lambda sid: plan, [])
    fix = rep["fix_first"]
    assert [f["status"] for f in fix][:2] == ["fail", "fail"] and fix[-1]["status"] == "warn"
    # the restroom door is found by two tools and listed once, with both
    restroom = next(f for f in fix if f["anchor"] and f["anchor"].get("opening") == "o1")
    assert {"door_widths", "bathroom_clearance"} <= set(restroom["tools"])
    assert sum((f["anchor"] or {}).get("opening") == "o1" for f in fix) == 1
    page = html_doc(rep)
    # bathroom_clearance uses the toilet the phone scan measured, 1.1 m off the side wall: no grab bar wall
    assert page.count('class="n fail"') == sum(f["status"] == "fail" for f in fix) == 3 and "What we did not check" in page
    assert "Parking" in page                       # the kind's own limits
    assert "30 in" in page                         # the 0.76 m door, in inches on the plan


def test_fire_report_has_occupancy_and_preplan(tmp_path, plan):
    s = visit(tmp_path, plan, "fire")
    rep = build(s.doc, lambda sid: plan, [])
    assert rep["occupancy"][SID]["total"] == 41
    page = html_doc(rep)
    assert "How many people the space holds" in page and "§6.2.2 Doorways out" in page


def test_ceiling_photos_make_the_alarm_census(tmp_path, plan):
    s = visit(tmp_path, plan, "fire")
    caps = [{"id": "cap_1", "kind": "photo", "file": "cap_1.jpg", "scan": SID, "room": "r1", "values": {"check": "smoke_alarm"}},
            {"id": "cap_2", "kind": "photo", "file": "cap_2.jpg", "scan": SID, "room": "r0", "values": {"check": "smoke_alarm"}}]
    seen = {"cap_1": True, "cap_2": False}
    rep = build(s.doc, lambda sid: plan, caps, alarm=lambda cid: {"ceiling_visible": True, "smoke_alarm_visible": seen[cid],
                                                                 "what": "ceiling", "confidence": "medium"})
    by_room = {a["room"]: a["status"] for a in rep["alarms"]}
    assert by_room["r1"] == "pass" and by_room["r0"] == "warn"
    assert by_room["r2"] == "unknown"              # the storage room had no photo
    assert "r3" not in by_room                     # the restroom adds no occupants and is not asked for
    assert any(f["id"] == "alarm:cap_2" for f in rep["fix_first"])


def test_pdf_prints(tmp_path, plan):
    from threshold.report import pdf
    try:
        pdf.chrome()
    except pdf.Unavailable:
        pytest.skip("no Chrome on this machine")
    s = visit(tmp_path, plan, "accessibility")
    data = pdf.from_html(html_doc(build(s.doc, lambda sid: plan, [])))
    assert data[:5] == b"%PDF-" and len(data) > 10_000
