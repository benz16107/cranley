"""Parking count: marked stalls counted from above by the vision model on orthophoto tiles (whole-row boxes split
into stalls or dropped), cross-checked by Vexcel detection: its lot outlines give a capacity estimate and its cars a
floor. Accessible stalls where the model sees them, vehicles on capture day, beside the CoStar record's spaces and
ratio. Vexcel's SAM 3 boxes whole lots for "parking space", not stalls (seen 2026-11-13 at three lots, four tile sizes).
"""
from __future__ import annotations

from shapely import wkt as shapely_wkt
from shapely.geometry import Point, box
from shapely.ops import unary_union

from ...aerial import detect as aerial_detect
from .. import Check, Finding, Metric, Source, ToolResult, Verdict, field, tool
from .._site import (
    FT2_PER_M2,
    Where,
    capture,
    fact,
    footprint,
    geo,
    locate,
    metres,
    ortho_media,
    parcel,
    pin,
    pins,
    property_record,
    record_claims,
    record_source,
    src,
    to_m,
)

STALL_M = (2.7, 5.5)      # a typical US stall, width by depth
SINGLE_MAX_M2 = 30.0      # the engine's cap for one stall
ROW_DEPTH_M = (3.5, 7.5)  # a box this deep and at least twice as long is a row of stalls side by side
TILE_M = 90.0             # 1024 px over 90 m is 9 cm a pixel: stripes are about one pixel wide
MAX_TILES = 6
M2_PER_STALL = 30.0       # a stall plus its share of the aisle, about 320 ft2: the usual surface-lot planning figure
EST = Source(layer="vexcel", method="geometry", confidence="low",
             note="Area of the lots Vexcel's detector outlines on the parcel, less the building, over 30 m2 per stall "
                  "(stall plus aisle share); the boxes are axis-aligned, so landscaping inside them counts too")

class Inputs(Where):
    use_vision: bool = field(True, description="Cross-check the count with the vision model (cached)")
    agree_pct: float = field(15, pref="parking.agree_pct", unit="%", ge=1, le=100,
                             description="Counts within this share of the record agree")


def stalls_from(dets: list[dict], area_m, lat0: float) -> dict:
    """Stall boxes in metres from parking-space detections: singles kept, one-deep rows split, the rest dropped.
    Only boxes whose centre is inside `area_m` (the parcel) count."""
    fwd = to_m(lat0)[0]
    singles, rows, dropped = [], [], []
    for d in dets:
        if d["label"] != "parking space" or d["image"] != "spherical-ortho":
            continue
        g = metres(shapely_wkt.loads(d["polygon"]), lat0)
        if area_m is not None and not area_m.contains(g.centroid):
            continue
        x0, y0, x1, y1 = g.bounds
        w, h = x1 - x0, y1 - y0
        if w * h <= SINGLE_MAX_M2:
            singles.append({"box": g, "n": 1, "det": d})
            continue
        short, long_ = min(w, h), max(w, h)
        if ROW_DEPTH_M[0] <= short <= ROW_DEPTH_M[1] and long_ >= 2 * short:
            n = max(2, round(long_ / STALL_M[0]))
            rows.append({"box": g, "n": n, "det": d})
        else:
            dropped.append({"box": g, "det": d})
    # a single inside a row is the same stall twice
    singles = [s for s in singles if not any(r["box"].contains(s["box"].centroid) for r in rows)]
    # overlapping singles (two boxes on one stall)
    kept = []
    rank = {"high": 0.9, "medium": 0.6, "low": 0.3}  # the vision model gives classes, Vexcel numbers
    for s in sorted(singles, key=lambda s: -rank.get(s["det"]["confidence"], s["det"]["confidence"])):
        if any(k["box"].intersection(s["box"]).area > 0.5 * min(k["box"].area, s["box"].area) for k in kept):
            continue
        kept.append(s)
    return {"singles": kept, "rows": rows, "dropped": dropped,
            "count": len(kept) + sum(r["n"] for r in rows), "back": to_m(lat0)[1], "fwd": fwd}


