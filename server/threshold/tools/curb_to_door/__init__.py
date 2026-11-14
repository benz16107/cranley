"""Curb to door: the part outside. Parking near the entrance and accessible stalls if the aerial photo shows them,
the distance from parking to the entrance, the ground rise along it, and steps at the entrance seen in the
entry panoramas. The join between the aerial photo and the scan is uncertain, and the tool says so."""
from __future__ import annotations

import math

from pydantic import BaseModel

from ...aerial import detect as aerial_detect
from ...aerial import site
from ...geometry import to_latlon
from ...geometry.georef import VERIFIED
from ...sources.index import rows as index_rows
from .. import (Assumption, Check, Finding, Metric, Pin, PinsOverlay, ScanScope, Source, ToolResult, Verdict, field,
                tool)
from ..types import GeoAnchor, Media, OpeningAnchor, PanoAnchor, PointAnchor
from .._access import STD, label, pick_entrance, quality, rooms, sill_step, step_kind
from .._access import look

LABELS = ["parking space", "car", "driveway", "wheelchair symbol", "sidewalk"]
PARKING = ("parking space", "car", "driveway")


class Inputs(BaseModel):
    scan: str = field(source="selection.scan", description="Scan id")
    radius_m: float = field(40, ge=10, le=100, unit="m", description="How far around the building to look")
    read_panoramas: bool = field(True, description="Look for steps in the panoramas by the entrance")


