"""Facility audit: one bundle for a business's own building, ending in a prioritised fix list with rough costs.

Runs door_widths (32 in clear, the 2010 ADA Standards for public accommodations, section 404.2.3), bathroom_clearance,
egress_routes, the life-safety objects the vision model saw on the panoramas (smoke alarms, sprinkler heads, exit
signs, fire extinguishers), the occupant load at 150 gross ft² per person (IBC 2021 Table 1004.5, business areas)
against the doorways out, and the cleaning takeoff. Prices come from the what-if cost book (low reliability national
averages); a fix the book has no price for says "get a quote" instead of a guessed number.

Findings are leads, not a code inspection: "not seen" in a photo is never "absent".
"""
from __future__ import annotations

from pydantic import BaseModel

from ...whatif.cost import PRICES
from .. import Check, Finding, Metric, ScanScope, Source, ToolResult, Verdict, field, run_tool, tool

FT2_PER_M2 = 10.7639
SF_PER_OCCUPANT = 150  # IBC 2021 Table 1004.5, business areas, gross
TWO_EXITS_ABOVE = 49   # IBC 2021 Table 1006.2.1: Group B spaces with more than 49 occupants need two exits
TRAVEL_SPRINKLERED_M = 91.4
TRAVEL_M = 61.0        # IBC 2021 Table 1017.2: exit access travel distance, Group B without sprinklers, 200 ft (300 ft with)
BOOK = Source(layer="model", method="simulation", confidence="low",
              note="What-if cost book: national averages from cost guides, not a quote, no local labour rate")
AREA = Source(layer="matterport", method="geometry", confidence="high", note="Sum of room areas on the scan")
SEEN_LABELS = ("smoke alarm", "sprinkler head", "exit sign", "fire extinguisher")


class Inputs(BaseModel):
    scan: str = field(source="selection.scan", description="Scan id of the building or suite")
    door_width_m: float = field(0.813, pref="access.door_width_m", unit="m", gt=0.3, le=2.0,
                                description="Clear width a door needs (32 in, ADA 404.2.3)")
    read_panoramas: bool = field(True, description="Let the vision model read the panoramas (restroom fixtures, "
                                                   "life-safety objects); cached after the first run")
    cleaning: bool = field(True, description="Price a cleaning contract from the takeoff")


def price(pid: str) -> tuple[float, str]:
    p = PRICES[pid]
    return p[1], p[3]


