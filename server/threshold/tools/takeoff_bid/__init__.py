"""Takeoff bid: trade quantities from one engine (geometry.takeoff, plus floor finishes and fixtures seen in the
panoramas), priced with rates that are the bidder's own editable assumptions. Three price books: a cleaning bid,
an apartment unit turn, and a fit-out refresh."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from ... import geometry
from ...vision import reader
from .. import (
    Assumption,
    Finding,
    Legend,
    LensOverlay,
    Metric,
    Pin,
    PinsOverlay,
    RoomAnchor,
    ScanScope,
    Source,
    ToolResult,
    Verdict,
    field,
    tool,
)
from ..room_labeller import ensure_labels, facts, store
from ..types import Media

FT2 = facts.M2_TO_FT2
FT = 3.28084
GEOM = Source(layer="matterport", method="geometry", confidence="high", note="geometry.takeoff on the wall graph")
FINISH = Source(layer="model", method="vision", confidence="medium", note="Floor finish from the straight-down panorama face")
FIXTURE = Source(layer="model", method="vision", confidence="medium", note="Fixtures counted in the room's central panorama")
PRICE = Source(layer="model", method="simulation", confidence="low", note="Your rates times measured quantities; rates are assumptions")

HARD = {"hardwood or wood-look", "tile or stone", "polished or sealed concrete", "vinyl or linoleum", "rubber or gym flooring"}
WET = ("restroom", "Bathroom")
SKIP_CLEAN = ("server or electrical room", "storage", "Utility Room", "warehouse floor", "loading area", "Void")
FIXTURES = ["toilet", "urinal", "sink", "bathtub", "shower"]


class Inputs(BaseModel):
    scan: str = field(source="selection.scan", description="Scan id")
    trade: Literal["cleaning", "unit_turn", "fit_out"] = field(
        ask="Which bid: a cleaning bid, an apartment unit turn, or a fit-out estimate?", pref="bid.trade")
    # cleaning
    carpet_ft2_per_hour: float = field(3500, description="Carpet vacuuming rate", pref="bid.clean.carpet_rate", unit="ft²/h", gt=0)
    hard_ft2_per_hour: float = field(2500, description="Hard floor mopping rate", pref="bid.clean.hard_rate", unit="ft²/h", gt=0)
    fixture_minutes: float = field(4, description="Minutes per restroom fixture", pref="bid.clean.fixture_min", unit="min", ge=0)
    glass_ft2_per_hour: float = field(600, description="Glass cleaning rate", pref="bid.clean.glass_rate", unit="ft²/h", gt=0)
    glass_visits_per_month: float = field(1, description="Window cleaning visits per month", pref="bid.clean.glass_visits", ge=0)
    visits_per_week: float = field(3, description="Cleaning visits per week", pref="bid.clean.visits", ge=0, le=7)
    wage: float = field(22, description="Loaded labour cost per hour", pref="bid.wage", unit="$/h", ge=0)
    markup: float = field(0.35, description="Overhead and margin on labour", pref="bid.markup", ge=0, le=3)
    # unit turn
    paint_per_ft2: float = field(0.95, description="Paint, two coats, labour and material, per wall ft²", pref="bid.turn.paint", unit="$/ft²", ge=0)
    paint_ft2_per_gallon: float = field(350, description="Coverage per gallon per coat", pref="bid.turn.coverage", unit="ft²/gal", gt=0)
    carpet_per_yd2: float = field(32, description="Carpet replaced, installed", pref="bid.turn.carpet", unit="$/yd²", ge=0)
    replace_carpet: bool = field(False, description="Replace carpet (heavy turn) instead of cleaning it", pref="bid.turn.replace_carpet")
    carpet_clean_per_ft2: float = field(0.30, description="Carpet cleaning", pref="bid.turn.carpet_clean", unit="$/ft²", ge=0)
    hard_floor_per_ft2: float = field(0.60, description="Hard floor clean and touch-up", pref="bid.turn.hard", unit="$/ft²", ge=0)
    per_door: float = field(30, description="Door and hardware touch-up, each", pref="bid.turn.door", unit="$", ge=0)
    per_window: float = field(35, description="Blind replaced, each window", pref="bid.turn.blind", unit="$", ge=0)
    per_fixture: float = field(25, description="Fixture service, each", pref="bid.turn.fixture", unit="$", ge=0)
    # fit-out
    flooring_per_ft2: float = field(4.5, description="New carpet tile or LVT, installed", pref="bid.fit.floor", unit="$/ft²", ge=0)
    ceiling_per_ft2: float = field(3.0, description="Ceiling tile replaced", pref="bid.fit.ceiling", unit="$/ft²", ge=0)
    partition_per_lf: float = field(95, description="New partition, framed and finished", pref="bid.fit.partition", unit="$/lf", ge=0)
    new_door: float = field(1400, description="New door, frame and hardware", pref="bid.fit.door", unit="$", ge=0)
    add_offices: int = field(0, description="Private offices to build in the open area", pref="bid.fit.add_offices", ge=0, le=50)
    contingency: float = field(0.15, description="Contingency on the fit-out", pref="bid.fit.contingency", ge=0, le=1)
    label_with_vision: bool = field(True, description="Label rooms and read floor finishes from the panoramas first")


def finishes(sid: str, plan: dict, rooms: list[str]) -> dict[str, dict]:
    """Floor finish per room: from the overlay when read before, else read now and saved there."""
    doc = store.load(sid)
    todo = [r for r in rooms if "shares" not in doc["finishes"].get(r, {})]
    if todo:
        doc["finishes"].update(reader.floor_finishes(plan, todo, views=4))
        store.save(doc)
    return doc["finishes"]


def fixtures(plan: dict, rooms: list[dict]) -> dict[str, dict]:
    """Fixture counts per wet room from its central panorama: {room id: {counts, evidence}}."""
    panos = {}
    for r in rooms:
        ps = reader.room_panos(plan, r)
        if ps:
            panos[ps[0]["id"]] = r["id"]
    if not panos:
        return {}
    out = {rid: {"counts": {}, "evidence": None} for rid in panos.values()}
    for d in reader.find_objects(plan, labels=FIXTURES, panos=list(panos)):
        rid = panos.get(d["pano_anchor"]["pano"])
        if rid:
            out[rid]["counts"][d["label"]] = out[rid]["counts"].get(d["label"], 0) + 1
            out[rid]["evidence"] = out[rid]["evidence"] or d["finding"]["media"][0]["ref"]
    return out


def _money(x: float) -> str:
    return f"${x:,.0f}"


@tool(id="takeoff_bid", title="Takeoff bid", icon="calculator",
      summary="Quantities for a trade from the scan (floor by finish, paintable wall, glass, doors, fixtures), priced "
              "with your own rates: a cleaning bid, an apartment unit turn, or a fit-out estimate.",
      model_description="Measure trade quantities in one scan with geometry.takeoff plus floor finishes and restroom "
                        "fixtures seen in the panoramas, then price them with editable rates. trade = cleaning (hours per "
                        "visit and a monthly price), unit_turn (paint gallons, flooring, doors, blinds, fixtures) or fit_out "
                        "(flooring, ceiling, paint, optional new offices). Quantities are measurements with sources; every "
                        "price is an assumption.",
      personas=["apartment_manager", "office_tenant"],
      requires=[{"layer": "matterport.walls", "need": "optional", "fallback": "floor area only"}, {"layer": "matterport.panos"}],
      blocks=["VerdictHeader", "MetricRow", "MiniChart", "FloorPlanMini", "AssumptionChips", "Controls", "EvidenceStrip", "StepLog"],
      overlays=["lens", "pins"], annotations={"cost": "slow"},
      examples=["What would it cost to clean this office three nights a week?", "Scope the turn for this unit",
                "Rough fit-out price for this suite"])
def run(ctx, i: Inputs) -> ToolResult:
    sid = i.scan
    plan = ensure_labels(ctx, sid, i.label_with_vision)
    q = facts.quality(plan)
    t = geometry.takeoff(plan)
    if not t.get("available"):
        return ToolResult(scope=ScanScope(sid=sid), verdict=Verdict(status="unknown", text=t.get("reason", "No rooms to measure.")))
    rows = {x["room"]: x for x in t["rooms"] if not x["void"] and not x["unwalled"] and x["floor_area"]}
    labels = {r["id"]: r.get("label") or "Unlabelled room" for r in plan["rooms"]}
    ctx.step(f"Measured {len(rows)} rooms: {t['total']['floor_area'] * FT2:,.0f} ft² of floor")
    fin = finishes(sid, plan, list(rows)) if i.label_with_vision else store.load(sid)["finishes"]
    ctx.step(f"Read floor finishes for {sum(1 for r in rows if r in fin)} rooms")
    walls_ok = bool(q["walls"])
    windows_ok = any(o["type"] == "window" for o in plan.get("openings") or [])
    findings, metrics, pins, lens, assumptions = [], [], [], {}, []
    cannot: list[str] = [] if walls_ok else ["wall area, glass, doors and windows (no wall graph)"]

    def shares(rid: str) -> dict[str, float]:
        e = fin.get(rid) or {}
        return e.get("shares") or ({e["finish"]: 1.0} if e.get("finish") else {"not read": 1.0})

    by_finish: dict[str, float] = {}
    for rid, x in rows.items():
        for f, sh in shares(rid).items():
            by_finish[f] = by_finish.get(f, 0) + x["floor_area"] * FT2 * sh
    for f, a in sorted(by_finish.items(), key=lambda kv: -kv[1]):
        metrics.append(Metric(id=f"floor.{f.replace(' ', '_')}", label=f"Floor: {f}", value=round(a), unit="ft²",
                              source=FINISH if f != "not read" else GEOM))
    wet = [plan_room for plan_room in plan["rooms"] if plan_room["id"] in rows and labels[plan_room["id"]] in WET]
    fx = fixtures(plan, wet) if wet and i.label_with_vision else {}
    if wet:
        ctx.step(f"Counted fixtures in {len(fx)} of {len(wet)} restrooms or bathrooms")
    n_fix = sum(sum(v["counts"].values()) for v in fx.values())
    for rid, v in fx.items():
        c = ", ".join(f"{n} {k}{'s' if n > 1 else ''}" for k, n in v["counts"].items()) or "none seen"
        pins.append(Pin(id=rid, anchor=RoomAnchor(sid=sid, room=rid), label=c, status="unknown"))
        findings.append(Finding(id=f"takeoff_bid:{sid}:fixtures:{rid}", title=f"Fixtures, {labels[rid]}", status="unknown",
                                detail=f"{c}, counted in the room's central panorama; fixtures out of its view are missed.",
                                anchor=RoomAnchor(sid=sid, room=rid), source=FIXTURE,
                                media=[Media(kind="pano", ref=v["evidence"])] if v["evidence"] else []))

    def A(id, label, value, unit=None, editable=True):
        assumptions.append(Assumption(id=id, label=label, value=value, unit=unit, editable=editable))

    if i.trade == "cleaning":
        mins: dict[str, float] = {}
        carpet = hard = unknown = 0.0
        for rid, x in rows.items():
            if labels[rid] in SKIP_CLEAN:
                continue
            m = sum((fx.get(rid) or {"counts": {}})["counts"].values()) * i.fixture_minutes
            for f, sh in shares(rid).items():
                if f in ("outdoor paving or deck", "artificial turf or grass"):
                    continue
                a = x["floor_area"] * FT2 * sh
                carpet += a if f == "carpet" else 0
                hard += a if f in HARD else 0
                unknown += a if f not in HARD and f != "carpet" else 0
                m += a / (i.carpet_ft2_per_hour if f == "carpet" else i.hard_ft2_per_hour) * 60
            if m:
                mins[rid] = m
        glass = t["total"]["glazed_area"] * FT2 if windows_ok else 0.0
        hours = sum(mins.values()) / 60
        glass_h = glass / i.glass_ft2_per_hour * i.glass_visits_per_month
        month_h = hours * i.visits_per_week * 52 / 12 + glass_h
        price = month_h * i.wage * (1 + i.markup)
        lens = {k: round(v, 1) for k, v in mins.items()}
        metrics = [Metric(id="cleanable", label="Cleanable floor", value=round(carpet + hard + unknown), unit="ft²", source=GEOM),
                   Metric(id="hours_per_visit", label="Labour hours per visit", value=round(hours, 2), unit="h", source=PRICE),
                   Metric(id="monthly_price", label="Monthly price", value=round(price), unit="$", source=PRICE),
                   Metric(id="fixtures", label="Restroom fixtures", value=n_fix, unit="", source=FIXTURE),
                   Metric(id="glass", label="Exterior glass (one side)", value=round(glass) if windows_ok else None, unit="ft²", source=GEOM),
                   *metrics]
        for id, lab, v, u in (("bid.clean.carpet_rate", "Carpet rate", i.carpet_ft2_per_hour, "ft²/h"),
                              ("bid.clean.hard_rate", "Hard floor rate", i.hard_ft2_per_hour, "ft²/h"),
                              ("bid.clean.fixture_min", "Minutes per fixture", i.fixture_minutes, "min"),
                              ("bid.clean.glass_rate", "Glass rate", i.glass_ft2_per_hour, "ft²/h"),
                              ("bid.clean.visits", "Visits per week", i.visits_per_week, None),
                              ("bid.wage", "Labour cost", i.wage, "$/h"), ("bid.markup", "Overhead and margin", i.markup, None)):
            A(id, lab, v, u)
        skipped = [labels[r] for r in rows if labels[r] in SKIP_CLEAN]
        text = (f"About {hours:.1f} labour hours per visit and {_money(price)} a month at {i.visits_per_week:g} visits a week, "
                f"for {carpet + hard + unknown:,.0f} ft² ({carpet:,.0f} carpet, {hard:,.0f} hard floor"
                + (f", {unknown:,.0f} finish not read" if unknown else "") + f") and {n_fix} restroom fixtures.")
        if skipped:
            text += f" Left out: {len(skipped)} storage, server or warehouse rooms."
        legend = Legend(title="Cleaning minutes per visit", unit="min", min=0, max=max(lens.values(), default=0))
        cannot.append("interior glass and partitions")
        if walls_ok and not windows_ok:
            cannot.append("exterior windows (the wall graph maps none)")
        if not wet:
            cannot.append("restrooms: none inside the scanned space, so shared core restrooms are not priced")
    elif i.trade == "unit_turn":
        if not walls_ok:
            return ToolResult(scope=ScanScope(sid=sid), verdict=Verdict(status="unknown", text=(
                "No wall graph in this scan, so paintable wall area, doors and windows cannot be measured; a turn scope "
                f"needs them. Floor area alone is {t['total']['floor_area'] * FT2:,.0f} ft².")), metrics=metrics)
        wall = sum((x["wall_area_net"] or 0) for x in rows.values()) * FT2
        gallons = wall * 2 / i.paint_ft2_per_gallon
        carpet = by_finish.get("carpet", 0.0)
        hard = sum(a for f, a in by_finish.items() if f in HARD)
        doors, windows = t["total"]["doors"], t["total"]["windows"]
        cost = {"Paint": wall * i.paint_per_ft2,
                "Carpet": carpet / 9 * i.carpet_per_yd2 if i.replace_carpet else carpet * i.carpet_clean_per_ft2,
                "Hard floors": hard * i.hard_floor_per_ft2, "Doors": doors * i.per_door, "Blinds": windows * i.per_window,
                "Fixtures": n_fix * i.per_fixture}
        total = sum(cost.values())
        lens = {rid: round((x["wall_area_net"] or 0) * FT2) for rid, x in rows.items() if x["wall_area_net"]}
        metrics = [Metric(id="turn_cost", label="Turn cost", value=round(total), unit="$", source=PRICE),
                   Metric(id="paint_wall", label="Paintable wall, net of openings", value=round(wall), unit="ft²", source=GEOM),
                   Metric(id="paint_gallons", label="Paint, two coats", value=round(gallons, 1), unit="gal", source=PRICE),
                   Metric(id="doors", label="Doors and openings", value=doors, unit="", source=GEOM),
                   Metric(id="windows", label="Windows (blinds)", value=windows, unit="", source=GEOM),
                   Metric(id="fixtures", label="Bathroom fixtures seen", value=n_fix, unit="", source=FIXTURE),
                   *metrics, *[Metric(id=f"cost.{k.replace(' ', '_')}", label=k, value=round(v), unit="$", source=PRICE)
                               for k, v in cost.items()]]
        for id, lab, v, u in (("bid.turn.paint", "Paint", i.paint_per_ft2, "$/ft²"), ("bid.turn.coverage", "Coverage", i.paint_ft2_per_gallon, "ft²/gal"),
                              ("bid.turn.replace_carpet", "Replace carpet", i.replace_carpet, None),
                              ("bid.turn.carpet", "Carpet installed", i.carpet_per_yd2, "$/yd²"),
                              ("bid.turn.carpet_clean", "Carpet cleaning", i.carpet_clean_per_ft2, "$/ft²"),
                              ("bid.turn.hard", "Hard floor", i.hard_floor_per_ft2, "$/ft²"), ("bid.turn.door", "Per door", i.per_door, "$"),
                              ("bid.turn.blind", "Per blind", i.per_window, "$"), ("bid.turn.fixture", "Per fixture", i.per_fixture, "$")):
            A(id, lab, v, u)
        text = (f"Turn scope about {_money(total)}: {wall:,.0f} ft² of wall ({gallons:.0f} gallons for two coats), "
                f"{carpet:,.0f} ft² carpet to {'replace' if i.replace_carpet else 'clean'}, {hard:,.0f} ft² hard floor, "
                f"{doors} doors, {windows} blinds, {n_fix} fixtures.")
        legend = Legend(title="Paintable wall per room", unit="ft²", min=0, max=max(lens.values(), default=0))
        cannot.append("condition: the scan is the unit as marketed, so damage, appliance and cabinet work are not seen")
        if not windows_ok:
            cannot.append("windows: the wall graph maps none, so blinds are not counted and paint is not net of windows")
    else:
        floor = t["total"]["floor_area"] * FT2
        wall = t["total"]["wall_area_net"] * FT2 if walls_ok else 0.0
        part_lf = i.add_offices * 3 * 3.5 * FT  # three new walls of a 3.5 m office against an existing wall
        cost = {"Flooring": floor * i.flooring_per_ft2, "Ceiling tiles": floor * i.ceiling_per_ft2,
                "Paint": wall * i.paint_per_ft2, "New partitions": part_lf * i.partition_per_lf, "New doors": i.add_offices * i.new_door}
        sub = sum(cost.values())
        total = sub * (1 + i.contingency)
        lens = {rid: round(x["floor_area"] * FT2 * (i.flooring_per_ft2 + i.ceiling_per_ft2) + (x["wall_area_net"] or 0) * FT2 * i.paint_per_ft2)
                for rid, x in rows.items()}
        metrics = [Metric(id="fit_out_cost", label="Fit-out estimate", value=round(total), unit="$", source=PRICE),
                   Metric(id="per_ft2", label="Per ft² of floor", value=round(total / floor, 2) if floor else None, unit="$/ft²", source=PRICE),
                   Metric(id="floor_area", label="Floor area", value=round(floor), unit="ft²", source=GEOM),
                   Metric(id="wall_area", label="Wall area net of openings", value=round(wall) if walls_ok else None, unit="ft²", source=GEOM),
                   *metrics, *[Metric(id=f"cost.{k.replace(' ', '_')}", label=k, value=round(v), unit="$", source=PRICE)
                               for k, v in cost.items() if v]]
        for id, lab, v, u in (("bid.fit.floor", "Flooring", i.flooring_per_ft2, "$/ft²"), ("bid.fit.ceiling", "Ceiling tiles", i.ceiling_per_ft2, "$/ft²"),
                              ("bid.turn.paint", "Paint", i.paint_per_ft2, "$/ft²"), ("bid.fit.partition", "Partition", i.partition_per_lf, "$/lf"),
                              ("bid.fit.door", "New door", i.new_door, "$"), ("bid.fit.add_offices", "Offices to add", i.add_offices, None),
                              ("bid.fit.contingency", "Contingency", i.contingency, None)):
            A(id, lab, v, u)
        text = (f"Fit-out refresh about {_money(total)} ({_money(total / floor) if floor else '?'}/ft²): new flooring and "
                f"ceiling tiles over {floor:,.0f} ft², paint on {wall:,.0f} ft² of wall"
                + (f", {i.add_offices} new offices ({part_lf:,.0f} lf of partition)" if i.add_offices else "") + ".")
        legend = Legend(title="Refresh cost per room", unit="$", min=0, max=max(lens.values(), default=0))
        cannot.append("above-ceiling space and electrical, mechanical and plumbing capacity, which a scan cannot see")
    text += " Quantities are measured; every price is your assumption. Not measured: " + "; ".join(cannot) + "."
    overlays = []
    if lens:
        overlays.append(LensOverlay(values=lens, ramp="sequential", legend=legend))
    if pins:
        overlays.append(PinsOverlay(pins=pins))
    for f, a in by_finish.items():
        ev = next((fin[r]["evidence"] for r in rows if (fin.get(r) or {}).get("finish") == f), None)
        n_rooms = sum(1 for r in rows if f in shares(r))
        if ev:
            findings.append(Finding(id=f"takeoff_bid:{sid}:finish:{f.replace(' ', '_')}", title=f"Floor finish: {f}",
                                    status="unknown", detail=f"{a:,.0f} ft² across {n_rooms} room{'s' if n_rooms != 1 else ''}.",
                                    anchor=None, source=FINISH, media=[Media(kind="pano", ref=f"{ev['sid']}/{ev['pano']}/{ev['face']}")]))
    return ToolResult(scope=ScanScope(sid=sid), verdict=Verdict(status="pass" if walls_ok else "warn", text=text),
                      metrics=metrics, findings=findings, overlays=overlays, assumptions=assumptions)
