"""Home search for pets and kids: scanned homes across Houston or Los Angeles filtered by what pet owners and
parents ask. Apartments by the community's pet policy (dogs up to a weight, cats, pet rent) from the CoStar kit;
houses by the listing (fenced yard, no pool, pet friendly), the yard measured by pet_fit runs or worked out from cached
Vexcel answers, and the distance to playgrounds, parks, dog parks, schools or courts from one city-wide OpenStreetMap
request. Nothing here calls Vexcel or Matterport: homes no earlier run has measured cannot answer a yard criterion,
and the result says how many could."""
from __future__ import annotations

import functools
import json
from typing import Literal

from pydantic import BaseModel

from ... import nearby
from ...aerial import site as aerial
from ...aerial import vexcel
from ...config import CACHE
from ...sources import index
from .. import Check, Finding, Metric, NotApplicable, Source, ToolResult, Verdict, field, tool
from ..pet_fit import policy, yard
from ..types import Action, GeoAnchor, Pin, PinsOverlay, ScansScope

KIT = Source(layer="costar", method="lookup", confidence="medium", note="CoStar kit: community pet policy, listing features")
NEAR = Source(layer="model", method="geometry", confidence="low",
              note=f"{nearby.NOTE}; straight line times {nearby.DETOUR}, at {nearby.WALK_M_MIN:g} m a minute")
YARD = Source(layer="vexcel", method="geometry", confidence="medium",
              note="Yard behind the house measured by a pet_fit run, else parcel less footprint from cached Vexcel answers")
NearCat = Literal[nearby.CITY_CATEGORIES]
NEAR_SETS = {"playground and park": ["playground", "park"], "dog park": ["dog_park"], "park": ["park"],
             "elementary school": ["school_elementary"], "playground and elementary school": ["playground", "school_elementary"],
             "soccer field": ["soccer"], "tennis court": ["tennis"], "pickleball court": ["pickleball"]}


class Inputs(BaseModel):
    city: Literal["Houston", "Los Angeles"] = field(ask="Which city, Houston or Los Angeles?", pref="search.city")
    kind: Literal["house", "apartment_unit"] = field("house", pref="search.kind", description="Houses or apartments")
    dog_lb: float | None = field(None, gt=0, le=250, description="Apartments: the community allows a dog of this weight")
    cats: bool = field(False, description="Apartments: the community allows cats")
    max_pet_rent: float | None = field(None, ge=0, description="Apartments: monthly pet rent at most this, in dollars")
    fenced: bool = field(False, description="Houses: the listing says the yard is fenced")
    no_pool: bool = field(False, description="Houses: no pool (Vexcel, else the listing)")
    min_yard_m2: float | None = field(None, gt=0, description="Houses: yard at least this big (behind the house when pet_fit measured it)")
    min_flat_pct: float | None = field(None, ge=0, le=100, description="Houses: at least this share of the back yard flat (pet_fit runs only)")
    near: list[NearCat] = field([], description="Each of these within `walk_min` (straight-line estimate)")
    near_set: Literal[tuple(NEAR_SETS)] | None = field(None, description="A common set of places to be near, added to `near`")
    walk_min: float = field(10, gt=0, le=60, unit="min", description="Walk for `near`")
    limit: int = field(20, ge=1, le=100)


def _stamp() -> str:
    from ...sources import costar
    return str(costar.kit_dir().stat().st_mtime_ns)


@functools.lru_cache(maxsize=4)
def table(city: str, kind: str) -> list[dict]:
    """One row per scanned home of this kind in the city: location, and what the kit says about pets, fences and
    pools. Built once from the kit (about 20 s) and kept on disk under cache/home_search/."""
    f = CACHE / "home_search" / f"{city.lower().replace(' ', '_')}-{kind}-{_stamp()}.json"
    if f.exists():
        return json.loads(f.read_text())
    rows = []
    by_prop: dict = {}
    for sid, r in index.rows().items():
        if r.get("kind") != kind or r.get("city") != city or not r.get("lat"):
            continue
        b = policy.bundle(sid, None)
        row = {"sid": sid, "name": r.get("address") or r.get("name"), "lat": float(r["lat"]), "lon": float(r["lon"])}
        if kind == "apartment_unit":
            apt = policy.apartment(b)
            if not apt:
                continue
            pid = apt["property_id"]
            by_prop.setdefault(pid, 0)
            by_prop[pid] += 1
            dog, cat = policy.policy_for(apt, "dog"), policy.policy_for(apt, "cat")
            row.update(property_id=pid, no_pets=apt["no_pets"], has_policy=bool(apt["policies"]),
                       dog=dog is not None, dog_lb=(dog or {}).get("weight"), dog_rent=(dog or {}).get("rent"),
                       cat=cat is not None, cat_rent=(cat or {}).get("rent"), path=apt["path"])
        else:
            lst = policy.listing(b)
            row.update(listing=lst["has"], fenced=policy.fenced(lst), pool_listed=bool(lst["pool"]) and not any(
                "community" in x.lower() for x in lst["pool"]), pet_friendly=lst["pet_friendly"], no_pets=lst["no_pets"],
                dog_park=bool(lst["dog_park"]))
        rows.append(row)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(rows))
    return rows


