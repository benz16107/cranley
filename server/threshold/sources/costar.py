"""The CoStar data kit: property and listing records for the scans. Sponsor data: it stays in the data folder, never in git.

Where the kit comes from, first match wins:
  1. COSTAR_KIT_DIR, default $THRESHOLD_DATA_DIR/kit: the unpacked kit (index.md, data/*.jsonl, the two starter CSVs).
  2. COSTAR_KIT_ZIP (a path) or COSTAR_KIT_URL (downloaded once into the cache), opened with COSTAR_ZIP_PASSWORD and
     unpacked into that folder. A zip cannot be read at an offset, so it has to be unpacked.
Nothing configured raises NotConfigured, which the API turns into a 404 that says what to set.

The data is JSON Lines, 400 MB. A small SQLite file in the cache maps (dataset, key) to a byte offset, so a lookup
reads one line instead of scanning. It is built on first use (a few seconds) and again when a data file changes.

Scan to record join: the kit's two starter CSVs (PropertyId or ListingId with MatterportModelId) win; the
costar_property_id and homes_listing_id columns of models_index.csv are the fallback. `python -m threshold.sources.costar
--check` prints how often the two disagree.
"""
from __future__ import annotations

import csv
import functools
import json
import sqlite3
import sys
import threading
from collections import defaultdict
from pathlib import Path

from ..config import CACHE, DATA, env
from . import index as scan_index
from .upstream import check, send

DATASETS = ("commercial-property", "commercial-listing-summary", "location-occupancy", "company-detail",
            "commercial-sale-comp", "apartment-listing", "residential-listings", "residential-listing-features")
MAX_LIST = 60       # a trimmed record shows at most this many items of any list; ?full=1 lifts it
MAX_TEXT = 600      # and at most this many characters of any text
MAX_TENANCIES = 50
MAX_SALES = 10
_build = threading.Lock()


class NotConfigured(LookupError):
    """The kit is not set up. A LookupError, so the API answers 404 with this message."""


# --- finding and opening the kit ---
def kit_dir() -> Path:
    return Path(env().get("COSTAR_KIT_DIR") or DATA / "kit")


def _unpack(zip_path: Path, dest: Path, password: str | None) -> None:
    import pyzipper  # reads both AES and the older ZipCrypto; the stdlib zipfile reads only the latter
    with pyzipper.AESZipFile(zip_path) as z:
        if password:
            z.setpassword(password.encode())
        try:
            z.extractall(dest)  # extractall drops ".." and absolute paths from member names
        except RuntimeError as e:
            raise NotConfigured("the CoStar kit zip rejected COSTAR_ZIP_PASSWORD: copy it again from the CoStar keys card") from e


def ensure_kit() -> Path:
    d = kit_dir()
    if (d / "data").is_dir():
        return d
    e = env()
    zip_path = Path(e["COSTAR_KIT_ZIP"]) if e.get("COSTAR_KIT_ZIP") else None
    if zip_path and not zip_path.is_file():
        zip_path = None
    if not zip_path and e.get("COSTAR_KIT_URL"):
        zip_path = CACHE / "costar-kit.zip"
        if not zip_path.exists():
            r = send("GET", e["COSTAR_KIT_URL"], stream=True)
            try:
                with open(zip_path.with_suffix(".part"), "wb") as f:
                    for chunk in r.iter_bytes(1 << 20):
                        f.write(chunk)
            finally:
                r.close()
            zip_path.with_suffix(".part").rename(zip_path)
    if not zip_path:
        raise NotConfigured("the CoStar kit is not configured: set COSTAR_KIT_DIR (the unpacked kit), COSTAR_KIT_ZIP or "
                            "COSTAR_KIT_URL, with COSTAR_ZIP_PASSWORD for a zip")
    with _build:
        if not (d / "data").is_dir():
            d.mkdir(parents=True, exist_ok=True)
            _unpack(zip_path, d, e.get("COSTAR_ZIP_PASSWORD"))
    if not (d / "data").is_dir():
        raise NotConfigured(f"{zip_path} has no data/ folder: is it the CoStar kit?")
    return d


