"""Office fit: does a team's program fit this suite as built? Rooms come from the label overlay (room_labeller),
areas from the scan, the comparison from the CoStar record (listed space, last tenant, asking rent)."""
from __future__ import annotations

import math
import re

from pydantic import BaseModel

from ...geometry._plan import indoor_rooms
from ...sources import costar
from .. import (
    Assumption,
    Check,
    Finding,
    Legend,
    LensOverlay,
    Metric,
    Pin,
    PinsOverlay,
    RoomAnchor,
    RuleOverlay,
    ScanScope,
    Source,
    ToolResult,
    Verdict,
    field,
    tool,
)
from ..room_labeller import ensure_labels, facts
from .._access import cannot, elevations
from ..types import SelectRooms

M2 = facts.M2_TO_FT2
AREA = Source(layer="matterport", method="geometry", confidence="high", note="Room floor areas from the scan")
LABELS = Source(layer="model", method="vision", confidence="medium", note="Room types from the room labeller")
RECORD = Source(layer="costar", method="lookup", confidence="high", note="CoStar record")
CALC = Source(layer="matterport", method="simulation", confidence="medium",
              note="Capacity from measured areas and your space standards")
TYPICAL_LOAD = (1.08, 1.22)  # multi-tenant office: rentable over usable, BOMA load factors seen in practice


class Inputs(BaseModel):
    scan: str = field(source="selection.scan", description="Scan id")
    headcount: int = field(ask="How many people need a seat?", pref="office.headcount", ge=1, le=2000)
    private_offices: int = field(0, ask="How many of them need a private office?", pref="office.private_offices", ge=0)
    meeting_rooms: int = field(1, ask="How many meeting rooms do you need?", pref="office.meeting_rooms", ge=0)
    meeting_seats: int = field(6, ask="How many seats should the largest meeting room have?", pref="office.meeting_seats", ge=2)
    kitchen: bool = field(True, description="Needs a kitchen or break room", pref="office.kitchen")
    desk_m2: float = field(6.5, description="Open-plan area per workstation, aisles included", pref="office.desk_m2",
                           unit="m2", ge=3.5, le=15)
    seat_m2: float = field(2.3, description="Meeting room area per seat", pref="office.meeting_seat_m2", unit="m2", ge=1.4, le=5)
    office_min_m2: float = field(7.5, description="Smallest room that works as a private office",
                                 pref="office.private_office_min_m2", unit="m2", ge=4, le=20)
    label_with_vision: bool = field(True, description="Label unlabelled rooms from the panoramas first (slow once)")


def _ft2(m2: float) -> str:
    return f"{m2 * M2:,.0f} ft²"


