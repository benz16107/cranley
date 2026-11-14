"""Unit compare: several apartment units (or suites) of one property side by side on measured facts, with the
listing's rent per measured square foot where the record has a rent."""
from __future__ import annotations

import re
import statistics

from pydantic import BaseModel

from ... import geometry
from ...sources import costar
from .. import (
    Check,
    Finding,
    Metric,
    RoomAnchor,
    Source,
    ToolError,
    ToolResult,
    Verdict,
    field,
    tool,
)
from ..office_fit import SF, _rate, record_facts
from ..room_labeller import ensure_labels, facts
from ..storage_space import storage
from ..types import ScansScope

FT2 = facts.M2_TO_FT2
AREA = Source(layer="matterport", method="geometry", confidence="high", note="Measured in the scan")
RECORD = Source(layer="costar", method="lookup", confidence="high", note="Apartment listing or lease listing in the CoStar kit")
ADA_DOOR_M = 0.813  # 32 in clear
BEDS = re.compile(r"(\d)\s*(?:br|bd|bed)", re.IGNORECASE)
BATHS = re.compile(r"(\d(?:\.\d)?)\s*(?:ba|bath)", re.IGNORECASE)


class Inputs(BaseModel):
    scans: list[str] = field([], description="Scan ids of the units or suites to compare")
    property: int | None = field(None, description="CoStar property id: compare all its unit scans")
    scan: str | None = field(None, source="selection.scan", description="One unit: compare it with the other units of its property")
    max_units: int = field(12, ge=2, le=40, description="At most this many units")
    label_with_vision: bool = field(False, description="Label unlabelled rooms from the panoramas first (slow once)")


def _title_layout(name: str) -> tuple[int | None, float | None, float | None]:
    b, ba, sf = BEDS.search(name), BATHS.search(name), SF.search(name)
    beds = 0 if re.search(r"studio", name, re.IGNORECASE) else int(b.group(1)) if b else None
    return beds, float(ba.group(1)) if ba else None, float(sf.group(1).replace(",", "")) if sf else None


def apartment_rent(pid: int | None, beds, baths, sf) -> tuple[float | None, str]:
    """Asking rent per month for the floor plan with these beds, baths and listed size, from the apartment listing."""
    if not pid or beds is None:
        return None, ""
    lst = costar.by_property("apartment-listing", pid)
    if not lst:
        return None, "no apartment listing"
    plans = [m for m in lst[0].get("apartmentModels") or [] if m.get("numBeds") == beds
             and (baths is None or m.get("numBaths") == baths)]
    if sf:
        plans = [m for m in plans if m.get("minSquareFeet") and abs(m["minSquareFeet"] - sf) <= 0.03 * sf] or plans
    rents = [(m["minRent"] + (m.get("maxRent") or m["minRent"])) / 2 for m in plans if m.get("minRent")]
    if not rents:
        return None, "the listing gives no rent for this floor plan" if plans else "no matching floor plan in the listing"
    return statistics.median(rents), f"{len(plans)} matching floor plan{'s' if len(plans) > 1 else ''} in the apartment listing"


