"""Truck access: can a 53 ft trailer reach and back to this building's docks? The approach street and driveway, gate or
no gate, entrance width and truck court depth measured on the orthophoto and the surface model, room to turn a WB-67,
trailer parking, overhead obstructions, arrival directions and a route on the aerial photo.

Turning geometry: AASHTO's WB-67 design vehicle (the 53 ft trailer): minimum design turning radius 45 ft (13.7 m),
minimum inside radius 4.4 ft (1.3 m), from "A Policy on Geometric Design of Highways and Streets" (the Green Book),
design vehicle table, as reproduced in US Army bulletin 20-02 (api.army.mil, 2025) and Iowa DOT Design Manual 6A-2.
A 90 degree turn in place sweeps the outer minus the inner radius, 12.4 m: that is the entrance width that needs no
help from curb returns. Truck court depth for backing a 53 ft trailer: 130 ft (39.6 m) is the planning figure, 120 ft
the low end (ENCOR Advisors, Steelco and Innowave warehouse site-planning guides).
"""
from __future__ import annotations

import io
import math
import statistics
from itertools import pairwise

from PIL import Image
from shapely.geometry import LineString, Point, Polygon

from ...aerial import detect as aerial_detect
from ...aerial import site as aerial
from .. import Check, Finding, Metric, Source, ToolResult, Verdict, field, tool
from .._site import (
    M_PER_FT,
    Where,
    bearing,
    capture,
    compass,
    dist_m,
    fact,
    geo,
    geo_route,
    heights,
    locate,
    metres,
    ortho_media,
    osm,
    parcel,
    pin,
    pins,
    to_m,
)
from ..loading_docks import survey

WB67_OUTER_M = 45 * M_PER_FT
WB67_INNER_M = 4.4 * M_PER_FT
TURN_SWEEP_M = WB67_OUTER_M - WB67_INNER_M
TALL_M = 4.5          # taller than a 13 ft 6 in trailer: a building, a wall or a tree, not a parked trailer
OVERHEAD_M = 1.5      # anything this far above the ground on the drive line is worth a look
RAY_STEP_M, RAY_MAX_M, RAY_START_M = 2.0, 80.0, 4.0
TURN = Source(layer="model", method="simulation", confidence="medium",
              note="AASHTO Green Book WB-67: 45 ft design radius, 4.4 ft inside radius (via US Army bulletin 20-02)")
COURT_SRC = Source(layer="vexcel", method="geometry", confidence="medium",
                   note="Rays from the dock wall: ends at the first point the surface model is 4.5 m above the building's "
                        "ground, or where the orthophoto turns to vegetation for 4 m. Fences and kerbs are not seen.")
WIDTH_SRC = Source(layer="vexcel", method="geometry", confidence="low",
                   note="Paved run across the driveway on the orthophoto, by colour; kerbs are one pixel, so +-0.5 m")
OSM_SRC = Source(layer="model", method="lookup", confidence="medium", note=osm.NOTE)


class Inputs(Where):
    court_min_m: float = field(39.6, pref="truck.court_min_m", unit="m", ge=10, le=80,
                               description="Truck court depth a 53 ft trailer needs to back in (130 ft)")
    entrance_min_m: float = field(round(TURN_SWEEP_M, 1), pref="truck.entrance_min_m", unit="m", ge=3, le=30,
                                  description="Entrance width for a WB-67 to turn in without curb returns")
    use_vision: bool = field(True, description="Ask the vision model whether a gate closes the entrance (cached)")


# ---- measuring on the orthophoto --------------------------------------------------------------------

class Photo:
    """An orthophoto as pixels, with lon/lat lookups."""

    def __init__(self, lat: float, lon: float, size_m: float):
        self.o = aerial.ortho(lat, lon, size_m, 1024)
        self.im = Image.open(io.BytesIO(self.o.image)).convert("RGB")
        self.mpp = self.o.metres_per_px

    def rgb(self, lon: float, lat: float):
        x, y = self.o.to_px(lon, lat)
        if not (0 <= x < self.im.width and 0 <= y < self.im.height):
            return None
        return self.im.getpixel((int(x), int(y)))


def green(c) -> bool:
    r, g, b = c
    return g > r * 1.06 and g > b * 1.06 and g > 50