def fit(rooms: list[dict], p: Inputs) -> dict:
    """Allocate rooms to the program. rooms: [{id, label, area, windows}]. Pure; no plan, no record."""
    by = lambda lab: sorted((r for r in rooms if r["label"] == lab and r.get("area")), key=lambda r: -r["area"])
    offices, meetings, opens = by("private office"), by("conference room"), by("open office")
    seats = {r["id"]: math.floor(r["area"] / p.seat_m2) for r in meetings}
    meetings.sort(key=lambda r: -seats[r["id"]])
    roles: dict[str, dict] = {}
    changes: list[dict] = []

    # Meeting rooms first: the largest conference rooms, as many as asked.
    use_meet = meetings[:p.meeting_rooms]
    spare_meet = meetings[p.meeting_rooms:]
    for i, r in enumerate(use_meet):
        roles[r["id"]] = {"role": "meeting", "seats": seats[r["id"]], "label": f"Meeting, {seats[r['id']]} seats"}
    # Private offices: the smallest rooms that meet the minimum, so the large ones can be shared.
    tiny = [r for r in offices if r["area"] < p.office_min_m2]
    fits = sorted((r for r in offices if r["area"] >= p.office_min_m2), key=lambda r: r["area"])
    use_off = fits[:p.private_offices]
    spare_off = fits[p.private_offices:] + tiny
    for i, r in enumerate(use_off):
        roles[r["id"]] = {"role": "office", "seats": 1, "label": f"Private office {i + 1}"}
    short_off = p.private_offices - len(use_off)
    if short_off > 0:  # rooms that could become offices without building walls
        cands = [r for r in spare_meet if p.office_min_m2 <= r["area"] <= 25] + \
                [r for r in by("storage") if r["area"] >= p.office_min_m2 and (r.get("windows") or 0) > 0]
        for r in cands[:short_off]:
            roles[r["id"]] = {"role": "office", "seats": 1, "label": "Convert to office", "convert": r["label"]}
            if r in spare_meet:
                spare_meet.remove(r)
            changes.append({"kind": "convert", "room": r["id"], "text": f"Use the {r['area']:.0f} m² ({_ft2(r['area'])}) "
                            f"{r['label']} as a private office", "status": "warn"})
            short_off -= 1
    short_meet = max(0, p.meeting_rooms - len(use_meet))
    if short_meet:  # a spare private office big enough for four can host a small meeting
        cands = [r for r in spare_off if r["area"] >= 4 * p.seat_m2][:short_meet]
        for r in cands:
            spare_off.remove(r)
            n = math.floor(r["area"] / p.seat_m2)
            roles[r["id"]] = {"role": "meeting", "seats": n, "label": f"Meeting, {n} seats", "convert": r["label"]}
            changes.append({"kind": "convert", "room": r["id"], "text": f"Use the {r['area']:.0f} m² private office as a "
                            f"{n}-seat meeting room", "status": "warn"})
            short_meet -= 1
    largest = max((roles[r]["seats"] for r in roles if roles[r]["role"] == "meeting"), default=0)

    # Desks: the open areas at the chosen density, plus one person in each spare private office.
    open_area = sum(r["area"] for r in opens)
    need_desks = p.headcount - p.private_offices
    desks = 0
    for r in opens:
        n = math.floor(r["area"] / p.desk_m2)
        desks += n
        roles[r["id"]] = {"role": "desks", "seats": n, "label": f"Open area, {n} desks"}
    shared = 0
    for r in spare_off:  # a spare office twice the smallest size holds two people
        n = 2 if r["area"] >= 2 * p.office_min_m2 else 1
        shared += n
        roles[r["id"]] = {"role": "desks", "seats": n, "label": "Office for two more people" if n == 2 else "Office for one more person"}
    for r in spare_meet:
        roles[r["id"]] = {"role": "spare", "seats": seats[r["id"]], "label": f"Spare meeting room, {seats[r['id']]} seats"}
    for lab, role in (("kitchen or break room", "kitchen"), ("reception", "reception"), ("restroom", "restroom"),
                      ("storage", "storage"), ("phone booth", "phone booth"), ("server or electrical room", "server")):
        for r in by(lab):
            roles.setdefault(r["id"], {"role": role, "seats": 0, "label": lab.capitalize()})
    have_desks = desks + shared
    short_desks = max(0, need_desks - have_desks)
    if short_desks and open_area:
        tight = open_area / max(need_desks - shared, 1)
        if tight >= 4.5:
            changes.append({"kind": "density", "text": f"Plan the open area at {tight:.1f} m² ({tight * M2:.0f} ft²) per desk "
                            f"instead of {p.desk_m2:.1f}: benching density, tight but common", "status": "warn"})
    surplus = open_area - need_desks * p.desk_m2 if open_area else 0.0
    if short_off > 0 and surplus >= short_off * max(p.office_min_m2, 10):
        changes.append({"kind": "build", "offices": short_off, "text": f"Build {short_off} private office"
                        f"{'s' if short_off > 1 else ''} in the open area, which has about {_ft2(surplus)} more than your "
                        "desks need; price it with Takeoff bid (fit-out)", "status": "warn"})
        surplus -= short_off * max(p.office_min_m2, 10)
        short_off = 0
    if short_meet > 0 and surplus >= short_meet * p.meeting_seats * p.seat_m2:
        changes.append({"kind": "build", "text": f"Build {short_meet} meeting room{'s' if short_meet > 1 else ''} for "
                        f"{p.meeting_seats} in the open area", "status": "warn"})
        largest = max(largest, p.meeting_seats)
        short_meet = 0
    kitchens = by("kitchen or break room")
    if p.kitchen and not kitchens:
        changes.append({"kind": "kitchen", "text": "Add a kitchenette; the suite shows none, so plumbing is the cost to check",
                        "status": "warn"})
    program_m2 = need_desks * p.desk_m2 + p.private_offices * max(p.office_min_m2, 10) + \
        p.meeting_rooms * p.meeting_seats * p.seat_m2 + (12 if p.kitchen else 0)
    program_m2 *= 1.15  # circulation and support the program does not name
    usable = sum(r["area"] for r in rooms if r.get("area") and r.get("indoor", True))
    if short_desks and not any(c["kind"] == "density" for c in changes):
        changes.append({"kind": "space", "text": f"Look for about {_ft2(max(program_m2 - usable, short_desks * p.desk_m2))} more, "
                        f"or seat {short_desks} people elsewhere", "status": "fail"})
    if largest < p.meeting_seats and p.meeting_rooms:
        changes.append({"kind": "meeting", "text": f"The largest meeting room seats {largest}; book an outside room for "
                        f"{p.meeting_seats}, or open two rooms into one", "status": "warn"})
    hard = short_off > 0 or short_meet > 0 or (short_desks > 0 and not any(c["kind"] == "density" for c in changes))
    soft = bool(changes)
    return {"roles": roles, "changes": changes, "desks": have_desks, "need_desks": need_desks, "short_desks": short_desks,
            "offices": len(offices), "short_offices": max(short_off, 0), "meeting": len(meetings), "short_meetings": short_meet,
            "largest_meeting": largest, "kitchens": len(kitchens), "restrooms": len(by("restroom")),
            "reception": len(by("reception")), "storage": len(by("storage")), "open_area": open_area,
            "program_m2": program_m2, "usable_m2": usable,
            "status": "fail" if hard else "warn" if soft else "pass"}