def unit_row(ctx, sid: str, label_with_vision: bool) -> dict:
    plan = ensure_labels(ctx, sid, label_with_vision)
    q = facts.quality(plan)
    rooms = facts.live_rooms(plan)
    t = geometry.takeoff(plan)
    area = t["total"]["floor_area"] if t.get("available") and q["walls"] else sum(r.get("area") or 0 for r in rooms)
    labels = [r.get("label") for r in rooms]
    st = storage(plan)
    # under 0.5 m is a wall-graph fragment, not a door
    doors = [o["width"] for o in plan.get("openings") or [] if o["type"] == "doorway" and (o.get("width") or 0) >= 0.5]
    has_windows = any(o["type"] == "window" for o in plan.get("openings") or [])
    home = facts.scan_kind(sid) in ("apartment_unit", "house")
    name = facts.scan_name(sid)
    beds_t, baths_t, sf = _title_layout(name)
    beds = (labels.count("Bedroom") if "Bedroom" in labels or q["labels"] else beds_t) if home else None
    baths = (labels.count("Bathroom") if "Bathroom" in labels else baths_t) if home else None
    by_type: dict[str, float] = {}
    for r in rooms:
        if r.get("area"):
            by_type[r.get("label") or "Unlabelled"] = by_type.get(r.get("label") or "Unlabelled", 0) + r["area"]
    rent, rent_note, rent_unit = None, "", "$/ft²/mo"
    pid = facts.property_id(sid)
    if facts.scan_kind(sid) in ("office", "warehouse", "retail"):
        rf = record_facts(sid, name)
        sf = sf or (rf["space"] or {}).get("squareFeetMax")
        r, service = _rate(rf["space"]) if rf["space"] else (None, None)
        if r and sf:
            rent, rent_note, rent_unit = r * sf / 12, f"asking ${r:.2f}/ft²/yr on {sf:,.0f} listed ft² ({service})", "$/ft²/mo"
    else:
        rent, rent_note = apartment_rent(pid, beds_t if beds_t is not None else beds, baths_t, sf)
    layout = ("studio" if beds == 0 else f"{beds} bed") + (f", {baths:g} bath" if baths is not None else "") if beds is not None else \
        (f"{[facts.commercial(x) for x in labels].count('private office')} private offices, "
         f"{[facts.commercial(x) for x in labels].count('open office')} open areas")
    return {"sid": sid, "name": name, "walls": q["walls"], "area_m2": area, "listed_ft2": sf, "beds": beds, "baths": baths,
            "layout": layout, "by_type": by_type, "storage_m2": st["area"], "storage_share": st["share"],
            "windows": t["total"]["windows"] if has_windows and t.get("available") else None,
            "glazed_m2": t["total"]["glazed_area"] if has_windows and t.get("available") else None,
            "windows_mapped": has_windows,
            "door_min_m": min(doors) if doors else None, "narrow_doors": sum(1 for w in doors if w < ADA_DOOR_M) if doors else None,
            "rent": rent, "rent_note": rent_note, "rent_unit": rent_unit,
            "rent_per_ft2": rent / (area * FT2) if rent and area else None, "largest_room": max(rooms, key=lambda r: r.get("area") or 0)["id"] if rooms else None}


def pick(inputs: Inputs) -> list[str]:
    if inputs.scans:
        return inputs.scans[:inputs.max_units]
    pid = inputs.property or (facts.property_id(inputs.scan) if inputs.scan else None)
    if not pid:
        raise ToolError("Give two or more scans, a CoStar property id, or select a unit that belongs to a property in the kit.")
    kind = facts.scan_kind(inputs.scan) if inputs.scan else "apartment_unit"
    same = [s for s in costar.scans_of_property(pid) if facts.scan_kind(s) == kind]
    if inputs.scan and inputs.scan in same:
        same.remove(inputs.scan)
        same.insert(0, inputs.scan)
    return same[:inputs.max_units]


@tool(id="unit_compare", title="Unit compare", icon="columns",
      summary="Ranks several units or suites side by side on measured area, rooms, storage, windows and door widths, "
              "with rent per measured square foot.",
      model_description="Compare apartment units (or office suites) on measured facts: floor area, layout, area per room "
                        "type, storage, windows, narrowest doorway, listed against measured size, and the listing's rent per "
                        "measured ft². Give `scans`, a `property` id, or one selected unit (it is compared with the other "
                        "units of its property). Ranked by rent per measured ft², else by area.",
      personas=["apartment_manager", "renter_listing", "costar_researcher", "office_tenant"],
      requires=[{"layer": "matterport.rooms"}, {"layer": "costar.property", "need": "optional", "fallback": "no rent"}],
      blocks=["VerdictHeader", "MetricRow", "RankedTable", "MiniChart", "CheckList", "EvidenceStrip", "StepLog"],
      examples=["Compare the units in this building", "Which floor plan gives the most space for the rent?"])