def inside(dets: list[dict], label: str, area_m, lat0: float, image: str = "spherical-ortho") -> list[dict]:
    fwd = to_m(lat0)[0]
    return [d for d in dets if d["label"] == label and d["image"] in (image, "ortho")
            and (area_m is None or area_m.contains(Point(fwd(*d["anchor"]["geo"]))))]


def pick_tiles(area_m, lots: list, cars: list[dict], lat0: float) -> list[tuple[float, float]]:
    """Tile centres (metres) over the parcel, keeping tiles that touch a lot or hold two or more cars, busiest first."""
    fwd = to_m(lat0)[0]
    car_pts = [Point(fwd(*d["anchor"]["geo"])) for d in cars]
    x0, y0, x1, y1 = area_m.bounds
    out = []
    y = y0 + TILE_M / 2
    while y - TILE_M / 2 < y1:
        x = x0 + TILE_M / 2
        while x - TILE_M / 2 < x1:
            cell = box(x - TILE_M / 2, y - TILE_M / 2, x + TILE_M / 2, y + TILE_M / 2)
            if cell.intersects(area_m):
                n = sum(cell.contains(p) for p in car_pts)
                lot = sum(cell.intersection(g).area for g in lots)
                if n >= 2 or lot > 200:
                    out.append((n + lot / 30, (x, y)))
            x += TILE_M
        y += TILE_M
    return [c for _, c in sorted(out, reverse=True)]


def agree(a, b, pct: float) -> str:
    if a is None or b in (None, 0):
        return "unknown"
    return "pass" if abs(a - b) <= max(2, b * pct / 100) else "warn"


@tool(id="parking_count", title="Parking count", icon="car",
      summary="Counts parking stalls and parked cars from the aerial photo and compares them with the record.",
      model_description="For any address in Houston or Los Angeles: parking stalls on the parcel counted on the Vexcel "
                        "orthophoto by the vision model on 90 m tiles (whole-row boxes split into stalls), cross-checked against "
                        "the lot area Vexcel's detector outlines and the cars it counts, accessible stalls where visible, vehicles on capture day and occupancy, beside the CoStar "
                        "record's parking spaces and ratio. Surface lots only: garages and stalls under trees are invisible.",
      personas=["commercial_underwriter", "apartment_manager", "costar_researcher", "office_tenant", "truck_dispatcher"],
      requires=[{"layer": "vexcel.ortho"}, {"layer": "vexcel.property"}, {"layer": "costar.property", "need": "optional"}],
      blocks=["VerdictHeader", "MetricRow", "CheckList", "EvidenceStrip", "AssumptionChips", "StepLog"],
      overlays=["pins"], annotations={"cost": "slow"},
      examples=["How many parking spaces does this property have?", "Is the lot full?"])
