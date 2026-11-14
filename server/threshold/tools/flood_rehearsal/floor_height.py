"""How high the finished floor stands above the ground outside the entry, from independent estimates.

Each method returns a value, an error (one standard error, metres), a confidence and a note, or None with the
reason. `combine` takes the most precise one as the number, and widens its range to take in any other
medium- or high-confidence estimate that disagrees. A lower bound (the step at an exterior door) clips the range.

Methods
- drone_pixels: an RTK drone photo looking at a door. The vision model boxes the threshold and the ground at the
  foot of the wall; the calibrated focal length turns rows into angles and the laser range finder gives the
  distance to the wall. Height = distance x (tan of the threshold's angle - tan of the ground's angle).
- drone_laser_ground: the same threshold, against the ground where steep photos' laser hits land near the door.
- scan_outdoor: the Matterport capture's outdoor panoramas near the entry stand on the ground; the camera height
  measured on indoor panoramas (panorama z minus the room's floor) gives the ground's z.
- vexcel_eave: Vexcel surface model at the eave minus the surface model on the ground beside the house, minus
  the wall height from the scan (ceiling plus framing). One-storey scans only.
- door_step: an exterior doorway whose sill lies below the room's floor shows the step down outside. The yard is
  at or below that, so the floor is at least that high: a lower bound.
"""
from __future__ import annotations

import io
import math
import statistics
from collections.abc import Callable

from PIL import Image
from shapely import wkt as shapely_wkt
from shapely.geometry import LineString, Point, Polygon

from ...geometry._plan import floor_z, polygons, room_floor_z

ENTRY_LABELS = ("Entrance", "Foyer", "Living Room", "Hallway", "Family Room", "Dining Room", "Kitchen")
NEAR_DOOR_M = 8.0
FRAMING_M, FRAMING_ERR_M = 0.30, 0.15      # top plates, joists and soffit between the ceiling and the eave
THRESHOLD_TO_FLOOR_M = 0.03                 # a threshold strip stands about this far above the finished floor
DRONE_PX = 1600                             # whole photo sent to find the door
CROP_PX = 1000                              # crop around the door sent to find the threshold and ground lines
BOX_ERR = 0.012                             # the model's box edges: about 1.2% of the image they are drawn on


def _est(method: str, value: float, err: float, confidence: str, note: str, **evidence) -> dict:
    return {"method": method, "value_m": round(value, 3), "err_m": round(err, 3), "confidence": confidence,
            "note": note, "evidence": evidence}


def _local(lat0: float, lon0: float):
    kx, ky = 111320.0 * math.cos(math.radians(lat0)), 110574.0
    return (lambda lon, lat: ((lon - lon0) * kx, (lat - lat0) * ky)), (lambda x, y: (lon0 + x / kx, lat0 + y / ky))


# ---- scan --------------------------------------------------------------------------------------

def exterior_doors(plan: dict) -> list[dict]:
    """Exterior doorways (one room) on the lowest floor, best entry first: entry-like rooms before garages."""
    if not plan.get("floors"):
        return []
    fz = floor_z(plan)
    lowest = min(fz, key=fz.get)
    labels = {r["id"]: r.get("label") for r in plan.get("rooms") or []}
    doors = [o for o in plan.get("openings") or [] if o["type"] == "doorway" and len(o.get("rooms") or []) == 1
             and o["floor"] == lowest]

    def rank(o):
        lab = labels.get(o["rooms"][0]) or ""
        return (lab == "Garage", ENTRY_LABELS.index(lab) if lab in ENTRY_LABELS else len(ENTRY_LABELS), -(o["width"] or 0))
    return sorted(doors, key=rank)


def outdoor_panos(plan: dict) -> list[dict]:
    """Panoramas standing outside every walled room polygon of their floor."""
    polys = polygons(plan)
    walled = [(r["floor"], polys[r["id"]]) for r in plan.get("rooms") or [] if r.get("walls") and polys[r["id"]] is not None]
    out = []
    for p in plan.get("panos") or []:
        pt = Point(p["position"][:2])
        if not any(f == p.get("floor") and poly.buffer(0.15).contains(pt) for f, poly in walled):
            out.append(p)
    return out