def like(c, ref, tol: float = 38) -> bool:
    return c is not None and math.dist(c, ref) < tol and not green(c)


def paved_run(photo: Photo, lat0: float, centre: tuple[float, float], direction: tuple[float, float],
              cap_m: float = 40) -> float | None:
    """Width of the paved strip through `centre` (lon, lat) across `direction` (unit east, north): walk both ways
    while the colour stays like the centre, allowing gaps under 0.6 m (paint, cracks)."""
    fwd, back = to_m(lat0)
    cx, cy = fwd(*centre)
    ref = photo.rgb(*centre)
    if ref is None or green(ref):
        return None
    nx, ny = -direction[1], direction[0]
    step = photo.mpp
    total = 0.0
    for sgn in (1, -1):
        d, miss, last = 0.0, 0.0, 0.0
        while d < cap_m / 2:
            d += step
            c = photo.rgb(*back(cx + sgn * nx * d, cy + sgn * ny * d))
            if like(c, ref):
                last, miss = d, 0.0
            else:
                miss += step
                if miss > 0.6:
                    break
        total += last
    return round(total, 1)


def court_depth(photo: Photo | None, face: dict, lat0: float, ref_z: float | None, n_rays: int = 5) -> dict:
    """Clear depth in front of a wall: rays every so often along it, ended by tall things (surface model) or by
    vegetation (orthophoto)."""
    back = to_m(lat0)[1]
    a, b = face["edge"].coords[0], face["edge"].coords[1]
    nx, ny = face["normal"]
    starts = [(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t) for t in [0.1 + 0.8 * i / (n_rays - 1) for i in range(n_rays)]]
    ds = [RAY_START_M + RAY_STEP_M * i for i in range(int((RAY_MAX_M - RAY_START_M) / RAY_STEP_M) + 1)]
    pts = [back(sx + nx * d, sy + ny * d) for sx, sy in starts for d in ds]
    zs = heights("dsm", pts) if ref_z is not None else [None] * len(pts)
    rays = []
    for i, (sx, sy) in enumerate(starts):
        end, why = RAY_MAX_M, "no obstacle within the search distance"
        veg = 0
        for j, d in enumerate(ds):
            z = zs[i * len(ds) + j]
            if z is not None and z - ref_z > TALL_M:
                end, why = d, "something taller than a trailer (building, wall or tree)"
                break
            c = photo.rgb(*pts[i * len(ds) + j]) if photo else None
            veg = veg + 1 if c is not None and green(c) else 0
            if veg * RAY_STEP_M >= 4:
                end, why = d - (veg - 1) * RAY_STEP_M, "pavement ends at vegetation"
                break
        rays.append({"start": back(sx, sy), "end": back(sx + nx * end, sy + ny * end), "depth_m": end, "ended_by": why})
    deps = [r["depth_m"] for r in rays]
    return {"rays": rays, "median_m": statistics.median(deps), "min_m": min(deps), "max_m": max(deps)}


# ---- streets and the entrance -----------------------------------------------------------------------

def _line(w: dict, lat0: float) -> LineString:
    return LineString([to_m(lat0)[0](*p) for p in w["points"]])


