"""Matterport Model API: GraphQL with basic auth, and a disk cache for the scans and images we serve.

Signed image links expire in about an hour, so links are looked up fresh and only the bytes are kept.
Raw model responses are cached, ScanPlans are derived from them in memory, so a better `normalize` needs no re-fetch.
"""
from __future__ import annotations

import functools
import io
import json
import threading
import time

import httpx
import numpy as np
from PIL import Image

from ..config import DATA, env
from ..scanplan import QUERY, apply_georef_fit, apply_recovered_walls, normalize
from . import footprint, recover, user_scans
from . import index as _index
from .upstream import cache_path, cached, check, one_flight, send

URL = "https://api.matterport.com/api/models/graph"
LINK_TTL = 1800
RES = ("2k", "4k")
VIEWS = ("furnished", "defurnished")
_links: dict[tuple, tuple[float, dict]] = {}  # (kind, model id, res) -> (fetched at, links)
_stitch = threading.Lock()  # one panorama stitch at a time: a 4096 px one needs several hundred MB


def index() -> dict[str, dict]:
    """sid -> typed index row (see sources/index.py)."""
    return _index.rows()


def graph(query: str, **variables) -> dict:
    e = env()
    r = send("POST", URL, json={"query": query, "variables": variables},
             auth=(e["MATTERPORT_API_KEY"], e["MATTERPORT_API_TOKEN"]))
    body = r.json()
    errors = body.get("errors") or []
    if errors and not (body.get("data") or {}).get("model"):
        code = (errors[0].get("extensions") or {}).get("code", "")
        raise LookupError("no such scan, or it is not shared with this key" if code == "not.found"
                          else errors[0].get("message", "Matterport error"))
    return body["data"]


def model(sid: str) -> dict:
    """The raw Model API response for QUERY, from the disk cache when there. Seeds from $THRESHOLD_DATA_DIR/raw."""
    check(sid, "sid")
    f = cache_path("model", f"{sid}.json")
    seed = DATA / "raw" / f"{sid}.json"
    if not f.exists() and seed.exists():
        raw = json.loads(seed.read_text())
        return raw["data"]["model"] if "data" in raw else raw
    return json.loads(cached(f, lambda: json.dumps(graph(QUERY, id=sid)["model"]).encode()))


@functools.lru_cache(maxsize=512)
def plan_json(sid: str) -> bytes:
    if user_scans.owns(sid):  # a phone scan of someone's own home (sources/user_scans.py)
        return user_scans.plan_json(sid)
    p = normalize(model(sid), index().get(sid))
    if not p["quality"]["walls"]:
        apply_recovered_walls(p, _recover(p), (index().get(sid) or {}).get("kind"))
    fit, ring = footprint.scan_fit(p)
    apply_georef_fit(p, fit, footprint.verdict(fit), ring)
    return json.dumps(p, separators=(",", ":")).encode()


def _recover(p: dict) -> list[dict]:
    """Walls recovered from each floor's schematic DXF and PNG, for a scan with no wall graph. A floor whose
    schematic cannot be fetched or read is skipped; the plan still loads."""
    parts = []
    for i, fl in enumerate(p["floors"]):
        have = {fp["format"] for fp in p["floorplans"] if fp["floor"] == fl["id"] and fp["flags"] == ["schematic"]}
        if "dxf" not in have:
            continue
        try:
            dxf = floorplan(p["sid"], fl["id"], "dxf", "schematic").decode("utf-8", "replace")
            png = np.asarray(Image.open(io.BytesIO(floorplan(p["sid"], fl["id"], "png", "schematic"))).convert("L")) \
                if "png" in have else None
            rec = recover.recover_floor(dxf, png, [r for r in p["rooms"] if r["floor"] == fl["id"]],
                                        [x for x in p["panos"] if x["floor"] == fl["id"]])
        except (LookupError, httpx.HTTPError, ValueError, OSError):
            continue
        if rec["walls"]:
            parts.append(recover.plan_parts(fl["id"], f"r{i}", rec))
    return parts


def plan(sid: str) -> dict:
    """The ScanPlan. A fresh dict each call, so callers may change it."""
    return json.loads(plan_json(sid))


def _fresh(key: tuple, load) -> dict:
    with one_flight(repr(key)):
        hit = _links.get(key)
        if not hit or time.time() - hit[0] > LINK_TTL:
            hit = _links[key] = (time.time(), load())
        return hit[1]


def _pano_links(model_id: str, res: str) -> dict[str, list[str]]:
    q = 'query($id: ID!, $res: String!) { model(id: $id) { panoLocations { id skybox(resolution: $res) { status children } } } }'
    return _fresh(("pano", model_id, res), lambda: {p["id"]: (p.get("skybox") or {}).get("children") or []
                                                    for p in graph(q, id=model_id, res=res)["model"]["panoLocations"]})