def camera_height(plan: dict) -> tuple[float, float, int] | None:
    """Median and spread of panorama height above the room floor, over panoramas in walled rooms."""
    rz = room_floor_z(plan)
    walled = {r["id"] for r in plan.get("rooms") or [] if r.get("walls")}
    h = [p["position"][2] - rz[p["room"]] for p in plan.get("panos") or [] if p.get("room") in walled]
    if len(h) < 3:
        return None
    q = statistics.quantiles(h, n=4)
    return statistics.median(h), (q[2] - q[0]) / 1.35, len(h)


def scan_outdoor(plan: dict, door: dict | None) -> dict | None:
    if door is None:
        return None
    cam = camera_height(plan)
    near = [p for p in outdoor_panos(plan) if math.dist(p["position"][:2], door["center"]) <= NEAR_DOOR_M]
    if cam is None or not near:
        return None
    floor = room_floor_z(plan)[door["rooms"][0]]
    ground = [p["position"][2] - cam[0] for p in near]
    g = statistics.median(ground)
    spread = (statistics.quantiles(ground, n=4)[2] - statistics.quantiles(ground, n=4)[0]) / 1.35 if len(ground) >= 4 else 0.1
    err = math.sqrt(cam[1] ** 2 + spread ** 2 + 0.05 ** 2 + (0.1 / math.sqrt(len(near))) ** 2)
    return _est("scan_outdoor", floor - g, max(err, 0.06), "medium" if len(near) >= 3 else "low",
                f"{len(near)} outdoor panoramas within {NEAR_DOOR_M:.0f} m of the entry, camera "
                f"{cam[0]:.2f} m above the floor on {cam[2]} indoor panoramas. Assumes the tripod stayed at that "
                "height outside; a panorama on a walkway or porch reads high ground, so the floor reads low.",
                panos=[p["id"] for p in near], camera_m=round(cam[0], 3), door=door["id"])


def door_step(plan: dict) -> dict | None:
    rz = room_floor_z(plan)
    labels = {r["id"]: r.get("label") for r in plan.get("rooms") or []}
    steps = [(rz[o["rooms"][0]] - o["sill"], o) for o in exterior_doors(plan)
             if o.get("sill") is not None and labels.get(o["rooms"][0]) != "Garage"]
    steps = [(s, o) for s, o in steps if 0.03 <= s <= 1.0]
    if not steps:
        return None
    s, o = max(steps, key=lambda x: x[0])
    return _est("door_step", s, 0.03, "medium", "An exterior doorway's sill lies below the room's floor: the step down "
                "outside. The ground is at or below the step, so this is a lower bound.", door=o["id"])


# ---- Vexcel surface model ------------------------------------------------------------------------

def footprint_xy(footprint_wkt: str, to_xy) -> Polygon:
    """The footprint in local metres; of a MultiPolygon, the biggest part (the house, not a shed)."""
    g = shapely_wkt.loads(footprint_wkt)
    g = max(getattr(g, "geoms", [g]), key=lambda x: x.area)
    return Polygon([to_xy(*c) for c in g.exterior.coords])


def vexcel_eave(plan: dict, footprint_wkt: str | None, lat0: float, lon0: float,
                dsm: Callable[[list[tuple[float, float]]], list[float]]) -> dict | None:
    floors = plan.get("floors") or []
    if len(floors) != 1 or not footprint_wkt:
        return None
    ceil = [r["height"] for r in plan.get("rooms") or [] if r.get("height")]
    if not ceil:
        return None
    to_xy, to_ll = _local(lat0, lon0)
    fp = footprint_xy(footprint_wkt, to_xy)
    inner, outer = fp.buffer(-0.8).exterior, fp.buffer(2.5).exterior
    pts_in = [inner.interpolate(d) for d in range(0, int(inner.length), 2)]
    pts_out = [outer.interpolate(d) for d in range(0, int(outer.length), 2)]
    if len(pts_in) < 6:
        return None
    z = dsm([to_ll(p.x, p.y) for p in pts_in + pts_out])
    zin, zout = z[:len(pts_in)], z[len(pts_in):]
    eave = statistics.quantiles(zin, n=5)[0]
    ground = statistics.quantiles(zout, n=4)[0]
    wall = statistics.median(ceil) + FRAMING_M
    return _est("vexcel_eave", eave - ground - wall, math.sqrt(0.3 ** 2 + FRAMING_ERR_M ** 2), "low",
                f"Vexcel surface model: eave (20th percentile 0.8 m inside the footprint) stands {eave - ground:.2f} m "
                f"above the ground 2.5 m outside (lower quartile); minus a {statistics.median(ceil):.2f} m ceiling and "
                f"{FRAMING_M:.2f} m of framing. The model's grid blurs the eave and catches shrubs.",
                eave_m=round(eave, 2), ground_m=round(ground, 2), wall_m=round(wall, 2))