SUITE = re.compile(r"\bsuite\s*[-#]?\s*([0-9]+[A-Za-z]?|[A-Za-z][0-9]*)\b", re.IGNORECASE)
SF = re.compile(r"([0-9][0-9,]{2,})\s*(?:sf|sq\.?\s?ft|square feet)", re.IGNORECASE)


WORK_ROOMS = ("private office", "open office", "conference room", "reception")
OVERLAP_M2 = 0.5  # a bathroom's floor over at least this much of an office counts as above it


def under_bathrooms(plan: dict) -> list[tuple[dict, dict, float]] | None:
    """(office, restroom above it, overlap m²) for every work room with a restroom on the next floor up over it, from
    the room outlines of a multi-floor scan. None when the scan has one floor (nothing above it is scanned)."""
    from ...geometry._plan import polygons
    el = elevations(plan)
    floors = sorted({r["floor"] for r in plan.get("rooms") or []}, key=lambda f: el.get(f) or 0)
    if len(floors) < 2:
        return None
    polys, out = polygons(plan), []
    for i, f in enumerate(floors[:-1]):
        up = floors[i + 1]
        wet = [r for r in plan["rooms"] if r["floor"] == up and facts.commercial(r.get("label")) == "restroom"
               and polys.get(r["id"]) is not None]
        for r in plan["rooms"]:
            if r["floor"] != f or facts.commercial(r.get("label")) not in WORK_ROOMS or polys.get(r["id"]) is None:
                continue
            for w in wet:
                a = polys[r["id"]].intersection(polys[w["id"]]).area
                if a >= OVERLAP_M2:
                    out.append((r, w, a))
    return out


def _rate(sp: dict) -> tuple[float | None, str | None]:
    """Asking rent per ft² per year, and its service type, from one listing space."""
    lo, hi = sp.get("rateLow") or 0, sp.get("rateHigh") or 0
    if not lo and not hi:
        return None, None
    r = (lo + hi) / 2 if lo and hi else lo or hi
    r *= 12 if sp.get("rateBasis") == 1 else 1
    service = costar._enums().get("ServiceType", {}).get(str(sp.get("serviceType")))
    return r, service


def record_facts(sid: str, name: str) -> dict:
    """Listed size, asking rent and the suite's tenants, matched by the suite number in the scan's title."""
    out: dict = {"suite": None, "title_ft2": None, "space": None, "tenant": None, "property_rentable_ft2": None}
    m = SUITE.search(name)
    out["suite"] = m.group(1).upper() if m else None
    s = SF.search(name)
    out["title_ft2"] = float(s.group(1).replace(",", "")) if s else None
    rec = facts.record(sid)
    pid = facts.property_id(sid)
    if not rec or not pid:
        return out
    out["property_rentable_ft2"] = (rec.get("property") or {}).get("rentableBuildingAreaSquareFeet")
    spaces = [sp for l in costar.by_property("commercial-listing-summary", pid) for sp in (l.get("forLeaseSummary") or {}).get("spaces") or []]
    if out["suite"]:
        hit = [sp for sp in spaces if (sp.get("suite") or "").upper().replace(" ", "") == out["suite"]]
        out["space"] = hit[0] if hit else None
    tenancies = sorted(costar.by_property("location-occupancy", pid), key=lambda t: t.get("fromDate") or "", reverse=True)
    for t in tenancies:
        if out["suite"] and any((x.get("suite") or "").upper() == out["suite"] for x in t.get("spaces") or []):
            c = costar.get("company-detail", t["tenantLocationId"]) if t.get("tenantLocationId") else None
            out["tenant"] = {"name": (c or {}).get("name"), "employees": (c or {}).get("numEmployees"),
                             "from": (t.get("fromDate") or "")[:10], "to": (t.get("toDate") or "")[:10] or None,
                             "ft2": next((x.get("squareFeetOccupied") for x in t["spaces"] if (x.get("suite") or "").upper() == out["suite"]), None)}
            break
    return out


