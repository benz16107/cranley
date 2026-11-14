"""Detection by name from the air: Vexcel Custom Elements (SAM 3) first, the vision model on the ortho second.

Request shape (from Vexcel's Elements101 sample, confirmed with our key on 2026-11-13): `wkt` + `srid` +
`buffer-meter`, an `images` array whose items name an `endpoint` ("ortho/extract" or "oriented/extract")
and its `request`, and `model-input.elements[]` of `{label, model: "sam3", detection-threshold}`. Leaving
out `images[].endpoint` gives the 400 "Parameter 'endpoint' is mandatory".
"""
from __future__ import annotations

from shapely import wkt as shapely_wkt

from . import site, vexcel

DETECT_LAYERS = "urban,urban-r,wide-area"
# SAM 3 also returns whole rows and whole lots for "parking space" (seen 2026-11-13 at an apartment lot and
# a warehouse). A stall is about 14 m2 and a car about 9, so larger ortho boxes for these are dropped.
MAX_AREA_M2 = {"parking space": 30.0, "car": 30.0}


def _vexcel(lat: float, lon: float, size_m: float, labels: list[str], obliques: bool, threshold: float) -> dict:
    pt = site.point(lat, lon)
    images = [{"endpoint": "ortho/extract", "request": {"layer": DETECT_LAYERS, "srid": 4326, "wkt": pt}}]
    if obliques:
        coll, dirs = site.oblique_directions(lat, lon)
        images += [{"endpoint": "oriented/extract", "request": {"layer": DETECT_LAYERS, "srid": 4326, "wkt": pt,
                                                                 "product-type": d, "collection": coll}} for d in dirs]
    body = {"wkt": pt, "srid": 4326, "buffer-meter": size_m / 2, "images": images,
            "model-input": {"elements": [{"label": l, "model": "sam3", "detection-threshold": threshold} for l in labels],
                            "include": ["bbox", "confidence", "pixel-bbox"]}}
    r = vexcel.post_json("elements/detect", body)
    kinds = {i["image-id"]: (i.get("metadata") or {}).get("product-type") for i in r.get("images") or []}
    dets = []
    for f in r.get("features") or []:
        for d in f["properties"].get("detections") or []:
            g = shapely_wkt.loads(d["bbox"])
            kind = kinds.get(d.get("imageId"), d.get("imageId"))
            cap = MAX_AREA_M2.get(f["properties"]["label"])
            if cap and kind == "spherical-ortho" and site.area_m2(g, lat) > cap:
                continue
            c = g.centroid
            dets.append({"label": f["properties"]["label"], "confidence": round(d.get("confidence") or 0, 3),
                         "anchor": {"geo": [round(c.x, 7), round(c.y, 7)]}, "polygon": d["bbox"],
                         "image": kind, "pixel_bbox": d.get("pixel-bbox")})
    return {"method": "vexcel-elements", "detections": dets,
            "images": [{"id": k, "product_type": v} for k, v in kinds.items()],
            "source": site.source("lookup", "medium", f"Vexcel Custom Elements (SAM 3), threshold {threshold}. "
                                  "Oblique detections are placed on the ground via Vexcel's elevation model, "
                                  "and one object seen in several images is counted once per image")}


def _vision(lat: float, lon: float, size_m: float, labels: list[str]) -> dict:
    from ..vision.model import BOX, CONFIDENCE, ask
    o = site.ortho(lat, lon, size_m, 1024)
    schema = {"type": "object", "additionalProperties": False, "required": ["detections"], "properties": {"detections": {
        "type": "array", "items": {"type": "object", "additionalProperties": False,
                                   "required": ["label", "box", "confidence"],
                                   "properties": {"label": {"type": "string", "enum": labels}, "box": BOX, "confidence": CONFIDENCE}}}}}
    prompt = (f"This is a north-up aerial orthophoto, {o.width} by {o.height} pixels, about {o.metres_per_px:.2f} m per pixel. "
              f"Find every instance of: {', '.join(labels)}. Give a tight box for each in pixel coordinates "
              "(x0, y0 top left, x1, y1 bottom right). Return an empty list when none are visible.")
    a = ask([o.image], prompt, schema, key=f"aerial_detect/{lat:.6f},{lon:.6f},{size_m}")
    dets = []
    for d in a["detections"]:
        b = d["box"]
        lo0, la0 = o.to_lonlat(b["x0"], b["y1"])
        lo1, la1 = o.to_lonlat(b["x1"], b["y0"])
        dets.append({"label": d["label"], "confidence": d["confidence"],
                     "anchor": {"geo": [round((lo0 + lo1) / 2, 7), round((la0 + la1) / 2, 7)]},
                     "polygon": f"POLYGON(({lo0} {la0},{lo1} {la0},{lo1} {la1},{lo0} {la1},{lo0} {la0}))",
                     "image": "ortho", "pixel_bbox": [b["x0"], b["y0"], b["x1"] - b["x0"], b["y1"] - b["y0"]]})
    return {"method": "vision-fallback", "detections": dets, "images": [{"id": "ortho", "product_type": "spherical-ortho"}],
            "ortho": o.transform(),
            "source": {"layer": "vexcel", "method": "vision", "confidence": "low",
                       "note": "Vision model counted and boxed on the Vexcel orthophoto; positions from the ortho transform"}}


def detect(lat: float, lon: float, size_m: float = 80, labels: list[str] | tuple = ("car",), *,
           obliques: bool = False, threshold: float = 0.4, method: str = "auto") -> dict:
    """Located boxes for each label within a square `size_m` across. method: "auto" (Vexcel, then the vision
    model if Vexcel fails), "vexcel" or "vision"."""
    labels = list(labels)
    error = None
    if method in ("auto", "vexcel"):
        try:
            out = _vexcel(lat, lon, size_m, labels, obliques, threshold)
        except vexcel.VexcelError as e:
            if method == "vexcel":
                raise
            error = str(e)
            out = _vision(lat, lon, size_m, labels)
    else:
        out = _vision(lat, lon, size_m, labels)
    by_image: dict[str, dict[str, int]] = {}
    for d in out["detections"]:
        by_image.setdefault(d["image"], {}).setdefault(d["label"], 0)
        by_image[d["image"]][d["label"]] += 1
    # One object appears once per image that sees it, so a label's count is its count in the single image
    # that sees the most of them (a lower bound when no one image sees every side).
    out["counts"] = {l: max((c.get(l, 0) for c in by_image.values()), default=0) for l in labels}
    out["counts_by_image"] = by_image
    out["vexcel_error"] = error
    return {"lat": lat, "lon": lon, "size_m": size_m, **out}