def ground_grade(footprint_wkt: str | None, lat0: float, lon0: float,
                 dtm: Callable[[list[tuple[float, float]]], list[float]]) -> dict | None:
    """Bare-ground heights 3 m around the house: how far the ground falls across the lot and the low side.
    Relative heights within one Vexcel model; the absolute datum does not matter here."""
    if not footprint_wkt:
        return None
    to_xy, to_ll = _local(lat0, lon0)
    fp = footprint_xy(footprint_wkt, to_xy)
    ring = fp.buffer(3.0).exterior
    pts = [ring.interpolate(d) for d in range(0, int(ring.length), 3)]
    z = dtm([to_ll(p.x, p.y) for p in pts])
    c = fp.centroid
    lo = min(range(len(z)), key=z.__getitem__)
    az = math.degrees(math.atan2(pts[lo].x - c.x, pts[lo].y - c.y)) % 360
    side = ["north", "northeast", "east", "southeast", "south", "southwest", "west", "northwest"][int((az + 22.5) // 45) % 8]
    return {"fall_m": round(max(z) - min(z), 2), "low_side": side, "low_lonlat": to_ll(pts[lo].x, pts[lo].y),
            "points": [{"lonlat": to_ll(p.x, p.y), "z": round(v, 2)} for p, v in zip(pts, z)]}


# ---- drone ------------------------------------------------------------------------------------------

DOOR_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["door_visible", "door", "kind", "confidence"],
               "properties": {"door_visible": {"type": "boolean"},
                              "door": {"type": "object", "additionalProperties": False, "required": ["x0", "y0", "x1", "y1"],
                                       "properties": {k: {"type": "integer"} for k in ("x0", "y0", "x1", "y1")}},
                              "kind": {"type": "string", "enum": ["front entry door", "side or back door", "patio or sliding door", "none"]},
                              "confidence": {"type": "string", "enum": ["high", "medium", "low"]}}}
LINE = {"type": "object", "additionalProperties": False, "required": ["x0", "y0", "x1", "y1"],
        "properties": {k: {"type": "integer"} for k in ("x0", "y0", "x1", "y1")}}
LINES_SCHEMA = {"type": "object", "additionalProperties": False,
                "required": ["threshold", "ground", "steps_between", "ground_visible", "confidence"],
                "properties": {"threshold": LINE, "ground": LINE, "ground_visible": {"type": "boolean"},
                               "steps_between": {"type": "integer", "description": "Steps or porch levels from the yard up to the threshold"},
                               "confidence": {"type": "string", "enum": ["high", "medium", "low"]}}}


def _jpeg(im: Image.Image, px: int) -> bytes:
    s = px / max(im.size)
    im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS) if abs(s - 1) > 1e-3 else im
    buf = io.BytesIO()
    im.convert("RGB").save(buf, "JPEG", quality=88)
    return buf.getvalue()


# Drones without calibrated intrinsics in their metadata: focal length in px of the full-size image, from the
# 35 mm equivalent in the photos' EXIF over the image diagonal (Mavic 3: Hasselblad L2D-20c, 24 mm, 5280 x 3956;
# Mavic 4 Pro: L3D-100c, 28 mm, 6144 x 4096; read from the files on 2026-11-14).
FOCAL_BY_PRODUCT = {"DJIMavic3": (24 * math.hypot(5280, 3956) / 43.27, 5280, 3956),
                    "Mavic4 Pro L3A": (28 * math.hypot(6144, 4096) / 43.27, 6144, 4096)}


def heading(p: dict) -> float:
    """Compass direction of the camera. The Matrice 4E's gimbal yaw is a compass heading; on the Mavic 3 and 4
    flights it is not (100 to 215 degrees off the bearing to the house), while the flight yaw points at the house
    within a few degrees, so with the gimbal centred the flight yaw is used."""
    g, f = p.get("gimbal_yaw_deg"), p.get("flight_yaw_deg")
    if f is None or g is None or abs((g - f + 180) % 360 - 180) < 20:
        return g if g is not None else f
    return f


