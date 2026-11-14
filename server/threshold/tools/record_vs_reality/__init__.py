"""Record versus reality: every checkable claim in a scan's CoStar or listing record beside what the data measures.

Each claim gets a verdict (confirmed, contradicted, cannot verify), a confidence and its evidence: the rooms counted,
a panorama crop, or an aerial crop. The scan's scope (home, unit, suite, floor, building) decides which claims it
can answer, so a unit's area is never set beside a building's. The cheap pass reads the plan and the record; the
deep pass adds the aerial photo and the panoramas. Modules: claims (what is said), measure (what the plan
measures), gather (aerial and panorama evidence), compare (verdicts), result (ToolResult).
"""
from __future__ import annotations

from pydantic import BaseModel

from .. import Action, Assumption, ToolError, ToolResult, field, tool
from . import claims as cl
from . import compare as cmp
from . import gather, measure, result


class Inputs(BaseModel):
    scan: str = field(source="selection.scan", description="Scan id")
    deep: bool = field(False, pref="truth.deep", description="Also read the aerial photo and the panoramas "
                                                            "(slower; uses the shared aerial and vision services)")
    area_low: float = field(cmp.DEFAULTS["area_low"], pref="truth.area_low", ge=0.5, le=1.0,
                            description="Lowest share of a listed area the measured interior area may be and still "
                                        "confirm it (interior area runs below a gross listed area)")
    area_high: float = field(cmp.DEFAULTS["area_high"], pref="truth.area_high", ge=1.0, le=1.5,
                             description="Highest share of a listed area the measured interior area may be")


def audit(plan: dict, rec: dict | None, *, deep: bool = False, params: dict | None = None, extra_claims=(),
          step=lambda s: None) -> dict:
    """The comparisons for one scan, and what they rest on. Shared by listing_claims and field_audit."""
    scan = cl.scan_scope(plan, rec)
    claims = cl.from_record(plan, rec) + list(extra_claims)
    step(f"Found {len(claims)} checkable claims; the scan covers {scan['scope']} ({scan['why']})")
    ev = gather.gather(plan, rec, scan, claims, aerial_on=deep, panos_on=deep)
    if deep:
        got = [k for k in ("site", "parking", "docks", "objects", "labels") if ev.get(k) is not None]
        errs = [ev[k] for k in ev if k.endswith("_error")]
        step("Read " + (", ".join(got) or "no extra evidence") + (f"; missing: {'; '.join(errs)}" if errs else ""))
    comps = cmp.compare(plan, scan, claims, ev, params)
    fa = measure.floor_area(plan)
    return {"scan": scan, "claims": claims, "comparisons": comps, "evidence": ev,
            "area_ft2": fa["ft2"] if fa["available"] else None}


@tool(id="record_vs_reality", title="Record versus reality", icon="scale",
      summary="Sets each fact in the CoStar or listing record beside what the scan and the aerial photo measure, "
              "with the evidence.",
      model_description="For one scan, compare every checkable claim in its CoStar property record or residential "
                        "listing (area, bedrooms, bathrooms, stories, ceiling height, parking, sprinklers, dock doors, "
                        "pool, listing feature sentences, the scan title) with what the plan, panoramas and aerial "
                        "photo measure. Returns one check and one finding per claim with a verdict: confirmed, "
                        "contradicted or cannot verify. Set deep=true to read the aerial photo and panoramas.",
      personas=["costar_researcher", "renter_listing", "insurance_underwriter", "apartment_manager"],
      requires=[{"layer": "costar.property"}, {"layer": "matterport.rooms"},
                {"layer": "matterport.room_labels", "need": "optional"},
                {"layer": "vexcel.ortho", "need": "optional", "fallback": "aerial claims cannot be verified"}],
      blocks=["VerdictHeader", "MetricRow", "CheckList", "EvidenceStrip", "FloorPlanMini", "AssumptionChips",
              "StepLog", "ActionBar"],
      overlays=["rule", "pins"], annotations={"cost": "slow"},
      examples=["Does this listing match the scan?", "Is the record's square footage right?",
                "How many parking spaces does it really have?"])
def run(ctx, inputs: Inputs) -> ToolResult:
    plan = ctx.plan(inputs.scan)
    rec = gather.record(inputs.scan)
    if rec is None and not cl.parse_title(plan.get("name")):
        raise ToolError(f"Scan {inputs.scan} has no CoStar or listing record and its title states nothing to check.")
    a = audit(plan, rec, deep=inputs.deep, params={"area_low": inputs.area_low, "area_high": inputs.area_high},
              step=ctx.step)
    comps = a["comparisons"]
    ctx.step(f"Compared {len(comps)} claims")
    assumptions = [
        Assumption(id="truth.area_low", label="Interior area may be this share of a listed area", value=inputs.area_low,
                   editable=True),
        Assumption(id="truth.area_high", label="and at most this share", value=inputs.area_high, editable=True),
        Assumption(id="interior_area", label="Measured area is interior floor area of walled rooms; garages, patios, "
                                             "balconies, basements and unbounded captures are left out", value=True),
        Assumption(id="half_bath", label="A bathroom smaller than this counts as half", value=measure.HALF_BATH_M2,
                   unit="m²"),
    ]
    actions = [Action(id="derived", label="Propose the fields this record lacks", tool="derived_fields",
                      inputs={"scan": inputs.scan})]
    if not inputs.deep:
        actions.insert(0, Action(id="deep", label="Check against the aerial photo and panoramas",
                                 tool="record_vs_reality", inputs={"scan": inputs.scan, "deep": True}))
    return result.build("record_vs_reality", inputs.scan, comps, a["scan"], a["area_ft2"], assumptions, actions)