def fixes_for(doors: ToolResult | None, baths: ToolResult | None, egress: ToolResult | None, need_m: float) -> list[dict]:
    """The fix list from the sub-results: {priority, area, title, qty, unit_cost, total, source, why}. Pure."""
    out = []
    if egress:
        for c in egress.checks:
            if c.id == "exit" and c.status == "fail":
                cost, src = price("widen_door")
                out.append({"priority": 1, "area": "egress", "title": "Widen the widest way out to a full exit width", "qty": 1,
                            "unit_cost": cost, "total": cost, "source": src,
                            "why": f"Widest doorway out is {c.measured:.2f} m against {c.threshold:.2f} m"})
            if c.id.startswith("length:") and c.status in ("warn", "fail") and c.measured is not None:
                out.append({"priority": 1, "area": "egress", "title": "Way out longer than the travel distance limit", "qty": 1,
                            "unit_cost": None, "total": None, "source": "No price: confirm sprinklers (300 ft allowed) or add an exit",
                            "why": f"{c.measured:.0f} m to an entrance against {c.threshold:.0f} m (200 ft, IBC 2021 Table 1017.2, "
                                   "Group B without sprinklers)", "measured": c.measured})
            if c.id.startswith("pinch:") and c.status == "fail":
                out.append({"priority": 1, "area": "egress", "title": "Clear or widen a narrow hallway on a way out", "qty": 1,
                            "unit_cost": None, "total": None, "source": "No price in the cost book: get a quote",
                            "why": f"Hallway {c.measured:.2f} m wide"})
    if doors:
        narrow = [c for c in doors.checks if c.status == "fail" and c.measured is not None]
        close = [c for c in narrow if c.measured >= need_m - 0.05]   # within 5 cm: swing-clear hinges gain about that much
        wide = [c for c in narrow if c.measured < need_m - 0.05]
        if close:
            cost, src = price("offset_hinges")
            out.append({"priority": 2, "area": "access", "title": "Swing-clear hinges on doors just under 32 in", "qty": len(close),
                        "unit_cost": cost, "total": cost * len(close), "source": src,
                        "why": ", ".join(f"{c.measured:.2f} m" for c in close[:8])})
        if wide:
            cost, src = price("widen_door")
            out.append({"priority": 2, "area": "access", "title": "Widen doorways well under 32 in", "qty": len(wide),
                        "unit_cost": cost, "total": cost * len(wide), "source": src,
                        "why": ", ".join(f"{c.measured:.2f} m" for c in wide[:8])})
    if baths:
        grab = [c for c in baths.checks if c.status == "fail" and "grab" in c.rule.lower()]
        if grab:
            cost, src = price("grab_bar")
            out.append({"priority": 2, "area": "access", "title": "Grab bars at the toilet (side and rear)", "qty": 2 * len(grab),
                        "unit_cost": cost, "total": cost * 2 * len(grab), "source": src, "why": f"{len(grab)} restrooms without them seen"})
        turn = [c for c in baths.checks if c.status == "fail" and "turn" in c.rule.lower()]
        if turn:
            out.append({"priority": 2, "area": "access", "title": "Restroom too small to turn a wheelchair: reconfigure",
                        "qty": len(turn), "unit_cost": None, "total": None, "source": "No price in the cost book: get a quote",
                        "why": ", ".join(f"{c.measured:.2f} m circle" for c in turn if c.measured is not None)})
    return sorted(out, key=lambda f: (f["priority"], -(f["total"] or 0)))


def seen_counts(plan: dict, read: bool) -> dict | None:
    from ..fire_preplan.common import VisionBudget, objects
    found = objects(plan, VisionBudget(1 if read else 0))
    if found is None:
        return None
    return {k: sum(d["label"] == k and d["finding"]["source"]["confidence"] in ("high", "medium") for d in found) for k in SEEN_LABELS}


@tool(id="facility_audit", title="Facility audit", icon="clipboard-check",
      summary="Your building in one pass: doors, restrooms, ways out, life-safety equipment seen, occupant load and "
              "cleaning cost, ending in a prioritised fix list with rough costs.",
      model_description="For a business auditing its current building or suite (one scan): ADA Title III style checks "
                        "(32 in door clear width, restroom clearances), egress routes and exit widths, occupant load at 150 "
                        "ft² per person against the doorways out, smoke alarms, sprinkler heads, exit signs and extinguishers "
                        "seen on the panoramas, and a cleaning contract price from the takeoff. Returns a prioritised fix "
                        "list priced from the what-if cost book (low reliability), and says where a fix needs a quote.",
      personas=["facility_manager", "office_tenant"],
      requires=[{"layer": "matterport.openings"}, {"layer": "matterport.panos", "need": "optional"}],
      blocks=["VerdictHeader", "MetricRow", "MiniChart", "CheckList", "EvidenceStrip", "AssumptionChips", "StepLog"],
      annotations={"cost": "slow"},
      examples=["Audit our office for accessibility and life safety", "What should we fix first in this building, and what will it cost?"])