# --- the offset index ---
def _keys(ds: str, r: dict) -> list[tuple[str, int]]:
    """(kind, key) pairs to index a record under: its own id, and the property it belongs to."""
    keys = [("id", r["id"])] if r.get("id") is not None and ds != "location-occupancy" else []
    if ds == "residential-listings" and r.get("residentialListingId"):
        keys.append(("rid", r["residentialListingId"]))
    if ds in ("commercial-listing-summary", "location-occupancy", "apartment-listing", "residential-listings") and r.get("propertyId"):
        keys.append(("prop", r["propertyId"]))
    if ds == "commercial-listing-summary":
        keys += [("prop", p["id"]) for p in ((r.get("forLeaseSummary") or {}).get("properties") or []) if p.get("id")]
    if ds == "commercial-sale-comp":
        keys += [("prop", e["propertyId"]) for e in r.get("entities") or [] if e.get("propertyId")]
    return keys


def _db_path() -> Path:
    return CACHE / "costar.sqlite"


def _stamp(d: Path) -> str:
    sizes = {ds: (d / "data" / f"{ds}.jsonl").stat().st_size for ds in DATASETS if (d / "data" / f"{ds}.jsonl").exists()}
    return json.dumps({"layout": 2, **sizes})  # bump "layout" when _keys changes


def _connect(d: Path) -> sqlite3.Connection:
    p = _db_path()
    stamp = _stamp(d)
    if p.exists():
        con = sqlite3.connect(p)
        try:
            if con.execute("select v from meta where k = 'stamp'").fetchone() == (stamp,):
                return con
        except sqlite3.Error:
            pass
        con.close()
    with _build:  # one build at a time; a second caller waits, then finds it done
        if p.exists():
            con = sqlite3.connect(p)
            try:
                if con.execute("select v from meta where k = 'stamp'").fetchone() == (stamp,):
                    return con
            except sqlite3.Error:
                pass
            con.close()
        tmp = p.with_suffix(".building")
        tmp.unlink(missing_ok=True)
        tmp.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(tmp)
        con.executescript("create table rec (ds text, kind text, key integer, off integer, len integer);"
                          "create table meta (k text primary key, v text);")
        for ds in DATASETS:
            f = d / "data" / f"{ds}.jsonl"
            if not f.exists():
                continue
            off, rows = 0, []
            with open(f, "rb") as fh:
                for line in fh:
                    if line.strip():
                        rows += [(ds, kind, key, off, len(line)) for kind, key in _keys(ds, json.loads(line))]
                    off += len(line)
            con.executemany("insert into rec values (?, ?, ?, ?, ?)", rows)
        con.execute("create index rec_key on rec (ds, kind, key)")
        con.execute("insert into meta values ('stamp', ?)", (stamp,))
        con.commit()
        con.close()
        tmp.replace(p)
        return sqlite3.connect(p)


def _lookup(ds: str, kind: str, key: int) -> list[dict]:
    d = ensure_kit()
    con = _connect(d)
    try:
        spots = con.execute("select distinct off, len from rec where ds = ? and kind = ? and key = ? order by off", (ds, kind, key)).fetchall()
    finally:
        con.close()
    if not spots:
        return []
    with open(d / "data" / f"{ds}.jsonl", "rb") as fh:
        out = []
        for off, n in spots:
            fh.seek(off)
            out.append(json.loads(fh.read(n)))
    return out


def get(ds: str, key: int) -> dict | None:
    """The record of this dataset with this id, or None."""
    rows = _lookup(ds, "id", key)
    return rows[0] if rows else None


def by_resident_listing_id(rid: int) -> list[dict]:
    """Residential listings with this Homes.com ResidentialListingId (the id models_index.csv calls homes_listing_id)."""
    return _lookup("residential-listings", "rid", rid)


def by_property(ds: str, property_id: int) -> list[dict]:
    """The records of this dataset that belong to a commercial property (or, for residential-listings, to a home)."""
    return _lookup(ds, "prop", property_id)


