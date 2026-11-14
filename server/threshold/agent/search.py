"""Search for the investigator: scans (the index), CoStar properties (record fields), and measured facts (the access
workstream's `GET /api/search/measures`, used only when that route exists at run time).

Property search reads a small digest of the CoStar kit, built once (about half a minute) into
$THRESHOLD_DATA_DIR/cache/agent/properties.json and rebuilt when a kit file changes. Results are compact rows for the
model to choose from; the model never quotes them as measurements.
"""
from __future__ import annotations

import inspect
import json
import threading
from collections import Counter, defaultdict

from ..config import CACHE

MAX_ROWS = 25
_lock = threading.Lock()


def _pid_map() -> dict[str, int]:
    """sid -> CoStar property id: the kit's starter CSV first, then the index column."""
    from ..sources import costar, index
    out: dict[str, int] = {}
    try:
        for sid, pids in costar.joins()["model_property"].items():
            out[sid] = pids[0]
    except costar.NotConfigured:
        pass
    for sid, r in index.rows().items():
        if sid not in out and r["costar_property_id"].isdigit():
            out[sid] = int(r["costar_property_id"])
    return out


def find_scans(city: str | None = None, kind: str | None = None, text: str | None = None, address: str | None = None,
               property_id: int | None = None, drone: bool | None = None, empty_room_view: bool | None = None,
               splat: bool | None = None, limit: int = 10) -> dict:
    """Scans matching every filter given. `kind`: house, apartment_unit, amenity, office, warehouse, retail, other."""
    from ..sources import index
    pids = _pid_map()
    _, rows = index.search(text, address, city, None, kind, splat, empty_room_view, limit=len(index.rows()) or 1)
    hits = [r for r in rows if (drone is None or (r["drone_photos"] > 0) == drone)
            and (property_id is None or pids.get(r["sid"]) == property_id)]
    limit = max(1, min(limit, MAX_ROWS))
    return {"matched": len(hits),
            "scans": [{"sid": r["sid"], "name": r["name"], "kind": r["kind"], "address": r["address"], "city": r["city"],
                       "property_id": pids.get(r["sid"]), "drone": r["drone_photos"] > 0,
                       "empty_room_view": r["defurnished"], "rooms": r["rooms"]} for r in hits[:limit]]}


# ---- CoStar properties ----

def _build_digest() -> list[dict]:
    from ..sources import costar, index
    d = costar.ensure_kit()
    enums = costar._enums()
    types, subtypes = enums.get("PropertyType", {}), enums.get("PropertySubtype", {})
    apt = {}
    with open(d / "data" / "apartment-listing.jsonl", encoding="utf-8") as f:
        for line in f:
            a = json.loads(line)
            apt[a["propertyId"]] = a
    names = {}
    with open(d / "data" / "company-detail.jsonl", encoding="utf-8") as f:
        for line in f:
            c = json.loads(line)
            names[c["id"]] = c.get("name")
    tenants: dict[int, list[tuple[str, str]]] = defaultdict(list)
    with open(d / "data" / "location-occupancy.jsonl", encoding="utf-8") as f:
        for line in f:
            t = json.loads(line)
            n = names.get(t.get("tenantLocationId"))
            if n and t.get("propertyId"):
                tenants[t["propertyId"]].append((t.get("fromDate") or "", n))
    scans: dict[int, Counter] = defaultdict(Counter)
    flags: dict[int, set] = defaultdict(set)
    rows = index.rows()
    for sid, pid in _pid_map().items():
        r = rows.get(sid)
        if r:
            scans[pid][r["kind"]] += 1
            if r["drone_photos"] not in ("", "0"):
                flags[pid].add("drone")
            if r["defurnished"] == "yes":
                flags[pid].add("empty_room_view")
    out = []
    with open(d / "data" / "commercial-property.jsonl", encoding="utf-8") as f:
        for line in f:
            p = json.loads(line)
            a = apt.get(p["id"])
            c = {k: v["value"] for k, v in costar.claims({"property": p, "apartment_listing": a}).items()
                 if not isinstance(v["value"], (list, dict))}
            addr = p.get("primaryAddress") or {}
            seen, ten = set(), []
            for _, n in sorted(tenants.get(p["id"], []), reverse=True):
                if n not in seen:
                    seen.add(n)
                    ten.append(n)
            out.append({"id": p["id"], "name": p.get("buildingName") or (a or {}).get("buildingName"),
                        "type": types.get(str(p.get("propertyType")), "Unknown"),
                        "subtype": subtypes.get(str(p.get("propertySubtype"))),
                        "address": " ".join(x for x in (addr.get("streetNumber"), addr.get("streetDirection"),
                                                        addr.get("streetName"), addr.get("streetType")) if x) or None,
                        "city": addr.get("city"), "lat": addr.get("latitude"), "lon": addr.get("longitude"),
                        "facts": c, "rent_min": (a or {}).get("minRent") or None, "rent_max": (a or {}).get("maxRent") or None,
                        "units_available": (a or {}).get("numUnitsAvailable"), "tenants": ten[:30],
                        "scans": dict(scans.get(p["id"], {})), "flags": sorted(flags.get(p["id"], set()))})
    return out