def entrance(o: dict, target: tuple[float, float], lat0: float, parcel_m=None) -> dict | None:
    """The driveway mouth nearest the truck court: where a service way meets a named street. Falls back to the
    nearest point on the nearest named street when OSM maps no driveway."""
    fwd, back = to_m(lat0)
    tx, ty = fwd(*target)
    T = Point(tx, ty)
    named = [(w, _line(w, lat0)) for w in o["streets"] if w["tags"].get("name") and len(w["points"]) > 1]
    if not named:
        return None
    best = None
    for w in o["service"]:
        if len(w["points"]) < 2:
            continue
        sl = _line(w, lat0)
        for end in (Point(sl.coords[0]), Point(sl.coords[-1])):
            st, stl = min(named, key=lambda n: n[1].distance(end))
            if stl.distance(end) > 4:
                continue
            if parcel_m is not None and sl.distance(parcel_m) > 25:
                continue
            score = sl.distance(T)
            if best is None or score < best["score"]:
                inner = sl if Point(sl.coords[0]).distance(end) < 1 else LineString(list(sl.coords)[::-1])
                best = {"score": score, "street": st, "street_line": stl, "mouth": (end.x, end.y), "way": w, "drive": inner,
                        "mapped": True}
    if best is None:
        st, stl = min(named, key=lambda n: n[1].distance(T))
        p = stl.interpolate(stl.project(T))
        best = {"score": p.distance(T), "street": st, "street_line": stl, "mouth": (p.x, p.y), "way": None,
                "drive": LineString([(p.x, p.y), (tx, ty)]), "mapped": False}
    mx, my = best["mouth"]
    sl = best["street_line"]
    t = sl.project(Point(mx, my))
    p0, p1 = sl.interpolate(max(0, t - 3)), sl.interpolate(min(sl.length, t + 3))
    L = max(math.dist((p0.x, p0.y), (p1.x, p1.y)), 1e-9)
    best["street_dir"] = ((p1.x - p0.x) / L, (p1.y - p0.y) / L)
    d0 = best["drive"].interpolate(min(8, best["drive"].length * 0.5))
    L = max(math.dist((mx, my), (d0.x, d0.y)), 1e-9)
    best["drive_dir"] = ((d0.x - mx) / L, (d0.y - my) / L)
    best["mouth_ll"] = back(mx, my)
    best["inside_ll"] = back(d0.x, d0.y)
    # the nearest other named street gives a landmark
    others = [(w, l) for w, l in named if w["tags"]["name"] != best["street"]["tags"]["name"]]
    if others:
        cw, cl = min(others, key=lambda n: n[1].distance(sl))
        x = sl.intersection(cl)
        if not x.is_empty:
            xp = x if x.geom_type == "Point" else x.representative_point()
            best["cross"] = {"name": cw["tags"]["name"], "dist_m": round(xp.distance(Point(mx, my))),
                             "dir": compass(math.degrees(math.atan2(mx - xp.x, my - xp.y)))}
    return best


def gates_near(o: dict, mouth_ll, drive_ll: list, lat0: float, within_m: float = 12) -> list[dict]:
    fwd = to_m(lat0)[0]
    line = LineString([fwd(*p) for p in drive_ll]) if len(drive_ll) > 1 else Point(fwd(*mouth_ll))
    return [g for g in o["gates"] if min(line.distance(Point(fwd(*p))) for p in g["points"]) <= within_m]


def gate_vision(s, mouth_ll) -> dict | None:
    from ...vision.model import CONFIDENCE, ask
    o = aerial.ortho(mouth_ll[1], mouth_ll[0], 50, 768)
    schema = {"type": "object", "additionalProperties": False, "required": ["gate", "confidence", "note"],
              "properties": {"gate": {"type": "string", "enum": ["closed gate", "open gate", "no gate", "unclear"]},
                             "confidence": CONFIDENCE, "note": {"type": "string"}}}
    prompt = ("North-up aerial photo, 50 m across, centred on where a driveway leaves the street. Is there a gate across "
              "this driveway (a sliding or swing gate, a lift arm, a fence line crossing the drive)? Answer from what is "
              "visible; a note of a few words says what you see.")
    return ask([o.image], prompt, schema, key=f"truck_access/gate/{mouth_ll[1]:.6f},{mouth_ll[0]:.6f}")


def low_text(l: dict) -> str:
    what = l["tags"].get("name") or ("a height barrier" if l["tags"].get("barrier") else "a road")
    h = l["maxheight_m"]
    ft = f"{int(h / M_PER_FT)} ft {round((h / M_PER_FT % 1) * 12)} in ({h:.2f} m)" if h else "below the legal height"
    return f"{what}, {ft}, {l['dist_m']:.0f} m {l['dir']}"


# ---- the tool ---------------------------------------------------------------------------------------

