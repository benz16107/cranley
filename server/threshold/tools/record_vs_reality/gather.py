"""Evidence from the network: the CoStar record, Vexcel aerial facts and detections, and panorama reads.

Every call goes through an engine that caches on disk (`sources.costar`, `aerial.site`, `aerial.detect`,
`vision.reader`). Tests replace the functions in `SOURCES` with hand-made ones.
"""
from __future__ import annotations

import math
from urllib.parse import urlencode

from shapely import wkt as shapely_wkt
from shapely.geometry import Point, shape

ORTHO_PX = 1024
# Checked by eye on 2026-11-14: Vexcel's SAM 3 boxes whole lots for "parking space", and the vision fallback asked
# for "parking space" boxes parked cars. This label on the vision fallback gets closest; counts are lower bounds.
STALL = "painted parking stall (one striped space, empty or occupied)"
DOCK = "loading dock door"


def _record(sid: str) -> dict | None:
    from ...sources import costar
    try:
        return costar.record(sid)
    except LookupError:
        return None


def _site(lat: float, lon: float) -> dict:
    from ...aerial import site
    return site.site_facts(lat, lon)


def _ortho(lat: float, lon: float, size_m: float):
    from ...aerial import site
    return site.ortho(lat, lon, size_m, ORTHO_PX)


def _detect(lat: float, lon: float, size_m: float, labels: list[str], obliques: bool, method: str) -> dict:
    from ...aerial import detect
    return detect.detect(lat, lon, size_m, labels, obliques=obliques, method=method)


def _objects(plan: dict, labels: list[str], panos: list[str]) -> list[dict]:
    from ...vision import reader
    return reader.find_objects(plan, labels, panos=panos, max_panos=len(panos))


def _labels(plan: dict) -> list[dict]:
    from ...vision import reader
    return reader.label_rooms(plan)


SOURCES = {"record": _record, "site": _site, "ortho": _ortho, "detect": _detect, "objects": _objects, "labels": _labels}


def record(sid: str) -> dict | None:
    return SOURCES["record"](sid)


def latlon(plan: dict, rec: dict | None) -> tuple[float, float] | None:
    """The building's point: the record's geocoded address first (it sits on the building), else the scan's."""
    for a in ((rec or {}).get("property") or {}).get("primaryAddress"), (((rec or {}).get("residential_listing") or {})
                                                                          .get("property") or {}).get("address"):
        if a and a.get("latitude") and a.get("longitude"):
            return float(a["latitude"]), float(a["longitude"])
    g = plan.get("geo") or {}
    return (g["lat"], g["lon"]) if g.get("lat") is not None and g.get("lon") is not None else None


def ortho_ref(lat: float, lon: float, size_m: float) -> str:
    return "aerial/ortho?" + urlencode({"lat": f"{lat:.7f}", "lon": f"{lon:.7f}", "size_m": round(size_m), "px": ORTHO_PX})


def _box(o, polygon_wkt: str) -> tuple[float, float, float, float] | None:
    """A lon/lat polygon as fractions (x0, y0, x1, y1) of the ortho image."""
    g = shapely_wkt.loads(polygon_wkt)
    w, s, e, n = g.bounds
    x0, y0 = o.to_px(w, n)
    x1, y1 = o.to_px(e, s)
    f = [x0 / o.width, y0 / o.height, x1 / o.width, y1 / o.height]
    if max(f) < 0 or min(f) > 1:
        return None
    return tuple(round(min(1.0, max(0.0, v)), 4) for v in f)


def _span_m(site: dict, lat: float) -> float:
    """Side of a square that holds the parcel, clamped to 60 to 240 m."""
    if not site.get("parcel"):
        return 100.0
    w, s, e, n = shape(site["parcel"]).bounds
    side = max((e - w) * 111320.0 * math.cos(math.radians(lat)), (n - s) * 110574.0) * 1.1
    return float(min(240.0, max(60.0, side)))


