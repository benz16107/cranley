"""models_index.csv (14,944 scans the hackathon keys can see): typed rows, search, and grouping into buildings.

`kind` is a guess from the scan's name and id prefix, for browsing and sampling. The index has no property type.
"""
from __future__ import annotations

import csv
import functools
import re
from collections import defaultdict

from ..config import DATA

KINDS = ("house", "apartment_unit", "amenity", "office", "warehouse", "retail", "other")
_AMENITY = re.compile(r"fitness|gym\b|pool|club|lobby|lounge|laundry|yoga|leasing|business center|\bspa\b|theat|cinema|"
                      r"game room|rooftop|terrace|courtyard|mail|package|amenit|cafe|community kitchen|dog|pet |sauna|"
                      r"conference|cowork|bike|cycle|entrance|resident", re.I)
_WAREHOUSE = re.compile(r"warehouse|industrial|distribution|manufactur|\bflex\b", re.I)
_UNIT = re.compile(r"\b\d(\.\d)?\s?(br|bd|bed|ba)\b|studio|bachelor|\bunit\b|\bplan\b|townhome|\d\s?[x/+]\s?\d|\bmodel\b", re.I)
_RETAIL = re.compile(r"retail|restaurant|shop|store|salon|clinic|\bbar\b|showroom|barber", re.I)
_OFFICE = re.compile(r"suite|office|\bfloor\b|\bsf\b|sq\s?ft|\bfl\b", re.I)


def _prefix(internal_id: str) -> str:
    return re.split(r"[-_ ]", (internal_id or "").strip().lower())[0]


def kind_of(r: dict) -> str:
    name, pre = r["name"] or "", _prefix(r["internal_id"])
    if r["segment"] == "residential" and (r["splat"] == "yes" or pre.startswith("home") or not _UNIT.search(name)):
        return "house" if not _AMENITY.search(name) else "amenity"
    if _AMENITY.search(name):
        return "amenity"
    if _WAREHOUSE.search(name):
        return "warehouse"
    if _UNIT.search(name) or pre in ("apartments", "apts", "apt", "unit"):
        return "apartment_unit"
    if _RETAIL.search(name):
        return "retail"
    if r["segment"] == "commercial" and (_OFFICE.search(name) or pre in ("loopnet", "tenx")):
        return "office"
    return "other"


def _num(v: str, cast=float):
    try:
        return cast(v) if v not in ("", None) else None
    except ValueError:
        return None


@functools.cache
def rows() -> dict[str, dict]:
    """sid -> row, in file order. Keys and string values are as in the CSV; numbers and flags are typed, and
    `kind` and `has_street` are added. Do not mutate."""
    f = DATA / "models_index.csv"
    if not f.exists():
        return {}
    out = {}
    for r in csv.DictReader(open(f, encoding="utf-8")):
        r = {k: (v or "").strip() for k, v in r.items()}
        r["kind"] = kind_of(r)
        r["has_street"] = bool(re.search(r"\d", r["address"]) and "," in r["address"])
        out[r["sid"]] = r
    return out


def public(r: dict) -> dict:
    """The row as the API serves it: typed, small."""
    return {"sid": r["sid"], "name": r["name"], "kind": r["kind"], "segment": r["segment"],
            "address": r["address"] or None, "city": r["city"] or None,
            "lat": _num(r["lat"]), "lon": _num(r["lon"]),
            "splat": r["splat"] == "yes", "defurnished": r["defurnished"] == "yes",
            "drone_photos": _num(r["drone_photos"], int) or 0, "panos": _num(r["pano_count"], int) or 0,
            "rooms": _num(r["room_count"], int) or 0, "floors": _num(r["floor_count"], int) or 0,
            "costar_property_id": r["costar_property_id"] or None, "homes_listing_id": r["homes_listing_id"] or None,
            "created": r["created"] or None, "has_summary": r["ai_summary"] == "yes"}


