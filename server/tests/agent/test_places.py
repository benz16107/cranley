"""Runs on places without a scan, property fan-out, search, ranking, the turn budget. Hand-made data only."""
import json

import pytest
from langchain_core.messages import AIMessage

from threshold.agent import search
from threshold.agent.budget import Budget, BudgetSpent
from threshold.agent.investigator import Investigation, turn
from threshold.agent.workspace import BriefSet, Rejected, Scope, ToolEnable
from threshold.tools import Place, ToolContext, run_tool
from threshold.tools.places import Site

from .test_investigator import Scripted, call

SCANS = [{"sid": "t1", "name": "1BR, 1BA", "kind": "apartment_unit"},
         {"sid": "t2", "name": "Fitness center", "kind": "amenity"}]
RECORD = {"propertyApartment": {"models": [
    {"id": 11, "modelName": "The One", "numBeds": 1, "numBaths": 1, "attachments": []},
    {"id": 22, "modelName": "The Two", "numBeds": 2, "numBaths": 2, "attachments": [{"videoKey": "t9"}]}]}}


def sites(place: Place) -> Site:
    if place.property_id == 7 or place.address == "1 Main St":
        return Site(place, 29.7, -95.3, "1 Main St", "Houston", 7, ["t1", "t2"], "test", SCANS, RECORD)
    if place.geo:
        return Site(place, place.geo[1], place.geo[0], located_by="point given")
    raise LookupError(f"no place {place.key()}")


@pytest.fixture
def ws(session):
    session.sites = sites
    session.submit(BriefSet(by="user", persona="apartment_manager", text="Check my community", summary="Manager",
                            scope=Scope(places=[Place(property_id=7)])))
    for t in ("door_widths", "room_census", "property_coverage"):
        session.submit(ToolEnable(tool=t))
    return session


def test_place_needs_one_target_and_keys_are_stable():
    with pytest.raises(ValueError):
        Place()
    with pytest.raises(ValueError):
        Place(geo=(200, 10))
    assert [Place(scan="s").key(), Place(property_id=7).key(), Place(address="1 Main St.").key(),
            Place(geo=(-95.3, 29.7)).key()] == ["s", "p7", "a1-main-st", "g-95.30000,29.70000"]


def test_coverage_runs_on_a_property_without_a_scan():
    r = run_tool("property_coverage", {"place": {"property_id": 7}}, ToolContext(sites=sites))
    assert r.scope.property_id == 7 and r.scope.sids == ["t1", "t2"]
    status = {c.id: c.status for c in r.checks}
    assert status["plan.11"] == "pass"            # named 1BR, 1BA
    assert status["plan.22"] == "unknown"         # attached to a scan this place does not have
    assert status["area.fitness"] == "pass" and status["area.pool"] == "unknown"
    assert r.verdict.status == "warn"
    assert run_tool("property_coverage", {"place": {"geo": [-95.0, 29.0]}}, ToolContext(sites=sites)).verdict.status == "unknown"


def test_run_on_place_records_it_and_keys_panels_by_place(ws):
    out = Investigation(ws).run("property_coverage", {})  # the workspace's one place fills it
    assert out["place"] == "p7" and out["verdict"] == "warn"
    run = ws.doc.runs[-1]
    assert run.place.property_id == 7 and run.sid is None
    assert any(p.id == "panel:property_coverage:p7" for p in ws.doc.panels)
    assert run.steps[0].startswith("Found 2 scans")  # streamed progress landed on the record
    assert "not in this workspace" in Investigation(ws).run("property_coverage", {"place": {"property_id": 8}})["error"]


