"""Resolve a Place (scan, CoStar property, address or point) to a Site: coordinates, address, property and scans.

Tools call it through `ctx.site(place)`; tests swap it with `ToolContext(sites=...)`. Lookups use the scan index
(models_index.csv) and the CoStar kit's property records. There is no street geocoder: an address must match a scanned
building or a CoStar property, otherwise the person gives a point.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from .types import AddressScope, GeoScope, Place, PropertyScope, ScanScope

NEAR_M = 60  # a point this close to a scanned building is that building


@dataclass
class Site:
    place: Place
    lat: float | None
    lon: float | None
    address: str | None = None
    city: str | None = None
    property_id: int | None = None
    sids: list[str] = field(default_factory=list)
    located_by: str = ""
    scans: list[dict] = field(default_factory=list)  # [{sid, name, kind}] for sids, from the index
    record: dict | None = None                       # the CoStar commercial-property record, when there is one

    @property
    def key(self) -> str:
        return self.place.key()

    def scope(self):
        """The ToolResult scope for this place."""
        p = self.place
        if p.scan:
            return ScanScope(sid=p.scan)
        if p.property_id is not None:
            return PropertyScope(property_id=p.property_id, sids=self.sids)
        if p.address:
            return AddressScope(address=p.address, geo=(self.lon, self.lat) if self.lat is not None else None)
        return GeoScope(geo=p.geo)


def _words(s: str | None) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", (s or "").lower()))


def _metres(lat1, lon1, lat2, lon2) -> float:
    k = math.cos(math.radians((lat1 + lat2) / 2))
    return 6371000 * math.hypot(math.radians(lat2 - lat1), math.radians(lon2 - lon1) * k)


def _row_site(place: Place, r: dict, how: str) -> Site:
    from ..sources import costar, index
    pub = index.public(r)
    return Site(place, pub["lat"], pub["lon"], pub["address"], pub["city"], costar.property_id_of(r["sid"]),
                [r["sid"]], how, [{"sid": r["sid"], "name": pub["name"], "kind": pub["kind"]}])


def _property_site(place: Place, pid: int) -> Site:
    from ..sources import costar, index
    sids = costar.scans_of_property(pid)
    rec = None
    try:
        rec = costar.get("commercial-property", pid)
    except costar.NotConfigured:
        pass
    if not sids and not rec:
        raise LookupError(f"no CoStar property {pid}")
    a = (rec or {}).get("primaryAddress") or {}
    rows = [index.public(index.rows()[s]) for s in sids if s in index.rows()]
    first = next((r for r in rows if r["lat"] is not None), {})
    street = " ".join(x for x in (a.get("streetNumber"), a.get("streetDirection"), a.get("streetName"), a.get("streetType")) if x)
    return Site(place, a.get("latitude") or first.get("lat"), a.get("longitude") or first.get("lon"),
                ", ".join(x for x in (street, a.get("city")) if x) or first.get("address"), a.get("city") or first.get("city"),
                pid, sids, "CoStar property record" if a.get("latitude") else "scan index",
                [{"sid": r["sid"], "name": r["name"], "kind": r["kind"]} for r in rows], rec)


def default_site(place: Place) -> Site:
    from ..sources import costar, index
    if place.scan:
        r = index.rows().get(place.scan)
        if not r and place.scan.startswith("u_"):  # a person's own phone scan: not in the index, no location
            return Site(place, None, None, sids=[place.scan], located_by="phone scan with no location",
                        scans=[{"sid": place.scan, "name": None, "kind": None}])
        if not r:
            raise LookupError(f"no scan {place.scan} in the index")
        return _row_site(place, r, "scan index")
    if place.property_id is not None:
        return _property_site(place, place.property_id)
    if place.address:
        want = _words(place.address)
        for r in index.rows().values():
            if r["address"] and want and (want in _words(r["address"]) or _words(r["address"]) in want):
                return _whole(_row_site(place, r, "scan index address"))
        try:
            for pid, addr in costar.joins()["property_address"].items():
                if want and want in _words(addr):
                    s = _property_site(place, pid)
                    s.located_by = "CoStar property address"
                    return s
        except costar.NotConfigured:
            pass
        raise LookupError(f"I cannot place \"{place.address}\": no scanned building or CoStar property has that "
                          "address. Give a point (longitude, latitude) instead.")
    lon, lat = place.geo
    best, best_d = None, NEAR_M
    for r in index.rows().values():
        try:
            d = _metres(lat, lon, float(r["lat"]), float(r["lon"]))
        except ValueError:
            continue
        if d < best_d:
            best, best_d = r, d
    if not best:
        return Site(place, lat, lon, located_by="point given")
    s = _row_site(place, best, f"point given; nearest scanned building {round(best_d)} m away")
    s.lat, s.lon = lat, lon
    return _whole(s)


def _whole(s: Site) -> Site:
    """A place that lands on one scanned building covers the building's whole CoStar property."""
    if s.property_id:
        whole = _property_site(s.place, s.property_id)
        s.sids, s.scans, s.record = whole.sids, whole.scans, whole.record
    return s
