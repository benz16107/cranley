"""Pet fit: is this home right for these pets? Per pet profile (a dog by weight and age, an indoor or outdoor cat, a
small animal), a verdict with reasons, from the scan (stairs, open floor, floor finishes, a crate or pen spot, a
litter box away from food, a pet door to the yard, windows and balconies a cat could fall from), the air (yard off the
footprint, flat share from Vexcel ground heights, tree shade, a fence, the pool), the records (the apartment
community's pet policy, weight limit and fees; the listing's fence, floor and pet lines), and OpenStreetMap (busy
road, next building, dog parks, vets, emergency vets, trails).

Thresholds are the editable assumptions below, not a standard: no body publishes a minimum yard for a dog. Sources:
ADA 2010 403.3 (1:20) for "flat"; Whitney and Mehlhaff, "High-rise syndrome in cats", JAVMA 191(11):1399 (1987) for
window and balcony falls; AVMA "Warm weather pet safety" for shade; CPSC Pub. 362 p. 14 for pet doors and pools.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel
from shapely.geometry import Point
from shapely.ops import nearest_points

from ...sources import index
from .. import (Assumption, Check, Finding, Metric, NotApplicable, OpeningAnchor, Pin, PinsOverlay, RoomAnchor, ScanScope, Source,
                ToolResult, Verdict, field, tool)
from .._access import quality
from .._site import Site, Where, capture, footprint, geo, geo_route, locate, ortho_media, parcel, pin, to_m
from .._site import align as al
from ..nearby import assumptions as near_assumptions
from ..nearby import report as near_report
from ..types import BoxOverlay, RouteOverlay, RuleOverlay, SelectOpenings
from . import home, policy, yard

GEO = Source(layer="matterport", method="geometry", confidence="medium", note="Matterport wall graph, empty rooms")
GEO_LOW = Source(layer="matterport", method="geometry", confidence="low",
                 note="Floor heights from the panoramas; the step count is the rise over a 17.8 cm riser")
VEX = Source(layer="vexcel", method="geometry", confidence="medium", note="Vexcel parcel and footprint")
OSM = Source(layer="model", method="geometry", confidence="medium", note="OpenStreetMap contributors (ODbL), via Overpass")
STD = {"flat": "ADA 2010 403.3: steeper than 1:20 (5%) a walking surface is a ramp; used here as 'flat'",
       "fall": "Whitney and Mehlhaff, High-rise syndrome in cats, JAVMA 191(11):1399-1403 (1987): 132 cats fell from "
               "the second floor up; screens on windows and balconies",
       "shade": "AVMA, Warm weather pet safety: give outdoor pets shade and water",
       "pool": "CPSC Pub. 362 (2015) p. 14: no pet door that leads to the pool unless a fence isolates the pool"}
SIZES = (("small", 25), ("medium", 50), ("large", 90), ("giant", 1e9))
YARD_M2 = {"small": 20.0, "medium": 40.0, "large": 80.0, "giant": 100.0}
OPEN_RUN_M = 5.0
FLAT_OK = 0.6
SHADE_OK = 0.10
ROAD_DOG_M = 30.0
ROAD_CAT_M = 100.0
WORD = {"pass": "fits", "warn": "fits with changes", "fail": "does not fit", "unknown": "cannot tell"}
RANK = {"pass": 0, "unknown": 1, "warn": 2, "fail": 3}


class Pet(BaseModel):
    kind: Literal["dog", "cat", "small"] = field(description="dog, cat, or small (rabbit, guinea pig, bird, reptile)")
    weight_lb: float | None = field(None, gt=0, le=250, description="Weight in pounds (dogs)")
    age: Literal["young", "adult", "senior"] = "adult"
    outdoor: bool = field(False, description="A cat that goes outside")
    name: str | None = None


class Inputs(Where):
    pets: list[Pet] = field([Pet(kind="dog", weight_lb=40)], min_length=1, max_length=6, pref="pets.profile",
                            ask="Which pets? For each: dog (weight in lb and age: young, adult or senior), cat (indoor or "
                                "outdoor) or a small animal",
                            description="One profile per pet; each gets its own verdict")
    use_vision: bool = field(True, description="Read floor finishes in the panoramas and a fence from the aerial photo (cached)")
    nearby: bool = field(True, description="Look up dog parks, vets and trails in OpenStreetMap (cached)")
    riser_m: float = field(0.178, pref="access.riser_m", unit="m", gt=0.1, le=0.25)


def size(p: Pet) -> str:
    return next(s for s, top in SIZES if (p.weight_lb or 40) < top)


def describe(p: Pet) -> str:
    if p.kind == "dog":
        w = f", {p.weight_lb:g} lb" if p.weight_lb else ""
        return (p.name + ": " if p.name else "") + f"{'senior ' if p.age == 'senior' else 'young ' if p.age == 'young' else ''}{size(p)} dog{w}"
    if p.kind == "cat":
        return (p.name + ": " if p.name else "") + f"{'outdoor' if p.outdoor else 'indoor'} cat" + (" (senior)" if p.age == "senior" else " (kitten)" if p.age == "young" else "")
    return (p.name + ": " if p.name else "") + "small animal"


# ---- evidence ------------------------------------------------------------------------------------------

def gather(ctx, inputs: Inputs) -> dict:
    """Everything the rules read, measured once for all the pets."""
    E: dict = {"notes": []}
    s: Site | None
    try:
        s = locate(ctx, inputs)
    except NotApplicable as e:  # a phone scan: no location
        s = Site(inputs.lat, inputs.lon, inputs.scan, None, None, "point given") if inputs.lat is not None else None
        E["notes"].append(str(e))
    E["site"] = s
    sid = inputs.scan
    kind = (index.rows().get(sid) or {}).get("kind") if sid else None
    E["plan"] = plan = ctx.plan(sid) if sid else None
    b = policy.bundle(sid, s.property_id if s else None)
    E["apt"] = policy.apartment(b)
    E["listing"] = policy.listing(b)
    E["apartment"] = kind == "apartment_unit" or (kind is None and E["apt"] is not None)
    ctx.step(f"{'Apartment' if E['apartment'] else 'Home'}; records: "
             + ("community pet policy" if E["apt"] and E["apt"]["policies"] else "no pet policy in the record" if E["apt"] else
                "home listing" if E["listing"]["has"] else "none in the kit"))
    if plan is not None and quality(plan).get("walls"):
        E["stairs"] = home.stairs(plan, inputs.riser_m)
        E["open"] = home.open_floor(plan)
        E["crates"] = {sz: home.crate_spot(plan, sz) for sz in {size(p) for p in inputs.pets if p.kind == "dog"}}
        if any(p.kind == "small" for p in inputs.pets):
            E["crates"]["pen"] = home.crate_spot(plan, "pen")
        E["litter"] = home.litter_spot(plan) if any(p.kind == "cat" for p in inputs.pets) else None
        E["doors"] = home.pet_doors(plan) if not E["apartment"] else []
        E["fall"] = home.fall_windows(plan)
        ctx.step(f"Indoors: {E['stairs']['floors']} floors, {len(E['doors'])} exterior doors for a pet door, "
                 f"{len(E['fall']['windows'])} upper-floor windows")
    elif plan is not None:
        E["notes"].append("This scan has no wall graph, so stairs, spots and doors could not be measured.")
    if plan is not None and inputs.use_vision:
        try:
            E["finish"] = home.finishes(plan)
        except Exception as e:  # noqa: BLE001  the floors stay unread
            ctx.step(f"Floor finishes not read: {str(e)[:100]}")
    if s is not None and not E["apartment"]:
        outdoor(ctx, inputs, E, s, plan)
    if s is not None and inputs.nearby:
        ctx.step("Looking up dog parks, vets and trails in OpenStreetMap (one cached request per area)")
        start = E.get("house_ll") or (s.lon, s.lat)
        E["near"] = near_report("pet_fit", s.key, s.lat, s.lon, ["dog_park", "vet", "emergency_vet", "park", "trail"],
                                start=start, k=2, ok_min=15, far_min=30, prefix="near")
        try:
            from ... import nearby
            E["road"] = nearby.busy_road_m(s.lat, s.lon, start)
            fp = footprint(s) if not E["apartment"] else None
            E["neighbour"] = nearby.neighbour_m(s.lat, s.lon, fp) if fp is not None else None
        except RuntimeError as e:
            E["notes"].append(str(e))
    return E


def outdoor(ctx, inputs: Inputs, E: dict, s: Site, plan: dict | None) -> None:
    ys = yard.yard_shape(s)
    E["pool"] = yard.pool_info(s)
    if ys is None:
        E["notes"].append("Vexcel has no parcel or footprint here, so the yard cannot be measured.")
        return
    yd, house, lot = ys
    back = to_m(s.lat)[1]
    E["house_ll"] = back(*house.centroid.coords[0])
    E["lot_m2"] = lot
    E["yard_m2"] = yd.area if yd is not None else 0.0
    street = yard.street_side(s, house) if inputs.nearby else None
    E["street"] = street[2] if street else None
    by = yard.back_yard(yd, house, street) if yd is not None else None
    E["back_m2"] = by.area if by is not None else 0.0
    E["back_shape"] = by
    if by is not None and by.area > 10:
        ctx.step(f"Yard {E['yard_m2']:.0f} m2, {E['back_m2']:.0f} m2 behind the house; reading Vexcel ground and surface heights")
        E["terrain"] = yard.terrain(s, by)
    if inputs.use_vision:
        try:
            E["fence_photo"] = yard.fence_from_photo(s, True)
        except Exception as e:  # noqa: BLE001
            ctx.step(f"Fence not read from the photo: {str(e)[:100]}")
    if E["pool"]["pool"]:
        from ..path_to_water import find_pool
        try:
            p = find_pool(s, footprint(s), parcel(s))
            E["pool_shape"] = p["polygon"] if p else None
        except Exception as e:  # noqa: BLE001
            ctx.step(f"Pool outline not found: {str(e)[:100]}")
    if plan is not None and E.get("doors"):
        a = al.check(plan, footprint(s))
        E["align"] = a
        if a["available"]:
            for d in E["doors"]:
                d["ll"] = al.to_lonlat(plan, a, *d["outer"])
            fwd = to_m(s.lat)[0]
            E["doors"] = yard.rank_doors(E["doors"], street, fwd)


# ---- the rules ------------------------------------------------------------------------------------------

def rules(p: Pet, E: dict, k: str) -> list[tuple]:
    """(check id, rule, measured, threshold, unit, status, standard, finding id, reason when not a pass) for one pet."""
    R = []
    add = lambda *a: R.append(a)  # noqa: E731
    sz = size(p)
    apt, lst, st = E.get("apt"), E.get("listing") or {}, E.get("stairs")
    # policy
    if apt is not None:
        pol = policy.policy_for(apt, p.kind)
        f = f"pet_fit:{k}:policy"
        if apt["no_pets"]:
            add("policy", "The community allows this pet", None, None, "", "fail", None, f, "the community allows no pets")
        elif not apt["policies"]:
            add("policy", "The community allows this pet", None, None, "", "unknown", None, f,
                "the record carries no pet policy; ask the leasing office")
        elif pol is None:
            add("policy", "The community allows this pet", None, None, "", "fail", None, f,
                f"the record lists pet policies for {', '.join(sorted({x['type'] for x in apt['policies']}))} but not this pet")
        else:
            w = pol.get("weight")
            if p.kind == "dog" and w and p.weight_lb and p.weight_lb > w:
                add("policy", "Weight under the community's limit", p.weight_lb, w, "lb", "fail", None, f,
                    f"over the {w} lb limit")
            elif p.kind == "dog" and w and not p.weight_lb:
                add("policy", "Weight under the community's limit", None, w, "lb", "warn", None, f, f"a {w} lb limit applies")
            else:
                add("policy", "The community allows this pet", p.weight_lb if p.kind == "dog" else None, w,
                    "lb" if w else "", "pass", None, f, "")
    elif lst.get("no_pets"):
        add("policy", "The listing allows pets", None, None, "", "fail", None, f"pet_fit:{k}:listing", "the listing says no pets")
    # stairs
    if st:
        f = f"pet_fit:{k}:stairs"
        hard_on_joints = p.kind == "dog" and (p.age == "senior" or sz == "giant" or (p.age == "young" and sz in ("large", "giant")))
        if hard_on_joints or (p.kind == "cat" and p.age == "senior"):
            s = "pass" if not st["steps_max"] else "warn" if st["bedroom_on_entry"] else "fail"
            add("stairs", "Daily life without stairs", st["steps_max"], 0, "steps", s, None, f,
                "" if s == "pass" else f"about {st['steps_max']} steps" + ("" if st["bedroom_on_entry"] else " to every bedroom"))
    if apt is not None and apt.get("walkup") and not apt.get("elevators") and p.kind == "dog" and (p.age == "senior" or sz in ("large", "giant")):
        add("walkup", "An elevator in the building", 0, 1, "elevators", "warn", None, f"pet_fit:{k}:walkup",
            "a walk-up with no elevator in the record; the unit's floor is not in the scan")
    # floor
    o, fin = E.get("open"), E.get("finish")
    if o and p.kind == "dog" and p.age != "senior" and sz != "small":
        s = "pass" if o["run_m"] >= OPEN_RUN_M else "warn"
        add("open", "An open run of floor indoors", round(o["run_m"], 2), OPEN_RUN_M, "m", s, None, f"pet_fit:{k}:open",
            "" if s == "pass" else "no room gives a long open run")
    if fin and p.kind == "dog" and p.age == "senior":
        s = "warn" if fin["hard_share"] > 0.7 else "pass"
        add("floors", "Grip underfoot (share of hard floor)", round(100 * fin["hard_share"]), 70, "%", s, None,
            f"pet_fit:{k}:floors", "" if s == "pass" else "mostly hard floors; add runners where the dog walks")
    # spots
    if p.kind in ("dog", "small") and "crates" in E:
        c = E["crates"].get("pen" if p.kind == "small" else sz)
        add("crate", "A pen spot clear of doors" if p.kind == "small" else f"A {sz}-dog crate spot clear of doors", 1 if c else 0,
            1, "", "pass" if c else "warn", None, f"pet_fit:{k}:crate", "" if c else "no clear spot for a crate in the living rooms or bedrooms")
    if p.kind == "cat" and "crates" in E:
        lt = E.get("litter")
        add("litter", "A litter box spot away from food", round(lt["food_m"], 2) if lt and lt.get("food_m") is not None else (1 if lt else 0),
            home.LITTER_FROM_FOOD_M if lt and lt.get("food_m") is not None else 1, "m" if lt and lt.get("food_m") is not None else "",
            "pass" if lt else "warn", None, f"pet_fit:{k}:litter", "" if lt else "no litter box spot 3 m or more from the kitchen")
    # falls
    fall = E.get("fall")
    if p.kind == "cat" and (fall or E.get("apartment")):
        n = len((fall or {}).get("windows") or []) + len((fall or {}).get("balconies") or [])
        if E.get("apartment"):
            add("fall", "Windows and balcony safe from a fall", n or None, 0, "openings", "warn", STD["fall"], f"pet_fit:{k}:fall",
                "the scan does not say which floor the unit is on; from the second floor up, screen every window and the balcony")
        else:
            add("fall", "Upper-floor windows and balconies screened", n, 0, "openings", "warn" if n else "pass", STD["fall"],
                f"pet_fit:{k}:fall", f"{n} upper-floor windows or balconies to screen" if n else "")
    # yard
    if not E.get("apartment") and E.get("site") is not None:
        need = YARD_M2.get(sz if p.kind == "dog" else "small", 20.0)
        if "back_m2" in E and p.kind == "dog":
            s = "pass" if E["back_m2"] >= need else "warn"
            add("yard", "Yard behind the house", round(E["back_m2"], 1), need, "m2", s, None, f"pet_fit:{k}:yard",
                "" if s == "pass" else "a small yard behind the house")
        t = E.get("terrain")
        if t and p.kind == "dog":
            s = "pass" if t["flat_share"] >= FLAT_OK else ("fail" if p.age == "senior" and t["flat_share"] < 0.3 else "warn")
            add("flat", "Flat share of the back yard", round(100 * t["flat_share"]), round(100 * FLAT_OK), "%", s, STD["flat"],
                f"pet_fit:{k}:slope", "" if s == "pass" else "much of the yard slopes")
            s = "pass" if t["canopy_share"] >= SHADE_OK else "warn"
            add("shade", "Tree shade in the back yard", round(100 * t["canopy_share"]), round(100 * SHADE_OK), "%", s, STD["shade"],
                f"pet_fit:{k}:shade", "" if s == "pass" else "little tree shade; add shade and water")
        fence = fence_state(E)
        if p.kind == "dog" or (p.kind == "cat" and p.outdoor):
            s = {"yes": "pass", "partial": "warn", "no": "warn" if p.kind == "cat" else "fail"}.get(fence, "unknown")
            add("fence", "A fence around the yard", {"yes": 1, "partial": 0.5, "no": 0}.get(fence), 1, "", s, None,
                f"pet_fit:{k}:fence", {"pass": "", "warn": "the fence is partial or missing", "fail": "no fence seen around the yard",
                                       "unknown": "no fence in the listing and the photo cannot tell"}[s])
        pool = E.get("pool") or {}
        if pool.get("pool") and (p.kind == "dog" or (p.kind == "cat" and p.age == "young")):
            s = "pass" if pool["enclosed"] else ("fail" if p.age in ("young", "senior") or p.kind == "cat" else "warn")
            add("pool", "The pool is fenced off", 1 if pool["enclosed"] else 0, 1, "", s, STD["pool"], f"pet_fit:{k}:pool",
                "" if s == "pass" else "a pool with no fence of its own (a dog that falls in needs steps to climb out)")
    # roads and places
    road = E.get("road")
    if road and (p.kind == "dog" or (p.kind == "cat" and p.outdoor)):
        lim = ROAD_CAT_M if p.kind == "cat" else ROAD_DOG_M
        s = "pass" if road["m"] >= lim or (p.kind == "dog" and fence_state(E) == "yes") else "warn"
        add("road", "Distance to the nearest busy road", road["m"], lim, "m", s, None, f"pet_fit:{k}:road",
            "" if s == "pass" else f"a busy road ({road['name']}) is close")
    near = (E.get("near") or {}).get("hits") or {}
    if p.kind == "dog" and "dog_park" in near:
        h = (near.get("dog_park") or [None])[0]
        s = "pass" if h and h["minutes"] <= 15 else "warn"
        if s == "warn" and lst.get("dog_park"):
            add("dog_park", "A dog park nearby (the listing names one in the community)", None, None, "", "pass", None,
                f"pet_fit:{k}:listing", "")
        else:
            add("dog_park", "A dog park within a 15-minute walk", h["minutes"] if h else None, 15, "min", s, None,
                f"pet_fit:{k}:near:dog_park", "" if s == "pass" else "no dog park within a 15-minute walk")
    return R


def fence_state(E: dict) -> str | None:
    lf = policy.fenced(E.get("listing") or {})
    if lf:
        return lf
    ph = (E.get("fence_photo") or {}).get("back_yard_fenced")
    if ph == "yes":
        return "partial" if (E.get("fence_photo") or {}).get("gaps") == "yes" else "yes"
    return "no" if ph == "no" else None


# ---- the result -------------------------------------------------------------------------------------------

def evidence(E: dict, k: str, sid: str | None) -> tuple[list, list, list]:
    """Shared findings, metrics and overlays from the evidence (one each, whatever the pets)."""
    F, M, O = [], [], []
    s = E.get("site")
    here = geo(*E["house_ll"]) if E.get("house_ll") else geo(s.lon, s.lat) if s else None
    st = E.get("stairs")
    if st:
        M.append(Metric(id="steps", label="Most steps from the entrance floor (estimate)", value=st["steps_max"], unit="steps", source=GEO_LOW))
        F.append(Finding(id=f"pet_fit:{k}:stairs", title="Stairs", status="warn" if st["steps_max"] else "pass", anchor=None,
                         source=GEO_LOW, detail=f"{st['floors']} floors; about {st['steps_max']} steps from the entrance floor to the "
                                                "farthest one" + ("; a bedroom is on the entrance floor." if st["bedroom_on_entry"] else
                                                                   "; no bedroom on the entrance floor." if st["floors"] > 1 else ".")))
    o = E.get("open")
    if o:
        M.append(Metric(id="open_run", label="Longest open room", value=round(o["run_m"], 2), unit="m", source=GEO))
        F.append(Finding(id=f"pet_fit:{k}:open", title=f"Longest open run: the {o['label'].lower()}", status="pass",
                         anchor=RoomAnchor(sid=sid, room=o["room"]), source=GEO,
                         detail=f"{o['run_m']:.1f} m long, a {o['circle_m']:.1f} m clear circle, {o['area']:.0f} m2, empty room."))
    fin = E.get("finish")
    lf = (E.get("listing") or {}).get("floors")
    if fin or lf:
        detail = (f"Read in the panoramas: {100 * fin['carpet_share']:.0f}% carpet, {100 * fin['hard_share']:.0f}% hard floor "
                  f"over {fin['area_m2']:.0f} m2 of {len(fin['rooms'])} rooms. " if fin else "") + \
                 (f"The listing says: {', '.join(lf)}." if lf else "")
        F.append(Finding(id=f"pet_fit:{k}:floors", title="Floor finishes", status="pass", anchor=None, detail=detail.strip(),
                         source=Source(layer="model", method="vision", confidence=fin["confidence"],
                                       note="Vision model on the straight-down panorama face, one per room") if fin else
                         Source(layer="costar", method="lookup", confidence="medium", note="Listing features, Flooring")))
        if fin:
            M.append(Metric(id="hard_floor", label="Hard floor share", value=round(100 * fin["hard_share"]), unit="%",
                            source=Source(layer="model", method="vision", confidence=fin["confidence"])))
    for key, c in (E.get("crates") or {}).items():
        if c:
            F.append(Finding(id=f"pet_fit:{k}:crate:{key}", title="Pen spot" if key == "pen" else f"Crate spot ({key} dog)",
                             status="pass", anchor=RoomAnchor(sid=sid, room=c["room"]), source=GEO,
                             detail=f"In the {c['label'].lower()}, {c['size'][0]:.2f} by {c['size'][1]:.2f} m with room for "
                                    "the door to open, clear of doorways (empty room)."))
            O.append(BoxOverlay(center=c["center"], size=c["size"], yaw_deg=round(c["yaw_deg"], 1),
                                label="Pen" if key == "pen" else f"Crate ({key} dog)", status="pass"))
    lt = E.get("litter")
    if lt:
        F.append(Finding(id=f"pet_fit:{k}:litter", title="Litter box spot", status="pass", anchor=RoomAnchor(sid=sid, room=lt["room"]),
                         source=GEO, detail=f"In the {lt['label'].lower()}" + (f", {lt['food_m']:.1f} m from the kitchen or dining room."
                                                                             if lt.get("food_m") is not None else ", on a floor with no kitchen.")))
        O.append(BoxOverlay(center=lt["center"], size=lt["size"], yaw_deg=round(lt["yaw_deg"], 1), label="Litter box", status="pass"))
    fall = E.get("fall") or {}
    if fall.get("windows") or fall.get("balconies"):
        ws, bs = fall.get("windows") or [], fall.get("balconies") or []
        top = ws[0] if ws else None
        F.append(Finding(id=f"pet_fit:{k}:fall", title="Windows and balconies a cat could fall from", status="warn",
                         anchor=OpeningAnchor(sid=sid, opening=top["id"]) if top else RoomAnchor(sid=sid, room=bs[0]["id"]),
                         source=GEO_LOW, detail=f"{len(ws)} windows on upper floors" + (f", the highest about {top['drop_m']:.1f} m "
                                                                                     "above the lowest floor" if top else "")
                         + (f"; {len(bs)} balconies or terraces" if bs else "") + ". Fit screens that a cat cannot push out."))
        if ws:
            O.append(RuleOverlay(select=SelectOpenings(openings=[w["id"] for w in ws]), style="warn"))
            O.append(PinsOverlay(pins=[Pin(id=f"fall_{w['id']}", anchor=OpeningAnchor(sid=sid, opening=w["id"]),
                                           label="Fall risk window", status="warn") for w in ws[:8]]))
    doors = E.get("doors") or []
    if doors:
        d = doors[0]
        r = home.door_route(E["plan"], d)
        F.append(Finding(id=f"pet_fit:{k}:pet_door", title=f"Pet door: the {d['label'].lower()} door", status="pass",
                         anchor=OpeningAnchor(sid=sid, opening=d["opening"]) if d.get("opening") else geo(*d["ll"]) if d.get("ll") else None,
                         source=GEO, detail=f"An exterior door from the {d['label'].lower()}, {d.get('width') or 0:.2f} m wide"
                         + (f", {d['street_m']:.0f} m from {E.get('street') or 'the street'} (the back of the house)" if d.get("street_m") else "")
                         + (f"; {r['length_m']:.1f} m from the living room" if r else "") + "."))
        if r:
            z = r["points"][0][2]
            O.append(RouteOverlay(floor=r["floor"], label="Way out to the yard",
                                  points=[tuple(p) for p in r["points"]] + [(d["center"][0], d["center"][1], z), (*d["outer"], z)],
                                  chokes=[]))
        if d.get("ll") and E.get("back_shape") is not None:
            t = E.get("terrain") or {}
            dest = t.get("flat_center") or to_m(s.lat)[1](*E["back_shape"].representative_point().coords[0])
            O.append(geo_route([d["ll"], dest], "Pet door to the yard"))
        if d.get("ll") and E.get("pool_shape") is not None and not (E.get("pool") or {}).get("enclosed"):
            fwd, back = to_m(s.lat)
            from .._site import metres
            q = nearest_points(metres(E["pool_shape"], s.lat), Point(fwd(*d["ll"])))[0]
            O.append(geo_route([d["ll"], back(q.x, q.y)], "Pet door to the pool (no pool fence)", [(d["ll"], 0.0, "fail")]))
    if "back_m2" in E:
        M.insert(0, Metric(id="yard_back", label="Yard behind the house", value=round(E["back_m2"], 1), unit="m2", source=VEX))
        M.append(Metric(id="yard_all", label="Yard, all sides", value=round(E["yard_m2"], 1), unit="m2", source=VEX))
        F.append(Finding(id=f"pet_fit:{k}:yard", title="Yard", status="pass", anchor=here, source=VEX,
                         media=[ortho_media(s, 60)] if s else [],
                         detail=f"Parcel {E['lot_m2']:.0f} m2; yard off the footprint {E['yard_m2']:.0f} m2, of which "
                                f"{E['back_m2']:.0f} m2 is behind the house (farther from {E.get('street') or 'the street'} than "
                                f"the house centre). Aerial capture {capture(s)}."))
    t = E.get("terrain")
    if t:
        tsrc = Source(layer="vexcel", method="geometry", confidence="medium",
                      note=f"Vexcel ground model at {t['points']} points {t['step_m']} m apart")
        M.insert(1, Metric(id="yard_flat", label="Flat share of the back yard", value=round(100 * t["flat_share"]), unit="%", source=tsrc))
        M.append(Metric(id="yard_shade", label="Tree shade over the back yard", value=round(100 * t["canopy_share"]), unit="%",
                        source=Source(layer="vexcel", method="geometry", confidence="low",
                                      note=f"Surface more than {yard.CANOPY_M} m above ground, outside the house: trees, or a shed")))
        F.append(Finding(id=f"pet_fit:{k}:slope", title="Slope of the back yard", status="pass" if t["flat_share"] >= FLAT_OK else "warn",
                         anchor=geo(*t["flat_center"]) if t.get("flat_center") else here, source=tsrc,
                         detail=f"{100 * t['flat_share']:.0f}% under 5% slope, {100 * t['steep_share']:.0f}% over 15%; median "
                                f"{t['median_slope_pct'] or 0:.1f}%, {t['relief_m']:.1f} m from the lowest to the highest point."))
        F.append(Finding(id=f"pet_fit:{k}:shade", title="Tree shade", status="pass" if t["canopy_share"] >= SHADE_OK else "warn",
                         anchor=here, source=M[-1].source, detail=f"{100 * t['canopy_share']:.0f}% of the back yard is under a tree "
                                                                  "canopy (or a shed) on the capture day."))
    fs = fence_state(E)
    if not E.get("apartment") and s is not None:
        lf = policy.fenced(E.get("listing") or {})
        ph = E.get("fence_photo")
        F.append(Finding(id=f"pet_fit:{k}:fence", title={"yes": "Fenced yard", "partial": "Partly fenced yard", "no": "No fence seen"}.get(fs, "Fence unknown"),
                         status={"yes": "pass", "partial": "warn", "no": "warn"}.get(fs, "unknown"), anchor=here,
                         source=Source(layer="costar", method="lookup", confidence="medium", note="Listing features") if lf else
                         Source(layer="model", method="vision", confidence=(ph or {}).get("confidence", "low"), note="Vision model on a 50 m orthophoto"),
                         media=[ortho_media(s, 50)],
                         detail=(f"The listing says: {', '.join((E.get('listing') or {}).get('fence') or [])}. " if lf else "")
                         + (f"From the air: back yard fenced {ph['back_yard_fenced']}, gaps {ph['gaps']} ({ph['note']}). " if ph else "")
                         + "Check gates and the gap under the fence on site."))
    pool = E.get("pool") or {}
    if pool.get("pool"):
        F.append(Finding(id=f"pet_fit:{k}:pool", title="Pool on the parcel", status="pass" if pool["enclosed"] else "warn",
                         anchor=geo(*E["pool_shape"].centroid.coords[0]) if E.get("pool_shape") is not None else here,
                         source=Source(layer="vexcel", method="lookup", confidence="medium", note="Vexcel pool facts"),
                         detail=f"{pool.get('area') or 0:.0f} m2; " + ("Vexcel counts it enclosed (fenced)." if pool["enclosed"] else
                                                                     "Vexcel counts it not enclosed. Pets need a fence or a ramp out.")))
    road = E.get("road")
    if road:
        M.append(Metric(id="busy_road", label="Nearest busy road", value=road["m"], unit="m", source=OSM))
        F.append(Finding(id=f"pet_fit:{k}:road", title="Nearest busy road", status="pass", anchor=geo(*road["point"]), source=OSM,
                         detail=f"{road['name']} ({road['highway'].replace('_', ' ')} road), {road['m']:.0f} m in a straight line."))
    nb = E.get("neighbour")
    if nb:
        M.append(Metric(id="neighbour", label="Gap to the next building", value=nb["m"], unit="m", source=OSM))
        F.append(Finding(id=f"pet_fit:{k}:neighbour", title="Next building", status="pass", anchor=geo(*nb["point"]), source=OSM,
                         detail=f"{nb['m']:.1f} m from the house to the nearest other building in OpenStreetMap."))
    apt = E.get("apt")
    if apt is not None:
        csrc = Source(layer="costar", method="lookup", confidence="medium", note=f"CoStar property {apt['property_id']}, {apt['path']}")
        if apt["policies"]:
            parts = []
            for x in apt["policies"]:
                bits = [f"up to {x['numPets']}" if x.get("numPets") else None, f"{x['weight']} lb limit" if x.get("weight") else None,
                        f"${x['rent']}/month pet rent" if x.get("rent") else None,
                        f"${x['minFee']}" + (f" to ${x['maxFee']}" if x.get("maxFee") and x["maxFee"] != x.get("minFee") else "") + " fee"
                        if x.get("minFee") else None, f"${x['deposit']} deposit" if x.get("deposit") else None,
                        "interview" if x.get("isPetInterviewRequired") else None, "spayed or neutered" if x.get("isSpayedNeutered") else None]
                parts.append(f"{x['type']}s: " + ", ".join(b for b in bits if b))
            text = "; ".join(parts) + "."
            cm = next((x.get("comments") for x in apt["policies"] if x.get("comments")), None)
            if cm:
                text += f" The record's comment: \"{cm[:300]}\""
            for x in apt["policies"]:
                if x.get("weight"):
                    M.append(Metric(id=f"weight_limit.{x['type']}", label=f"Weight limit, {x['type']}s", value=x["weight"], unit="lb", source=csrc))
                if x.get("rent"):
                    M.append(Metric(id=f"pet_rent.{x['type']}", label=f"Pet rent, {x['type']}s", value=x["rent"], unit="$/month", source=csrc))
        else:
            text = "No pets allowed." if apt["no_pets"] else "The record carries no pet policy for this community."
        F.append(Finding(id=f"pet_fit:{k}:policy", title="Community pet policy", status="fail" if apt["no_pets"] else "pass" if apt["policies"] else "unknown",
                         anchor=here, source=csrc, detail=text + (" Negotiable per the record." if apt.get("negotiable") else "")
                         + " The record's pet amenities (dog park, pet wash) are amenity ids the kit does not name, so they are not shown."))
        if apt.get("walkup") is not None:
            F.append(Finding(id=f"pet_fit:{k}:walkup", title="Walk-up building" if apt["walkup"] else "Building access", status="warn" if apt["walkup"] and not apt["elevators"] else "pass",
                             anchor=here, source=Source(layer="costar", method="lookup", confidence="medium",
                                                         note=f"CoStar property {apt['property_id']}, propertyApartment.isWalkup and elevators"),
                             detail=f"{'A walk-up' if apt['walkup'] else 'Not a walk-up'}; {apt['elevators']} elevators in the record."))
    lst = E.get("listing") or {}
    if lst.get("pets") or lst.get("dog_park"):
        F.append(Finding(id=f"pet_fit:{k}:listing", title="What the listing says about pets", status="fail" if lst.get("no_pets") else "pass",
                         anchor=here, source=Source(layer="costar", method="lookup", confidence="medium", note=f"Listing {lst.get('id')} features"),
                         detail="; ".join((lst.get("pets") or []) + (lst.get("dog_park") or [])) + "."))
    elif s is not None and not E.get("apartment") and "road" in E:
        F.append(Finding(id=f"pet_fit:{k}:neighbour", title="Next building not measured", status="unknown", anchor=here,
                         source=Source(layer="model", method="lookup", confidence="low", note="OpenStreetMap building coverage"),
                         detail="OpenStreetMap maps too few buildings around this home to measure the gap to the neighbours."))
    road_pin = [pin("busy_road", *road["point"], f"Busy road: {road['name']}", "warn")] if road else []
    pool_pin = [pin("pool", *E["pool_shape"].centroid.coords[0], "Pool", "pass" if pool.get("enclosed") else "fail")] \
        if E.get("pool_shape") is not None else []
    if road_pin or pool_pin:
        O.append(PinsOverlay(pins=road_pin + pool_pin))
    return F, M, O


@tool(id="pet_fit", title="Pet fit", icon="paw-print",
      summary="Whether a home suits your dog, cat or small animal: stairs, floors, a crate and litter spot, a pet door, "
              "fall-risk windows, the yard's size, slope, shade and fence, the pool, busy roads, the pet policy and fees, "
              "and dog parks and vets nearby.",
      model_description="Per pet profile (dog by weight and age, indoor or outdoor cat, small animal), a verdict with reasons "
                        "for one home: from the scan (stairs, open floor, floor finishes read in the panoramas, a crate or pen "
                        "spot, a litter box 3 m from food, a pet door candidate with the route to the yard, upper-floor windows "
                        "and balconies), from Vexcel (yard behind the house, flat share from ground heights, tree shade, fence, "
                        "pool), from CoStar (the community's pet policy, weight limit, pet rent and fees; the listing's fence, "
                        "floor and pet lines) and OpenStreetMap (busy road, next building, dog parks, vets, emergency vets). "
                        "Works on a house, an apartment unit, a phone scan (indoor only) or a point (outdoor only).",
      personas=["dog_owner_home", "cat_owner_apartment", "senior_dog_owner"],
      requires=[{"layer": "matterport.rooms"}, {"layer": "vexcel.property", "need": "optional"},
                {"layer": "costar.property", "need": "optional"}, {"layer": "osm.places", "need": "optional"}],
      blocks=["VerdictHeader", "MetricRow", "CheckList", "EvidenceStrip", "FloorPlanMini", "AssumptionChips", "StepLog"],
      overlays=["box", "route", "pins", "rule"], annotations={"cost": "slow"},
      examples=["Is this house good for my 70 lb lab?", "Does this apartment allow a dog over 50 lb?",
                "Can my older dog live here without stairs?", "Is it safe for an indoor cat?"])
def run(ctx, inputs: Inputs) -> ToolResult:
    if not inputs.scan and inputs.lat is None and not inputs.property_id:
        raise NotApplicable("Pick a home, or give a CoStar property id or a point.")
    E = gather(ctx, inputs)
    s = E["site"]
    k = s.key if s else inputs.scan
    findings, metrics, overlays = evidence(E, k, inputs.scan)
    near = E.get("near") or {}
    findings += near.get("findings", [])
    overlays += near.get("overlays", [])
    for m in near.get("metrics", []):
        metrics.append(m)
    checks, lines = [], []
    worst = "pass"
    for i, p in enumerate(inputs.pets):
        R = rules(p, E, k)
        pid = f"pet{i + 1}"
        for cid, rule, measured, thr, unit, st, std, fid, _ in R:
            checks.append(Check(id=f"{pid}.{cid}", rule=f"{describe(p).capitalize()}: {rule}", measured=measured, threshold=thr,
                                unit=unit, status=st, standard=std, findings=[fid]))
        judged = [r for r in R if r[5] != "unknown"]
        st = max((r[5] for r in judged), key=RANK.get, default="unknown")
        reasons = [r[8] for r in R if r[5] in ("fail", "warn") and r[8]]
        unknown = [r[8] for r in R if r[5] == "unknown" and r[8]]
        lines.append(f"{describe(p).capitalize()}: {WORD[st]}" + (f" ({'; '.join(reasons[:3])})" if reasons else "") + ".")
        findings.append(Finding(id=f"pet_fit:{k}:{pid}", title=f"Verdict: {describe(p)}", status=st, anchor=None,
                                source=Source(layer="model", method="geometry", confidence="medium",
                                              note="Rules over the measured checks; see each check's source"),
                                detail=(f"{WORD[st].capitalize()}. " + ("Reasons: " + "; ".join(reasons) + ". " if reasons else
                                                                         "Every measured check passes. ")
                                        + ("Not known: " + "; ".join(unknown) + "." if unknown else "")).strip()))
        worst = max(worst, st, key=RANK.get)
    text = " ".join(lines)
    if E["notes"]:
        text += " " + " ".join(n.rstrip(".") + "." for n in E["notes"][:2])
    assumptions = [
        Assumption(id="pets.yard_m2", label="Yard behind the house wanted, by dog size",
                   value=", ".join(f"{k_} {v:g}" for k_, v in YARD_M2.items()), unit="m2"),
        Assumption(id="pets.flat", label="Flat means under this slope", value=yard.FLAT_PCT, unit="%"),
        Assumption(id="pets.open_run", label="An open run of floor for a young or adult dog", value=OPEN_RUN_M, unit="m"),
        Assumption(id="access.riser_m", label="Riser height for the step estimate", value=inputs.riser_m, unit="m", editable=True),
        Assumption(id="pets.sizes", label="Dog sizes by weight", value="small under 25, medium under 50, large under 90, giant 90 and over", unit="lb"),
        Assumption(id="pets.empty_rooms", label="Spots are found in the empty scanned rooms; furniture is not in the plan", value=True),
    ] + (near_assumptions("walk", 15) if near else [])
    return ToolResult(scope=s.scope if s else ScanScope(sid=inputs.scan), verdict=Verdict(status=worst, text=text), metrics=metrics,
                      checks=checks, findings=findings, overlays=overlays, assumptions=assumptions)