def test_geo_anchors_and_map_pins_validate(ws):
    pins = {"op": "overlay.upsert", "overlay": {"id": "o", "overlay": {"kind": "pins", "pins": [
        {"id": "p", "anchor": {"geo": [-95.3, 29.7]}, "label": "Gate", "status": "warn"}]}}}
    ws.submit(pins)
    assert ws.doc.overlays[-1].sid is None and ws.doc.overlays[-1].overlay.pins[0].anchor.geo == (-95.3, 29.7)
    ws.submit({"op": "camera.focus", "anchor": {"geo": [-95.3, 29.7]}})
    with pytest.raises(Rejected):
        ws.submit({"op": "overlay.upsert", "overlay": {"id": "l", "overlay": {
            "kind": "lens", "values": {}, "ramp": "sequential", "legend": {"title": "x", "unit": "", "min": 0, "max": 1}}}})


def test_consider_adds_places_and_scans(ws):
    inv = Investigation(ws)
    out = inv.consider(scans=["t1", "nope"], addresses=["1 Main St", "Nowhere"], points=[[-95.0, 29.0]])
    assert "t1" in ws.doc.brief.scope.sids and "a1-main-st" in out["places"] and "g-95.00000,29.00000" in out["places"]
    assert len(out["problems"]) == 2


def test_fan_out_is_bounded_and_aggregates(ws):
    inv = Investigation(ws, budget=Budget(max_fan_out=1, parallel=2))
    out = inv.fan_out("door_widths", 7)
    agg = next(r for r in ws.doc.runs if r.id == out["run"])
    assert agg.place.property_id == 7 and agg.result.scope.sids == ["t1"]
    metrics = {m.id: m.value for m in agg.result.metrics}
    assert metrics["scans_checked"] == 1 and metrics["scans_not_checked"] == 1 and metrics["verdicts.fail"] == 1
    assert agg.result.checks[0].findings and out["worst_scans"][0]["scan"] == "t1"
    assert "1 more scans were not checked" in agg.summary
    out = Investigation(ws).fan_out("door_widths", 7, kinds=["amenity"], max_scans=5)
    assert out["verdict"] == "fail" and "t2" in ws.doc.brief.scope.sids


def test_tool_run_budget_refuses_politely(ws):
    ws.submit(BriefSet(scope=Scope(sids=["t1"], places=ws.doc.brief.scope.places)))
    inv = Investigation(ws, budget=Budget(tool_runs=1))
    assert inv.run("room_census", {"scan": "t1"})["verdict"]
    assert "budget" in inv.run("room_census", {"scan": "t1"})["error"]
    assert inv.budget.report()["used"] == {"model_calls": 0, "tool_runs": 1, "refused_tool_runs": 1}


def test_model_call_cap_stops_the_turn(ws):
    b = Budget(model_calls=1)
    b.count_call()
    with pytest.raises(BudgetSpent):
        b.count_call()
    model = Scripted(messages=iter([call("write_todos", {"todos": [{"content": "a", "status": "in_progress"}]}, 1),
                                    call("note", {"text": "x"}, 2), AIMessage(content="never reached")]))
    out = turn(ws, agent_model=model, budget=Budget(model_calls=1))
    assert out["status"] == "done" and out["budget"]["stopped_by"] == "model calls"
    assert out["budget"]["used"]["model_calls"] == 2  # the second call trips the cap
    assert json.loads((ws.root / f"{ws.base.id}.casefile.json").read_text())["budget"]["stopped_by"] == "model calls"


def test_rank_orders_candidates_and_drops_measured_reasons(ws):
    ws.submit(BriefSet(scope=Scope(sids=["t1", "t2"], places=ws.doc.brief.scope.places)))
    inv = Investigation(ws)
    runs = {s: inv.run("door_widths", {"scan": s})["run"] for s in ("t1", "t2")}
    out = inv.rank(["t2", "t1"], ["Wider doors throughout.", "Bedroom door is 0.7 m."])
    panel = next(p for p in ws.doc.panels if p.id == "agent:ranked")
    assert panel.blocks[0].rows == [runs["t2"], runs["t1"]] and out["ranked_by"] == "door_widths"
    assert [b.type for b in panel.blocks] == ["RankedTable", "Note"] and out["reasons_dropped_for_measurements"] == ["t1"]
    assert "error" in inv.rank(["zzz"], ["x"])


