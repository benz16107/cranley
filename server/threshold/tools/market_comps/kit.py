"""The CoStar kit's commercial properties as compact rows, for comps, scorecards and candidate search.

One pass over commercial-property, commercial-listing-summary and commercial-sale-comp builds a row per non-residential
property: type, class, size, year, location, the industrial facts, normalised asking rents of its active lease spaces,
the space marketed as available, and its single-property sales with price per square foot. The rows are cached as JSON
in $THRESHOLD_DATA_DIR/cache (sponsor data, never in git) and rebuilt when a data file changes size.

The pure functions (`summarize`, `rents`, `sales`) take records, so tests use small hand-made ones.
"""
from __future__ import annotations

import functools
import json
import math
import statistics
from collections import defaultdict

from ...config import CACHE

SKIP_TYPES = {11, 15, 16}  # multifamily, residential, homes: not business space
TYPE_NAME = {1: "Hospitality", 2: "Industrial", 3: "Land", 5: "Office", 6: "Retail", 7: "Flex", 8: "Sports and entertainment",
             9: "Mixed use", 10: "Specialty", 13: "Healthcare"}
CLASS_NAME = {1: "A", 2: "B", 3: "C", 4: "F"}
SERVICE = {7: "Full service", 8: "Industrial gross", 9: "Modified gross", 10: "Net", 12: "Double net", 13: "Triple net (NNN)",
           19: "Full service gross", 1: "Plus cleaning", 2: "Plus electric and cleaning", 4: "Plus electric", 6: "Plus utilities",
           15: "Tenant electric", 11: "Negotiable", 14: "To be determined"}
PRICE_STATUS = {1: "affidavit", 2: "approximate", 3: "confirmed", 4: "declaration", 5: "full value", 6: "mini", 7: "unconfirmed",
                8: "allocated"}
LEASE_TYPES = {14, 16, 17, 19, 20, 21, 28}
SUBLEASE_TYPES = {19, 20}
SPRINKLER = {1: "wet", 2: "dry", 3: "ESFR"}
LAYOUT = 4  # bump when a row's shape changes


def _dig(r, path: str):
    for part in path.split("."):
        r = r.get(part) if isinstance(r, dict) else None
    return r


def rents(listings: list[dict]) -> list[dict]:
    """Asking rents of active lease spaces as $ per ft² per year: rateLow and rateHigh averaged, monthly rates times
    12, zeros (no rate given), off-market spaces, per-acre rates and other currencies dropped."""
    out = []
    for l in listings:
        f = l.get("forLeaseSummary")
        if not f or l.get("listingType") not in LEASE_TYPES or l.get("listingStatus") != 1:
            continue
        if f.get("askingRateMeasurementType") not in (0, 1, None):  # 2 acres, 3 square metres
            continue
        for s in f.get("spaces") or []:
            if s.get("dateOffMarket") or s.get("isInventoryOffMarket") or s.get("monetaryUnit") not in (1, None):
                continue
            lo, hi = s.get("rateLow") or 0, s.get("rateHigh") or 0
            per = {1: 12, 2: 1}.get(s.get("rateBasis"))
            if not (lo or hi) or not per:
                continue
            out.append({"rate": round((lo + (hi or lo)) / 2 * per, 2), "service": SERVICE.get(s.get("serviceType"), "unknown"),
                        "sf": s.get("squareFeetMax"), "sublease": l["listingType"] in SUBLEASE_TYPES, "listing": l.get("id"),
                        "use": s.get("spaceUse")})
    return out


