"""Loading docks: dock doors and drive-in doors counted on the four oblique views (Vexcel detection, checked by the
vision model on the dock face), from inside where a scan exists, and set beside the CoStar record's counts."""
from __future__ import annotations

import io
import math
import statistics

from PIL import Image
from shapely.geometry import LineString, Point

from ...aerial import detect as aerial_detect
from ...aerial import site as aerial
from .. import Check, Finding, Metric, Source, ToolResult, Verdict, field, tool
from .._site import (
    Where,
    capture,
    footprint,
    geo,
    locate,
    metres,
    oblique_media,
    pin,
    pins,
    property_record,
    record_claims,
    record_source,
    to_m,
)

SHOWS = {"oblique-north": "south", "oblique-south": "north", "oblique-east": "west", "oblique-west": "east"}
LABEL = "loading dock"           # what Vexcel's SAM 3 finds dock doors by (tested 2026-11-13: "loading dock door" finds none)
THRESHOLD = 0.25
NEAR_WALL_M = (1.0, 16.0)        # oblique detections are put on the ground by the elevation model: a door on the
                                 # wall lands a few metres out; inside the footprint is a rooftop unit
SAM = Source(layer="vexcel", method="vision", confidence="medium",
             note="Vexcel Custom Elements (SAM 3) on the oblique views, label 'loading dock', threshold 0.25, kept "
                  "only 1 to 16 m outside this building's footprint, one oblique per wall")
VISION_TYPES = ["dock-high door", "drive-in door", "other door"]


class Inputs(Where):
    use_vision: bool = field(True, description="Ask the vision model to check the count on the dock face (cached)")
    inside: bool = field(True, description="With a scan, also look for dock doors in its panoramas")