def test_find_properties_filters_digest_rows():
    rows = [{"id": 1, "name": "Tall", "type": "Multifamily", "subtype": "MultiFamily_Apartments", "address": "1 A St",
             "city": "Houston", "facts": {"units": 200, "passenger_elevators": 2}, "rent_min": 1200, "rent_max": 2000,
             "tenants": [], "scans": {"apartment_unit": 3}, "flags": []},
            {"id": 2, "name": "Walkup", "type": "Multifamily", "subtype": None, "address": "2 B St", "city": "Houston",
             "facts": {"units": 12, "is_walkup": True}, "rent_min": None, "rent_max": None, "tenants": ["Acme Co"],
             "scans": {"apartment_unit": 1}, "flags": ["drone"]},
            {"id": 3, "name": "Office", "type": "Office", "subtype": None, "address": "3 C St", "city": "Los Angeles",
             "facts": {}, "rent_min": None, "rent_max": None, "tenants": [], "scans": {}, "flags": []}]
    ids = lambda **kw: [p["property_id"] for p in search.find_properties(rows=rows, **kw)["properties"]]  # noqa: E731
    assert ids(city="houston", property_type="multifamily") == [1, 2]
    assert ids(elevator=True) == [1] and ids(elevator=False) == [2]
    assert ids(max_rent=1500) == [1] and ids(tenant="acme") == [2] and ids(drone=True) == [2]
    assert ids(city="Los Angeles") == []  # no scans, never offered


def test_measure_search_passes_only_declared_parameters(monkeypatch):
    seen = {}

    class Route:
        path, methods = search.MEASURES, {"GET"}

        @staticmethod
        def endpoint(min_door_width_m: float | None = None, city: str | None = None):
            seen.update(min_door_width_m=min_door_width_m, city=city)
            return {"scans": [{"sid": f"s{i}"} for i in range(40)]}

    out = search.find_by_measure(Route, {"min_door_width_m": 0.8, "teleport": True})
    assert seen == {"min_door_width_m": 0.8, "city": None} and len(out["scans"]) == search.MAX_ROWS
    assert "min_door_width_m (default None)" in search.measures_params(Route)


def test_custom_panel_binds_to_workspace_data_only(ws):
    ws.submit(BriefSet(scope=Scope(sids=["t1"], places=ws.doc.brief.scope.places)))
    inv = Investigation(ws)
    run = inv.run("door_widths", {"scan": "t1"})["run"]
    real = ws.doc.findings[0].id
    out = inv.compose_panel("Doors that matter", [
        {"type": "VerdictHeader", "run": run},
        {"type": "MetricRow", "run": run, "metrics": ["narrowest", "made_up"]},
        {"type": "EvidenceStrip", "findings": [real, "door_widths:t1:nope"]},
        {"type": "FloorPlanMini", "sid": "t1", "overlays": ["door_widths:t1:0", "ghost"]},
        {"type": "RankedTable", "title": "x", "columns": [{"metric": "made_up", "label": "x", "better": "higher"}], "rows": [run]},
        {"type": "MiniChart", "run": "run_missing", "title": "x", "metrics": ["a"]},
        {"type": "Note", "text": "The bedroom door is the one to measure on site."},
        {"type": "Note", "text": "It is 0.7 m wide."},
        {"type": "Teleporter"}])
    panel = next(p for p in ws.doc.panels if p.id == out["panel"])
    assert out["panel"] == "custom:doors-that-matter"
    assert [b.type for b in panel.blocks] == ["VerdictHeader", "MetricRow", "EvidenceStrip", "FloorPlanMini", "Note"]
    assert panel.blocks[1].metrics == ["narrowest"] and panel.blocks[2].findings == [real]
    assert panel.blocks[3].overlays == ["door_widths:t1:0"] and len(out["dropped"]) == 7
    assert "error" in inv.compose_panel("Empty", [{"type": "Note", "text": "Door is 2 ft."}])