def available(listings: list[dict]) -> dict:
    """Space marketed for lease now: total ft² over active spaces and the largest contiguous block."""
    total, block, sizes = 0.0, 0.0, []
    for l in listings:
        f = l.get("forLeaseSummary")
        if not f or l.get("listingType") not in LEASE_TYPES or l.get("listingStatus") != 1:
            continue
        for s in f.get("spaces") or []:
            if s.get("dateOffMarket") or s.get("isInventoryOffMarket"):
                continue
            total += s.get("squareFeetMax") or 0
            block = max(block, s.get("squareFeetMaxContiguous") or 0, s.get("squareFeetMax") or 0)
            if s.get("squareFeetMax"):
                sizes.append(round(s["squareFeetMax"]))
        block = max(block, f.get("maxContiguousSquareFeet") or 0)
    return {"sf": round(total) or None, "max_contiguous_sf": round(block) or None, "spaces": sorted(set(sizes))}


def sales(pid: int, comps: list[dict], rba: float | None) -> list[dict]:
    """Single-property sales of this property with a price in dollars: price, status, date and price per ft²."""
    out = []
    for s in comps:
        ents = [e for e in s.get("entities") or [] if e.get("assetType") in (1, None)]
        if len(ents) != 1 or ents[0].get("propertyId") != pid or not s.get("soldForPrice") or s.get("monetaryUnit") not in (1, None):
            continue
        sf = ents[0].get("totalSquarefeet") or rba
        out.append({"price": s["soldForPrice"], "status": PRICE_STATUS.get(s.get("salePriceStatus"), "unknown"),
                    "date": (s.get("soldDate") or "")[:10], "sf": sf, "psf": round(s["soldForPrice"] / sf, 2) if sf else None,
                    "id": s.get("id")})
    return sorted(out, key=lambda x: x["date"], reverse=True)


def _year(p: dict, kind: int) -> int | None:
    ys = [e["year"] for e in p.get("constructionEvents") or [] if e.get("eventType") == kind and e.get("year")]
    return max(ys) if ys else None


def summarize(p: dict, listings: list[dict], comps: list[dict]) -> dict:
    """The compact row of one property record with its listings and sale comps."""
    a = p.get("primaryAddress") or {}
    sect = next((p[k] for k in ("propertyIndustrial", "propertyFlex", "propertyOffice", "propertyRetail") if p.get(k)), {}) or {}
    st = sect.get("structural") or {}
    clear = st.get("ceilingHeightFeet")
    docks = [sect[k] for k in ("numExternalLoadingDocks", "numInternalLoadingDocks") if sect.get(k) is not None]
    park = p.get("parking") or []
    cars = sum(x.get("totalSpaces") or 0 for x in park if x.get("parkingType") != 5)
    trailers = sum(x.get("totalSpaces") or 0 for x in park if x.get("parkingType") == 5)
    rba = p.get("rentableBuildingAreaSquareFeet") or sect.get("rentableBuildingAreaSquareFeet") or \
        sect.get("grossLeasableAreaSquareFeet") or p.get("grossBuildingAreaSquareFeet")
    street = " ".join(str(x) for x in (a.get("streetNumber"), a.get("streetDirection"), a.get("streetName"), a.get("streetType")) if x)
    elec = sect.get("electric") or {}
    return {
        "id": p["id"], "type": TYPE_NAME.get(p.get("propertyType"), "Other"), "type_id": p.get("propertyType"),
        "subtype": p.get("propertySubtype"), "class": CLASS_NAME.get(p.get("buildingClass")),
        "name": p.get("name") or p.get("propertyName"), "address": ", ".join(x for x in (street, a.get("city")) if x) or None,
        "city": a.get("city"), "lat": a.get("latitude"), "lon": a.get("longitude"),
        "rba": rba, "stories": p.get("numStoriesAboveGrade"), "year_built": _year(p, 2), "year_renovated": _year(p, 4),
        "clear_ft": round(clear + (st.get("ceilingHeightInches") or 0) / 12, 1) if clear else None,
        "docks": sum(docks) if docks else None, "drive_ins": _dig(sect, "driveInBays.numDriveInBays"),
        "parking_ratio": p.get("parkingRatio"), "parking_spaces": cars or None, "trailer_spaces": trailers or None,
        "sprinklers": SPRINKLER.get(p.get("sprinklerType")) or ({True: "yes", False: "no"}.get(p.get("hasSprinklers"))),
        "rail": bool(sect.get("railAccess")) if sect.get("railAccess") is not None else None,
        "amps": elec.get("amps") or elec.get("ampsHigh") or elec.get("ampsLow"),
        "owner_occupied": sect.get("isOwnerOccupied"),
        "rents": rents(listings), "available": available(listings), "sales": sales(p["id"], comps, rba),
    }