def properties() -> list[dict]:
    from ..sources import costar
    path = CACHE / "agent" / "properties.json"
    stamp = costar._stamp(costar.ensure_kit())
    with _lock:
        if path.exists():
            data = json.loads(path.read_text())
            if data.get("stamp") == stamp:
                return data["properties"]
        props = _build_digest()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"stamp": stamp, "properties": props}))
        return props


def find_properties(city: str | None = None, property_type: str | None = None, text: str | None = None,
                    tenant: str | None = None, min_units: int | None = None, max_rent: int | None = None,
                    min_area_ft2: float | None = None, max_area_ft2: float | None = None,
                    elevator: bool | None = None, built_after: int | None = None, scan_kind: str | None = None,
                    drone: bool | None = None, empty_room_view: bool | None = None, limit: int = 10,
                    rows: list[dict] | None = None) -> dict:
    """CoStar properties that have scans and match every filter. `property_type` is a CoStar type such as Multifamily,
    Office, Industrial, GeneralRetail, Flex, Hospitality, Healthcare. Ranked by how many scans each has."""
    def ok(p):
        f = p["facts"]
        area = f.get("gross_area") or f.get("rentable_area")
        return (p["scans"]
                and (not city or city.lower() in (p["city"] or "").lower())
                and (not property_type or property_type.lower() in f"{p['type']} {p['subtype'] or ''}".lower())
                and (not text or all(w in " ".join(str(x) for x in (p["name"], p["address"], p["subtype"])).lower()
                                     for w in text.lower().split()))
                and (not tenant or any(tenant.lower() in t.lower() for t in p["tenants"]))
                and (min_units is None or (f.get("units") or 0) >= min_units)
                and (max_rent is None or (p["rent_min"] is not None and p["rent_min"] <= max_rent))
                and (min_area_ft2 is None or (area or 0) >= min_area_ft2)
                and (max_area_ft2 is None or (area is not None and area <= max_area_ft2))
                and (elevator is None or bool(f.get("passenger_elevators") or f.get("has_elevator")) == elevator)
                and (built_after is None or (f.get("year_built") or 0) >= built_after)
                and (not scan_kind or p["scans"].get(scan_kind))
                and (drone is None or ("drone" in p["flags"]) == drone)
                and (empty_room_view is None or ("empty_room_view" in p["flags"]) == empty_room_view))
    hits = sorted((p for p in (rows if rows is not None else properties()) if ok(p)),
                  key=lambda p: -sum(p["scans"].values()))
    limit = max(1, min(limit, MAX_ROWS))
    keep = ("units", "passenger_elevators", "is_walkup", "year_built", "stories", "gross_area")
    return {"matched": len(hits),
            "properties": [{"property_id": p["id"], "name": p["name"], "type": p["subtype"] or p["type"],
                            "address": p["address"], "city": p["city"], "scans": p["scans"], "flags": p["flags"],
                            "facts": {k: p["facts"][k] for k in keep if p["facts"].get(k) is not None},
                            "rent_range": [p["rent_min"], p["rent_max"]] if p["rent_min"] else None,
                            "tenants": p["tenants"][:5]} for p in hits[:limit]]}


# ---- measured facts (access workstream), detected at run time ----

MEASURES = "/api/search/measures"


def measures_route():
    """The `GET /api/search/measures` endpoint when it is mounted, else None."""
    try:
        from ..api.app import app
    except Exception:
        return None
    return next((r for r in app.routes if getattr(r, "path", None) == MEASURES and "GET" in getattr(r, "methods", ())), None)


def measures_params(route) -> str:
    sig = inspect.signature(route.endpoint)
    return ", ".join(f"{n}" + (f" (default {p.default!r})" if p.default is not inspect.Parameter.empty else "")
                     for n, p in sig.parameters.items() if n not in ("request", "response"))


def find_by_measure(route, params: dict) -> dict:
    """Call the measure search in process, passing only the parameters it declares."""
    from fastapi import HTTPException
    sig = inspect.signature(route.endpoint)
    kw = {k: v for k, v in params.items() if k in sig.parameters and v is not None}
    try:
        out = route.endpoint(**kw)
    except HTTPException as e:
        return {"error": str(e.detail)}
    except TypeError as e:
        return {"error": f"measure search refused the parameters: {e}"}
    body = getattr(out, "body", None)
    data = json.loads(body) if body is not None else out
    if isinstance(data, dict):  # keep the reply small for the model
        for k, v in data.items():
            if isinstance(v, list):
                data[k] = v[:MAX_ROWS]
    return data