def intrinsics(p: dict) -> dict | None:
    if p.get("focal_px"):
        return {"focal_px": p["focal_px"], "cx_px": p["cx_px"], "cy_px": p["cy_px"], "intrinsics": "calibrated"}
    f = FOCAL_BY_PRODUCT.get(p.get("product") or "")
    return {"focal_px": f[0], "cx_px": f[1] / 2, "cy_px": f[2] / 2, "intrinsics": "published"} if f else None


def wall_distance(p: dict, fp_xy: Polygon, to_xy) -> tuple[float, str] | None:
    """Horizontal distance to the house along the optical axis: the laser's, else the GPS ray to the footprint."""
    cam = to_xy(p["lon"], p["lat"])
    if p.get("lrf_lat") is not None and p.get("lrf_m"):
        hit = to_xy(p["lrf_lon"], p["lrf_lat"])
        return (math.dist(cam, hit), "laser") if fp_xy.buffer(1.5).contains(Point(hit)) else None
    b = math.radians(heading(p))
    ray = LineString([cam, (cam[0] + 60 * math.sin(b), cam[1] + 60 * math.cos(b))])
    x = ray.intersection(fp_xy.exterior)
    pts = [Point(c) for g in getattr(x, "geoms", [x]) for c in getattr(g, "coords", [])]
    return (min(Point(cam).distance(q) for q in pts), "gps") if pts else None


def drone_candidates(photos: list[dict], fp_xy: Polygon, to_xy) -> list[dict]:
    """Low, near-level photos aimed at the house, one per side, lowest first; RTK and laser ones first."""
    ok = []
    for p in photos:
        if None in (p.get("alt"), p.get("gimbal_pitch_deg"), p.get("lat"), p.get("gimbal_yaw_deg")):
            continue
        if p["alt"] > 6 or not -25 <= p["gimbal_pitch_deg"] <= 5:
            continue
        k, d = intrinsics(p), wall_distance(p, fp_xy, to_xy)
        if k is None or d is None or d[0] > 40:
            continue
        ok.append({**p, **k, "wall_m": d[0], "wall_source": d[1]})
    ok.sort(key=lambda p: (p["wall_source"] != "laser", p["alt"], abs(p["gimbal_pitch_deg"])))
    out, yaws = [], []
    for p in ok:
        if all(abs((heading(p) - y + 180) % 360 - 180) > 25 for y in yaws):
            out.append(p)
            yaws.append(heading(p))
    return out


def drone_heights(photo: dict, img_w: int, u: float, v_thr: float, v_gnd: float, to_xy) -> dict:
    """Threshold and ground altitudes (photo's absolute frame) from pixel rows in an image `img_w` wide."""
    s = img_w / (2 * photo["cx_px"])
    f, cx, cy = photo["focal_px"] * s, photo["cx_px"] * s, photo["cy_px"] * s
    cam = to_xy(photo["lon"], photo["lat"])
    d_h = photo.get("wall_m") or math.dist(cam, to_xy(photo["lrf_lon"], photo["lrf_lat"]))
    phi = math.atan2(u - cx, f)
    d = d_h / math.cos(phi)                         # wall taken as square to the view, near the image centre

    def alt(v):
        return photo["alt_abs"] + d * math.tan(math.radians(photo["gimbal_pitch_deg"]) + math.atan2(cy - v, f))
    bearing = math.radians(heading(photo)) + phi
    door_xy = (cam[0] + d * math.sin(bearing), cam[1] + d * math.cos(bearing))
    lrf_pred = photo["alt_abs"] + d_h * math.tan(math.radians(photo["gimbal_pitch_deg"]))
    check = photo["lrf_alt_abs"] - lrf_pred if photo.get("lrf_alt_abs") is not None else None
    return {"threshold_abs": alt(v_thr), "ground_abs": alt(v_gnd), "distance_m": d, "focal_scaled": f,
            "door_xy": door_xy, "laser_check_m": check}


