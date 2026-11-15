"""Scan data routes (Contract 2 in docs/ARCHITECTURE.md): the scan index and buildings, the ScanPlan, panoramas,
floor plans, the splat, drone photos and the CoStar record. Every upstream response is cached on disk."""
from __future__ import annotations

import functools
import hashlib
import json
import re
import threading

import httpx
from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse

from ..sources import costar, hackathon, index as scan_index, matterport as mp

router = APIRouter(prefix="/api")
JPEG = {"Cache-Control": "max-age=86400"}


def _call(fn, *a, **k):
    """Run a source call; a LookupError is a 404 with its message, and an upstream failure is a 502."""
    try:
        return fn(*a, **k)
    except LookupError as e:
        raise HTTPException(404, str(e)) from None
    except httpx.HTTPStatusError as e:
        raise HTTPException(502, f"upstream answered {e.response.status_code} for {e.request.url.host}") from None
    except httpx.TransportError as e:
        raise HTTPException(502, f"upstream unreachable: {type(e).__name__}") from None
    except KeyError as e:
        raise HTTPException(503, f"setting missing: {e}") from None


def _json(data) -> Response:
    return Response(json.dumps(data, separators=(",", ":")), media_type="application/json")


# --- the index ---
@router.get("/scans")
def scans(q: str | None = None, address: str | None = None, city: str | None = None, segment: str | None = None,
          kind: str | None = Query(None, description="house, apartment_unit, amenity, office, warehouse, retail or other"),
          splat: bool | None = None, defurnished: bool | None = None, rooms_min: int | None = None, rooms_max: int | None = None,
          floors_min: int | None = None, limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)) -> dict:
    """Index rows. `q` needs every word in the name, address, ids or postal code; `address` is a substring."""
    if kind and kind not in scan_index.KINDS:
        raise HTTPException(422, "kind is one of " + ", ".join(scan_index.KINDS))
    total, rows = scan_index.search(q, address, city, segment, kind, splat, defurnished, rooms_min, rooms_max, floors_min, limit, offset)
    return {"total": total, "offset": offset, "scans": rows}


@functools.lru_cache(maxsize=1)
def _buildings_cache() -> tuple:
    """Features for every building, built once. Scans are listed as compact arrays to keep 10,000 features small:
    scans = [[sid, name, kind, rooms, panos], ...]. The kit's join gives the property id when it is configured."""
    feats = []
    for b in scan_index.buildings(costar.property_id_of):
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [b["lon"], b["lat"]]},
                      "properties": {"id": b["id"], "property_id": b["property_id"], "address": b["address"], "city": b["city"],
                                     "segment": b["segment"], "count": len(b["scans"]),
                                     "splat": any(s["splat"] for s in b["scans"]), "defurnished": any(s["defurnished"] for s in b["scans"]),
                                     "kinds": sorted({s["kind"] for s in b["scans"]}),
                                     "scans": [[s["sid"], s["name"], s["kind"], s["rooms"], s["panos"]] for s in b["scans"]]}})
    return tuple(feats)


@functools.lru_cache(maxsize=1)
def _buildings_body() -> tuple[bytes, str]:
    """The unfiltered answer, the one the map asks for: its bytes and an ETag, made once."""
    body = json.dumps({"type": "FeatureCollection", "features": list(_buildings_cache())}, separators=(",", ":")).encode()
    return body, '"' + hashlib.sha1(body).hexdigest()[:20] + '"'


def _warm_buildings() -> None:
    """Build the list in the background at start, so the first visitor after a restart does not wait for it."""
    threading.Thread(target=_buildings_body, name="warm-buildings", daemon=True).start()


router.add_event_handler("startup", _warm_buildings)


@router.get("/buildings")
def buildings(request: Request, segment: str | None = None, city: str | None = None, splat: bool | None = None,
              bbox: str | None = Query(None, description="west,south,east,north")) -> Response:
    """GeoJSON, one point per building (scans that share a CoStar property id, else an address, else a spot).
    properties: id, property_id, address, city, segment, count (scans), splat, defurnished, kinds, scans (compact rows
    [sid, name, kind, rooms, panos]). Gzipped by the app, about 400 kB for all of them."""
    box = None
    if bbox:
        try:
            box = [float(x) for x in bbox.split(",")]
            assert len(box) == 4
        except (ValueError, AssertionError):
            raise HTTPException(422, "bbox is west,south,east,north") from None
    if not (segment or city or splat is not None or box):
        body, etag = _buildings_body()
        # no-cache: the browser keeps it and asks again each visit; an unchanged list answers 304 with no body
        headers = {"ETag": etag, "Cache-Control": "no-cache"}
        if etag in (request.headers.get("if-none-match") or ""):
            return Response(status_code=304, headers=headers)
        return Response(body, media_type="application/json", headers=headers)
    feats = [f for f in _buildings_cache()
             if (not segment or f["properties"]["segment"] == segment)
             and (not city or city.lower() in (f["properties"]["city"] or "").lower())
             and (splat is None or f["properties"]["splat"] == splat)
             and (not box or box[0] <= f["geometry"]["coordinates"][0] <= box[2] and box[1] <= f["geometry"]["coordinates"][1] <= box[3])]
    return _json({"type": "FeatureCollection", "features": feats})