def run(ctx, inputs: Inputs) -> ToolResult:
    sids = pick(inputs)
    if len(sids) < 1:
        raise ToolError("No units to compare.")
    rows = []
    for s in sids:
        try:
            rows.append(unit_row(ctx, s, inputs.label_with_vision))
        except ToolError as e:
            ctx.step(f"Skipped {s}: {e}")
    ctx.step(f"Measured {len(rows)} units")
    priced = [r for r in rows if r["rent_per_ft2"]]
    rows.sort(key=lambda r: (r["rent_per_ft2"] is None, r["rent_per_ft2"] or 0, -(r["area_m2"] or 0)))
    findings, checks, metrics = [], [], []
    for i, r in enumerate(rows):
        parts = [f"{r['layout']}", f"{r['area_m2'] * FT2:,.0f} ft² measured" if r["area_m2"] else "no area"]
        if r["listed_ft2"]:
            parts.append(f"{r['listed_ft2']:,.0f} ft² listed")
        if r["rent"]:
            parts.append(f"${r['rent']:,.0f}/mo ({r['rent_note']}), ${r['rent_per_ft2']:.2f} per measured ft²")
        elif r["rent_note"]:
            parts.append(f"no rent: {r['rent_note']}")
        parts.append(f"storage {r['storage_m2'] * FT2:,.0f} ft² ({100 * (r['storage_share'] or 0):.1f}%)")
        if r["windows"] is not None:
            parts.append(f"{r['windows']} windows, {r['glazed_m2'] * FT2:,.0f} ft² of glass")
        elif r["walls"]:
            parts.append("windows not mapped in this scan's wall graph")
        if r["door_min_m"]:
            parts.append(f"narrowest doorway {r['door_min_m'] * 39.37:.0f} in" + (f", {r['narrow_doors']} under 32 in" if r["narrow_doors"] else ""))
        big = sorted(((k, v) for k, v in r["by_type"].items()), key=lambda kv: -kv[1])[:4]
        parts.append("rooms: " + ", ".join(f"{k} {v * FT2:,.0f} ft²" for k, v in big))
        if not r["walls"]:
            parts.append("no wall graph, so windows and doors are not measured")
        findings.append(Finding(id=f"unit_compare:{r['sid']}:row", title=f"{i + 1}. {r['name']}", status="unknown",
                                detail="; ".join(parts) + ".", anchor=RoomAnchor(sid=r["sid"], room=r["largest_room"]) if r["largest_room"] else None,
                                source=AREA))
        metrics.append(Metric(id=f"area.{r['sid']}", label=r["name"], value=round(r["area_m2"] * FT2) if r["area_m2"] else None,
                              unit="ft²", source=AREA))
        if r["listed_ft2"] and r["area_m2"]:
            ratio = r["area_m2"] * FT2 / r["listed_ft2"]
            checks.append(Check(id=f"listed.{r['sid']}", rule=f"Measured against listed area, {r['name']}",
                                measured=round(r["area_m2"] * FT2), threshold=r["listed_ft2"], unit="ft²",
                                status="pass" if ratio >= 0.9 else "warn"))
    best = rows[0] if rows else None
    head = [Metric(id="area", label="Measured area (best ranked)", value=round(best["area_m2"] * FT2) if best and best["area_m2"] else None,
                   unit="ft²", source=AREA),
            Metric(id="rent_per_ft2", label="Rent per measured ft² (best ranked)",
                   value=round(best["rent_per_ft2"], 2) if best and best["rent_per_ft2"] else None, unit="$/ft²/mo", source=RECORD),
            Metric(id="storage_share", label="Storage share (best ranked)",
                   value=round(100 * best["storage_share"], 1) if best and best["storage_share"] is not None else None, unit="%", source=AREA),
            Metric(id="units", label="Units compared", value=len(rows), unit="", source=AREA)]
    if priced:
        text = (f"{len(rows)} spaces compared. Most space for the rent: {best['name']} at ${best['rent_per_ft2']:.2f} per measured "
                f"ft² a month ({best['area_m2'] * FT2:,.0f} ft²).")
    else:
        text = f"{len(rows)} spaces compared by measured area; the record has no rent for them. Largest: {best['name']}." if best else "No units."
    short = [c for c in checks if c.status == "warn"]
    if short:
        text += f" {len(short)} measure under 90% of their listed size."
    if any(not r["walls"] for r in rows):
        text += " Some units have no wall graph: their areas are Matterport room sizes and their doors and windows are not measured."
    return ToolResult(scope=ScansScope(sids=[r["sid"] for r in rows]), verdict=Verdict(status="warn" if short else "pass", text=text),
                      metrics=head + metrics, checks=checks, findings=findings)