def pano_face(sid: str, pano: str, face: int, res: str = "2k", view: str = "furnished") -> bytes:
    check(sid, "sid"), check(pano)
    if res not in RES or view not in VIEWS or not 0 <= face <= 5:
        raise LookupError("res is 2k or 4k, view is furnished or defurnished, face is 0 to 5")

    def load() -> bytes:
        model_id = sid if view == "furnished" else plan(sid)["ids"]["defurnished_view"]
        if not model_id:
            raise LookupError("this scan has no defurnished view")
        for attempt in (0, 1):
            faces = _pano_links(model_id, res).get(pano) or []
            if face >= len(faces):
                raise LookupError("no such panorama face")
            try:
                return send("GET", faces[face]).content
            except httpx.HTTPStatusError as e:  # a signed link that expired early: look it up again, once
                if attempt or e.response.status_code not in (401, 403, 404, 410):
                    raise
                _links.pop(("pano", model_id, res), None)
        raise AssertionError("unreachable")

    return cached(cache_path("pano", sid, view, res, f"{pano}_{face}.jpg"), load)


def stitch(faces: list[Image.Image], width: int) -> Image.Image:
    """Six cube faces (0 up, 1-4 the horizon turning right, 5 down) into one equirectangular image, width x width/2."""
    h = width // 2
    lon = ((np.arange(width, dtype=np.float32) + 0.5) / width * 2 * np.pi - np.pi)[None, :]
    lat = (np.pi / 2 - (np.arange(h, dtype=np.float32) + 0.5) / h * np.pi)[:, None]
    x, y, z = np.cos(lat) * np.sin(lon), np.broadcast_to(np.sin(lat), (h, width)), np.cos(lat) * np.cos(lon)  # y up, z forward
    ax, ay, az = np.abs(x), np.abs(y), np.abs(z)
    out = np.zeros((h, width, 3), np.uint8)
    n = faces[0].width
    for k, mask, u, v in [
        (1, (az >= ax) & (az >= ay) & (z > 0), lambda: x / az, lambda: -y / az),
        (2, (ax >= ay) & (ax >= az) & (x > 0), lambda: -z / ax, lambda: -y / ax),
        (3, (az >= ax) & (az >= ay) & (z < 0), lambda: -x / az, lambda: -y / az),
        (4, (ax >= ay) & (ax >= az) & (x < 0), lambda: z / ax, lambda: -y / ax),
        (0, (ay >= ax) & (ay >= az) & (y > 0), lambda: x / ay, lambda: z / ay),
        (5, (ay >= ax) & (ay >= az) & (y < 0), lambda: x / ay, lambda: -z / ay),
    ]:
        col = np.clip(((u()[mask] + 1) / 2 * n).astype(np.int32), 0, n - 1)
        row = np.clip(((v()[mask] + 1) / 2 * n).astype(np.int32), 0, n - 1)
        out[mask] = np.asarray(faces[k])[row, col]
    return Image.fromarray(out)


def equirect(sid: str, pano: str, width: int = 2048, view: str = "furnished") -> bytes:
    if not 512 <= width <= 4096 or width % 2:
        raise LookupError("w is an even number from 512 to 4096")

    def make() -> bytes:
        res = "4k" if width > 2048 else "2k"
        faces = [Image.open(io.BytesIO(pano_face(sid, pano, k, res, view))).convert("RGB") for k in range(6)]
        with _stitch:
            buf = io.BytesIO()
            stitch(faces, width).save(buf, "JPEG", quality=88)
        return buf.getvalue()

    return cached(cache_path("equirect", sid, view, f"{pano}_{width}.jpg"), make)


def floorplan(sid: str, floor: str, fmt: str = "jpg", flags: str = "photogramy") -> bytes:
    check(sid, "sid"), check(floor)
    if fmt not in ("jpg", "png", "dxf") or not all(f.replace("_", "").isalnum() for f in flags.split(",")):
        raise LookupError("fmt is jpg, png or dxf; flags are comma separated words")
    want = sorted(flags.split(","))

    def load() -> bytes:
        q = 'query($id: ID!) { model(id: $id) { assets { floorplans(provider: "matterport") { format flags url floor { id } } } } }'
        for fp in graph(q, id=sid)["model"]["assets"]["floorplans"]:
            if fp["format"] == fmt and sorted(fp.get("flags") or []) == want and (fp.get("floor") or {}).get("id") == floor and fp.get("url"):
                return send("GET", fp["url"]).content
        raise LookupError("no such floor plan")

    return cached(cache_path("floorplan", sid, f"{floor}_{'-'.join(want)}.{fmt}"), load)