def directions(e: dict, gate: str, dock_side: str, dock_bearing: float, n_doors: int, depth: float, drive_m: float,
               lows: list[dict]) -> str:
    street = e["street"]["tags"]["name"]
    head = compass(math.degrees(math.atan2(*e["drive_dir"])))
    where = (f", {e['cross']['dist_m']} m {e['cross']['dir']} of {e['cross']['name']}" if e.get("cross") else "")
    parts = [f"Approach on {street}.",
             (f"Turn in at the {'driveway' if e['mapped'] else 'frontage (no driveway is mapped; look for the curb cut)'}"
              f"{where}, heading {head}."),
             gate,
             f"Follow the drive about {drive_m:.0f} m to the truck court on the {dock_side} side of the building.",
             (f"The {n_doors or 'dock'} doors face {compass(dock_bearing)}; the court is about {depth:.0f} m deep from the "
              f"dock wall, so pull across the court and back straight to the door.")]
    if lows:
        parts.append("Low clearance nearby: " + "; ".join(low_text(l) for l in lows[:3]) + ". Plan the route around them.")
    return " ".join(p for p in parts if p)


@tool(id="truck_access", title="Truck access", icon="truck",
      summary="Whether a 53 ft trailer can reach and back to the docks: entrance, gate, court depth, turning room, "
              "overhead obstructions, arrival directions and a route on the aerial photo.",
      model_description="For a warehouse or any commercial address in Houston or Los Angeles: finds the dock wall, "
                        "measures the truck court depth and the entrance width on the orthophoto and surface model, "
                        "checks them against a WB-67 (53 ft trailer, AASHTO) and the 130 ft court guideline, names the "
                        "street and driveway (OpenStreetMap), gate or no gate, posted low clearances within 1.5 km, "
                        "trailer parking, and writes arrival directions. Returns a route overlay on the map (floor 'geo', "
                        "points [lon, lat, 0]) and pins on the tight spots.",
      personas=["truck_dispatcher"],
      requires=[{"layer": "vexcel.ortho"}, {"layer": "vexcel.dsm"}, {"layer": "vexcel.oblique"},
                {"layer": "osm.streets", "need": "optional"}, {"layer": "costar.property", "need": "optional"}],
      blocks=["VerdictHeader", "MetricRow", "CheckList", "EvidenceStrip", "Note", "AssumptionChips", "StepLog"],
      overlays=["route", "pins"], annotations={"cost": "slow"},
      examples=["Can a 53 foot trailer get into this warehouse?", "Which entrance do trucks use here?"])