@tool(id="office_fit", title="Office fit", icon="users",
      summary="Whether your team fits this suite as built: desks, private offices, meeting rooms and kitchen, "
              "with the listed size and the last tenant beside it.",
      model_description="Test a tenant program (headcount, private offices, meeting rooms and seats, kitchen) against one "
                        "office scan. Counts what the suite has from room labels and measured areas, shows which room serves "
                        "as what, compares listed against measured area (load factor), the last tenant's employee count "
                        "against computed capacity, and the asking rent. Returns pass/warn/fail and up to three changes "
                        "that would make it fit. Labels unlabelled rooms first (slow once).",
      personas=["office_tenant", "costar_researcher"],
      requires=[{"layer": "matterport.rooms"}, {"layer": "matterport.panos", "need": "optional", "fallback": "existing labels"},
                {"layer": "costar.property", "need": "optional", "fallback": "no record comparison"}],
      blocks=["VerdictHeader", "MetricRow", "CheckList", "MiniChart", "FloorPlanMini", "AssumptionChips", "Controls",
              "EvidenceStrip", "StepLog"],
      overlays=["lens", "pins", "rule"], annotations={"cost": "slow"},
      examples=["Will 28 people with 6 private offices and two meeting rooms fit here?", "How many desks does this suite hold?"])
