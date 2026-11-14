"""Roof facts: material, shape, condition, defects and their share of the roof, solar, roof objects, tree overhang and
height, from Vexcel's aerial facts, with the aerial crop and the capture date as evidence."""
from __future__ import annotations

from .. import Check, Finding, Metric, ToolResult, Verdict, field, tool
from .._site import (
    Where,
    capture,
    fact,
    facts,
    footprint,
    geo,
    locate,
    metric,
    ortho_media,
    pin,
    pins,
    src,
)

# Defects that mean water can already get in, against those that are wear.
SERIOUS = {"missing_material", "tarp", "structural_damage"}
WEAR = {"patch", "rust", "debris", "discoloration", "water_pooling", "algae_staining", "vent_staining",
        "vegetation_on_roof"}


class Inputs(Where):
    max_tree_cover_pct: float = field(25, pref="roof.max_tree_cover_pct", unit="%", ge=0, le=100,
                                      description="Tree cover over the roof above this is a warning")


def roof_metrics(s) -> list[Metric]:
    out = [metric(s, "roof_height", "Roof height above ground"), metric(s, "footprint_area", "Roof footprint"),
           metric(s, "roof_tree_cover", "Trees over the roof"), metric(s, "roof_condition", "Condition score")]
    for obj in ("ac_unit", "chimney", "roof_vent", "satellite_dish", "skylight"):
        out.append(metric(s, f"roof_{obj}", metric_id=f"objects.{obj}"))
    return [m for m in out if m]


def defects(s) -> list[tuple[str, float | None]]:
    """(defect id, % of roof) for every defect Vexcel reports; the discoloration subtypes replace the parent."""
    found = [(k[len("roof_defect_"):], x["value"]) for k, x in facts(s)["by_id"].items() if k.startswith("roof_defect_")]
    subs = {"water_pooling", "algae_staining", "vent_staining", "vegetation_on_roof"}
    if any(d in subs for d, _ in found):
        found = [(d, v) for d, v in found if d != "discoloration"]
    for d in fact(s, "roof_defects", []) or []:  # a defect detected without a share still counts
        d = d.replace("-", "_")
        if d not in {x for x, _ in found} and not (d == "discoloration" and any(x in subs for x, _ in found)):
            found.append((d, None))
    return sorted(found, key=lambda t: -(t[1] or 0))


@tool(id="roof_facts", title="Roof facts", icon="home",
      summary="Roof material, shape, condition, defects, solar, rooftop objects, trees over the roof and height, "
              "read from the aerial photo.",
      model_description="Roof of one building at a scan, a CoStar property or a lat/lon: Vexcel material, shape, "
                        "condition score, each defect with its share of the roof, solar, rooftop object counts, tree "
                        "cover over the roof and roof height, with the orthophoto and capture date. For insurers and "
                        "storm plans. Works for any address in Houston or Los Angeles.",
      personas=["commercial_underwriter", "insurance_underwriter", "houston_homeowner_storm", "costar_researcher"],
      requires=[{"layer": "vexcel.property"}, {"layer": "vexcel.ortho"}],
      blocks=["VerdictHeader", "MetricRow", "CheckList", "EvidenceStrip", "MiniChart", "AssumptionChips", "StepLog"],
      overlays=["pins"],
      examples=["What shape is this roof in?", "Is there damage on the roof?", "Does it have solar?"])