def faces_of(fp_m) -> list[dict]:
    """The four sides of the footprint's minimum rotated rectangle, in metres, each with its outward bearing."""
    rect = fp_m.minimum_rotated_rectangle
    pts = list(rect.exterior.coords)[:4]
    c = rect.centroid
    out = []
    for a, b in zip(pts, pts[1:] + pts[:1]):
        mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        nx, ny = b[1] - a[1], -(b[0] - a[0])
        if nx * (mx - c.x) + ny * (my - c.y) < 0:
            nx, ny = -nx, -ny
        L = math.hypot(nx, ny)
        az = math.degrees(math.atan2(nx / L, ny / L)) % 360
        out.append({"edge": LineString([a, b]), "normal": (nx / L, ny / L), "bearing": az, "length_m": math.dist(a, b),
                    "side": ["north", "east", "south", "west"][int(((az + 45) % 360) // 90)]})
    return out


def _iou(a, b) -> float:
    ax0, ay0, aw, ah = a
    bx0, by0, bw, bh = b
    ix = max(0, min(ax0 + aw, bx0 + bw) - max(ax0, bx0))
    iy = max(0, min(ay0 + ah, by0 + bh) - max(ay0, by0))
    inter = ix * iy
    return inter / max(aw * ah + bw * bh - inter, 1e-9)


def keep_doors(dets: list[dict], fp_m, lat0: float) -> list[dict]:
    """Dock detections that sit just outside this building, one per door: overlapping boxes in one image merge and
    boxes far larger than the typical door (a whole dock row) are dropped."""
    fwd = to_m(lat0)[0]
    near = []
    for d in dets:
        if d["image"] == "spherical-ortho" or d["label"] != LABEL:
            continue
        x, y = fwd(*d["anchor"]["geo"])
        dist = fp_m.exterior.distance(Point(x, y)) if not fp_m.contains(Point(x, y)) else 0.0
        if NEAR_WALL_M[0] <= dist <= NEAR_WALL_M[1]:
            near.append({**d, "xy": (x, y), "wall_m": dist})
    areas = [d["pixel_bbox"][2] * d["pixel_bbox"][3] for d in near if d.get("pixel_bbox")]
    typical = statistics.median(areas) if areas else 0
    kept: list[dict] = []
    for d in sorted(near, key=lambda d: -d["confidence"]):
        b = d.get("pixel_bbox")
        if b and typical and b[2] * b[3] > 4 * typical:
            continue
        if b and any(k["image"] == d["image"] and _iou(k["pixel_bbox"], b) > 0.3 for k in kept if k.get("pixel_bbox")):
            continue
        kept.append(d)
    return kept


def assign(doors: list[dict], faces: list[dict]) -> dict[str, list[dict]]:
    """Doors per wall side, each side counted from the one oblique that looks at it (others see it edge-on)."""
    by: dict[str, list[dict]] = {}
    for d in doors:
        f = min(faces, key=lambda f: f["edge"].distance(Point(d["xy"])))
        d["side"] = f["side"]
        if SHOWS.get(d["image"]) == f["side"]:
            by.setdefault(f["side"], []).append(d)
    return by


def vision_count(s, direction: str, size_m: float) -> dict | None:
    """The vision model's own list of doors on the face an oblique shows, with boxes as fractions of the crop."""
    from ...vision.model import BOX, CONFIDENCE, ask, jpeg
    ob = next((o for o in aerial.obliques(s.lat, s.lon, size_m) if o["direction"] == direction), None)
    if ob is None:
        return None
    img = jpeg(ob["image"], 1600)
    w, h = Image.open(io.BytesIO(img)).size
    schema = {"type": "object", "additionalProperties": False, "required": ["doors"], "properties": {"doors": {
        "type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["type", "box", "confidence"],
                                   "properties": {"type": {"type": "string", "enum": VISION_TYPES}, "box": BOX,
                                                  "confidence": CONFIDENCE}}}}}
    prompt = (f"An oblique aerial photo, {w} by {h} pixels, looking {direction.split('-')[1]} at a commercial building "
              f"whose {SHOWS[direction]} wall faces the camera. The building of interest is the one at the centre of the "
              "image. List every truck door in that wall: 'dock-high door' (raised to trailer bed height, with a dock "
              "seal, bumpers or a trailer backed to it), 'drive-in door' (a large roll-up door at ground level that a truck "
              "can drive through, often with a ramp), 'other door' (a person door or a small door). Ignore doors on other "
              "buildings. Box each door in pixels (x0, y0 top left, x1, y1 bottom right).")
    a = ask([img], prompt, schema, key=f"loading_docks/{s.lat:.6f},{s.lon:.6f}/{direction}")
    doors = [{**d, "frac": (d["box"]["x0"] / w, d["box"]["y0"] / h, d["box"]["x1"] / w, d["box"]["y1"] / h)} for d in a["doors"]]
    return {"direction": direction, "doors": doors,
            "counts": {t: sum(d["type"] == t for d in doors) for t in VISION_TYPES}}


def inside_count(ctx, sid: str) -> dict | None:
    from ...vision.reader import find_objects
    plan = ctx.plan(sid)
    if not plan.get("panos"):
        return None
    found = find_objects(plan, labels=["loading dock door", "roll-up door"], max_panos=4)
    return {"found": found, "dock": sum(f["label"] == "loading dock door" for f in found),
            "rollup": sum(f["label"] == "roll-up door" for f in found)}


def survey(ctx, s, use_vision: bool = True, inside: bool = True) -> dict:
    """Everything the two truck tools need about a building's doors. Also used by truck_access."""
    fp = footprint(s)
    out: dict = {"footprint": fp, "faces": [], "doors": [], "by_side": {}, "record": record_claims(property_record(s.property_id))}
    if fp is None:
        return out
    fp_m = metres(fp, s.lat)
    faces = faces_of(fp_m)
    c = fp.centroid
    x0, y0, x1, y1 = fp_m.bounds
    size = min(300, max(60, max(x1 - x0, y1 - y0) + 50))
    ctx.step(f"Building footprint {fp_m.area:.0f} m2; looking at the four oblique views over {size:.0f} m")
    det = aerial_detect.detect(c.y, c.x, size, [LABEL], obliques=True, threshold=THRESHOLD)
    doors = keep_doors(det["detections"], fp_m, s.lat)
    by = assign(doors, faces)
    ctx.step(f"Vexcel found {sum(1 for d in det['detections'] if d['image'] != 'spherical-ortho')} dock candidates on "
             f"the obliques; {sum(map(len, by.values()))} sit on this building's walls, seen face-on")
    out.update(faces=faces, doors=[d for ds in by.values() for d in ds], by_side=by, size_m=size, center=(c.x, c.y),
               images=det.get("images"))
    if use_vision and by:
        side = max(by, key=lambda k: len(by[k]))
        direction = next(d for d, f in SHOWS.items() if f == side)
        try:
            out["vision"] = vision_count(s, direction, size)
            ctx.step(f"Vision model on the {side} wall: " + ", ".join(f"{v} {k}" for k, v in out["vision"]["counts"].items()))
        except Exception as e:  # noqa: BLE001  the count stands without the cross-check
            out["vision_error"] = str(e)[:200]
    if inside and s.sid:
        try:
            out["inside"] = inside_count(ctx, s.sid)
        except Exception as e:  # noqa: BLE001
            out["inside_error"] = str(e)[:200]
    return out


def agree(a: float | None, b: float | None) -> str:
    if a is None or b is None:
        return "unknown"
    return "pass" if abs(a - b) <= max(2, 0.2 * b) else "warn"


@tool(id="loading_docks", title="Loading docks", icon="truck",
      summary="Counts dock doors and drive-in doors on each wall from the oblique aerial views and beside the "
              "CoStar record.",
      model_description="For a warehouse, flex building or any commercial address: dock doors counted per wall on Vexcel "
                        "oblique views, split into dock-high and drive-in by the vision model on the dock face, from "
                        "inside when a scan exists, and compared with the CoStar record (numExternalLoadingDocks + "
                        "numInternalLoadingDocks, driveInBays). Returns pins per door, the dock side, and checks.",
      personas=["commercial_underwriter", "truck_dispatcher", "costar_researcher"],
      requires=[{"layer": "vexcel.oblique"}, {"layer": "costar.property", "need": "optional"},
                {"layer": "matterport.panos", "need": "optional"}],
      blocks=["VerdictHeader", "MetricRow", "CheckList", "EvidenceStrip", "StepLog", "ActionBar"],
      overlays=["pins"], annotations={"cost": "slow"},
      examples=["How many dock doors does this warehouse have?", "Which side are the docks on?"])
def run(ctx, inputs: Inputs) -> ToolResult:
    s = locate(ctx, inputs)
    sv = survey(ctx, s, inputs.use_vision, inputs.inside)
    k, rec = s.key, sv["record"]
    if sv["footprint"] is None:
        return ToolResult(scope=s.scope, verdict=Verdict(status="unknown",
                          text="Vexcel has no building footprint here, so the walls cannot be read."))
    by = sv["by_side"]
    aerial_n = sum(map(len, by.values()))
    vis = sv.get("vision")
    rec_docks = (rec.get("dock_doors") or {}).get("value")
    rec_drive = (rec.get("drive_in_bays") or {}).get("value")
    metrics = [Metric(id="aerial_docks", label="Dock doors seen from the air", value=aerial_n, unit="", source=SAM)]
    vsrc = Source(layer="model", method="vision", confidence="low",
                  note=f"Vision model on the {vis['direction']} oblique (one wall only)" if vis else "Vision model")
    if vis:
        metrics += [Metric(id="vision_dock_high", label="Dock-high doors (vision, one wall)", value=vis["counts"]["dock-high door"], unit="", source=vsrc),
                    Metric(id="vision_drive_in", label="Drive-in doors (vision, one wall)", value=vis["counts"]["drive-in door"], unit="", source=vsrc)]
    if rec_docks is not None:
        metrics.append(Metric(id="record_docks", label="Dock doors in the record", value=rec_docks, unit="",
                              source=record_source(rec["dock_doors"]["path"], s.property_id)))
    if rec_drive is not None:
        metrics.append(Metric(id="record_drive_in", label="Drive-in bays in the record", value=rec_drive, unit="",
                              source=record_source(rec["drive_in_bays"]["path"], s.property_id)))
    for side, ds in by.items():
        metrics.append(Metric(id=f"side.{side}", label=f"{side.capitalize()} wall", value=len(ds), unit="doors", source=SAM))

    checks, findings, ps = [], [], []
    for side, ds in sorted(by.items(), key=lambda kv: -len(kv[1])):
        direction = next(d for d, f in SHOWS.items() if f == side)
        fid = f"loading_docks:{k}:{side}"
        findings.append(Finding(id=fid, title=f"Dock doors on the {side} wall", status="pass", anchor=geo(*ds[0]["anchor"]["geo"]),
                                source=SAM, media=[oblique_media(s, direction, sv["size_m"])],
                                detail=f"{len(ds)} doors seen face-on in the {direction} view, capture {capture(s)}."))
        for i, d in enumerate(ds):
            ps.append(pin(f"dock_{side}_{i + 1}", *d["anchor"]["geo"], f"dock {side} {i + 1}", "pass"))
    if vis:
        side = SHOWS[vis["direction"]]
        n_sam = len(by.get(side, []))
        n_vis = vis["counts"]["dock-high door"] + vis["counts"]["drive-in door"]
        fid = f"loading_docks:{k}:vision:{side}"
        st = agree(n_sam, n_vis)
        checks.append(Check(id="vision_agrees", rule=f"Two detectors agree on the {side} wall", measured=n_sam,
                            threshold=n_vis, unit="doors", status=st, findings=[fid]))
        findings.append(Finding(id=fid, title=f"Vision model's door list, {side} wall", status=st, source=vsrc,
                                anchor=geo(*sv["center"]),
                                detail=f"{vis['counts']['dock-high door']} dock-high, {vis['counts']['drive-in door']} drive-in, "
                                       f"{vis['counts']['other door']} other doors; Vexcel detection counted {n_sam} on this wall.",
                                media=[oblique_media(s, vis["direction"], sv["size_m"], tuple(round(v, 4) for v in d["frac"]))
                                       for d in vis["doors"] if d["type"] != "other door"][:12]))
    best = aerial_n
    if vis:  # the vision count covers one wall; the others keep Vexcel's count
        side = SHOWS[vis["direction"]]
        best = aerial_n - len(by.get(side, [])) + vis["counts"]["dock-high door"] + vis["counts"]["drive-in door"]
    if rec_docks is not None or rec_drive is not None:
        want = (rec_docks or 0) + (rec_drive or 0)
        st = agree(best, want)
        fid = f"loading_docks:{k}:record"
        checks.append(Check(id="record_agrees", rule="Truck doors seen match the record (docks plus drive-ins)",
                            measured=best, threshold=want, unit="doors", status=st, findings=[fid]))
        findings.append(Finding(id=fid, title="Record versus the aerial count", status=st, anchor=geo(s.lon, s.lat),
                                source=record_source(" and ".join(rec[x]["path"] for x in ("dock_doors", "drive_in_bays") if x in rec), s.property_id),
                                detail=f"Record: {rec_docks if rec_docks is not None else 'no'} dock doors, "
                                       f"{rec_drive if rec_drive is not None else 'no'} drive-in bays. Seen from the air: {best}. "
                                       "Doors under a canopy, behind a parked trailer or on an interior dock are not visible."))
    ins = sv.get("inside")
    if ins and ins["found"]:
        for f in ins["found"]:
            findings.append(Finding.model_validate({**f["finding"], "id": f"loading_docks:{k}:inside:{f['finding']['id']}",
                                                    "title": f"Inside: {f['label']}"}))
        metrics.append(Metric(id="inside_doors", label="Truck doors seen inside", value=ins["dock"] + ins["rollup"], unit="",
                              source=Source(layer="model", method="vision", confidence="low",
                                            note="Vision model on up to 4 panoramas of the scan")))
    sides = ", ".join(f"{len(v)} {s_}" for s_, v in sorted(by.items(), key=lambda kv: -len(kv[1])))
    if not aerial_n:
        status, text = "unknown", "No dock doors were seen on this building's walls from the air."
    else:
        status = "warn" if any(c.status == "warn" for c in checks) else "pass"
        text = f"About {best} truck doors seen from the air ({sides} wall)"
        text += (f"; the record says {rec_docks or 0} docks and {rec_drive or 0} drive-ins." if rec else "; no CoStar record to compare.")
    return ToolResult(scope=s.scope, verdict=Verdict(status=status, text=text), metrics=metrics, checks=checks,
                      findings=findings, overlays=pins(ps),
                      assumptions=[{"id": "detector", "label": "Detector label and threshold", "value": f"{LABEL}, {THRESHOLD}"},
                                   {"id": "capture", "label": "Aerial capture", "value": capture(s)}],
                      actions=[{"id": "truck", "label": "Check truck access", "tool": "truck_access",
                                "inputs": {k2: v for k2, v in inputs.model_dump().items() if k2 in ("scan", "property_id", "lat", "lon") and v is not None}}])