def run(ctx, inputs: Inputs) -> ToolResult:
    sid = inputs.scan
    plan = ensure_labels(ctx, sid, inputs.label_with_vision)
    q = facts.quality(plan)
    fx = facts.room_facts(plan)
    indoor = {r["id"] for r in indoor_rooms(plan)}
    rooms = [{"id": r["id"], "label": facts.commercial(r.get("label")), "area": r.get("area"), "windows": fx[r["id"]]["windows"],
              "indoor": r["id"] in indoor} for r in facts.live_rooms(plan)]
    ctx.step(f"Read {len(rooms)} rooms and their labels")
    assumptions = [
        Assumption(id="office.desk_m2", label="Open-plan area per desk", value=inputs.desk_m2, unit="m²", editable=True),
        Assumption(id="office.meeting_seat_m2", label="Meeting room area per seat", value=inputs.seat_m2, unit="m²", editable=True),
        Assumption(id="office.private_office_min_m2", label="Smallest private office", value=inputs.office_min_m2, unit="m²", editable=True),
        Assumption(id="circulation", label="Circulation added to the program", value=15, unit="%"),
    ]
    if not any(r["area"] for r in rooms):
        return ToolResult(scope=ScanScope(sid=sid), assumptions=assumptions,
                          verdict=Verdict(status="unknown", text="This scan has no room areas, so capacity cannot be measured."))
    unlabelled = [r for r in rooms if not r["label"]]
    f = fit(rooms, inputs)
    ctx.step(f"Allocated rooms: {f['desks']} desks, {f['offices']} private offices, {f['meeting']} meeting rooms")

    # Record comparison
    name = facts.scan_name(sid)
    rf = record_facts(sid, name)
    checks, findings, metrics = [], [], []
    usable = f["usable_m2"]
    metrics += [Metric(id="desks", label="People seated as built", value=f["desks"] + min(inputs.private_offices, f["offices"]), unit="", source=CALC),
                Metric(id="headcount", label="People to seat", value=inputs.headcount, unit="", source=CALC),
                Metric(id="usable_area", label="Measured area inside the suite", value=round(usable, 1), unit="m²", source=AREA),
                Metric(id="program_area", label="Area your program needs", value=round(f["program_m2"], 1), unit="m²", source=CALC)]
    for k, lab in (("desks", "Desks in open areas and spare offices"), ("offices", "Private offices"), ("meeting", "Meeting rooms"),
                   ("kitchens", "Kitchens"), ("restrooms", "Restrooms in the suite"), ("reception", "Reception"), ("storage", "Storage rooms")):
        metrics.append(Metric(id=f"has.{k}", label=lab, value=f[k], unit="", source=LABELS))

    def chk(id, rule, measured, threshold, unit, status, fid=None):
        checks.append(Check(id=id, rule=rule, measured=measured, threshold=threshold, unit=unit, status=status,
                            findings=[fid] if fid else []))

    chk("desks", "Desks for everyone without a private office", f["desks"], f["need_desks"], "desks",
        "pass" if not f["short_desks"] else "warn" if any(c["kind"] == "density" for c in f["changes"]) else "fail")
    chk("offices", "Private offices", f["offices"], inputs.private_offices, "rooms",
        "pass" if f["offices"] >= inputs.private_offices else "warn" if not f["short_offices"] else "fail")
    chk("meetings", "Meeting rooms", f["meeting"], inputs.meeting_rooms, "rooms",
        "pass" if f["meeting"] >= inputs.meeting_rooms else "warn" if not f["short_meetings"] else "fail")
    if inputs.meeting_rooms:
        chk("meeting_seats", "Seats in the largest meeting room", f["largest_meeting"], inputs.meeting_seats, "seats",
            "pass" if f["largest_meeting"] >= inputs.meeting_seats else "warn")
    if inputs.kitchen:
        chk("kitchen", "Kitchen or break room", f["kitchens"], 1, "rooms", "pass" if f["kitchens"] else "warn")

    # a restroom on the floor above an office: leaks and noise through the ceiling (a manager's warning)
    under = under_bathrooms(plan) if q["walls"] else None
    if under is None:
        checks.append(cannot("above", "what is on the floor above: only one floor is scanned, so an office under a "
                                      "bathroom cannot be ruled out"))
    else:
        offs = sorted({r["id"] for r, _, _ in under})
        fid = f"office_fit:{sid}:under_bathroom"
        chk("under_bathroom", "Offices with a restroom on the floor above them", len(offs), 0, "rooms",
            "warn" if offs else "pass", fid if offs else None)
        if offs:
            findings.append(Finding(id=fid, title="Office under a bathroom", status="warn", source=AREA,
                                    anchor=RoomAnchor(sid=sid, room=under[0][0]["id"]),
                                    detail="; ".join(f"{facts.commercial(r.get('label'))} {r['id']} has {a:.1f} m² of a "
                                                     f"restroom above it" for r, w, a in under[:5]) +
                                           ". A leak or a flush comes through the ceiling; seat people elsewhere."))
    checks.append(cannot("noise", "sound through walls and floors: the scan measures rooms, not soundproofing"))
    listed = (rf["space"] or {}).get("squareFeetMax") or (rf["tenant"] or {}).get("ft2") or rf["title_ft2"]
    listed_from = ("the lease listing for suite " + rf["suite"] if (rf["space"] or {}).get("squareFeetMax") else
                   f"the tenancy record of {rf['tenant']['name'] or 'an unnamed tenant'}" if (rf["tenant"] or {}).get("ft2") else
                   "the scan's title" if rf["title_ft2"] else None)
    if listed and usable:
        load = listed / (usable * M2)
        lo, hi = TYPICAL_LOAD
        st = "pass" if lo <= load <= hi else "warn" if 0.8 <= load <= 1.6 else "unknown"
        why = ("inside the usual range, the share of lobbies, corridors and shared restrooms a multi-tenant lease bills"
               if st == "pass" else
               "too far from 1 to be the same space: the record's size is probably for part of the suite or another "
               "space, or the scan covers more than the suite, so this is not a usable comparison" if st == "unknown" else
               "below 1: the scan measured more than is listed, so it may take in common corridors, or the listed size is rounded down"
               if load < 1 else "above the usual range: ask for the measurement standard (BOMA) before signing")
        fid = f"office_fit:{sid}:load_factor"
        chk("load_factor", "Listed (rentable) over measured (usable) area", round(load, 2), hi, "", st, fid)
        findings.append(Finding(id=fid, title="Listed size against measured area", status=st,
                                detail=f"Listed {listed:,.0f} ft² ({listed_from}); measured {_ft2(usable)} inside the suite. "
                                       f"Load factor {load:.2f}, {why}. Measured area is floor inside the scanned rooms, "
                                       "so it is close to usable area, not BOMA rentable.",
                                anchor=None, source=RECORD))
        if st != "unknown":
            metrics.append(Metric(id="load_factor", label="Load factor (listed over measured)", value=round(load, 2), unit="", source=RECORD))
    t = rf["tenant"]
    if t and t.get("employees") and t.get("name"):
        cap = f["desks"] + f["offices"]
        st = "pass" if t["employees"] <= cap else "warn"
        fid = f"office_fit:{sid}:tenant"
        when = f"since {t['from']}" if not t["to"] else f"{t['from']} to {t['to']}"
        findings.append(Finding(id=fid, title="Tenant headcount against capacity", status=st, anchor=None, source=RECORD,
                                detail=f"{t['name']} ({when}) lists {t['employees']} employees at this location; the suite "
                                       f"seats {cap} at your standards. " + ("They fit." if st == "pass" else
                                                                            "They had more people than these standards allow, so they sat denser or not everyone was in at once.")))
        chk("tenant", f"Recorded employees of {t['name']} within computed capacity", t["employees"], cap, "people", st, fid)
    if rf["space"]:
        rate, service = _rate(rf["space"])
        if rate:
            metrics.append(Metric(id="asking_rent", label=f"Asking rent ({service or 'basis not given'})", value=round(rate, 2),
                                  unit="$/ft²/yr", source=RECORD))
            if listed:
                metrics.append(Metric(id="rent_per_measured", label="Asking rent per measured ft²",
                                      value=round(rate * listed / (usable * M2), 2), unit="$/ft²/yr", source=RECORD))
                metrics.append(Metric(id="rent_per_seat", label="Rent per seat per year",
                                      value=round(rate * listed / max(f["desks"] + f["offices"], 1)), unit="$", source=CALC))

    # Overlays: seats each room gives, and what each room serves as.
    roles = f["roles"]
    pins = [Pin(id=rid, anchor=RoomAnchor(sid=sid, room=rid), label=v["label"],
                status="warn" if v.get("convert") else "pass" if v["role"] in ("desks", "office", "meeting", "kitchen") else "unknown")
            for rid, v in roles.items()]
    seats = {rid: v["seats"] for rid, v in roles.items() if v["seats"]}
    overlays = []
    if seats:
        overlays.append(LensOverlay(values=seats, ramp="sequential",
                                    legend=Legend(title="Seats each room gives", unit="seats", min=0, max=max(seats.values()))))
    overlays.append(PinsOverlay(pins=pins))
    conv = [rid for rid, v in roles.items() if v.get("convert")]
    if conv:
        overlays.append(RuleOverlay(select=SelectRooms(rooms=conv), style="warn"))
    idle = [r["id"] for r in rooms if r["id"] not in roles]
    if idle:
        overlays.append(RuleOverlay(select=SelectRooms(rooms=idle), style="dim"))
    for i, c in enumerate(f["changes"][:3]):
        findings.append(Finding(id=f"office_fit:{sid}:change{i + 1}", title="Change that would make it fit", status=c["status"],
                                detail=c["text"] + ".", anchor=RoomAnchor(sid=sid, room=c["room"]) if c.get("room") else None,
                                source=CALC))

    status = f["status"]
    text = {"pass": "Your team fits as built", "warn": "Your team fits with changes", "fail": "Your team does not fit"}[status]
    n = lambda k, word: f"{k} {word}{'' if k == 1 else 's'}"
    want = lambda k: f" for the {k} you need" if k else ""
    text += (f": {n(f['desks'], 'desk')} for {n(f['need_desks'], 'person') if f['need_desks'] == 1 else str(f['need_desks']) + ' people'}, "
             f"{n(f['offices'], 'private office')}{want(inputs.private_offices)}, "
             f"{n(f['meeting'], 'meeting room')}{want(inputs.meeting_rooms)}.")
    if facts.scan_kind(sid) in ("house", "apartment_unit"):
        text += " This scan is a home, not office space."
    if unlabelled:
        text += f" {len(unlabelled)} room{'s have' if len(unlabelled) > 1 else ' has'} no label and count{'' if len(unlabelled) > 1 else 's'} for nothing."
        status = "warn" if status == "pass" else status
    if not q["walls"]:
        text += (" No wall graph: areas are Matterport's room sizes without outlines, so desks are counted from area alone "
                 "and doors and windows are unknown; offices to convert need a window check on site.")
    return ToolResult(scope=ScanScope(sid=sid), verdict=Verdict(status=status, text=text), metrics=metrics, checks=checks,
                      findings=findings, overlays=overlays, assumptions=assumptions)