def run(ctx, i: Inputs) -> ToolResult:
    sid = i.scan
    plan = ctx.plan(sid)
    q = plan.get("quality") or {}
    area_sf = round(sum(r.get("area") or 0 for r in plan.get("rooms") or []) * FT2_PER_M2)
    ctx.step(f"Scan {sid}: {len(plan.get('rooms') or [])} rooms, {area_sf:,} ft²" + ("" if q.get("openings", True) else ", no door widths"))

    def sub(tid, inputs):
        try:
            r = run_tool(tid, {"scan": sid, **inputs}, ctx)
            ctx.step(f"{tid}: {r.verdict.text}")
            return r
        except Exception as e:  # noqa: BLE001  one failed check does not sink the audit
            ctx.step(f"{tid} did not run: {str(e)[:120]}")
            return None
    doors = sub("door_widths", {"min_width_m": i.door_width_m})
    baths = sub("bathroom_clearance", {"door_width_m": max(i.door_width_m, 0.815), "read_panoramas": i.read_panoramas})
    egress = sub("egress_routes", {"min_width_m": i.door_width_m, "long_route_m": TRAVEL_M})
    if egress:  # the hose stretch is the fire crew's question, not the occupant's
        egress = egress.model_copy(update={"checks": [c for c in egress.checks if c.id != "hose"],
                                           "findings": [f for f in egress.findings if "hose" not in f.id.lower() and "Hose" not in f.title]})
    clean = sub("takeoff_bid", {"trade": "cleaning", "label_with_vision": i.read_panoramas}) if i.cleaning else None
    try:
        seen = seen_counts(plan, i.read_panoramas)
    except Exception as e:  # noqa: BLE001
        seen = None
        ctx.step(f"Life-safety photos not read: {str(e)[:120]}")

    metrics, checks, findings = [], [], []
    occupants = area_sf // SF_PER_OCCUPANT
    exits = next((c.measured for c in (egress.checks if egress else []) if c.id == "entrances"), None)
    metrics.append(Metric(id="area", label="Scanned floor area", value=area_sf, unit="ft²", source=AREA))
    metrics.append(Metric(id="occupant_load", label="Occupant load (150 ft² each)", value=occupants, unit="people",
                          source=Source(layer="model", method="geometry", confidence="medium", note="IBC 2021 Table 1004.5, business areas")))
    need_exits = 2 if occupants > TWO_EXITS_ABOVE else 1
    st = "unknown" if exits is None else "pass" if exits >= need_exits else "fail"
    checks.append(Check(id="exits_for_load", rule=f"Ways out for {occupants} occupants", measured=exits, threshold=need_exits, unit="",
                        status=st, standard="IBC 2021 Table 1006.2.1: Group B, more than 49 occupants need two exits",
                        findings=["facility_audit:" + sid + ":exits"] if st == "fail" else []))
    if st == "fail":
        findings.append(Finding(id=f"facility_audit:{sid}:exits", title="Fewer ways out than the occupant load needs", status="fail",
                                detail=f"{area_sf:,} ft² at 150 ft² a person is {occupants} occupants, which needs {need_exits} exits; "
                                       f"the scan shows {exits:g} doorway{'s' if exits != 1 else ''} to outside or unscanned space. "
                                       "An exit through a corridor the scan does not cover may exist: check on site.",
                                anchor=None, source=AREA))
    for r in (doors, baths, egress):
        if r:
            bad = [c for c in r.checks if c.status in ("fail", "warn")]
            checks += [c.model_copy(update={"id": f"{r.tool}.{c.id}"}) for c in bad[:15]]
            findings += [f for f in r.findings if f.status in ("fail", "warn")][:8]
    if seen is not None:
        vis = Source(layer="model", method="vision", confidence="medium", note="Vision model on each room's central panorama")
        for k, n in seen.items():
            metrics.append(Metric(id=f"seen.{k.replace(' ', '_')}", label=k.capitalize() + "s seen", value=n, unit="", source=vis))
        missing = [k for k in ("exit sign", "fire extinguisher", "smoke alarm") if not seen[k]]
        findings.append(Finding(id=f"facility_audit:{sid}:life_safety", title="Life-safety equipment seen on the photos",
                                status="warn" if missing else "pass", anchor=None, source=vis,
                                detail="; ".join(f"{n} {k}{'s' if n != 1 else ''}" for k, n in seen.items()) + "." +
                                       (f" None seen: {', '.join(missing)}. Something outside the photos is missed; check on site." if missing else "")))
    else:
        findings.append(Finding(id=f"facility_audit:{sid}:life_safety", title="Life-safety equipment not read", status="unknown",
                                anchor=None, source=BOOK, detail="The panoramas were not read in this run."))

    fixes = fixes_for(doors, baths, egress, i.door_width_m)
    if seen is not None:
        for f in fixes:
            if f["title"].startswith("Way out longer") and seen["sprinkler head"] and f["measured"] <= TRAVEL_SPRINKLERED_M:
                f.update(priority=3, area="life safety", title="Confirm the building is fully sprinklered",
                         source="Sprinkler heads were seen, so the 300 ft limit likely applies",
                         why=f["why"] + f"; within 300 ft ({TRAVEL_SPRINKLERED_M:.0f} m) if the whole building is sprinklered")
        fixes.sort(key=lambda f: (f["priority"], -(f["total"] or 0)))
        for k in ("exit sign", "fire extinguisher"):
            if not seen[k]:
                fixes.append({"priority": 3, "area": "life safety", "title": f"Confirm {k}s on site", "qty": 1, "unit_cost": None,
                              "total": None, "source": "Not seen on the photos; a walk-through costs nothing",
                              "why": f"No {k} seen on the panoramas"})
    total = sum(f["total"] or 0 for f in fixes)
    quote = [f for f in fixes if f["total"] is None]
    for n, f in enumerate(fixes, start=1):
        fid = f"facility_audit:{sid}:fix_{n}"
        findings.insert(n - 1, Finding(id=fid, title=f"Fix {n} ({f['area']}): {f['title']}",
                                       status="fail" if f["priority"] == 1 else "warn" if f["priority"] == 2 else "unknown", anchor=None, source=BOOK,
                                       detail=f"{f['why']}. " + (f"{f['qty']} x ${f['unit_cost']:,.0f} = ${f['total']:,.0f} ({f['source']})."
                                                                if f["total"] is not None else f"{f['qty']} to do. {f['source']}.")))
        if f["total"] is not None:
            metrics.append(Metric(id=f"cost.fix_{n}", label=f["title"], value=f["total"], unit="$", source=BOOK))
    metrics.insert(2, Metric(id="fix_total", label="Priced fixes", value=total, unit="$", source=BOOK))
    metrics.insert(3, Metric(id="fixes", label="Fixes found", value=len(fixes), unit="", source=BOOK))
    if clean:
        m = {x.id: x for x in clean.metrics}
        if "monthly_price" in m:
            metrics.append(m["monthly_price"].model_copy(update={"id": "cleaning_monthly", "label": "Cleaning contract per month"}))
    status = "fail" if any(f["priority"] == 1 for f in fixes) or any(c.status == "fail" for c in checks if c.id == "exits_for_load") \
        else "warn" if fixes or any(c.status == "warn" for c in checks) else "pass"
    text = (f"{len(fixes)} fixes found" + (f", ${total:,.0f} priced (low reliability)" if total else "") +
            (f", {len(quote)} unpriced (confirm on site or get a quote)" if quote else "") + f"; occupant load {occupants} at 150 ft² a person.") if fixes else \
        f"No door, restroom or way-out fixes found by the scan checks; occupant load {occupants} at 150 ft² a person."
    if clean and "monthly_price" in {x.id for x in clean.metrics}:
        text += f" Cleaning about ${next(x.value for x in clean.metrics if x.id == 'monthly_price'):,.0f} a month."
    return ToolResult(scope=ScanScope(sid=sid), verdict=Verdict(status=status, text=text), metrics=metrics, checks=checks,
                      findings=findings,
                      overlays=[o for r in (doors, egress) if r for o in r.overlays][:6],
                      assumptions=[{"id": "access.door_width_m", "label": "Door clear width", "value": i.door_width_m, "unit": "m", "editable": True},
                                   {"id": "occupant_factor", "label": "Area per occupant", "value": SF_PER_OCCUPANT, "unit": "ft²"},
                                   *[{"id": f"whatif.price.{k}", "label": PRICES[k][0], "value": PRICES[k][1], "unit": PRICES[k][2]}
                                     for k in ("widen_door", "offset_hinges", "grab_bar")]])