def run(ctx, inputs: Inputs) -> ToolResult:
    s = locate(ctx, inputs)
    f = facts(s)
    ctx.step(f"Read Vexcel's facts for the building nearest {s.lat:.5f}, {s.lon:.5f}: {len(f['facts'])} facts, "
             f"capture {capture(s)}")
    if not f["facts"] or fact(s, "roof_material") is None and fact(s, "footprint_area") is None:
        return ToolResult(scope=s.scope, verdict=Verdict(status="unknown",
                          text="Vexcel has no building at this point, so the roof cannot be read."))
    fp = footprint(s)
    c = fp.centroid if fp is not None else None
    at = geo(c.x, c.y) if c is not None else geo(s.lon, s.lat)
    photo = ortho_media(s, 120, fp)
    k = s.key
    findings, checks, ps = [], [], []

    material, shape = fact(s, "roof_material"), fact(s, "roof_shape")
    findings.append(Finding(id=f"roof_facts:{k}:type", title=f"Roof: {material or 'material unknown'}, {shape or 'shape unknown'}",
                            status="pass" if material else "unknown", anchor=at, source=src(s, "roof_material"),
                            detail=f"Material {material or 'not classified'}, shape {shape or 'not classified'}. "
                                   f"Imagery captured {capture(s)}.", media=[photo]))

    ds = defects(s)
    for d, share in ds:
        status = "fail" if d in SERIOUS else "warn"
        fid = f"roof_facts:{k}:defect:{d}"
        name = d.replace("_", " ")
        findings.append(Finding(id=fid, title=f"Roof defect: {name}", status=status, anchor=at, media=[photo],
                                source=src(s, f"roof_defect_{d}"),
                                detail=(f"Covers {share:.1f}% of the roof" if share is not None else "Share of the roof not given")
                                + f" (Vexcel model, capture {capture(s)}). Where on the roof is not given; check the photo."))
        checks.append(Check(id=f"defect.{d}", rule=f"No {name} on the roof", measured=share, threshold=0, unit="%",
                            status=status, findings=[fid]))
    if not ds and fact(s, "roof_defects") is not None:
        checks.append(Check(id="defects", rule="No roof defects detected", measured=0, threshold=0, unit="%", status="pass"))

    tree = fact(s, "roof_tree_cover")
    if tree is not None:
        st = "warn" if tree > inputs.max_tree_cover_pct else "pass"
        fid = f"roof_facts:{k}:trees"
        checks.append(Check(id="tree_cover", rule="Trees over the roof", measured=tree, unit="%",
                            threshold=inputs.max_tree_cover_pct, status=st, findings=[fid] if st != "pass" else []))
        if tree > 0:
            findings.append(Finding(id=fid, title="Trees overhang the roof", status=st, anchor=at, media=[photo],
                                    source=src(s, "roof_tree_cover"),
                                    detail=f"{tree:.0f}% of the roof is under tree canopy: limbs and debris in a storm."))

    solar = fact(s, "solar")
    if solar is not None:
        findings.append(Finding(id=f"roof_facts:{k}:solar", title="Solar panels on the roof" if solar else "No solar panels seen",
                                status="pass", anchor=at, source=src(s, "solar"), media=[photo],
                                detail=f"Vexcel solar class: {solar}."))

    ps.append(pin("roof", at.geo[0], at.geo[1], f"{material or 'roof'}, {shape or ''}".strip(", "),
                  "fail" if any(d in SERIOUS for d, _ in ds) else "warn" if ds else "pass"))
    serious = [d for d, _ in ds if d in SERIOUS]
    status = "fail" if serious else "warn" if ds else "pass" if material else "unknown"
    name = lambda xs: ", ".join(x.replace("_", " ") for x in xs)
    text = (f"{material or 'Unclassified'} {shape or ''} roof with {name(serious)}: needs an inspection." if serious else
            f"{material or 'Unclassified'} {shape or ''} roof with wear: {name(d for d, _ in ds)}." if ds else
            f"{material or 'Unclassified'} {shape or ''} roof, no defects detected.").replace("  ", " ")
    text += f" Imagery from {capture(s)}."
    ctx.step(f"{len(ds)} defects, tree cover {tree if tree is not None else 'unknown'}%")
    return ToolResult(scope=s.scope, verdict=Verdict(status=status, text=text), metrics=roof_metrics(s), checks=checks,
                      findings=findings, overlays=pins(ps),
                      assumptions=[{"id": "roof.max_tree_cover_pct", "label": "Warn above this tree cover",
                                    "value": inputs.max_tree_cover_pct, "unit": "%", "editable": True},
                                   {"id": "condition_scale", "label": "Vexcel does not publish its condition scale",
                                    "value": fact(s, "roof_condition")},
                                   {"id": "capture", "label": "Aerial capture", "value": capture(s)}])
