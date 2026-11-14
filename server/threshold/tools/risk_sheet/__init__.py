"""Risk sheet: one page for an insurance underwriter on one property. Roof, flood position (ground at the building
against the ground around it), wildfire defensible space where it matters, pool, trees over the roof and, where a
scan exists, interior hazards from the panoramas, each with evidence and confidence. Also written as a printable
HTML page under $THRESHOLD_DATA_DIR/media/sheets/ and served at /api/site/sheet/<name>.html (api/site_media.py)."""
from __future__ import annotations

import html
import statistics

from .. import Check, Finding, Metric, Source, ToolResult, Verdict, field, tool
from .._site import (
    Where,
    capture,
    fact,
    footprint,
    geo,
    heights,
    locate,
    metric,
    ortho_media,
    pin,
    pins,
    src,
    to_m,
)
from ..registry import ToolContext
from ..roof_facts import Inputs as RoofInputs
from ..roof_facts import run as roof_run

RINGS_M = (50, 100, 200)
LOW_M = 0.5            # ground this far below the median around it collects water
HAZARDS = ["smoke alarm", "fire extinguisher", "sprinkler head", "electrical panel", "water heater", "gas stove",
           "kitchen hood", "outlet near the floor"]
DTM = Source(layer="vexcel", method="geometry", confidence="medium",
             note="Vexcel bare-ground model (DTM) at the building and at 16 points on each ring; relative heights only, "
                  "no flood map, drainage or floor height above grade")


class Inputs(Where):
    use_vision: bool = field(True, description="Read interior hazards from the panoramas (cached)")
    max_panos: int = field(5, ge=1, le=12, description="Panoramas to read for interior hazards")


