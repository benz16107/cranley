"""Property coverage: which floor plans and common areas of a property have a scan, and which no scan covers.

Runs on a place (a CoStar property, or a scan or address that resolves to one), not on one scan. A floor plan counts
as covered when a scan is attached to it in the CoStar record (high confidence) or when a scan's name gives the same
bedrooms and bathrooms (medium). A common area counts as covered when a scan's name names it. "No scan" never means
the space does not exist.
"""
from __future__ import annotations

import re

from pydantic import BaseModel

from .. import Check, Finding, GeoAnchor, Metric, NotApplicable, Place, Source, ToolResult, Verdict, field, tool

RECORD = Source(layer="costar", method="lookup", confidence="high", note="Floor plans from the CoStar property record")
NAMES = Source(layer="matterport", method="lookup", confidence="medium", note="Matched on scan names")
AREAS = {
    "lobby": r"lobby|entrance|leasing|reception|front desk",
    "fitness": r"fitness|gym\b|yoga|cycle|spin",
    "pool": r"\bpool\b|spa\b|hot tub",
    "laundry": r"laundry|wash",
    "lounge": r"lounge|club|resident|game room|theat|cinema|business center|cowork|conference",
    "mail": r"mail|package",
    "outdoor": r"courtyard|terrace|rooftop|roof deck|patio|grill|dog|park",
    "parking": r"parking|garage",
}
BED = re.compile(r"(\d+(?:\.\d)?)\s*(?:br|bd|bed)", re.I)
BATH = re.compile(r"(\d+(?:\.\d)?)\s*(?:ba|bath)", re.I)


class Inputs(BaseModel):
    place: Place = field(source="selection.place")


def _attached(model: dict) -> set[str]:
    keys = {a.get("videoKey") for a in model.get("attachments") or []}
    keys |= {a.get("videoKey") for u in model.get("units") or [] for a in u.get("attachments") or []}
    return {k for k in keys if k}


def _beds_baths(name: str) -> tuple[float | None, float | None]:
    if re.search(r"studio|bachelor", name, re.I):
        b = BATH.search(name)
        return 0, float(b.group(1)) if b else None
    b, ba = BED.search(name), BATH.search(name)
    return (float(b.group(1)) if b else None), (float(ba.group(1)) if ba else None)


@tool(id="property_coverage", title="Property coverage",
      summary="For whoever manages or researches a whole property: which of its floor plans and shared spaces have "
              "a scan, and which none covers.",
      model_description="For one property (place with property_id), list its floor plans and common areas and which "
                        "have a scan. Use before or after investigating a whole property, to say what no scan covers.",
      requires=[{"layer": "costar.property"}, {"layer": "matterport.index"}],
      blocks=["VerdictHeader", "MetricRow", "CheckList", "StepLog"], personas=["apartment_manager", "costar_researcher"])
def run(ctx, inputs: Inputs) -> ToolResult:
    site = ctx.site(inputs.place)
    scans = site.scans
    ctx.step(f"Found {len(scans)} scans at {site.address or site.key}")
    if site.record and not (site.record.get("propertyApartment") or {}):
        raise NotApplicable("The CoStar record is not an apartment community, so there are no floor plans or shared "
                            "spaces to check scans against.")
    if scans and not site.record:
        raise NotApplicable(f"There is no CoStar property record for this place, so there is no list of floor plans or "
                            f"shared spaces to hold its {len(scans)} scan{'s' if len(scans) > 1 else ''} against.")
    apt = ((site.record or {}).get("propertyApartment") or {})
    models = apt.get("models") or []
    checks, covered_sids = [], set()
    for m in models:
        attached = _attached(m) & set(site.sids)
        named = {s["sid"] for s in scans if s["kind"] == "apartment_unit" and m.get("numBeds") is not None
                 and _beds_baths(s["name"] or "") == (float(m["numBeds"]), float(m["numBaths"]) if m.get("numBaths") else None)}
        hit = attached or named
        covered_sids |= hit
        label = m.get("modelName") or f"{m.get('numBeds')} bed, {m.get('numBaths')} bath"
        checks.append(Check(id=f"plan.{m.get('id')}", rule=f"Floor plan {label}", measured=len(hit), threshold=1, unit="scans",
                            status="pass" if hit else "unknown",
                            standard=None if hit else "No scan of this floor plan"))
    ctx.step(f"Matched scans to {sum(c.status == 'pass' for c in checks)} of {len(models)} floor plans")
    for area, pattern in AREAS.items():
        hit = {s["sid"] for s in scans if re.search(pattern, s["name"] or "", re.I)}
        checks.append(Check(id=f"area.{area}", rule=f"Shared space: {area}", measured=len(hit), threshold=1, unit="scans",
                            status="pass" if hit else "unknown",
                            standard=None if hit else "No scan names this space; it may still exist"))
    plans_done = sum(c.status == "pass" for c in checks if c.id.startswith("plan."))
    areas_done = sum(c.status == "pass" for c in checks if c.id.startswith("area."))
    units = sum(s["kind"] == "apartment_unit" for s in scans)
    gaps = [c for c in checks if c.status == "unknown"]
    anchor = GeoAnchor(geo=(site.lon, site.lat)) if site.lat is not None and site.lon is not None else None
    findings = [Finding(id=f"property_coverage:{site.key}:{c.id}", title=f"No scan: {c.rule.split(': ', 1)[-1].removeprefix('Floor plan ')}",
                        status="unknown", detail=c.standard or "", anchor=anchor, source=RECORD if c.id.startswith("plan.") else NAMES)
                for c in gaps]
    for f, c in zip(findings, gaps):
        c.findings = [f.id]
    text = (f"{plans_done} of {len(models)} floor plans and {areas_done} of {len(AREAS)} kinds of shared space have a scan."
            if models else f"The record lists no floor plans; {areas_done} of {len(AREAS)} kinds of shared space have a scan.")
    if not scans:
        text = "No scans at this place."
    return ToolResult(
        scope=site.scope(),
        verdict=Verdict(status="unknown" if not scans else "warn" if gaps else "pass", text=text),
        metrics=[Metric(id="scans", label="Scans", value=len(scans), unit="", source=NAMES),
                 Metric(id="unit_scans", label="Unit scans", value=units, unit="", source=NAMES),
                 Metric(id="floor_plans", label="Floor plans in the record", value=len(models), unit="", source=RECORD),
                 Metric(id="floor_plans_scanned", label="Floor plans with a scan", value=plans_done, unit="", source=RECORD)],
        checks=sorted(checks, key=lambda c: c.status != "unknown"), findings=findings)