@router.get("/property/{property_id}/scans")
def property_scans(property_id: int) -> dict:
    """Every scan of one CoStar property."""
    sids = costar.scans_of_property(property_id)
    if not sids:
        raise HTTPException(404, f"no scans for property {property_id}")
    rows = scan_index.rows()
    address = None
    try:
        address = costar.joins()["property_address"].get(property_id)
    except costar.NotConfigured:
        pass
    return {"property_id": property_id, "address": address, "count": len(sids),
            "scans": [scan_index.public(rows[s]) for s in sids if s in rows]}


# --- one scan ---
@router.get("/scan/{sid}/plan")
def plan(sid: str) -> Response:
    return Response(_call(mp.plan_json, sid), media_type="application/json")


@router.get("/scan/{sid}/record")
def record(sid: str, full: bool = False) -> dict:
    """The CoStar property or listing record for a scan, with its listings, tenancies, sales and `claims` (the
    checkable facts and where in the record each came from). Trimmed unless full=1. 404 until the kit is configured."""
    return _call(costar.record, sid, full)


@router.get("/scan/{sid}/pano/{pano}/equirect.jpg")
def equirect(sid: str, pano: str, w: int = 2048, view: str = "furnished") -> Response:
    if view not in mp.VIEWS:  # checked here: the source builds its cache path from `view` before it checks it
        raise HTTPException(404, "view is furnished or defurnished")
    return Response(_call(mp.equirect, sid, pano, w, view), media_type="image/jpeg", headers=JPEG)


@router.get("/scan/{sid}/pano/{pano}/{face}.jpg")
def pano_face(sid: str, pano: str, face: int, res: str = "2k", view: str = "furnished") -> Response:
    return Response(_call(mp.pano_face, sid, pano, face, res, view), media_type="image/jpeg", headers=JPEG)


@router.get("/scan/{sid}/floorplan/{floor}.{fmt}")
def floorplan(sid: str, floor: str, fmt: str, flags: str = "photogramy") -> Response:
    return Response(_call(mp.floorplan, sid, floor, fmt, flags), media_type=f"image/{'jpeg' if fmt == 'jpg' else fmt}", headers=JPEG)


# --- splat, sky and drone photos ---
_RANGE = re.compile(r"^bytes=(\d*)-(\d*)$")


def _byte_range(header: str | None, total: int) -> tuple[int, int] | None:
    """(start, end) inclusive for a single `Range: bytes=` header; None when absent or a form we do not serve
    (the whole file is then sent); ValueError when it cannot be satisfied."""
    m = _RANGE.match((header or "").strip())
    if not m or m.group(1) == m.group(2) == "":
        return None
    first, last = m.groups()
    start, end = (max(0, total - int(last)), total - 1) if first == "" else (int(first), min(int(last), total - 1) if last else total - 1)
    if start < 0 or start > end or start >= total:
        raise ValueError
    return start, end


@router.api_route("/scan/{sid}/splat", methods=["GET", "HEAD"])
def splat(sid: str, request: Request) -> Response:
    """splat.ply, with Range. The first request starts a download into the cache (70 to 660 MB); ranges are served
    as the bytes arrive, so asking for the first 60 MB answers once 60 MB are in."""
    total = _call(hackathon.splat_size, sid)
    heads = {"Accept-Ranges": "bytes", "Cache-Control": "max-age=86400", "Content-Type": "application/octet-stream"}
    try:
        span = _byte_range(request.headers.get("range"), total)
    except ValueError:
        return Response(status_code=416, headers={"Content-Range": f"bytes */{total}"})
    start, end = span or (0, total - 1)
    heads["Content-Length"] = str(end - start + 1)
    if span:
        heads["Content-Range"] = f"bytes {start}-{end}/{total}"
    status = 206 if span else 200
    if request.method == "HEAD":
        return Response(status_code=status, headers=heads)
    return StreamingResponse(hackathon.splat_bytes(sid, start, end), status_code=status, headers=heads)


@router.get("/scan/{sid}/splat/envmap/{face}.jpg")
def envmap(sid: str, face: str) -> Response:
    return Response(_call(hackathon.envmap, sid, face), media_type="image/jpeg", headers=JPEG)


@router.get("/scan/{sid}/drone")
def drone(sid: str, n: int = Query(60, ge=0, le=2000, description="photos to describe, spread through the flight; 0 is all")) -> dict:
    """Drone photos with GPS, height above take-off and gimbal angles, read from each photo's XMP block. The first call
    for a scan reads n small ranges (about n/4 seconds); later calls come from the cache."""
    return _call(hackathon.drone_list, sid, n)


@router.get("/scan/{sid}/drone/{name}")
def drone_image(sid: str, name: str, w: int = 1600) -> Response:
    return Response(_call(hackathon.drone_image, sid, name, w), media_type="image/jpeg", headers=JPEG)