def run(ctx, inputs: Inputs) -> ToolResult:
    s = locate(ctx, inputs)
    sv = survey(ctx, s, use_vision=False, inside=False)
    if sv["footprint"] is None:
        return ToolResult(scope=s.scope, verdict=Verdict(status="unknown",
                          text="Vexcel has no building footprint here, so there is no dock wall to measure from."))
    k, lat0 = s.key, s.lat
    fwd, back = to_m(lat0)
    by = sv["by_side"]
    ref_z = fact(s, "ground_elevation")
    size = min(400, sv["size_m"] + 120)
    c = sv["footprint"].centroid
    photo = Photo(c.y, c.x, size)
    faces = sv["faces"]
    if by:
        side = max(by, key=lambda x: len(by[x]))
        face = next(f for f in faces if f["side"] == side)
        face_note = f"{len(by[side])} dock doors seen on the {side} wall"
    else:  # no doors seen: take the wall with the deepest clear apron and say so
        depths = {f["side"]: court_depth(photo, f, lat0, ref_z, 3)["median_m"] for f in faces}
        side = max(depths, key=depths.get)
        face = next(f for f in faces if f["side"] == side)
        face_note = f"No dock doors seen; the {side} wall has the deepest paved apron, so it is assumed"
    ctx.step(face_note)
    court = court_depth(photo, face, lat0, ref_z)
    ctx.step(f"Court in front of the {side} wall: median {court['median_m']:.0f} m, narrowest {court['min_m']:.0f} m")
    nx, ny = face["normal"]
    edge = face["edge"]
    doors_here = by.get(side, [])
    # the door cluster's middle, projected onto the wall; the wall's middle when no doors were seen
    mid = edge.interpolate(statistics.median(edge.project(Point(d["xy"])) for d in doors_here)) if doors_here \
        else edge.interpolate(0.5, normalized=True)
    depth = court["median_m"]
    court_c = back(mid.x + nx * depth / 2, mid.y + ny * depth / 2)
    stage = back(mid.x + nx * min(20, depth * 0.6), mid.y + ny * min(20, depth * 0.6))
    (ax, ay), (bx, by_) = edge.coords[0], edge.coords[1]
    court_poly = Polygon([(ax, ay), (bx, by_), (bx + nx * depth, by_ + ny * depth), (ax + nx * depth, ay + ny * depth)])

    try:
        o = osm.around(c.y, c.x, streets_m=int(max(250, size)), limits_m=1500)
    except Exception as e:  # noqa: BLE001  directions degrade to "unknown street"
        o, osm_error = None, str(e)[:200]
    else:
        osm_error = None
    pc = parcel(s)
    e = entrance(o, court_c, lat0, metres(pc, lat0) if pc is not None else None) if o else None
    checks, findings, ps, metrics = [], [], [], []
    metrics += [Metric(id="court_depth", label="Truck court depth", value=round(court["median_m"], 1), unit="m", source=COURT_SRC),
                Metric(id="court_min", label="Shallowest point", value=round(court["min_m"], 1), unit="m", source=COURT_SRC),
                Metric(id="dock_wall", label="Dock wall length", value=round(face["length_m"], 1), unit="m",
                       source=Source(layer="vexcel", method="geometry", confidence="medium", note="Side of Vexcel's footprint"))]

    cst = "pass" if court["median_m"] >= inputs.court_min_m else "warn" if court["median_m"] >= 120 * M_PER_FT else "fail"
    fid = f"truck_access:{k}:court"
    shallow = min(court["rays"], key=lambda r: r["depth_m"])
    checks.append(Check(id="court", rule="Truck court deep enough to back a 53 ft trailer", measured=round(court["median_m"], 1),
                        threshold=inputs.court_min_m, unit="m", status=cst, standard="Warehouse site planning: 130 ft for a 53 ft trailer",
                        findings=[fid]))
    findings.append(Finding(id=fid, title=f"Truck court, {side} side", status=cst, anchor=geo(*shallow["end"]), source=COURT_SRC,
                            media=[ortho_media(s, size)],
                            detail=f"Median {court['median_m']:.0f} m across {len(court['rays'])} rays, shallowest "
                                   f"{court['min_m']:.0f} m, where {shallow['ended_by']}. Needs {inputs.court_min_m:.1f} m "
                                   f"(130 ft). Parked trailers do not end a ray; a fence or kerb may end the court sooner."))
    if cst != "pass":
        ps.append(pin("court_tight", *shallow["end"], "court ends", cst))
    turn_st = "pass" if court["median_m"] >= 2 * WB67_OUTER_M and face["length_m"] >= 2 * WB67_OUTER_M else "warn"
    checks.append(Check(id="turnaround", rule="Room for a WB-67 to turn around inside the court", measured=round(min(court["median_m"], face["length_m"]), 1),
                        threshold=round(2 * WB67_OUTER_M, 1), unit="m", status=turn_st,
                        standard="AASHTO WB-67, 45 ft design turning radius"))

    route_pts, chokes = [], []
    gate_txt = "Gate: unknown (no street data)."
    drive_m = 0.0
    if e:
        mouth = e["mouth_ll"]
        sd = e["street_dir"]
        mx, my = e["mouth"]
        before = back(mx - sd[0] * 40, my - sd[1] * 40)
        drive_ll = [back(*p) for p in e["drive"].coords]
        # straight from the driveway mouth into the nearest edge of the court, then to the doors. Mapped service
        # ways often loop round other buildings, so they only pick the mouth.
        ring = court_poly.exterior
        ent = ring.interpolate(ring.project(Point(mx, my)))
        entry = back(ent.x, ent.y)
        route_pts = [before, mouth] + ([entry] if dist_m(entry, mouth) > 3 else []) + [stage]
        drive_m = sum(dist_m(a, b) for a, b in pairwise(route_pts[1:]))
        L = max(math.hypot(ent.x - mx, ent.y - my), 1e-9)
        e["drive_dir"] = ((ent.x - mx) / L, (ent.y - my) / L) if L > 3 else e["drive_dir"]
        runs = [paved_run(photo, lat0, back(mx + e["drive_dir"][0] * t, my + e["drive_dir"][1] * t), e["drive_dir"])
                for t in range(6, int(min(20, max(7, L))) + 1, 2)]
        runs = [r for r in runs if r is not None]
        width = round(statistics.median(runs), 1) if runs else None  # islands and paint spoil single cross-sections
        wst = "unknown" if width is None else "pass" if width >= inputs.entrance_min_m else "warn" if width >= 3.7 else "fail"
        fid = f"truck_access:{k}:entrance"
        checks.append(Check(id="entrance", rule="Entrance wide enough for a WB-67 to turn in", measured=width,
                            threshold=inputs.entrance_min_m, unit="m", status=wst, findings=[fid],
                            standard="AASHTO WB-67 swept width in a 90 degree turn"))
        metrics.append(Metric(id="entrance_width", label="Entrance width", value=width, unit="m", source=WIDTH_SRC))
        findings.append(Finding(id=fid, title=f"Entrance from {e['street']['tags']['name']}", status=wst, anchor=geo(*mouth),
                                source=WIDTH_SRC if width is not None else OSM_SRC, media=[ortho_media(s, size)],
                                detail=(f"Paved width {width:.1f} m, the median of cross-sections 6 to 20 m in from the street"
                                        if width is not None else "Width could not be read on the photo") +
                                       (". The driveway is mapped in OpenStreetMap." if e["mapped"] else
                                        ". OpenStreetMap maps no driveway here; the point is the nearest street edge.")))
        chokes.append((mouth, width or 0.0, wst))
        ps.append(pin("entrance", *mouth, "truck entrance", wst))
        gs = gates_near(o, mouth, drive_ll, lat0)
        gv = None
        if inputs.use_vision:
            try:
                gv = gate_vision(s, mouth)
            except Exception:  # noqa: BLE001
                gv = None
        if gs:
            gate_txt = "A gate is mapped on the drive: expect to check in."
        elif gv and gv["gate"] in ("closed gate", "open gate"):
            gate_txt = f"The photo shows a {gv['gate']} at the entrance: expect to check in."
        elif gv and gv["gate"] == "no gate":
            gate_txt = "No gate is mapped or visible at the entrance."
        else:
            gate_txt = "No gate is mapped; the photo is unclear."
        gst = "warn" if gs or (gv and gv["gate"] in ("closed gate", "open gate")) else "pass" if gv and gv["gate"] == "no gate" else "unknown"
        findings.append(Finding(id=f"truck_access:{k}:gate", title="Gate at the entrance", status=gst, anchor=geo(*mouth),
                                source=OSM_SRC if gs else Source(layer="model", method="vision", confidence=(gv or {}).get("confidence", "low"),
                                                                 note="Vision model on a 50 m orthophoto crop of the entrance"),
                                detail=gate_txt + (f" ({gv['note']})" if gv else ""),
                                media=[ortho_media(s, size)]))
    else:
        route_pts = [court_c, stage]
        findings.append(Finding(id=f"truck_access:{k}:street", title="Approach street unknown", status="unknown",
                                anchor=geo(*court_c), source=OSM_SRC,
                                detail="No named street found in OpenStreetMap near the site" + (f" ({osm_error})" if osm_error else "") + "."))

    # overhead: the surface model along the drive line
    over = []
    if len(route_pts) > 2 and ref_z is not None:
        line = []
        for a, b in pairwise(route_pts[1:]):
            n = max(1, int(dist_m(a, b) / 4))
            line += [(a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n) for i in range(n)]
        zs = heights("dsm", line) if line else []
        for p, z in zip(line, zs):
            if z - ref_z > OVERHEAD_M and dist_m(p, stage) > 20:
                over.append((p, z - ref_z))
    lows = []
    for l in (o or {}).get("low_limits") or []:
        if l["tags"].get("railway"):  # level crossings tagged "below_default" carry no usable height
            continue
        p = min(l["points"], key=lambda q: dist_m(q, (c.x, c.y)))
        if dist_m(p, (c.x, c.y)) <= 1000:
            lows.append({**l, "points": [p], "dist_m": dist_m(p, (c.x, c.y)), "dir": compass(bearing((c.x, c.y), p))})
    lows.sort(key=lambda l: l["dist_m"])
    if over:
        p, h = max(over, key=lambda t: t[1])
        fid = f"truck_access:{k}:overhead"
        findings.append(Finding(id=fid, title="Something over or beside the drive line", status="warn", anchor=geo(*p),
                                source=Source(layer="vexcel", method="geometry", confidence="low",
                                              note="Surface model along the route; cannot tell a tree canopy from a parked truck"),
                                media=[ortho_media(s, size)],
                                detail=f"{len(over)} points on the route stand {OVERHEAD_M} m or more above the ground, up to "
                                       f"{h:.1f} m: tree limbs, a canopy or a parked vehicle. Check before sending a 13 ft 6 in trailer."))
        ps.append(pin("overhead", *p, "overhead?", "warn"))
    for i, l in enumerate(lows[:5]):
        ps.append(pin(f"low_{i}", *l["points"][0], "low clearance", "warn"))
    checks.append(Check(id="low_clearance", rule="Posted clearances under 13 ft 6 in within 1 km", measured=len(lows),
                        threshold=0, unit="", status="warn" if lows else "pass" if o else "unknown",
                        findings=[f"truck_access:{k}:low"] if lows else []))
    if lows:
        findings.append(Finding(id=f"truck_access:{k}:low", title="Low clearances near the site", status="warn",
                                anchor=geo(*lows[0]["points"][0]), source=OSM_SRC,
                                detail="; ".join(low_text(l) for l in lows[:6]) + ". From OpenStreetMap; unmapped limits are not known."))

    # trailer parking: the record, and trailers on the parcel on capture day
    rec = sv["record"]
    if rec.get("trailer_spaces"):
        metrics.append(Metric(id="trailer_spaces", label="Trailer spaces in the record", value=rec["trailer_spaces"]["value"],
                              unit="", source=Source(layer="costar", method="lookup", confidence="medium", note=rec["trailer_spaces"]["path"])))
    try:
        tr = aerial_detect.detect(c.y, c.x, size, ["semi trailer"], threshold=0.3)
        pm = metres(pc, lat0) if pc is not None else None
        on = [d for d in tr["detections"] if d["image"] == "spherical-ortho"
              and (pm is None or pm.buffer(5).contains(Point(fwd(*d["anchor"]["geo"]))))]
        metrics.append(Metric(id="trailers_seen", label="Trailers on site on capture day", value=len(on), unit="",
                              source=Source(layer="vexcel", method="vision", confidence="low",
                                            note=f"Vexcel SAM 3 'semi trailer' on the orthophoto, capture {capture(s)}")))
    except Exception as err:  # noqa: BLE001  trailer count is extra; the verdict stands without it
        ctx.step(f"Trailer count skipped: {str(err)[:120]}")

    n_doors = len(by.get(side, []))
    text_dir = directions(e, gate_txt, side, face["bearing"], n_doors, court["median_m"], drive_m, lows) if e else \
        "Street data is missing, so no arrival directions."
    findings.insert(0, Finding(id=f"truck_access:{k}:directions", title="Arrival directions", status="unknown" if not e else "pass",
                               anchor=geo(*(e["mouth_ll"] if e else court_c)), source=OSM_SRC, detail=text_dir))
    ps.append(pin("dock", *stage, f"{side} docks", cst))
    overlays = [geo_route(route_pts, "Truck route to the docks", chokes)] + pins(ps)
    worst = "fail" if any(c.status == "fail" for c in checks) else "warn" if any(c.status == "warn" for c in checks) else "pass"
    tight = [c.rule[0].lower() + c.rule[1:] for c in checks if c.status in ("fail", "warn")]
    text = (f"A 53 ft trailer {'can' if worst == 'pass' else 'can probably' if worst == 'warn' else 'may not'} reach the "
            f"{side} docks" + (f" from {e['street']['tags']['name']}" if e else "") + "." +
            (f" Tight: {'; '.join(tight)}." if tight else "") + f" Imagery {capture(s)}.")
    return ToolResult(scope=s.scope, verdict=Verdict(status=worst, text=text), metrics=metrics, checks=checks,
                      findings=findings, overlays=overlays,
                      assumptions=[{"id": "truck.court_min_m", "label": "Court depth needed", "value": inputs.court_min_m,
                                    "unit": "m", "editable": True},
                                   {"id": "truck.entrance_min_m", "label": "Entrance width needed", "value": inputs.entrance_min_m,
                                    "unit": "m", "editable": True},
                                   {"id": "vehicle", "label": "Design vehicle", "value": "WB-67, 53 ft trailer, 45 ft turning radius"},
                                   {"id": "dock_side", "label": "Dock wall", "value": face_note}])