def aerial(plan: dict, rec: dict | None, kind: str, claim_keys: set[str], detect_on: bool = True) -> dict:
    """Aerial evidence for one scan: site facts, an ortho crop, and (with detect_on) the detections the claims need.
    Stall counting uses the vision model, so callers that promise no model calls pass detect_on=False."""
    ll = latlon(plan, rec)
    if not ll:
        return {"aerial_error": "Neither the record nor the scan gives a location."}
    lat, lon = ll
    ev: dict = {}
    try:
        site = SOURCES["site"](lat, lon)
    except Exception as e:  # noqa: BLE001 - the aerial service is optional evidence; say why it is missing
        return {"aerial_error": f"The aerial service failed: {str(e)[:160]}"}
    ev["site"] = site
    span = _span_m(site, lat)
    ref = ortho_ref(lat, lon, span)
    ev["ortho_ref"] = ref
    ev["ortho_media"] = [{"kind": "ortho", "ref": ref, "box": None}]
    parcel = shape(site["parcel"]) if site.get("parcel") else None
    o = None
    try:
        o = SOURCES["ortho"](lat, lon, span)
    except Exception:  # noqa: BLE001
        pass
    want_parking = detect_on and kind != "home" and bool(claim_keys & {"parking_spaces", "parking_ratio"})
    want_docks = detect_on and "dock_doors" in claim_keys
    for name, labels, obliques, method, on in (("parking", [STALL], False, "vision", want_parking),
                                               ("docks", [DOCK], True, "auto", want_docks)):
        if not on:
            continue
        try:
            d = SOURCES["detect"](lat, lon, span, labels, obliques, method)
        except Exception as e:  # noqa: BLE001
            ev[f"{name}_error"] = str(e)[:160]
            continue
        dets = [x for x in d["detections"] if x["label"] == labels[0]]
        if name == "parking":
            dets = [x for x in dets if x["image"] in ("spherical-ortho", "ortho")]
            if parcel is not None:
                dets = [x for x in dets if parcel.buffer(0.00005).contains(Point(*x["anchor"]["geo"]))]
            count = len(dets)
        else:
            count = d["counts"].get(labels[0], 0)
        media = []
        if o is not None:
            for x in dets[:12]:
                if x["image"] in ("spherical-ortho", "ortho"):
                    b = _box(o, x["polygon"])
                    if b:
                        media.append({"kind": "ortho", "ref": ref, "box": b})
        ev[name] = {"count": count, "detections": dets, "method": d.get("method"), "counts_by_image": d.get("counts_by_image")}
        ev[f"{name}_media"] = media or ev["ortho_media"]
    return ev


# rooms whose central panorama is read for each kind of property, in priority order
HOME_ROOMS = ("Living Room", "Kitchen", "Family Room", "Laundry", "Utility Room", "Dining Room", "Bedroom")


def panoramas(plan: dict, home_like: bool, keys: set[str], max_panos: int = 5) -> dict:
    """Read the central panorama of the rooms that matter for the claims: features and bathrooms in a home or an
    apartment unit, the largest rooms' ceilings elsewhere."""
    from ...vision.reader import room_panos
    rooms = [r for r in plan["rooms"] if r.get("label") != "Void" and room_panos(plan, r)]
    if home_like:
        order = {lab: i for i, lab in enumerate(HOME_ROOMS)}
        rooms = [r for r in rooms if r.get("label") in order]
        rooms.sort(key=lambda r: (order[r["label"]], -(r.get("area") or 0)))
        seen, picked = set(), []
        for r in rooms:  # one room of each type first
            if r["label"] not in seen:
                picked.append(r)
                seen.add(r["label"])
        baths = sorted((r for r in plan["rooms"] if r.get("label") == "Bathroom" and room_panos(plan, r)),
                       key=lambda r: r.get("area") or 0)
        rooms = picked[:max_panos] + baths[:3]  # smallest bathrooms first: they decide full against half
        labels = ["fireplace", "kitchen island", "wood floor", "washer", "dryer", "bathtub", "shower", "toilet"]
        if "has_sprinklers" in keys:
            labels.append("sprinkler head")
    else:
        rooms.sort(key=lambda r: -(r.get("area") or 0))
        labels = ["sprinkler head", "smoke alarm", "exit sign"]
        rooms = rooms[:max_panos]
    if not rooms:
        return {"objects": [], "objects_rooms": [], "objects_error": "No room has a panorama to read."}
    panos = [room_panos(plan, r)[0]["id"] for r in rooms]
    try:
        objs = SOURCES["objects"](plan, labels, panos)
    except Exception as e:  # noqa: BLE001
        return {"objects_error": f"The panorama reader failed: {str(e)[:160]}"}
    fixtures = {r["id"]: set() for r in rooms if r.get("label") == "Bathroom"}
    for o in objs:
        if o.get("room") in fixtures:
            fixtures[o["room"]].add(o["label"])
    return {"objects": objs, "objects_rooms": [r["id"] for r in rooms], "objects_panos": panos, "fixtures": fixtures}


def gather(plan: dict, rec: dict | None, scan: dict, claims: list[dict], *, aerial_on: bool, panos_on: bool,
           detect_on: bool | None = None) -> dict:
    keys = {c["key"] for c in claims}
    ev: dict = {}
    if aerial_on:
        ev.update(aerial(plan, rec, scan["kind"], keys, panos_on if detect_on is None else detect_on))
    if panos_on:
        if keys & {"fireplace", "kitchen_island", "wood_floors", "laundry_in_unit", "has_sprinklers", "baths",
                   "unit_baths", "title_baths"}:
            ev.update(panoramas(plan, scan["kind"] == "home" or scan["scope"] == "unit", keys))
        if not (plan.get("quality") or {}).get("labels", True) and keys & {"beds", "baths", "unit_beds", "title_beds"}:
            try:
                ev["labels"] = SOURCES["labels"](plan)
            except Exception as e:  # noqa: BLE001
                ev["labels_error"] = str(e)[:160]
    st = next((c["value"] for c in claims if c["key"] == "stories" and isinstance(c["value"], (int, float))), None)
    ev["stories"] = int(st) if st else None
    ev["gross_area"] = next((c["value"] for c in claims if c["key"] in ("gross_area", "rentable_area")), None)
    return ev