def cached_facts(lat: float, lon: float) -> dict | None:
    """Vexcel site facts only when the answer is already on disk (no request)."""
    params = {"wkt": aerial.point(lat, lon), "srid": 4326, "include": "precomputed,calculated"}
    k = vexcel._key("GET", "property/extract", params, None)
    if not (vexcel.DIR / "property_extract" / k).exists():
        return None
    try:
        return aerial.site_facts(lat, lon)
    except Exception:  # noqa: BLE001  a cached error page or an odd shape: treat as not cached
        return None


def house_yard(row: dict, measured: dict) -> dict:
    """{yard_m2, behind, flat_pct, pool, how} from a pet_fit run when there is one, else from cached Vexcel facts."""
    m = measured.get(row["sid"])
    out = {"yard_m2": None, "behind": False, "flat_pct": None, "pool": None, "how": None}
    if m:
        out.update(yard_m2=m.get("back_m2"), behind=True, how="pet_fit",
                   flat_pct=100 * m["flat_share"] if m.get("flat_share") is not None else None)
    f = cached_facts(row["lat"], row["lon"])
    if f:
        by = {x["id"]: x["value"] for x in f.get("facts") or []}
        out["pool"] = by.get("pool")
        if out["yard_m2"] is None and by.get("parcel_area") and by.get("footprint_area"):
            out.update(yard_m2=max(by["parcel_area"] - by["footprint_area"], 0.0), how="vexcel")
    return out


@tool(id="home_search", title="Home search for pets and kids", icon="search",
      summary="Finds scanned homes across Houston or Los Angeles that suit your pets or kids: apartments that allow your "
              "dog's weight or cats, houses with a fenced, flat yard and no pool, near playgrounds, parks or dog parks.",
      model_description="City-wide search over the scanned homes. Apartments: by the community's CoStar pet policy (dog_lb: "
                        "allows a dog this heavy; cats; max_pet_rent). Houses: fenced (listing), no_pool (Vexcel, else the "
                        "listing), min_yard_m2 and min_flat_pct (measured by earlier pet_fit runs; yard area also from cached "
                        "Vexcel answers), and near: categories each within walk_min (straight-line estimate from one city-wide "
                        "OpenStreetMap request). Says how many homes could answer each criterion. Pins the matches.",
      personas=["dog_owner_home", "cat_owner_apartment", "senior_dog_owner", "parent_young_kids", "teen_soccer_family",
                "racket_player"],
      requires=[{"layer": "costar.property"}, {"layer": "osm.places", "need": "optional"}],
      blocks=["VerdictHeader", "MetricRow", "RankedTable", "CheckList", "StepLog"], overlays=["pins"],
      table=[{"metric": "yard_m2", "label": "Yard (m2)"}, {"metric": "dog_lb", "label": "Dog limit (lb)"},
             {"metric": "walk", "label": "Walk to the farthest place asked (min)", "better": "lower"}],
      examples=["Houston houses with a flat yard over 100 m2 and no pool", "LA apartments that allow dogs over 50 lb",
                "Houston homes within a 10-minute walk of a playground and a park"])
