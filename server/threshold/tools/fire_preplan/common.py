"""Shared by the fire tools (fire_preplan, egress_routes, life_safety_census, smoke_clock, size_up_quiz):
which scans a run covers, whether a scan has a wall graph, and the panorama object read with its budget."""
from __future__ import annotations

import io
import json

from shapely.geometry import Point

from ...config import CACHE
from ...geometry._plan import polygons, room_label
from .. import NotApplicable, Source, ToolError

GEOM = Source(layer="matterport", method="geometry", confidence="high", note="Matterport wall graph")
LABELS = Source(layer="matterport", method="lookup", confidence="medium", note="Matterport room classification")
OBJECTS_DIR = CACHE / "tools" / "fire_objects"
BEDROOM = "Bedroom"
HALL_LABELS = ("Hallway", "Entrance")
SLEEPING_LIKE = ("Bedroom",)


def walls_ok(plan: dict) -> bool:
    """True when the scan has a wall graph. Older fixtures carry no `quality`, so fall back to the walls list."""
    q = plan.get("quality") or {}
    return bool(q.get("walls", bool(plan.get("walls"))))


def labels_ok(plan: dict) -> bool:
    return any(r.get("label") not in (None, "Void") for r in plan.get("rooms") or [])


def live_rooms(plan: dict) -> list[dict]:
    return [r for r in plan.get("rooms") or [] if r.get("label") != "Void"]


def name(room: dict | None) -> str:
    return room_label(room) if room else "unknown room"


def floor_label(plan: dict, floor_id: str) -> str:
    fl = {f["id"]: f for f in plan.get("floors") or []}
    if len(fl) <= 1:
        return "the floor"
    seq = sorted(fl.values(), key=lambda f: f.get("sequence") or 0)
    return f"floor {[f['id'] for f in seq].index(floor_id) + 1}" if floor_id in fl else "an unknown floor"


def scope_sids(scan: str | None, whole_property: bool, property_id: int | None) -> tuple[list[str], int | None]:
    """The scans one run covers: one scan, or every scan of its CoStar property."""
    if property_id is None and not whole_property:
        if not scan:
            raise ToolError("Pick a scan or give a property id.")
        return [scan], None
    from ...sources import costar
    pid = property_id
    if pid is None:
        try:
            pid = costar.property_id_of(scan)
        except LookupError:
            pid = None
        if pid is None:
            return [scan], None  # caller says the property could not be found
    sids = costar.scans_of_property(pid)
    if not sids:
        raise NotApplicable(f"No scans found for property {pid}, so there is nothing to plan.")
    if scan and scan not in sids:
        sids = [scan, *sids]
    return sids, pid


def room_at(plan: dict, xy, floor: str | None = None) -> str | None:
    """Room whose polygon contains a point (same floor when given)."""
    polys = polygons(plan)
    p = Point(xy[0], xy[1])
    for r in plan.get("rooms") or []:
        if floor and r["floor"] != floor:
            continue
        poly = polys.get(r["id"])
        if poly is not None and poly.buffer(0.05).contains(p):
            return r["id"]
    return None


class VisionBudget:
    """How many scans a run may send to the vision model. Scans already read (cached) are free."""

    def __init__(self, scans: int):
        self.left = scans
        self.read: list[str] = []

    def allow(self, sid: str, fresh: bool = False) -> bool:
        if not fresh and (OBJECTS_DIR / f"{sid}.json").exists():
            return True
        if self.left <= 0:
            return False
        self.left -= 1
        return True


def room_pano_map(plan: dict) -> dict[str, list[dict]]:
    """Panoramas standing in each room: the plan's own assignment, else the room whose polygon holds the camera."""
    out: dict[str, list[dict]] = {}
    for p in plan.get("panos") or []:
        if not p.get("rotation"):
            continue
        rid = p.get("room") or room_at(plan, p["position"][:2], p.get("floor"))
        if rid:
            out.setdefault(rid, []).append(p)
    polys = polygons(plan)
    for rid, ps in out.items():
        poly = polys.get(rid)
        if poly is not None:
            c = poly.centroid
            ps.sort(key=lambda p: (p["position"][0] - c.x) ** 2 + (p["position"][1] - c.y) ** 2)
    return out


def central_pano(plan: dict, room: dict) -> dict | None:
    """The panorama nearest the room's centre."""
    ps = room_pano_map(plan).get(room["id"])
    return ps[0] if ps else None


def objects(plan: dict, budget: VisionBudget | None) -> list[dict] | None:
    """Things the vision model found in the central panorama of each room (smoke alarms, sprinkler heads, exit signs,
    extinguishers, electrical panels, water heaters, gas stoves, stairs, ...), each tagged with `in_room`.
    None when the scan was not read (no budget left) or has no panoramas with a rotation."""
    want = [ps[0]["id"] for rid, ps in room_pano_map(plan).items()
            if next((r for r in plan["rooms"] if r["id"] == rid), {}).get("label") != "Void"]
    if not want:
        return None
    f = OBJECTS_DIR / f"{plan['sid']}.json"
    cached = json.loads(f.read_text()) if f.exists() else None
    if cached and set(want) <= set(cached["panos"]):
        found = cached["found"]
    else:
        if budget is None or not budget.allow(plan["sid"], fresh=True):
            return None
        from ...vision.reader import find_objects
        found = find_objects(plan, panos=want, max_panos=len(want))  # already-read panoramas come from the cache
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"panos": want, "found": found}))
        budget.read.append(plan["sid"])
    pano_floor = {p["id"]: p.get("floor") for p in plan.get("panos") or []}
    pano_xy = {p["id"]: p["position"][:2] for p in plan.get("panos") or []}
    for d in found:
        pid = d["pano_anchor"]["pano"]
        d["in_room"] = ((room_at(plan, d["point"], pano_floor.get(pid)) if d.get("point") else None) or d.get("room")
                        or room_at(plan, pano_xy[pid], pano_floor.get(pid)))
    return found


def ceiling_quality(sid: str, pano: str) -> tuple[bool | None, str]:
    """Whether a panorama's up face (the ceiling photo) can be read: (readable, why). Fetches the face from the
    disk cache or Matterport. Too dark, blown out or flat (fog, a missing face) counts as unreadable."""
    from PIL import Image, ImageStat

    from ...sources import matterport as mp
    try:
        im = Image.open(io.BytesIO(mp.pano_face(sid, pano, 0, "2k"))).convert("L").resize((128, 128))
    except Exception as e:  # noqa: BLE001  any fetch failure means we could not look
        return None, f"ceiling photo unavailable ({type(e).__name__})"
    st = ImageStat.Stat(im)
    mean, sd = st.mean[0], st.stddev[0]
    if mean < 25:
        return False, "ceiling photo too dark to read"
    if mean > 245 and sd < 8:
        return False, "ceiling photo blown out"
    if sd < 3:
        return False, "ceiling photo is flat (no detail)"
    return True, "ceiling photo readable"