def flood_position(s, c) -> dict:
    """Ground at the building against the median ground on rings around it."""
    import math
    fwd, back = to_m(s.lat)
    cx, cy = fwd(c.x, c.y)
    pts = [(c.x, c.y)] + [back(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a)))
                          for r in RINGS_M for a in range(0, 360, 360 // 16)]
    zs = heights("dtm", pts)
    here, rest = zs[0], zs[1:]
    rings = {r: statistics.median(rest[i * 16:(i + 1) * 16]) for i, r in enumerate(RINGS_M)}
    below = sum(z > here for z in rest) / len(rest)
    return {"ground_m": round(here, 2), "rings": {r: round(z, 2) for r, z in rings.items()},
            "relative_m": round(here - statistics.median(rest), 2), "share_higher": round(100 * below)}


def interior(ctx, sid: str, n: int) -> list[dict]:
    from ...vision.reader import find_objects
    return find_objects(ctx.plan(sid), labels=HAZARDS, max_panos=n)


def sheet_html(title: str, verdict: Verdict, rows: list[tuple[str, str, str, str]], s, img: str) -> str:
    esc = html.escape
    tr = "".join(f"<tr class='{esc(st)}'><th>{esc(a)}</th><td>{esc(b)}</td><td class='st'>{esc(st)}</td><td class='src'>{esc(c)}</td></tr>"
                 for a, b, c, st in rows)
    return f"""<!doctype html><html lang="en"><meta charset="utf-8"><title>{esc(title)}</title>
<style>
@page {{ size: letter; margin: 14mm }}
body {{ font: 10.5pt/1.4 Georgia, 'Times New Roman', serif; color: #1d1d1b; background: #fbfaf7; max-width: 7.6in; margin: 0 auto; padding: 16px }}
h1 {{ font: 600 17pt/1.2 Georgia, serif; margin: 0 0 2px }} .addr {{ color: #5c5a55; margin-bottom: 10px }}
.verdict {{ border-left: 4px solid #8a8577; padding: 6px 10px; background: #f1efe9; margin: 8px 0 12px }}
.verdict.fail {{ border-color: #b3261e }} .verdict.warn {{ border-color: #b8860b }} .verdict.pass {{ border-color: #2e7d32 }}
img {{ width: 100%; max-height: 3.4in; object-fit: cover; border: 1px solid #d8d4ca }}
table {{ width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 9.5pt }}
th, td {{ text-align: left; vertical-align: top; padding: 5px 6px; border-bottom: 1px solid #e3dfd5 }}
th {{ width: 22%; font-weight: 600 }} td.st {{ width: 8%; text-transform: uppercase; font: 600 8pt/1.4 system-ui, sans-serif }}
tr.fail td.st {{ color: #b3261e }} tr.warn td.st {{ color: #8a6400 }} tr.pass td.st {{ color: #2e7d32 }} tr.unknown td.st {{ color: #6b6b6b }}
td.src {{ width: 30%; color: #6b675f; font-size: 8.5pt }} footer {{ margin-top: 12px; color: #6b675f; font-size: 8.5pt }}
</style>
<h1>Property risk sheet</h1><div class="addr">{esc(s.address or f"{s.lat:.5f}, {s.lon:.5f}")}{f" · scan {esc(s.sid)}" if s.sid else ""}</div>
<div class="verdict {esc(verdict.status)}">{esc(verdict.text)}</div>
<img src="{esc(img)}" alt="Aerial photo of the property, captured {esc(capture(s))}">
<table><tbody>{tr}</tbody></table>
<footer>Aerial facts: Vexcel, capture {esc(capture(s))}; Vexcel publishes no accuracy figures for its model outputs.
Interior items: vision model on the scan's panoramas. Every row names its source and confidence; nothing here replaces an
inspection.</footer></html>"""


@tool(id="risk_sheet", title="Risk sheet", icon="clipboard",
      summary="One printable page for an underwriter: roof, flood position, wildfire space, pool, trees and interior "
              "hazards, each with its evidence and confidence.",
      model_description="For one property at a scan, a CoStar id or a lat/lon in Houston or Los Angeles: runs roof_facts, "
                        "compares the ground at the building with rings 50 to 200 m around it (Vexcel DTM), reads "
                        "defensible-space tree cover (Los Angeles), pool and enclosure, trees over the roof, and with a scan "
                        "reads interior hazards (smoke alarms, extinguishers, panels, water heaters, stoves) from the "
                        "panoramas. Returns checks and findings and a printable HTML sheet at /api/site/sheet/<name>.html.",
      personas=["commercial_underwriter", "insurance_underwriter", "houston_homeowner_storm"],
      requires=[{"layer": "vexcel.property"}, {"layer": "vexcel.dtm"}, {"layer": "matterport.panos", "need": "optional"}],
      blocks=["VerdictHeader", "MetricRow", "CheckList", "EvidenceStrip", "StepLog", "ActionBar"],
      overlays=["pins"], annotations={"cost": "slow"},
      examples=["Give me a risk summary of this house", "Should I send an inspector to this property?"])
def run(ctx, inputs: Inputs) -> ToolResult:
    s = locate(ctx, inputs)
    k = s.key
    roof = roof_run(ToolContext(plans=ctx.plans), RoofInputs(scan=inputs.scan, property_id=inputs.property_id, lat=inputs.lat,
                                                             lon=inputs.lon))
    ctx.step(f"Roof: {roof.verdict.text}")
    if roof.verdict.status == "unknown" and not fact(s, "footprint_area"):
        return ToolResult(scope=s.scope, verdict=Verdict(status="unknown", text="Vexcel has no building here to assess."))
    fp = footprint(s)
    c = fp.centroid if fp is not None else None
    at = geo(c.x, c.y) if c is not None else geo(s.lon, s.lat)
    photo = ortho_media(s, 120, fp)
    findings = [f.model_copy(update={"id": f.id.replace("roof_facts:", "risk_sheet:")}) for f in roof.findings]
    checks = [ch.model_copy(update={"id": f"roof.{ch.id}", "findings": [x.replace("roof_facts:", "risk_sheet:") for x in ch.findings]})
              for ch in roof.checks]
    metrics = [m for m in roof.metrics if m.id in ("roof_height", "roof_condition", "roof_tree_cover")]
    rows = [("Roof", roof.verdict.text, "; ".join(sorted({f"{x.source.layer} {x.source.confidence}" for x in roof.findings})) or "Vexcel",
             roof.verdict.status)]

    # flood position
    try:
        fl = flood_position(s, c or type("P", (), {"x": s.lon, "y": s.lat})())
        st = "warn" if fl["relative_m"] <= -LOW_M else "pass"
        fid = f"risk_sheet:{k}:flood"
        checks.append(Check(id="flood_position", rule="Ground at the building not below the ground around it",
                            measured=fl["relative_m"], threshold=-LOW_M, unit="m", status=st, findings=[fid]))
        metrics.append(Metric(id="ground_relative", label="Ground against the surroundings", value=fl["relative_m"], unit="m", source=DTM))
        for r, z in fl["rings"].items():
            metrics.append(Metric(id=f"rings.{r}", label=f"Median ground at {r} m", value=round(z - fl["ground_m"], 2), unit="m", source=DTM))
        txt = (f"The ground at the building is {abs(fl['relative_m']):.1f} m {'below' if fl['relative_m'] < 0 else 'above'} the median "
               f"ground within {RINGS_M[-1]} m; {fl['share_higher']}% of the points around it are higher.")
        findings.append(Finding(id=fid, title="Flood position", status=st, anchor=at, source=DTM, media=[ortho_media(s, 420)],
                                detail=txt + " Relative height only: no flood map, drainage or floor height."))
        rows.append(("Flood position", txt, DTM.note.split(";")[0] + ", medium", st))
        ctx.step(f"Flood position: {fl['relative_m']:+.2f} m against the median around it")
    except Exception as e:  # noqa: BLE001  the sheet stands without this row
        rows.append(("Flood position", f"Not read: {str(e)[:80]}", "Vexcel DTM", "unknown"))

    # wildfire defensible space: Los Angeles, or wherever Vexcel reports trees close to the building
    z1, z2 = fact(s, "defensible_zone1_tree"), fact(s, "defensible_zone2_tree")
    if s.state == "CA" or (z1 or 0) > 0:
        st = "unknown" if z1 is None else "fail" if z1 > 10 else "warn" if (z2 or 0) > 30 else "pass"
        fid = f"risk_sheet:{k}:wildfire"
        checks.append(Check(id="defensible_space", rule="Tree cover within 5 ft of the building", measured=z1, threshold=10,
                            unit="%", status=st, standard="Defensible space zone 0 (0 to 5 ft)", findings=[fid]))
        txt = f"Tree cover {z1 if z1 is not None else '?'}% within 5 ft and {z2 if z2 is not None else '?'}% within 30 ft of the building."
        findings.append(Finding(id=fid, title="Wildfire defensible space", status=st, anchor=at, source=src(s, "defensible_zone1_tree"),
                                media=[photo], detail=txt))
        rows.append(("Wildfire space", txt, "Vexcel defensible-space zones, medium", st))
    for mid in ("defensible_zone1_tree", "defensible_zone2_tree"):
        m = metric(s, mid, metric_id=f"defensible.{mid.split("_")[1]}")
        if m:
            metrics.append(m)

    # pool
    pool = fact(s, "pool")
    if pool is not None:
        enc = sum(fact(s, f"pool_{t}_enclosed", 0) or 0 for t in ("in_ground", "above_ground", "hot_tub"))
        st = "pass" if not pool else "pass" if enc else "warn"
        txt = "No pool." if not pool else f"Pool on the parcel, {'enclosed' if enc else 'not enclosed'} per Vexcel."
        findings.append(Finding(id=f"risk_sheet:{k}:pool", title="Pool", status=st, anchor=at, source=src(s, "pool"), media=[photo],
                                detail=txt + (" Run path_to_water for the routes from the bedrooms." if pool and s.sid else "")))
        rows.append(("Pool", txt, "Vexcel pool facts, medium", st))

    tree = fact(s, "roof_tree_cover")
    if tree is not None:
        rows.append(("Trees over the roof", f"{tree:.0f}% of the roof under canopy.", "Vexcel, medium", "warn" if tree > 25 else "pass"))

    # inside
    if s.sid and inputs.use_vision:
        try:
            found = interior(ctx, s.sid, inputs.max_panos)
            counts = {h: sum(f["label"] == h for f in found) for h in HAZARDS}
            ctx.step("Inside: " + ", ".join(f"{v} {h}" for h, v in counts.items() if v))
            for f in found:
                findings.append(Finding.model_validate({**f["finding"], "id": f"risk_sheet:{k}:inside:{f['finding']['id']}",
                                                        "title": f"Inside: {f['label']}"}))
            alarms = counts["smoke alarm"]
            st = "pass" if alarms else "warn"
            checks.append(Check(id="smoke_alarms", rule=f"Smoke alarms seen in {inputs.max_panos} rooms read", measured=alarms,
                                threshold=1, unit="", status=st))
            for h, v in counts.items():
                metrics.append(Metric(id=f"inside.{h.replace(' ', '_')}", label=h.capitalize(), value=v, unit="",
                                      source=Source(layer="model", method="vision", confidence="low",
                                                    note=f"Vision model on {inputs.max_panos} panoramas; absence is not proof")))
            rows.append(("Inside", ", ".join(f"{v} {h}{'s' if v != 1 else ''}" for h, v in counts.items() if v) or "Nothing on the list seen",
                         f"Vision model, {inputs.max_panos} panoramas, low", st))
        except Exception as e:  # noqa: BLE001
            rows.append(("Inside", f"Not read: {str(e)[:80]}", "panoramas", "unknown"))
    elif not s.sid:
        rows.append(("Inside", "No scan of this property, so the inside is not assessed.", "", "unknown"))

    bad = [r for r in rows if r[3] == "fail"]
    warn = [r for r in rows if r[3] == "warn"]
    status = "fail" if bad else "warn" if warn else "pass"
    text = ("Send an inspector: " + "; ".join(r[0].lower() for r in bad) + "." if bad else
            "Quote with conditions; look at " + ", ".join(r[0].lower() for r in warn) + "." if warn else
            "Nothing from the air or the panoramas asks for an inspection.")
    verdict = Verdict(status=status, text=text)
    name = f"risk_sheet-{k}".replace(",", "_")
    from ...api.site_media import SHEETS
    SHEETS.mkdir(parents=True, exist_ok=True)
    (SHEETS / f"{name}.html").write_text(sheet_html("Risk sheet", verdict, rows, s, f"/api/aerial/ortho?lat={s.lat:.7f}&lon={s.lon:.7f}&size_m=90&px=1024"))
    findings.insert(0, Finding(id=f"risk_sheet:{k}:sheet", title="Printable risk sheet", status=status, anchor=at,
                               source=Source(layer="model", method="lookup", confidence="high", note="Built from the rows below"),
                               detail=f"/api/site/sheet/{name}.html"))
    return ToolResult(scope=s.scope, verdict=verdict, metrics=metrics, checks=checks, findings=findings,
                      overlays=pins([pin("property", at.geo[0], at.geo[1], "property", status)]),
                      assumptions=[{"id": "capture", "label": "Aerial capture", "value": capture(s)},
                                   {"id": "flood", "label": "Flood row is relative ground height, not a flood map", "value": True}],
                      actions=[{"id": "pool", "label": "Trace paths to the pool", "tool": "path_to_water",
                                "inputs": {"scan": s.sid}}] if pool and s.sid else [])