def run(ctx, inputs: Inputs) -> ToolResult:
    if inputs.near_set:
        inputs = inputs.model_copy(update={"near": list(dict.fromkeys(inputs.near + NEAR_SETS[inputs.near_set]))})
    apt = inputs.kind == "apartment_unit"
    asks_apt = inputs.dog_lb is not None or inputs.cats or inputs.max_pet_rent is not None
    asks_house = inputs.fenced or inputs.no_pool or inputs.min_yard_m2 is not None or inputs.min_flat_pct is not None
    if not (asks_apt or asks_house or inputs.near):
        raise NotApplicable("Say what the home needs: a dog's weight or cats (apartments), a fenced or flat yard or no pool "
                            "(houses), or places within a walk.")
    if apt and asks_house or not apt and asks_apt:
        raise NotApplicable("Pet policies, weight limits and pet rent are apartment criteria; fences, yards and pools are "
                            "house criteria. Set kind to match.")
    ctx.step(f"Reading the kit for scanned {'apartments' if apt else 'houses'} in {inputs.city}")
    rows = table(inputs.city, inputs.kind)
    measured = yard.measures() if not apt else {}
    places = None
    if inputs.near:
        ctx.step(f"Places across {inputs.city} from OpenStreetMap (one cached request)")
        try:
            places = nearby.city_places(inputs.city)
        except RuntimeError as e:
            return ToolResult(scope=ScansScope(sids=[]), verdict=Verdict(status="unknown", text=f"{e}. Try again shortly."))
    could = {k: 0 for k in ("policy", "fence", "pool", "yard", "flat", "near")}
    hits = []
    for r in rows:
        why, vals = [], {}
        ok = True
        if apt:
            if asks_apt:
                if r["no_pets"]:
                    continue
                if not r["has_policy"]:
                    continue
                could["policy"] += 1
            if inputs.dog_lb is not None:
                ok &= r["dog"] and (r["dog_lb"] is None or r["dog_lb"] >= inputs.dog_lb)
                vals["dog_lb"] = r["dog_lb"]
                why.append(f"dogs {'up to ' + str(r['dog_lb']) + ' lb' if r['dog_lb'] else 'with no weight limit given'}")
            if inputs.cats:
                ok &= r["cat"]
                why.append("cats allowed")
            if inputs.max_pet_rent is not None:
                rent = r["dog_rent"] if inputs.dog_lb is not None else r["cat_rent"]
                ok &= rent is None or rent <= inputs.max_pet_rent
                if rent is not None:
                    why.append(f"${rent}/month pet rent")
        else:
            if inputs.fenced:
                if r["fenced"] is None and not r["listing"]:
                    continue
                could["fence"] += 1
                ok &= r["fenced"] == "yes"
                why.append("fenced yard (listing)")
            y = house_yard(r, measured) if (inputs.no_pool or inputs.min_yard_m2 is not None or inputs.min_flat_pct is not None) else {}
            if inputs.no_pool:
                pool = y["pool"] if y["pool"] is not None else (r["pool_listed"] if r["listing"] else None)
                if pool is None:
                    continue
                could["pool"] += 1
                ok &= not pool
                why.append("no pool" + (" (Vexcel)" if y["pool"] is not None else " (listing)"))
            if inputs.min_yard_m2 is not None:
                if y["yard_m2"] is None:
                    continue
                could["yard"] += 1
                vals["yard_m2"] = round(y["yard_m2"], 1)
                ok &= y["yard_m2"] >= inputs.min_yard_m2
                why.append(f"{y['yard_m2']:.0f} m2 yard{' behind the house' if y['behind'] else ', all sides'}")
            if inputs.min_flat_pct is not None:
                if y["flat_pct"] is None:
                    continue
                could["flat"] += 1
                ok &= y["flat_pct"] >= inputs.min_flat_pct
                why.append(f"{y['flat_pct']:.0f}% flat")
        if places is not None and ok:
            could["near"] += 1
            worst = 0.0
            for c in inputs.near:
                d = nearby.straight_nearest(places[c], r["lon"], r["lat"])
                mins = d * nearby.DETOUR / nearby.WALK_M_MIN if d is not None else None
                ok &= mins is not None and mins <= inputs.walk_min
                worst = max(worst, mins or 1e9)
                if mins is not None:
                    why.append(f"{nearby.CATEGORIES[c][0].lower()} about {mins:.0f} min")
            vals["walk"] = round(worst, 1)
        if ok:
            hits.append((r, why, vals))
    key = (lambda h: h[2].get("walk", 0)) if inputs.near else (lambda h: -(h[2].get("yard_m2") or h[2].get("dog_lb") or 0))
    hits.sort(key=key)
    if apt:  # one row per community: units of one building share its policy
        seen, uniq = set(), []
        for h in hits:
            if h[0]["property_id"] not in seen:
                seen.add(h[0]["property_id"])
                uniq.append(h)
        n_match, hits = len(uniq), uniq
        unit = "communities"
        comms = len({r["property_id"] for r in rows if r["has_policy"] and not r["no_pets"]})
        no_limit = sum(1 for h in hits if inputs.dog_lb is not None and h[0]["dog_lb"] is None)
    else:  # one row per address: a house scanned twice is one house
        seen, uniq = set(), []
        for h in hits:
            if (h[0]["name"] or h[0]["sid"]) not in seen:
                seen.add(h[0]["name"] or h[0]["sid"])
                uniq.append(h)
        hits = uniq
        n_match, unit = len(hits), "houses"
    top = hits[:inputs.limit]
    checks, findings, cells, ps = [], [], [], []
    for i, (r, why, vals) in enumerate(top, 1):
        fid = f"home_search:{r['sid']}:match"
        checks.append(Check(id=f"rank.{i}", rule=f"#{i} {r['name']}: " + "; ".join(why), measured=vals.get("walk", vals.get("yard_m2", vals.get("dog_lb"))),
                            threshold=None, unit="min" if "walk" in vals else "m2" if "yard_m2" in vals else "lb" if "dog_lb" in vals else "",
                            status="pass", findings=[fid]))
        findings.append(Finding(id=fid, title=f"Match {i}", status="pass", detail="; ".join(why) + ".",
                                anchor=GeoAnchor(geo=(r["lon"], r["lat"])), source=NEAR if inputs.near else KIT))
        ps.append(Pin(id=f"m{i}", anchor=GeoAnchor(geo=(r["lon"], r["lat"])), label=r["name"] or r["sid"], status="pass"))
        for col in ("yard_m2", "dog_lb", "walk"):
            if col in vals:
                cells.append(Metric(id=f"m{i}/{col}", label=r["name"] or r["sid"], value=vals[col], unit="",
                                    source=NEAR if col == "walk" else YARD if col == "yard_m2" else KIT))
    asked = [k for k, v in (("policy", asks_apt), ("fence", inputs.fenced), ("pool", inputs.no_pool),
                            ("yard", inputs.min_yard_m2 is not None), ("flat", inputs.min_flat_pct is not None),
                            ("near", bool(inputs.near)))
             if v]
    ctx.step(f"{len(rows)} scanned {'apartment units' if apt else 'houses'}; could answer: "
             + ", ".join(f"{k} {could[k]}" for k in asked))
    pool_n = min(could[k] for k in asked) if asked else len(rows)
    if apt:
        text = (f"{n_match} of {comms} scanned communities in {inputs.city} with a pet policy in the record match"
                + (f" ({n_match - no_limit} state a limit that allows it, {no_limit} allow dogs and give no weight limit)" if no_limit else "")
                + f". {len(rows)} scanned units in all.")
    else:
        text = (f"{n_match} houses in {inputs.city} match." if n_match else f"No scanned houses in {inputs.city} match.")
        text += f" Searched {len(rows)} house scans; " + ", ".join(f"{could[k]} could answer the {k} criterion" for k in asked) + "."
    if inputs.min_flat_pct is not None or (inputs.min_yard_m2 is not None and not could["yard"]):
        text += " Yards are measured only where pet_fit has run; run it on a home to add it."
    if inputs.near:
        text += " Walks are straight-line estimates; open a home's Nearby for the street route."
    metrics = [Metric(id="matches", label=f"Matching {unit}", value=n_match, unit="", source=KIT),
               Metric(id="searched", label="Scans searched", value=len(rows), unit="", source=KIT),
               Metric(id="answerable", label="Could answer every criterion", value=pool_n, unit="", source=KIT)] + cells
    return ToolResult(scope=ScansScope(sids=[h[0]["sid"] for h in top]),
                      verdict=Verdict(status="pass" if n_match else "warn", text=text), metrics=metrics, checks=checks,
                      findings=findings, overlays=[PinsOverlay(pins=ps)] if ps else [],
                      actions=[Action(id=f"fit.{h[0]['sid']}", label=f"Check {h[0]['name']}", tool="pet_fit" if (asks_apt or asks_house) else "nearby",
                                      inputs={"scan": h[0]["sid"]}) for h in top[:3]])