def run(ctx, inputs: Inputs) -> ToolResult:
    s = locate(ctx, inputs)
    pc, fp = parcel(s), footprint(s)
    lat0 = s.lat
    area = pc if pc is not None else (fp.buffer(0.0008) if fp is not None else None)
    if area is None:
        return ToolResult(scope=s.scope, verdict=Verdict(status="unknown",
                          text="Vexcel has no parcel or building here, so the lot cannot be bounded."))
    area_m = metres(area, lat0).buffer(3)
    c = area.centroid
    x0, y0, x1, y1 = area_m.bounds
    size = min(300.0, max(60.0, max(x1 - x0, y1 - y0) + 10))
    clipped = size < max(x1 - x0, y1 - y0)
    if clipped:  # the detection square cannot cover the whole parcel: count only what it covers
        cx, cy = to_m(lat0)[0](c.x, c.y)
        area_m = area_m.intersection(box(cx - size / 2, cy - size / 2, cx + size / 2, cy + size / 2))
    ctx.step(f"Parcel {metres(area, lat0).area:.0f} m2; detecting over {size:.0f} m" + (" (parcel clipped)" if clipped else ""))
    det = aerial_detect.detect(c.y, c.x, size, ["parking space", "car"], threshold=0.3, keep_large=True)
    cars = inside(det["detections"], "car", area_m, lat0)
    lots = [metres(shapely_wkt.loads(d["polygon"]), lat0).intersection(area_m) for d in det["detections"]
            if d["label"] == "parking space" and d["image"] == "spherical-ortho"]
    lots = [g for g in lots if g.area > SINGLE_MAX_M2]
    lot_area = unary_union(lots).difference(metres(fp, lat0)).area if lots and fp is not None else \
        (unary_union(lots).area if lots else 0.0)
    ctx.step(f"Vexcel: {len(cars)} cars, {len(lots)} lot areas totalling {lot_area:.0f} m2 (its detector boxes whole lots, "
             "not stalls)")
    st = {"singles": [], "rows": [], "dropped": [], "count": 0, "back": to_m(lat0)[1]}
    tiles, candidates, vis_dets = [], [], []
    if inputs.use_vision:
        candidates = pick_tiles(area_m, lots, cars, lat0)
        tiles = candidates[:MAX_TILES]
        ctx.step(f"Reading {len(tiles)} of {len(candidates)} lot tiles of {TILE_M:.0f} m with the vision model")
        for tx, ty in tiles:
            lo, la = to_m(lat0)[1](tx, ty)
            try:
                r = aerial_detect.detect(la, lo, TILE_M, ["parking space", "accessible parking space"], method="vision")
            except Exception as e:  # noqa: BLE001  a missing tile lowers the count; the step log says so
                ctx.step(f"Tile skipped: {str(e)[:120]}")
                continue
            cell = box(tx - TILE_M / 2, ty - TILE_M / 2, tx + TILE_M / 2, ty + TILE_M / 2)
            fwd = to_m(lat0)[0]
            vis_dets += [d for d in r["detections"] if cell.contains(Point(fwd(*d["anchor"]["geo"])))]
        st = stalls_from([{**d, "label": "parking space", "image": "spherical-ortho"} for d in vis_dets], area_m, lat0)
        ctx.step(f"Vision: {len(st['singles'])} stalls, {len(st['rows'])} rows split into {sum(r['n'] for r in st['rows'])}, "
                 f"{len(st['dropped'])} large boxes dropped")
    v_access = [d for d in vis_dets if d["label"] == "accessible parking space"]
    estimate = round(lot_area / M2_PER_STALL) if lot_area else None
    vsrc = Source(layer="model", method="vision", confidence="low",
                  note=f"Vision model boxing stalls on {len(tiles)} orthophoto tiles of {TILE_M:.0f} m; boxes over 30 m2 split "
                       "into 2.7 m stalls when one row deep, else dropped")
    rec = record_claims(property_record(s.property_id))
    rec_spaces = (rec.get("car_spaces") or {}).get("value")
    ratio = (rec.get("parking_ratio") or {}).get("value")
    rba = (rec.get("rentable_area") or {}).get("value")
    k = s.key
    n = st["count"]
    metrics = [Metric(id="stalls", label="Marked stalls counted from above", value=n if inputs.use_vision else None, unit="",
                      source=vsrc),
               Metric(id="lot_estimate", label="Stalls the paved lot could hold", value=estimate, unit="", source=EST),
               Metric(id="cars", label="Cars on capture day", value=len(cars), unit="",
                      source=Source(layer="vexcel", method="vision", confidence="medium", note=f"Vexcel SAM 3 'car', capture {capture(s)}")),
               Metric(id="occupancy", label="Stalls occupied on capture day", value=round(100 * len(cars) / n) if n else None,
                      unit="%", source=vsrc)]
    vf = fact(s, "vehicles")
    if vf is not None:
        metrics.append(Metric(id="vehicles_vexcel", label="Vehicles (Vexcel parcel fact)", value=vf, unit="", source=src(s, "vehicles")))
    if inputs.use_vision:
        metrics.append(Metric(id="accessible", label="Accessible stalls seen", value=len(v_access), unit="", source=vsrc))
    if rec_spaces is not None:
        metrics.append(Metric(id="record_spaces", label="Spaces in the record", value=rec_spaces, unit="",
                              source=record_source(rec["car_spaces"]["path"], s.property_id)))
    if ratio is not None:
        metrics.append(Metric(id="record_ratio", label="Record ratio", value=ratio, unit="per 1,000 ft2",
                              source=record_source(rec["parking_ratio"]["path"], s.property_id)))
        if rba and n:
            metrics.append(Metric(id="measured_ratio", label="Counted ratio", value=round(n / (rba / 1000), 2),
                                  unit="per 1,000 ft2", source=vsrc))

    checks, findings = [], []
    photo = ortho_media(s, size)
    if rec_spaces is not None:
        st_ = agree(n, rec_spaces, inputs.agree_pct)
        fid = f"parking_count:{k}:record"
        checks.append(Check(id="record", rule="Stalls counted match the record", measured=n, threshold=rec_spaces, unit="stalls",
                            status=st_, findings=[fid]))
        findings.append(Finding(id=fid, title="Record versus the aerial count", status=st_, anchor=geo(c.x, c.y), media=[photo],
                                source=record_source(rec["car_spaces"]["path"], s.property_id),
                                detail=f"Record {rec_spaces} spaces; counted {n} on the surface lot. Garages, carports and stalls "
                                       "under trees cannot be seen from above, so a lower count is expected where they exist."))
    if inputs.use_vision and estimate:
        st_ = agree(n, estimate, 30)
        checks.append(Check(id="estimate", rule="Stalls counted match what the paved lot could hold", measured=n,
                            threshold=estimate, unit="stalls", status=st_))
    if inputs.use_vision and len(cars) > n:
        checks.append(Check(id="cars_fit", rule="At least as many stalls as cars parked", measured=n, threshold=len(cars),
                            unit="stalls", status="warn"))
    if st["dropped"]:
        findings.append(Finding(id=f"parking_count:{k}:dropped", title="Large boxes left out of the count", status="unknown",
                                anchor=geo(c.x, c.y), source=vsrc, media=[photo],
                                detail=f"{len(st['dropped'])} detections covered a whole lot or a double row and could not be "
                                       "split into stalls safely, so the count may be low there."))
    for i, d in enumerate(v_access):
        findings.append(Finding(id=f"parking_count:{k}:accessible:{i + 1}", title="Accessible stall", status="pass",
                                anchor=geo(*d["anchor"]["geo"]), source=vsrc, media=[photo],
                                detail="Seen by the vision model on the orthophoto (blue paint or the symbol)."))
    ps = []
    back = st["back"]
    for i, s_ in enumerate(st["singles"][:400]):
        p = s_["box"].centroid
        ps.append(pin(f"stall_{i}", *back(p.x, p.y), "", "pass"))
    for i, r in enumerate(st["rows"]):
        p = r["box"].centroid
        ps.append(pin(f"row_{i}", *back(p.x, p.y), f"row of {r['n']}", "pass"))
    for i, d in enumerate(v_access):
        ps.append(pin(f"accessible_{i}", *d["anchor"]["geo"], "accessible", "pass"))
    if not n:
        status = "unknown"
        text = (f"No marked stalls could be counted; {len(cars)} cars were parked on {capture(s)}"
                + (f" and the paved lot could hold about {estimate}" if estimate else "")
                + (f"; the record says {rec_spaces}." if rec_spaces is not None else "."))
    else:
        status = "warn" if any(ch.status == "warn" for ch in checks) else "pass"
        part = f" on {len(tiles)} of {len(candidates)} lot tiles (the busiest)" if len(candidates) > len(tiles) else ""
        text = (f"About {n} marked stalls counted from above{part}, {len(cars)} cars parked on {capture(s)}"
                + (f"; the record says {rec_spaces}." if rec_spaces is not None else "; no CoStar parking figure to compare."))
    if fp is not None and rba is None and n:
        rba_ft2 = metres(fp, lat0).area * FT2_PER_M2
        metrics.append(Metric(id="stalls_per_1000_footprint", label="Stalls per 1,000 ft2 of footprint",
                              value=round(n / (rba_ft2 / 1000), 2), unit="per 1,000 ft2", source=vsrc))
    return ToolResult(scope=s.scope, verdict=Verdict(status=status, text=text), metrics=metrics, checks=checks,
                      findings=findings, overlays=pins(ps),
                      assumptions=[{"id": "parking.agree_pct", "label": "Agree within", "value": inputs.agree_pct, "unit": "%",
                                    "editable": True},
                                   {"id": "stall", "label": "Stall size used to split rows", "value": "2.7 m by 5.5 m"},
                                   {"id": "surface_only", "label": "Garages and covered stalls are not counted", "value": True}])