# --- the scan to record join ---
@functools.cache
def joins() -> dict:
    """The starter CSVs as dicts: model_property, property_models, model_listing, listing_models, model_resident (the
    ResidentialListingIds of a model's listings), property_address."""
    d = ensure_kit()
    out: dict[str, dict] = {k: defaultdict(list) for k in ("model_property", "property_models", "model_listing", "listing_models", "model_resident")}
    out["property_address"] = {}
    with open(d / "commercial-properties.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            pid = int(r["PropertyId"])
            out["property_address"][pid] = ", ".join(x for x in (r["Address"], r["City"], r["State"]) if x)
            if r["MatterportModelId"]:
                out["model_property"][r["MatterportModelId"]].append(pid)
                out["property_models"][pid].append(r["MatterportModelId"])
    with open(d / "residential-listings.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["MatterportModelId"]:
                out["model_listing"][r["MatterportModelId"]].append(int(r["ListingId"]))
                out["model_resident"][r["MatterportModelId"]].append(int(r["ResidentialListingId"]))
                out["listing_models"][int(r["ListingId"])].append(r["MatterportModelId"])
    return out


def _int(v: str | None) -> int | None:
    return int(v) if v and v.strip().isdigit() else None


def resolve(sid: str) -> dict:
    """Which kit records a scan belongs to: {property_ids, listing_ids, source, index_property_id, index_listing_id}.
    `source` is "kit-csv" when the starter CSVs name the scan, else "models_index" when only its columns do."""
    row = scan_index.rows().get(sid) or {}
    j = joins()
    idx_p, idx_l = _int(row.get("costar_property_id")), _int(row.get("homes_listing_id"))  # idx_l is a ResidentialListingId
    pids, lids = list(j["model_property"].get(sid, [])), list(j["model_listing"].get(sid, []))
    source = "kit-csv" if pids or lids else None
    if not pids and not lids:
        pids, lids = ([idx_p] if idx_p else []), [x["id"] for x in by_resident_listing_id(idx_l)] if idx_l else []
        source = "models_index" if pids or lids else None
    return {"property_ids": pids, "listing_ids": lids, "source": source, "index_property_id": idx_p, "index_listing_id": idx_l}


def property_id_of(sid: str) -> int | None:
    """The one property id to group a scan under: the CSV's, else the index's. None without a kit or an id."""
    try:
        r = resolve(sid)
    except NotConfigured:
        return _int((scan_index.rows().get(sid) or {}).get("costar_property_id"))
    return r["property_ids"][0] if r["property_ids"] else None


def agreement() -> dict:
    """How often models_index.csv and the kit's starter CSVs name the same property or listing for a scan."""
    j, rows = joins(), scan_index.rows()
    stats = {}
    # models_index.csv's homes_listing_id is the kit's ResidentialListingId, so that is what the CSV side is compared on
    for name, csv_map, col in (("property", j["model_property"], "costar_property_id"), ("listing", j["model_resident"], "homes_listing_id")):
        c = defaultdict(int)
        for sid in set(rows) | set(csv_map):
            idx = _int((rows.get(sid) or {}).get(col))
            k = csv_map.get(sid)
            c["scans_in_csv" if k else "scans_not_in_csv"] += 1
            if k and idx:
                c["both_agree" if idx in k else "both_disagree"] += 1
            elif k:
                c["csv_only"] += 1
            elif idx:
                c["index_only"] += 1
        stats[name] = dict(c)
    stats["listing"]["both_disagree_id_not_in_kit"] = sum(
        1 for sid, k in j["model_resident"].items() if (i := _int((rows.get(sid) or {}).get("homes_listing_id"))) and i not in k and not by_resident_listing_id(i))
    stats["property"]["both_disagree_id_not_in_kit"] = sum(
        1 for sid, k in j["model_property"].items() if (i := _int((rows.get(sid) or {}).get("costar_property_id"))) and i not in k and not get("commercial-property", i))
    return stats


# --- shaping a record for the API ---
DROP = {"contacts", "listingContacts", "propertyContacts", "notes", "parcelNumbers", "parcelReferences", "addresses", "attachments",
        "primaryPhoto", "agents", "offices", "openHouses", "history", "media", "source", "mls", "transferDocuments", "schools",
        "units", "aliases", "brandProfiles", "permissionLevels"}


@functools.cache
def _enums() -> dict:
    return json.loads((ensure_kit() / "schemas" / "enums.json").read_text())


def _trim(v, path: str, cut: dict):
    """A copy without DROP keys, nulls and empty containers, lists capped at MAX_LIST, text at MAX_TEXT.
    What was cut short is recorded in `cut` as path -> original length."""
    if isinstance(v, dict):
        out = {}
        for k, x in v.items():
            if k in DROP:
                continue
            x = _trim(x, f"{path}.{k}" if path else k, cut)
            if x is not None and x != [] and x != {}:
                out[k] = x
        return out
    if isinstance(v, list):
        if len(v) > MAX_LIST:
            cut[path + "[]"] = len(v)
        return [x for x in (_trim(i, path + "[]", cut) for i in v[:MAX_LIST]) if x is not None and x != [] and x != {}]
    if isinstance(v, str) and len(v) > MAX_TEXT:
        cut[path] = len(v)
        return v[:MAX_TEXT]
    return v


def _shape(rec, full: bool, cut: dict):
    return rec if full else _trim(rec, "", cut)


def _dig(r, path: str):
    for part in path.split("."):
        r = r.get(part) if isinstance(r, dict) else None
    return r


def _first(r: dict, *paths: str):
    """(value, path) of the first of these dotted paths that is set."""
    for p in paths:
        v = _dig(r, p)
        if v is not None:
            return v, p
    return None, paths[0]


def _event_year(p: dict, kinds: tuple[int, ...]) -> tuple[int | None, str]:
    years = [e["year"] for e in p.get("constructionEvents") or [] if e.get("eventType") in kinds and e.get("year")]
    return (max(years) if years else None), "constructionEvents[eventType in " + "|".join(map(str, kinds)) + "].year"


def _decode(enum: str, v):
    return _enums().get(enum, {}).get(str(v), v) if v is not None else None


def claims(bundle: dict) -> dict:
    """What the record says that a scan can check, each with the exact path it came from in the full record.
    {id: {value, unit, path}}. Only values that are present appear."""
    out: dict[str, dict] = {}

    def put(key: str, value, unit: str | None, path: str):
        if value not in (None, [], {}, ""):
            out[key] = {"value": value, "unit": unit, "path": path}

    p = bundle.get("property")
    if p:
        for key, field, unit in (("gross_area", "grossBuildingAreaSquareFeet", "ft2"), ("rentable_area", "rentableBuildingAreaSquareFeet", "ft2"),
                                 ("typical_floor_area", "grossTypicalFloorSquareFeet", "ft2"), ("stories", "numStoriesAboveGrade", None),
                                 ("height", "buildingHeightInFeet", "ft"), ("parking_ratio", "parkingRatio", "spaces per 1,000 ft2"),
                                 ("has_sprinklers", "hasSprinklers", None)):
            put(key, p.get(field), unit, field)
        year, path = _event_year(p, (2,))
        put("year_built", year, None, path)
        year, path = _event_year(p, (4,))
        put("year_renovated", year, None, path)
        put("construction_material", _decode("BuildingConstructionMaterialType", p.get("buildingConstructionMaterial")), None, "buildingConstructionMaterial")
        put("sprinkler_type", _decode("SprinklerType", p.get("sprinklerType")) if p.get("sprinklerType") else None, None, "sprinklerType")
        spaces = [x["totalSpaces"] for x in p.get("parking") or [] if x.get("totalSpaces")]
        put("parking_spaces", sum(spaces) if spaces else None, None, "parking[].totalSpaces (sum)")
        put("amenity_ids", p.get("amenities"), "ids; the kit has no catalog to decode them", "amenities")
        put("floor_areas", [f["floorSize"]["squareFeet"] for f in p.get("floors") or [] if (f.get("floorSize") or {}).get("squareFeet")] or None,
            "ft2", "floors[].floorSize.squareFeet")
        for sect in ("propertyIndustrial", "propertyFlex", "propertyOffice", "propertyRetail"):
            s = p.get(sect)
            if not s:
                continue
            ft, path = _first(s, "structural.ceilingHeightFeet")
            if ft is not None:
                put("ceiling_height", ft + (_dig(s, "structural.ceilingHeightInches") or 0) / 12, "ft", f"{sect}.structural.ceilingHeightFeet (+ ceilingHeightInches / 12)")
            docks = [s[k] for k in ("numExternalLoadingDocks", "numInternalLoadingDocks") if s.get(k) is not None]
            put("dock_doors", sum(docks) if docks else None, None, f"{sect}.numExternalLoadingDocks + numInternalLoadingDocks")
            put("drive_in_bays", _dig(s, "driveInBays.numDriveInBays"), None, f"{sect}.driveInBays.numDriveInBays")
            put("crane_hook_height", _dig(s, "cranes.craneHookHeightFeet"), "ft", f"{sect}.cranes.craneHookHeightFeet")
            put("rentable_area", s.get("rentableBuildingAreaSquareFeet") if "rentable_area" not in out else None, "ft2", f"{sect}.rentableBuildingAreaSquareFeet")
            put("slab_to_slab", _dig(s, "structural.slabToSlabHeightFeet"), "ft", f"{sect}.structural.slabToSlabHeightFeet")
            lifts = [e.get("numElevators") or 1 for e in _dig(s, "structural.elevators") or [] if e.get("elevatorType") == 1 and e.get("elevatorState") == 1]
            put("passenger_elevators", sum(lifts) if lifts else None, None, f"{sect}.structural.elevators[elevatorType=1].numElevators")
        pa = p.get("propertyApartment")
        if pa:
            put("units", pa.get("totalNumUnits"), None, "propertyApartment.totalNumUnits")
            put("is_walkup", pa.get("isWalkup"), None, "propertyApartment.isWalkup")
            lifts = [e.get("numElevators") or 1 for e in pa.get("elevators") or [] if e.get("elevatorType") == 1 and e.get("elevatorState") == 1]
            put("passenger_elevators", sum(lifts) if lifts else None, None, "propertyApartment.elevators[elevatorType=1].numElevators")
            put("unit_mix", [{k: m.get(k) for k in ("numBeds", "numBaths", "minSquareFeet", "maxSquareFeet", "numUnits") if m.get(k) is not None}
                             for m in pa.get("models") or []][:MAX_LIST] or None, None, "propertyApartment.models[]")
        for sect in ("propertyResidence", "propertyPropertyResidence"):
            r = p.get(sect)
            if r:
                for key, field, unit in (("beds", "numBeds", None), ("baths", "numBaths", None), ("ceiling_height_main", "ceilingHeightMainInFeet", "ft")):
                    put(key, r.get(field), unit, f"{sect}.{field}")
    unit = (bundle.get("unit_match") or {})
    for scope in ("model", "unit"):
        m = unit.get(scope)
        if m:
            base = "propertyApartment.models[]" if scope == "model" else "propertyApartment.models[].units[]"
            put("unit_beds", m.get("numBeds"), None, base + ".numBeds")
            put("unit_baths", m.get("numBaths"), None, base + ".numBaths")
            put("unit_area_min", m.get("minSquareFeet"), "ft2", base + ".minSquareFeet")
            put("unit_area_max", m.get("maxSquareFeet"), "ft2", base + ".maxSquareFeet")
    a = bundle.get("apartment_listing")
    if a:
        put("year_built", a.get("yearBuilt") if "year_built" not in out else None, None, "apartment-listing.yearBuilt")
        put("listing_unit_area_min", a.get("minSquareFeet"), "ft2", "apartment-listing.minSquareFeet")
        put("listing_unit_area_max", a.get("maxSquareFeet"), "ft2", "apartment-listing.maxSquareFeet")
    l = bundle.get("residential_listing")
    if l:
        for key, paths, unit in (("beds", ("property.bedsMax", "property.bedsMin"), None), ("baths", ("property.bathsMax", "property.bathsMin"), None),
                                 ("living_area", ("property.sqftMax", "property.sqftMin"), "ft2"), ("stories", ("property.stories", "resoValues.structure.stories"), None),
                                 ("stories_in_building", ("resoValues.structure.storiesTotal",), None), ("year_built", ("property.yearBuilt", "resoValues.structure.yearBuilt"), None),
                                 ("parking_spaces", ("property.totalParkingSpaces", "resoValues.structure.parkingTotal"), None),
                                 ("has_elevator", ("resoValues.hasElevator",), None), ("has_accessibility_features", ("resoValues.hasAccessibilityFeatures",), None)):
            v, path = _first(l, *paths)
            put(key, v, unit, "residential-listings." + path)
    f = bundle.get("residential_features")
    if f:
        for key, field, unit in (("beds", "totalBedrooms", None), ("baths", "totalBathrooms", None), ("living_area", "homeSquareFeet", "ft2"),
                                 ("stories", "numberOfStories", None), ("year_built", "yearBuilt", None), ("parking_spaces", "totalParkingSpaces", None)):
            v = _dig(f, "derivedValues." + field)
            if key not in out:
                put(key, v, unit, "residential-listing-features.derivedValues." + field)
    return out


def _scan_scope(p: dict, sid: str) -> dict:
    """Which part of the property this scan is attached to, by the Matterport model ids on the property's attachments."""
    hit = lambda items: any(a.get("videoKey") == sid for a in items or [])  # noqa: E731
    pa = p.get("propertyApartment") or {}
    for m in pa.get("models") or []:
        for u in m.get("units") or []:
            if hit(u.get("attachments")):
                return {"scope": "unit", "model": m, "unit": u}
        if hit(m.get("attachments")):
            return {"scope": "floor_plan", "model": m}
    for u in pa.get("units") or []:
        if hit(u.get("attachments")):
            return {"scope": "unit", "unit": u}
    return {"scope": "building" if hit(p.get("attachments")) else "unknown"}


def record(sid: str, full: bool = False) -> dict:
    """Everything the kit holds for a scan: the property and what hangs off it, and the residential listing.
    Trimmed to a readable size unless full; `trimmed` says what was cut. `claims` is the short list of
    checkable facts with their source paths."""
    check(sid, "sid")
    ensure_kit()
    ids = resolve(sid)
    if not ids["property_ids"] and not ids["listing_ids"]:
        raise LookupError(f"scan {sid} has no CoStar record in the kit")
    cut: dict = {}
    out: dict = {"sid": sid, "match": {k: ids[k] for k in ("source", "property_ids", "listing_ids", "index_property_id", "index_listing_id")}}
    bundle: dict = {}
    for pid in ids["property_ids"][:1]:
        prop = get("commercial-property", pid)
        if not prop:
            out["match"]["note"] = f"property {pid} is named by the join but is not in commercial-property.jsonl"
            continue
        scope = _scan_scope(prop, sid)
        bundle["property"], bundle["unit_match"] = prop, scope
        listings = by_property("commercial-listing-summary", pid)
        tenancies = sorted(by_property("location-occupancy", pid), key=lambda t: t.get("fromDate") or "", reverse=True)
        sales = sorted(by_property("commercial-sale-comp", pid), key=lambda s: s.get("soldDate") or "", reverse=True)
        apt = by_property("apartment-listing", pid)
        bundle["apartment_listing"] = apt[0] if apt else None
        tenants = []
        for t in tenancies if full else tenancies[:MAX_TENANCIES]:
            company = get("company-detail", t["tenantLocationId"]) if t.get("tenantLocationId") else None
            t = dict(t, tenant=({k: company.get(k) for k in ("id", "name", "numEmployees", "suite", "businessStatus")} if company else None))
            tenants.append(t)
        out.update({
            "scope": scope["scope"],
            "property": _shape(prop, full, cut),
            "unit_match": {k: _shape({kk: vv for kk, vv in v.items() if kk != "attachments"}, full, cut) for k, v in scope.items() if k in ("model", "unit")} or None,
            "listings": [_shape(x, full, cut) for x in listings],
            "tenancies": {"count": len(tenancies), "items": [_shape(t, full, cut) for t in tenants]},
            "sale_comps": {"count": len(sales), "items": [_shape(s, full, cut) for s in (sales if full else sales[:MAX_SALES])]},
            "apartment_listing": _shape(apt[0], full, cut) if apt else None,
        })
    listings = [x for x in (get("residential-listings", lid) for lid in ids["listing_ids"]) if x]
    if ids["listing_ids"] and not listings:
        out["match"]["note"] = f"listings {ids['listing_ids']} are named by the join but are not in residential-listings.jsonl"
    # a scan can sit on several listings of one home (a sale, then a rental): show the most recently listed
    for lst in sorted(listings, key=lambda x: x.get("listDate") or "", reverse=True)[:1]:
        lid = lst["id"]
        feat = get("residential-listing-features", lid)
        bundle["residential_listing"], bundle["residential_features"] = lst, feat
        same_home = [x["id"] for x in by_property("residential-listings", lst["propertyId"]) if x["id"] != lid] if lst.get("propertyId") else []
        out["residential_listing"] = _shape(lst, full, cut)
        out["residential_features"] = _shape(feat, full, cut) if feat else None
        out["other_listings_of_this_home"] = same_home
    out["claims"] = claims(bundle)
    out["trimmed"] = cut
    return out


def scans_of_property(property_id: int) -> list[str]:
    """Scan ids of one property: the starter CSV's, plus scans whose models_index.csv column names it and the CSV does not."""
    try:
        sids = list(joins()["property_models"].get(property_id, []))
        listed = set(joins()["model_property"])
    except NotConfigured:
        sids, listed = [], set()
    sids += [sid for sid, r in scan_index.rows().items() if _int(r["costar_property_id"]) == property_id and sid not in sids and sid not in listed]
    return sids


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if args[:1] == ["--check"]:
        print(json.dumps(agreement(), indent=1))
    elif args[:1] == ["--index"]:
        _connect(ensure_kit()).close()
        print("index ready:", _db_path())
    else:
        print("usage: python -m threshold.sources.costar --check | --index", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