def asking_rent(row: dict) -> dict | None:
    """The row's area-weighted asking rent over its direct spaces (subleases when there is no direct space):
    {rate, service, spaces, sublease}."""
    rs = [r for r in row.get("rents") or [] if not r["sublease"]] or (row.get("rents") or [])
    if not rs:
        return None
    w = [(r["rate"], r["sf"] or 1) for r in rs]
    services = sorted({r["service"] for r in rs})
    return {"rate": round(sum(a * b for a, b in w) / sum(b for _, b in w), 2), "service": ", ".join(services),
            "spaces": len(rs), "sublease": all(r["sublease"] for r in rs)}


def last_sale(row: dict) -> dict | None:
    return next((s for s in row.get("sales") or [] if s.get("psf")), None)


def km(lat1, lon1, lat2, lon2) -> float:
    k = math.cos(math.radians((lat1 + lat2) / 2))
    return 6371 * math.hypot(math.radians(lat2 - lat1), math.radians(lon2 - lon1) * k)


def median(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def percentile(x: float, xs: list[float]) -> float | None:
    """Share of xs at or below x, 0 to 100."""
    xs = [v for v in xs if v is not None]
    return round(100 * sum(v <= x for v in xs) / len(xs)) if xs and x is not None else None


# ---- the cached rows over the whole kit ----------------------------------------------------------------

def _build(kit) -> dict[int, dict]:
    d = kit / "data"
    props: dict[int, dict] = {}
    with open(d / "commercial-property.jsonl", encoding="utf-8") as fh:
        for line in fh:
            # the type sits near the front of each record; skip apartments without parsing 60 KB of JSON
            head = line[:4000]
            if any(f'"propertyType": {t},' in head or f'"propertyType":{t},' in head for t in SKIP_TYPES):
                continue
            p = json.loads(line)
            if p.get("propertyType") not in SKIP_TYPES:
                props[p["id"]] = p
    listings, comps = defaultdict(list), defaultdict(list)
    with open(d / "commercial-listing-summary.jsonl", encoding="utf-8") as fh:
        for line in fh:
            l = json.loads(line)
            if l.get("propertyId") in props:
                listings[l["propertyId"]].append(l)
    with open(d / "commercial-sale-comp.jsonl", encoding="utf-8") as fh:
        for line in fh:
            s = json.loads(line)
            for pid in {e.get("propertyId") for e in s.get("entities") or []} & props.keys():
                comps[pid].append(s)
    return {pid: summarize(p, listings[pid], comps[pid]) for pid, p in props.items()}


@functools.cache
def rows() -> dict[int, dict]:
    """Every non-residential property in the kit as a compact row, keyed by PropertyId. Raises LookupError without a kit."""
    from ...sources import costar
    kit = costar.ensure_kit()
    stamp = json.dumps({"layout": LAYOUT, **{f.name: f.stat().st_size for f in (kit / "data").glob("commercial-*.jsonl")}})
    f = CACHE / "commercial_rows.json"
    if f.exists():
        body = json.loads(f.read_text())
        if body.get("stamp") == stamp:
            return {int(k): v for k, v in body["rows"].items()}
    out = _build(kit)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"stamp": stamp, "rows": out}))
    return out


def row(pid: int | None) -> dict | None:
    if not pid:
        return None
    try:
        return rows().get(int(pid))
    except LookupError:
        return None


PROFILE_TYPES = {"industrial": {2, 7}, "office": {5}, "retail": {6}, "flex": {7, 2}}