def search(q: str | None = None, address: str | None = None, city: str | None = None, segment: str | None = None,
           kind: str | None = None, splat: bool | None = None, defurnished: bool | None = None,
           rooms_min: int | None = None, rooms_max: int | None = None, floors_min: int | None = None,
           limit: int = 50, offset: int = 0) -> tuple[int, list[dict]]:
    """Rows matching every given filter, best first, and the total before paging. `q` needs every word to appear
    in the name, address, city, id or CoStar or Homes id; `address` is a substring of the address."""
    words = (q or "").lower().split()
    addr, city_l = (address or "").lower().strip(), (city or "").lower().strip()
    hits = []
    for r in rows().values():
        if segment and r["segment"] != segment or kind and r["kind"] != kind:
            continue
        if splat is not None and (r["splat"] == "yes") != splat or defurnished is not None and (r["defurnished"] == "yes") != defurnished:
            continue
        n_rooms, n_floors = _num(r["room_count"], int) or 0, _num(r["floor_count"], int) or 0
        if rooms_min is not None and n_rooms < rooms_min or rooms_max is not None and n_rooms > rooms_max:
            continue
        if floors_min is not None and n_floors < floors_min:
            continue
        if addr and addr not in r["address"].lower() or city_l and city_l not in r["city"].lower():
            continue
        score = 0
        if words:
            hay = " ".join((r["name"], r["address"], r["city"], r["sid"], r["internal_id"], r["costar_property_id"],
                            r["homes_listing_id"], r["postal_code"])).lower()
            if not all(w in hay for w in words):
                continue
            score = (100 if r["sid"].lower() == (q or "").lower().strip() else 0) \
                + sum(10 for w in words if w in r["name"].lower()) + sum(5 for w in words if r["address"].lower().startswith(w))
        hits.append((-score, len(hits), r))
    hits.sort(key=lambda h: h[:2])
    return len(hits), [public(h[2]) for h in hits[offset: offset + limit]]


def _address_key(r: dict) -> str:
    return re.sub(r"[^a-z0-9]+", " ", r["address"].lower()).strip()


def buildings(property_id_of=None) -> list[dict]:
    """Scans grouped into buildings. A CoStar property id groups first (833 of 1,869 ids appear under more than one
    spelling of the address), then a street address, then coordinates to 5 decimals (about a metre).
    `property_id_of(sid)` gives a scan's property id (the kit's join); without it the index column is used.
    Each group: id, property_id, address, city, segment, lon, lat, scans (index rows, public form)."""
    groups: dict[str, list[dict]] = defaultdict(list)
    pids: dict[str, int | None] = {}
    spot_owner: dict[tuple, str] = {}  # coordinates -> the property or address group that has a scan there
    loose = []                         # scans with neither a property id nor a street address
    for r in rows().values():
        lat, lon = _num(r["lat"]), _num(r["lon"])
        pid = property_id_of(r["sid"]) if property_id_of else _num(r["costar_property_id"], int)
        if pid:
            key = f"p{pid}"
            pids[key] = pid
        elif r["has_street"]:
            key = "a" + _address_key(r)
        elif lat is not None and lon is not None:
            loose.append((r, f"{lat:.5f},{lon:.5f}"))
            continue
        else:
            continue
        groups[key].append(r)
        if lat is not None and lon is not None:
            spot_owner.setdefault(f"{lat:.5f},{lon:.5f}", key)
    for r, spot in loose:  # an amenity room with no id of its own joins the building that has a scan at the same spot
        groups[spot_owner.get(spot, "g" + spot)].append(r)
    out = []
    for key, members in groups.items():
        pts = sorted((_num(m["lon"]), _num(m["lat"])) for m in members if m["lat"] and m["lon"])
        if not pts:
            continue  # nothing to put on a map
        lon, lat = pts[len(pts) // 2]
        named = next((m for m in members if m["has_street"]), members[0])
        out.append({"id": key, "property_id": pids.get(key), "address": named["address"] or None, "city": next((m["city"] for m in members if m["city"]), None),
                    "segment": named["segment"], "lon": lon, "lat": lat, "scans": [public(m) for m in members]})
    return out