def drone_threshold(sid: str, footprint_wkt: str | None, lat0: float, lon0: float, *, photos: list[dict],
                    image: Callable[[str, int], bytes], ask: Callable, max_photos: int = 5) -> tuple[list[dict], dict]:
    """Drone estimates (pixel ground and laser ground) and a trace of what was tried."""
    trace: dict = {"photos_listed": len(photos), "tried": []}
    if not footprint_wkt:
        trace["reason"] = "No Vexcel footprint to tell which laser hits landed on the house."
        return [], trace
    to_xy, _ = _local(lat0, lon0)
    fp = footprint_xy(footprint_wkt, to_xy)
    cands = drone_candidates(photos, fp, to_xy)
    trace["candidates"] = [p["name"] for p in cands]
    found = []
    for p in cands[:max_photos]:
        full = Image.open(io.BytesIO(image(p["name"], 4000)))
        a = ask([_jpeg(full, DRONE_PX)], "A drone photo of a house, taken from low height. Is an exterior door of this "
                "house visible (not a garage door)? If so, box the door opening including its frame, in pixels of this "
                f"{DRONE_PX}-pixel-wide image. If several are visible, box the one nearest the centre.",
                DOOR_SCHEMA, key=f"flood_door/{sid}/{p['name']}")
        t = {"photo": p["name"], "door_visible": a["door_visible"], "kind": a["kind"], "confidence": a["confidence"]}
        trace["tried"].append(t)
        if not a["door_visible"] or a["kind"] == "none" or a["confidence"] == "low":
            continue  # a low-confidence "door" was a raised patio under windows
        k = full.width / DRONE_PX
        b = a["door"]
        dh = (b["y1"] - b["y0"]) * k
        side = max(2.4 * dh, 500)
        cx0, cy0 = (b["x0"] + b["x1"]) / 2 * k, b["y1"] * k
        box = (max(0, cx0 - side / 2), max(0, cy0 - side * 0.6), min(full.width, cx0 + side / 2),
               min(full.height, cy0 + side * 0.4))
        crop = full.crop(tuple(round(x) for x in box))
        cs = CROP_PX / max(crop.size)
        lines = ask([_jpeg(crop, CROP_PX)], f"A crop ({crop.width * cs:.0f} by {crop.height * cs:.0f} pixels) of a drone "
                    "photo around a house door. Draw two thin boxes in pixels of this crop. 'threshold': along the door's "
                    "threshold, the line where the bottom of the door meets the floor of the house. 'ground': along the "
                    "line where the surrounding yard or ground (lawn, soil, mulch, or a walk at yard level) meets the "
                    "house's wall or foundation, as close to the door as you can see it; not the top of a porch or step. "
                    "Say how many steps or porch levels lie between the yard and the threshold.",
                    LINES_SCHEMA, key=f"flood_sill/{sid}/{p['name']}")
        t.update(lines_confidence=lines["confidence"], steps=lines["steps_between"], ground_visible=lines["ground_visible"])
        thr, gnd = lines["threshold"], lines["ground"]
        apart = abs((gnd["x0"] + gnd["x1"]) / 2 - (thr["x0"] + thr["x1"]) / 2) / CROP_PX
        t["ground_offset"] = round(apart, 2)
        if not lines["ground_visible"] or apart > 0.25:
            continue  # ground marked off to the side may lie on another wall at another distance
        u = box[0] + (thr["x0"] + thr["x1"]) / 2 / cs
        v_thr = box[1] + (thr["y0"] + thr["y1"]) / 2 / cs
        v_gnd = box[1] + (gnd["y0"] + gnd["y1"]) / 2 / cs
        h = drone_heights(p, full.width, u, v_thr, v_gnd, to_xy)
        sig_px = BOX_ERR * CROP_PX / cs
        ffh = h["threshold_abs"] - h["ground_abs"] - THRESHOLD_TO_FLOOR_M
        sig = h["distance_m"] * sig_px / h["focal_scaled"] * math.sqrt(2)
        if p["wall_source"] == "gps":  # about 2 m of GPS and footprint error in the distance, 3% in a published focal
            sig = math.hypot(sig, abs(ffh) * 2.0 / max(h["distance_m"], 1), abs(ffh) * 0.03)
        t.update(ffh_m=round(ffh, 3), err_m=round(sig, 3), distance_m=round(h["distance_m"], 2),
                 distance_from=p["wall_source"], intrinsics=p["intrinsics"],
                 laser_check_m=round(h["laser_check_m"], 3) if h["laser_check_m"] is not None else None,
                 crop=[round(x) for x in box])
        found.append((p, h, sig, t))
    if not found:
        trace["reason"] = trace.get("reason") or ("No low drone photo aimed at the house showed a door with the ground "
                                                  "beside it." if cands else "No low, level drone photo aimed at the "
                                                  "house with a known focal length.")
        return [], trace
    ffh = [t["ffh_m"] for *_, t in found]
    spread = statistics.pstdev(ffh) if len(ffh) > 1 else 0.0
    err = max(spread, math.sqrt(statistics.fmean(s ** 2 for _, _, s, _ in found)), 0.03)
    laser = all(p["wall_source"] == "laser" for p, *_ in found)
    conf = "high" if laser and len(found) >= 2 and spread < 0.08 else "medium"
    out = [_est("drone_pixels", statistics.fmean(ffh), err, conf,
                f"{len(found)} drone photo(s) facing a door: the model marked the threshold and the ground at the foot "
                "of the wall; the focal length and the distance to the wall turn those rows into heights. "
                + ("Calibrated focal length and laser distance (RTK drone)." if laser else
                   "Distance from the GPS position to the Vexcel footprint along the view, focal length from the "
                   "camera's published specification.") + " Assumes the wall is square to the view.",
                photos=[t["photo"] for *_, t in found])]
    # Ground from laser hits that landed near the door, outside the house, from steeper photos.
    _, h0, *_ = found[0]
    door = h0["door_xy"]
    near = [q["lrf_alt_abs"] for q in photos if q.get("lrf_lat") is not None and q.get("lrf_alt_abs") is not None
            and (q.get("gimbal_pitch_deg") or 0) < -15
            and 1.0 <= math.dist(to_xy(q["lrf_lon"], q["lrf_lat"]), door) <= 10
            and not fp.buffer(0.5).contains(Point(to_xy(q["lrf_lon"], q["lrf_lat"])))]
    trace["laser_ground_hits"] = len(near)
    if len(near) >= 2:
        g = statistics.median(near)
        thr = statistics.fmean(h["threshold_abs"] for _, h, _, _ in found)
        sp = statistics.pstdev(near)
        out.append(_est("drone_laser_ground", thr - g - THRESHOLD_TO_FLOOR_M, math.sqrt(sp ** 2 + err ** 2 / 2 + 0.03 ** 2),
                        "medium" if len(near) >= 3 else "low",
                        f"The same threshold against {len(near)} laser hits on the ground within 10 m of the door (RTK "
                        "altitudes). The hits may land on a driveway or a lower part of the yard.", hits=len(near)))
    return out, trace


