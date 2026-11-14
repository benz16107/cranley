"""Matterport Model API: GraphQL with basic auth, plus a disk cache for the scans and images we serve.

Signed image links expire in about an hour, so links are looked up fresh and only the bytes are kept.
"""
from __future__ import annotations

import csv
import functools
import json
import time

import httpx

from ..config import CACHE, DATA, env
from ..scanplan import QUERY, normalize

URL = "https://api.matterport.com/api/models/graph"
_links: dict[tuple, tuple[float, dict]] = {}  # (kind, model id, res) -> (fetched at, links)


def graph(query: str, **variables) -> dict:
    e = env()
    r = httpx.post(URL, json={"query": query, "variables": variables},
                   auth=(e["MATTERPORT_API_KEY"], e["MATTERPORT_API_TOKEN"]), timeout=90)
    r.raise_for_status()
    body = r.json()
    if body.get("errors") and not (body.get("data") or {}).get("model"):
        raise LookupError(body["errors"][0].get("message", "Matterport error"))
    return body["data"]


@functools.cache
def index() -> dict[str, dict]:
    f = DATA / "models_index.csv"
    return {r["sid"]: r for r in csv.DictReader(open(f))} if f.exists() else {}


def plan(sid: str) -> dict:
    f = CACHE / "plan" / f"{sid}.json"
    if f.exists():
        return json.loads(f.read_text())
    p = normalize(graph(QUERY, id=sid)["model"], index().get(sid))
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(p))
    return p


def _fresh(key: tuple, load) -> dict:
    hit = _links.get(key)
    if not hit or time.time() - hit[0] > 1800:
        hit = _links[key] = (time.time(), load())
    return hit[1]


def pano_face(sid: str, pano: str, face: int, res: str = "2k", view: str = "furnished") -> bytes:
    f = CACHE / "pano" / sid / view / res / f"{pano}_{face}.jpg"
    if f.exists():
        return f.read_bytes()
    model_id = sid if view == "furnished" else plan(sid)["ids"]["defurnished_view"]
    if not model_id:
        raise LookupError("this scan has no defurnished view")
    q = 'query($id: ID!, $res: String!) { model(id: $id) { panoLocations { id skybox(resolution: $res) { status children } } } }'
    links = _fresh(("pano", model_id, res), lambda: {p["id"]: (p.get("skybox") or {}).get("children") or []
                                                      for p in graph(q, id=model_id, res=res)["model"]["panoLocations"]})
    faces = links.get(pano) or []
    if face >= len(faces):
        raise LookupError("no such panorama face")
    data = httpx.get(faces[face], timeout=90).raise_for_status().content
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(data)
    return data


def floorplan(sid: str, floor: str, fmt: str = "jpg", flags: str = "photogramy") -> bytes:
    want = sorted(flags.split(","))
    f = CACHE / "floorplan" / sid / f"{floor}_{'-'.join(want)}.{fmt}"
    if f.exists():
        return f.read_bytes()
    q = 'query($id: ID!) { model(id: $id) { assets { floorplans(provider: "matterport") { format flags url floor { id } } } } }'
    for fp in graph(q, id=sid)["model"]["assets"]["floorplans"]:
        if fp["format"] == fmt and sorted(fp.get("flags") or []) == want and (fp.get("floor") or {}).get("id") == floor and fp.get("url"):
            data = httpx.get(fp["url"], timeout=90).raise_for_status().content
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(data)
            return data
    raise LookupError("no such floor plan")