def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Metres between two (lon, lat) points, flat earth (fine within a lot)."""
    lat = math.radians((a[1] + b[1]) / 2)
    return math.hypot((a[0] - b[0]) * 111320 * math.cos(lat), (a[1] - b[1]) * 110574)


@tool(id="curb_to_door", title="Curb to door", icon="car",
      summary="Looks at the way in from outside: parking near the entrance, accessible stalls if the aerial photo "
              "shows them, how far it is to the door, and steps at the door.",
      model_description="The outside part of an access audit for one scan, from the Vexcel aerial photo and the "
                        "entry panoramas: parking near the building (stalls, parked cars, driveway), wheelchair "
                        "symbols, straight-line distance and ground rise from the nearest parking to the entrance, "
                        "and steps, stairs or ramps at the entrance. Confidence is low where the scan's geo position "
                        "is approximate.",
      personas=["wheelchair_user", "older_adult_family"],
      requires=[{"layer": "vexcel.ortho"}, {"layer": "matterport.geo"}, {"layer": "matterport.panos", "need": "optional"}],
      blocks=["VerdictHeader", "MetricRow", "CheckList", "EvidenceStrip", "AssumptionChips", "StepLog"],
      overlays=["pins"], annotations={"cost": "slow"},
      examples=["How far is it from parking to the front door?", "Are there steps up to the entrance?"])
def run(ctx, inputs: Inputs) -> ToolResult:
    sid = inputs.scan
    plan = ctx.plan(sid)
    scope = ScanScope(sid=sid)
    idx = index_rows().get(sid, {})
    kind = idx.get("kind")
    geo = plan.get("geo") or {}
    lat, lon = geo.get("lat"), geo.get("lon")
    assumptions = [Assumption(id="georef", label="Scan-to-map rotation verified against the aerial photo",
                              value=bool(VERIFIED)),
                   Assumption(id="crow_flies", label="Distance is a straight line; the real path is longer",
                              value=True)]
    if lat is None or lon is None:
        return ToolResult(scope=scope, assumptions=assumptions, verdict=Verdict(status="unknown", text=(
            "This scan has no geocoordinates, so it cannot be placed on the aerial photo.")))
    notes = []
    ent = pick_entrance(plan) if quality(plan).get("walls") else None
    door = None
    if ent and kind == "house":
        ll = to_latlon(plan, *ent["center"])
        door = (ll[1], ll[0]) if ll else None
    if door is None:
        door = (lon, lat)
        notes.append("the scan's geo point stands in for the entrance" + (
            "; an apartment's door is inside the building, so this is the building's way in, not the unit's"
            if kind == "apartment_unit" else ""))
    join = Source(layer="vexcel", method="geometry", confidence="low",
                  note="Scan placed on the map by its geocoordinates; " + (
                      "the rotation convention is not yet verified against the photo" if not VERIFIED else "verified"))
    try:
        det = aerial_detect.detect(lat, lon, 2 * inputs.radius_m, LABELS, threshold=0.3)
    except Exception as e:
        return ToolResult(scope=scope, assumptions=assumptions, verdict=Verdict(status="unknown", text=(
            f"The aerial reader failed ({type(e).__name__}), so the outside cannot be checked.")))
    ctx.step(f"Aerial photo around the building: " + ", ".join(f"{n} {l}" for l, n in det["counts"].items() if n))
    dsrc = Source(**det["source"]) if det.get("source") else join
    parking = [d for d in det["detections"] if d["label"] in PARKING]
    access = [d for d in det["detections"] if d["label"] == "wheelchair symbol"]
    near = min(parking, key=lambda d: _dist(tuple(d["anchor"]["geo"]), door), default=None)
    dist = _dist(tuple(near["anchor"]["geo"]), door) if near else None
    rise = None
    if near:
        try:
            prof = site.elevation_profile((near["anchor"]["geo"][1], near["anchor"]["geo"][0]), (door[1], door[0]), 12)
            g = [p["ground_m"] for p in prof["points"]]
            rise = g[-1] - g[0]
        except Exception:
            notes.append("ground heights were not available")
    findings, checks, pins = [], [], []
    if near:
        fid = f"curb_to_door:{sid}:parking"
        findings.append(Finding(id=fid, title=f"Nearest parking ({near['label']})", status="unknown", source=dsrc,
                                anchor=GeoAnchor(geo=tuple(near["anchor"]["geo"])),
                                detail=f"About {dist:.0f} m in a straight line from the entrance point. A parked car "
                                       "or a driveway stands in for a stall where no stall is marked."))
        pins.append(Pin(id=fid, anchor=GeoAnchor(geo=tuple(near["anchor"]["geo"])), label="Nearest parking",
                        status="unknown"))
    for i, a in enumerate(access):
        fid = f"curb_to_door:{sid}:accessible:{i}"
        findings.append(Finding(id=fid, title="Wheelchair symbol on the ground", status="pass", source=dsrc,
                                anchor=GeoAnchor(geo=tuple(a["anchor"]["geo"])),
                                detail=f"Detected with confidence {a['confidence']:.2f}; probably an accessible stall."))
        pins.append(Pin(id=fid, anchor=GeoAnchor(geo=tuple(a["anchor"]["geo"])), label="Accessible stall?",
                        status="pass"))
    pins.append(Pin(id=f"curb_to_door:{sid}:door", anchor=GeoAnchor(geo=door), label="Entrance (approximate)",
                    status="unknown"))
    checks.append(Check(id="parking", rule="Parking near the building", measured=len(parking), threshold=1,
                        unit="found", status="pass" if parking else "warn",
                        findings=[f"curb_to_door:{sid}:parking"] if near else []))
    checks.append(Check(id="accessible_stall", rule="Accessible stall marked on the ground", measured=len(access),
                        threshold=1, unit="found", status="pass" if access else "unknown",
                        standard="ADA 2010 502 (accessible parking spaces); symbols are often too small to see"))
    checks.append(Check(id="distance", rule="Straight-line distance from the nearest parking to the entrance",
                        measured=round(dist, 1) if dist is not None else None, threshold=None, unit="m",
                        status="unknown" if dist is None else "pass" if dist <= 30 else "warn"))
    checks.append(Check(id="rise", rule="Ground rise from that parking to the entrance (bare-ground model)",
                        measured=round(rise, 2) if rise is not None else None, threshold=None, unit="m",
                        status="unknown" if rise is None or abs(rise) < 1.0 else "warn",  # under 1 m is model error
                        standard="Vexcel bare-ground model; differences under about a metre are within its error"))
    # the entrance itself: its sill, then what the panoramas by the door show
    step_status = "unknown"
    if ent:
        s = sill_step(plan, ent)
        k = step_kind(s)
        if k != "none":
            fid = f"curb_to_door:{sid}:sill"
            findings.append(Finding(id=fid, title="Step at the entrance door", status="fail",
                                    anchor=OpeningAnchor(sid=sid, opening=ent["opening"]),
                                    source=Source(layer="matterport", method="geometry", confidence="low",
                                                  note="Sill height against the floor level of the storey"),
                                    detail=f"The door sill is {s * 100:.0f} cm off the floor inside. {STD['level']}."))
            step_status = "fail"
    seen = []
    if inputs.read_panoramas and ent:
        cx, cy = ent["center"]
        panos = sorted((p for p in plan["panos"] if p.get("rotation") and p.get("floor") == ent["floor"]),
                       key=lambda p: math.dist(p["position"][:2], (cx, cy)))[:2]
        ctx.step(f"Reading {len(panos)} panoramas by the entrance for steps and ramps")
        found, err = look.objects(plan, [p["id"] for p in panos])
        if err:
            notes.append(err)
        for o in found:
            if o["label"] in ("step or threshold", "stairs", "ramp"):
                fd = o["finding"]
                a = fd["anchor"]
                seen.append(o["label"])
                findings.append(Finding(id=f"curb_to_door:{sid}:seen:{fd['id']}", title=f"Panorama shows {o['label']}",
                                        status="pass" if o["label"] == "ramp" else "warn", source=Source(**fd["source"]),
                                        anchor=PointAnchor(**a) if "point" in a else PanoAnchor(**a),
                                        detail=f"{fd['detail']}. Seen by the entrance, not measured.",
                                        media=[Media(**m) for m in fd["media"]]))
        if step_status == "unknown" and panos and not err:
            step_status = "warn" if any(x != "ramp" for x in seen) else "pass"
    checks.append(Check(id="entrance_step", rule="No step at the entrance (sill and entry panoramas)", measured=None,
                        threshold=None, unit="", status=step_status, standard=STD["level"]))
    for f in findings:
        if f.anchor is not None and not any(p.id == f.id for p in pins):
            pins.append(Pin(id=f.id, anchor=f.anchor, label=f.title, status=f.status))
    worst = [c.status for c in checks if c.id in ("parking", "distance", "rise", "entrance_step")]
    status = "fail" if "fail" in worst else "warn" if "warn" in worst else "unknown" if all(
        x == "unknown" for x in worst) else "pass"
    text = (f"Nearest parking about {dist:.0f} m from the entrance as the crow flies." if dist is not None else
            "No parking found in the aerial photo around the building.")
    text += {"fail": " There is a step at the entrance.", "warn": " Something on the way needs a look on site.",
             "pass": "", "unknown": ""}[step_status if step_status in ("fail", "warn") else "pass"]
    text += " Low confidence: " + "; ".join(notes + ["the aerial photo and the scan are joined by approximate "
                                                     "geocoordinates"]) + "."
    return ToolResult(
        scope=scope, verdict=Verdict(status=status, text=text), checks=checks, findings=findings,
        overlays=[PinsOverlay(pins=pins)], assumptions=assumptions,
        metrics=[Metric(id="parking_m", label="Parking to entrance (straight line)",
                        value=round(dist, 1) if dist is not None else None, unit="m", source=join),
                 Metric(id="parking_found", label="Parking places seen", value=len(parking), unit="", source=dsrc),
                 Metric(id="accessible", label="Wheelchair symbols seen", value=len(access), unit="", source=dsrc),
                 Metric(id="rise_m", label="Ground rise to the entrance", value=round(rise, 2) if rise is not None
                        else None, unit="m", source=Source(layer="vexcel", method="lookup", confidence="low",
                                                           note=site.GROUND_NOTE))])