# ---- combine -------------------------------------------------------------------------------------

def combine(estimates: list[dict], bound: dict | None = None, override: float | None = None) -> dict:
    """The number, its range, and how the independent estimates agree."""
    if override is not None:
        e = _est("measured", override, 0.02, "high", "You measured it.")
        estimates = [e] + estimates
    pts = [e for e in estimates if e]
    if not pts:
        return {"available": False, "reason": "No method could measure the floor height here.", "estimates": [],
                "bound": bound}
    best = min(pts, key=lambda e: (e["method"] != "measured", e["err_m"]))
    lo, hi = best["value_m"] - best["err_m"], best["value_m"] + best["err_m"]
    widened = []
    for e in pts:
        if e is best or e["confidence"] == "low" or best["method"] == "measured":
            continue
        if not lo <= e["value_m"] <= hi:
            lo, hi = min(lo, e["value_m"]), max(hi, e["value_m"])
            widened.append(e["method"])
    clipped = False
    if bound and lo < bound["value_m"]:
        lo, clipped = bound["value_m"], True
        hi = max(hi, lo)
    lo = max(lo, 0.0)
    hi = max(hi, lo)  # an estimate below the ground must not leave the range upside down
    pairs = [{"a": a["method"], "b": b["method"], "diff_m": round(a["value_m"] - b["value_m"], 3)}
             for i, a in enumerate(pts) for b in pts[i + 1:]]
    return {"available": True, "value_m": round(min(max(best["value_m"], lo), hi), 3), "lo_m": round(lo, 3),
            "hi_m": round(hi, 3), "method": best["method"], "confidence": best["confidence"], "estimates": pts,
            "bound": bound, "widened_by": widened, "clipped_by_bound": clipped, "agreement": pairs}
