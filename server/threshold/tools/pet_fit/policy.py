"""What the records say about pets: the apartment community's pet policies (CoStar property record, per pet type,
with the unit's floor plan overriding the community), walk-up and elevators, and for homes the listing's pet, fence,
flooring, pool and dog-park lines (Homes.com listing features). Each value keeps the record path it came from."""
from __future__ import annotations

import re

PET_TYPE = {0: "unknown", 1: "bird", 2: "cat", 3: "dog", 4: "fish", 5: "reptile", 6: "other"}
KIND_TYPES = {"dog": (3,), "cat": (2,), "small": (6, 1, 5, 4)}


def bundle(sid: str | None, property_id: int | None) -> dict:
    """{property, unit_model, listing, features, path_prefix} from the kit; empty without one."""
    from ...sources import costar
    out: dict = {}
    if sid:
        try:
            r = costar.record(sid, full=True)
        except LookupError:
            r = {}
        out["property"] = r.get("property")
        out["unit_model"] = (r.get("unit_match") or {}).get("model")
        out["listing"] = r.get("residential_listing")
        out["features"] = r.get("residential_features")
    if not out.get("property") and property_id:
        try:
            out["property"] = costar.get("commercial-property", int(property_id))
        except LookupError:
            pass
    return out


def apartment(b: dict) -> dict | None:
    """The community's pet rules, or None when the record is not an apartment community."""
    p = b.get("property") or {}
    pa = p.get("propertyApartment")
    if not pa:
        return None
    rp = pa.get("residentialProfile") or {}
    base = "propertyApartment.residentialProfile"
    pols, where = rp.get("petPolicies") or [], base
    um = b.get("unit_model") or {}
    if (um.get("residentialProfile") or {}).get("petPolicies"):
        pols, where = um["residentialProfile"]["petPolicies"], f"propertyApartment.models[id={um.get('id')}].residentialProfile"
    return {"property_id": p.get("id"), "no_pets": rp.get("hasNoPetsAllowed"), "negotiable": rp.get("isPetNegotiable"),
            "policies": [{**x, "type": PET_TYPE.get(x.get("petType"), "unknown")} for x in pols], "path": f"{where}.petPolicies",
            "walkup": pa.get("isWalkup"), "elevators": len(pa.get("elevators") or []),
            "units": pa.get("totalNumUnits"), "no_pets_path": f"{base}.hasNoPetsAllowed"}


def policy_for(apt: dict, kind: str) -> dict | None:
    return next((x for x in apt["policies"] if x.get("petType") in KIND_TYPES[kind]), None)


def lines(b: dict, *subcats: str) -> list[str]:
    f = b.get("features") or {}
    return [ln for s in f.get("sections") or [] if not subcats or s.get("subcategory") in subcats for ln in s.get("lines") or []]


def listing(b: dict) -> dict:
    """Pet, fence, floor, pool and community lines from a home's listing; empty lists when the kit has none."""
    allx = lines(b)
    lst = b.get("listing") or {}
    pets = lines(b, "Pet Policy")
    return {"has": bool(b.get("features") or lst), "pet_friendly": lst.get("isPetFriendly"),
            "pets": pets, "no_pets": any(re.search(r"no pets", x, re.IGNORECASE) for x in pets),
            "fence": [x for x in allx if re.search(r"fenc|block wall", x, re.IGNORECASE)],
            "floors": lines(b, "Flooring"),
            "pool": lines(b, "Pool"),
            "dog_park": [x for x in lines(b, "Recreation", "Community Features", "Amenities") if re.search(r"dog|pet", x, re.IGNORECASE)],
            "id": lst.get("id")}


def fenced(lst: dict) -> str | None:
    """'yes' when a listing line names a fence around the yard or lot, 'partial' for a partial one; a fence around the
    pool or spa alone does not count."""
    ls = [x.lower() for x in lst.get("fence") or [] if not re.search(r"pool|spa", x, re.IGNORECASE)]
    if not ls:
        return None
    return "partial" if any("partial" in x for x in ls) else "yes"
