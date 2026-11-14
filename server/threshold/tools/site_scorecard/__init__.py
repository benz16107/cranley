"""Site scorecard: rank 2 to 10 candidate buildings against a business's requirements and weights.

Each criterion becomes a 0 to 100 score from a measured or recorded value, with its evidence: the CoStar record and its
active lease listings (size available, asking rent, clear height, docks, parking ratio, class), the scan (measured
area, ceiling height, entrance width), OpenStreetMap (highway on-ramps, transit, substations), the FEMA flood zone, and
commute estimates when employee homes are given. A requirement marked "must" that a candidate fails is a deal-breaker
and ranks it last. A criterion with no evidence is left out of that candidate's score and counted against its coverage.

With `deep`, the scorecard also runs the profile's site tool on each candidate (industrial_fit, retail_site) and folds
their measured values in (truck court depth, parking counted on the aerial).
"""
from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Literal

from pydantic import BaseModel

from .. import (
    Action,
    Check,
    Finding,
    Metric,
    Place,
    Source,
    ToolError,
    ToolResult,
    Verdict,
    field,
    run_tool,
    tool,
)
from .._site import geo, pin, pins
from ..types import ScansScope
from ..market_comps import kit
from . import near

FT2_PER_M2 = 10.7639
FT_PER_M = 3.28084
Profile = Literal["office", "industrial", "retail", "flex"]

# criterion: (label, unit, better)
CRITERIA = {
    "size": ("Space available", "ft²", "higher"),
    "rent": ("Asking rent", "$/ft²/yr", "lower"),
    "clear_height": ("Clear height", "ft", "higher"),
    "docks": ("Dock doors", "", "higher"),
    "truck_court": ("Truck court depth", "m", "higher"),
    "parking": ("Parking ratio", "per 1,000 ft²", "higher"),
    "step_free": ("Step-free entrance width", "m", "higher"),
    "highway": ("Highway on-ramp", "km", "lower"),
    "transit": ("Transit stop", "m", "lower"),
    "flood": ("Flood zone", "", "higher"),
    "substation": ("Power substation", "km", "lower"),
    "hub": ("Airport or port", "km", "lower"),
    "co_tenancy": ("Shops and food within 400 m", "", "higher"),
    "commute": ("Median commute", "min", "lower"),
    "building_class": ("Building class", "", "higher"),
}
WEIGHTS: dict[str, dict[str, float]] = {
    "industrial": {"size": 3, "rent": 3, "clear_height": 3, "docks": 3, "truck_court": 2, "highway": 2, "flood": 2,
                   "parking": 1, "substation": 1, "hub": 1, "building_class": 1},
    "flex": {"size": 3, "rent": 3, "clear_height": 2, "docks": 2, "parking": 2, "highway": 2, "flood": 2, "transit": 1,
             "building_class": 1},
    "office": {"size": 3, "rent": 3, "commute": 3, "transit": 2, "parking": 2, "step_free": 2, "building_class": 2,
               "flood": 1, "highway": 1},
    "retail": {"size": 3, "rent": 3, "parking": 3, "co_tenancy": 3, "step_free": 2, "transit": 1, "flood": 1, "highway": 1},
}
MUST = {"industrial": ["size", "rent", "clear_height", "docks"], "flex": ["size", "rent"], "office": ["size", "rent"],
        "retail": ["size", "rent"]}
COLUMNS = {"industrial": ["rent", "size", "clear_height", "docks", "highway"],
           "flex": ["rent", "size", "clear_height", "parking", "highway"],
           "office": ["rent", "size", "commute", "transit", "parking"],
           "retail": ["rent", "size", "parking", "co_tenancy", "transit"]}
DEFAULTS = {"industrial": {"clear_height_min_ft": 24, "docks_min": 2, "parking_ratio_min": 0.5, "highway_max_km": 3},
            "flex": {"clear_height_min_ft": 16, "docks_min": 0, "parking_ratio_min": 2, "highway_max_km": 5},
            "office": {"parking_ratio_min": 3, "highway_max_km": 8, "transit_max_m": 800},
            "retail": {"parking_ratio_min": 4, "highway_max_km": 8, "transit_max_m": 800}}
UNVERIFIED_PENALTY = 10  # points off the score for each must-have with no evidence
SF_PER_PERSON = {"office": (150, 250), "flex": (250, 500), "industrial": (500, 2000), "retail": (100, 300)}
SCAN = Source(layer="matterport", method="geometry", confidence="high", note="Measured on the scan's floor plan")
FEMA = Source(layer="model", method="lookup", confidence="medium", note="FEMA flood hazard areas (Esri's hosted copy of the NFHL)")
OSM = Source(layer="model", method="lookup", confidence="medium", note=near.NOTE + ", straight-line distance")
SCORE = Source(layer="model", method="simulation", confidence="medium",
               note="Weighted mean of the criterion scores that have evidence; weights and thresholds are assumptions you can edit")


class Inputs(BaseModel):
    profile: Profile = field(ask="What kind of space is it: office, industrial (warehouse or distribution), retail or flex?",
                             pref="site.profile")
    candidates: list[Place] = field([], max_length=10, description="Buildings to compare (scans, CoStar properties, "
                                                                   "addresses or points); empty to find candidates")
    near: Place | None = field(None, description="With no candidates: search CoStar properties for lease around here")
    search_km: float = field(25, ge=1, le=80, unit="km", description="Search radius around `near`")
    city: Literal["Houston", "Los Angeles"] | None = field(None, description="With no candidates and no `near`: search this city")
    max_candidates: int = field(5, ge=2, le=10, description="How many candidates a search keeps")
    size_min_sf: float | None = field(None, pref="site.size_min_sf", unit="ft²", gt=0, description="Smallest space that works")
    size_max_sf: float | None = field(None, pref="site.size_max_sf", unit="ft²", gt=0, description="Largest space wanted")
    budget_sf_yr: float | None = field(None, pref="site.budget_sf_yr", unit="$/ft²/yr", gt=0,
                                       description="Highest asking rent per ft² per year")
    headcount: int | None = field(None, pref="office.headcount", ge=1, le=20000,
                                  description="People to house; sets the size range when none is given")
    docks_min: int | None = field(None, pref="site.docks_min", ge=0, le=500, description="Dock doors needed")
    clear_height_min_ft: float | None = field(None, pref="site.clear_height_min_ft", unit="ft", ge=8, le=60,
                                              description="Clear height needed under the structure")
    parking_ratio_min: float | None = field(None, pref="site.parking_ratio_min", unit="per 1,000 ft²", ge=0, le=20,
                                            description="Parking spaces per 1,000 ft² needed")
    step_free: bool = field(False, pref="site.step_free", description="Needs a step-free entrance (ADA)")
    highway_max_km: float | None = field(None, pref="site.highway_max_km", unit="km", gt=0, le=50,
                                         description="Furthest acceptable distance to a highway on-ramp")
    transit_max_m: float | None = field(None, pref="site.transit_max_m", unit="m", gt=0, le=5000,
                                        description="Furthest acceptable walk to a bus stop or station")
    flood: Literal["avoid", "prefer_outside", "any"] = field("prefer_outside", pref="site.flood",
                                                             description="Flood risk tolerance: avoid the 1% zone outright, "
                                                                         "prefer outside it, or ignore it")
    employees: list[str] = field([], pref="commute.employees",
                                 description="Home zip codes (77002:12 for 12 people) or lon,lat points, for commutes")
    weights: dict[str, float] = field({}, description="Weight per criterion, 0 to 5; overrides the profile's defaults")
    must: list[str] | None = field(None, description="Criteria a candidate must meet; default per profile")
    deep: bool = field(False, description="Also run the profile's site tool on each candidate (slow, cached)")
    use_osm: bool = field(True, description="Look up highways, transit and substations in OpenStreetMap (cached)")


@dataclass
class Cell:
    crit: str
    value: float | str | None
    score: float | None             # 0..100; None = no evidence
    threshold: float | None
    status: str                     # pass | warn | fail | unknown
    evidence: str
    source: Source
    display: float | None = None    # numeric value for the table


@dataclass
class Cand:
    key: str
    name: str
    lat: float | None
    lon: float | None
    sids: list[str]
    row: dict | None
    plan: dict | None = None
    cells: dict[str, Cell] = dc_field(default_factory=dict)
    total: float | None = None
    coverage: float = 0.0
    breakers: list[str] = dc_field(default_factory=list)
    unverified: list[str] = dc_field(default_factory=list)


def lin(x: float, ok: float, zero: float) -> float:
    """100 at `ok` or better, 0 at `zero` or worse, linear between (works both ways round)."""
    if ok == zero:
        return 100.0 if x == ok else 0.0
    t = (x - zero) / (ok - zero)
    return round(max(0.0, min(1.0, t)) * 100, 1)


def status_of(score: float | None) -> str:
    return "unknown" if score is None else "pass" if score >= 90 else "warn" if score >= 50 else "fail"


# ---- evidence for one candidate ----------------------------------------------------------------------

def scan_facts(plan: dict) -> dict:
    """Measured area (ft²), tallest room (ft) and widest entrance (m) from a ScanPlan."""
    q = plan.get("quality") or {}
    rooms = plan.get("rooms") or []
    area = sum(r.get("area") or 0 for r in rooms) * FT2_PER_M2
    hs = [r["height"] for r in rooms if r.get("height")]
    ents = [o["width"] for o in plan.get("openings") or [] if o.get("type") in ("doorway", "opening")
            and len(o.get("rooms") or []) == 1 and o.get("width")]
    return {"area_sf": round(area) or None, "height_ft": round(max(hs) * FT_PER_M, 1) if hs else None,
            "entrance_m": round(max(ents), 2) if ents and q.get("openings", True) else None}


def requirements(i: Inputs) -> dict:
    d = dict(DEFAULTS[i.profile])
    for k in ("clear_height_min_ft", "docks_min", "parking_ratio_min", "highway_max_km", "transit_max_m"):
        if getattr(i, k) is not None:
            d[k] = getattr(i, k)
    lo, hi = i.size_min_sf, i.size_max_sf
    if i.headcount and lo is None and hi is None:
        a, b = SF_PER_PERSON[i.profile]
        lo, hi = i.headcount * a, i.headcount * b
    d.update(size_min_sf=lo, size_max_sf=hi, budget_sf_yr=i.budget_sf_yr)
    return d


def score_size(c: Cand, req: dict) -> Cell | None:
    lo, hi = req.get("size_min_sf"), req.get("size_max_sf")
    row = c.row or {}
    avail = (row.get("available") or {}).get("max_contiguous_sf")
    sf, what, src = None, "", None
    if avail:
        sf, what = avail, "largest contiguous block marketed for lease"
        src = Source(layer="costar", method="lookup", confidence="medium", note=f"CoStar listings on property {row['id']}")
    elif row.get("rba"):
        sf, what = row["rba"], "whole building (no space marketed for lease in the kit)"
        src = Source(layer="costar", method="lookup", confidence="medium", note=f"CoStar property {row['id']}, rentable area")
    elif c.plan and scan_facts(c.plan)["area_sf"]:
        sf, what, src = scan_facts(c.plan)["area_sf"], "floor area measured on the scan", SCAN
    if sf is None:
        return None
    if lo is None and hi is None:
        return Cell("size", sf, None, None, "unknown", f"{sf:,.0f} ft², {what}; no size range given", src, sf)
    s = 100.0
    if lo and sf < lo:
        s = lin(sf, lo, lo * 0.5)
    elif hi and sf > hi:
        s = lin(sf, hi, hi * 3)
        if avail and row.get("available", {}).get("sf"):
            s = max(s, 70.0)  # a big block can usually be divided; the landlord sets the minimum
    rng = f"{lo:,.0f}" if lo else "any"
    rng += f" to {hi:,.0f}" if hi else " or more"
    return Cell("size", sf, s, lo, status_of(s), f"{sf:,.0f} ft², {what}; need {rng} ft²", src, sf)


def score_rent(c: Cand, req: dict) -> Cell | None:
    r = kit.asking_rent(c.row) if c.row else None
    if not r:
        return None
    b = req.get("budget_sf_yr")
    src = Source(layer="costar", method="lookup", confidence="medium",
                 note=f"CoStar listings on property {c.row['id']}: area-weighted asking rent, {r['service']}")
    ev = f"${r['rate']:,.2f}/ft²/yr asking ({r['service']}, {r['spaces']} space{'s' if r['spaces'] != 1 else ''}" + \
         (", sublease" if r["sublease"] else "") + ")"
    if not b:
        return Cell("rent", r["rate"], None, None, "unknown", ev + "; no budget given", src, r["rate"])
    s = lin(r["rate"], b, b * 1.5)
    return Cell("rent", r["rate"], s, b, status_of(s), ev + f"; budget ${b:,.2f}", src, r["rate"])


def score_clear(c: Cand, req: dict) -> Cell | None:
    need = req.get("clear_height_min_ft")
    ft, src, what = (c.row or {}).get("clear_ft"), None, "recorded clear height"
    if ft:
        src = Source(layer="costar", method="lookup", confidence="medium", note=f"CoStar property {c.row['id']}, ceiling height")
    elif c.plan and scan_facts(c.plan)["height_ft"]:
        ft, src, what = scan_facts(c.plan)["height_ft"], SCAN, "tallest room on the scan (to the ceiling, not under the structure)"
    if not ft:
        return None
    if not need:
        return Cell("clear_height", ft, None, None, "unknown", f"{ft:g} ft, {what}", src, ft)
    s = lin(ft, need, need - 8)
    return Cell("clear_height", ft, s, need, status_of(s), f"{ft:g} ft, {what}; need {need:g} ft", src, ft)


def score_docks(c: Cand, req: dict) -> Cell | None:
    n = (c.row or {}).get("docks")
    if n is None:
        return None
    need = req.get("docks_min") or 0
    src = Source(layer="costar", method="lookup", confidence="medium", note=f"CoStar property {c.row['id']}, loading docks")
    di = (c.row or {}).get("drive_ins")
    ev = f"{n} dock doors" + (f" and {di} drive-in doors" if di else "") + " in the record" + (f"; need {need}" if need else "")
    s = 100.0 if n >= need else round(100 * n / need, 1)
    return Cell("docks", n, s, need, status_of(s), ev, src, n)


def score_parking(c: Cand, req: dict) -> Cell | None:
    row = c.row or {}
    ratio, how = row.get("parking_ratio"), "recorded parking ratio"
    if not ratio and row.get("parking_spaces") and row.get("rba"):
        ratio, how = round(1000 * row["parking_spaces"] / row["rba"], 2), f"{row['parking_spaces']} recorded spaces over the rentable area"
    if ratio is None:
        return None
    need = req.get("parking_ratio_min") or 0
    src = Source(layer="costar", method="lookup", confidence="medium", note=f"CoStar property {row['id']}, parking")
    s = 100.0 if not need or ratio >= need else lin(ratio, need, 0)
    return Cell("parking", ratio, s, need, status_of(s), f"{ratio:g} per 1,000 ft² ({how}); need {need:g}", src, ratio)


def score_step_free(c: Cand, req: dict) -> Cell | None:
    if not c.plan:
        return None
    w = scan_facts(c.plan)["entrance_m"]
    if w is None:
        return None
    s = 100.0 if w >= 0.813 else lin(w, 0.813, 0.6)
    return Cell("step_free", w, s, 0.813, status_of(s),
                f"Widest entrance doorway {w:.2f} m on the scan (32 in, 0.813 m, is the ADA clear width); steps and slopes "
                f"at the door are not checked here: run step_free_route", SCAN, w)


def score_osm(c: Cand, req: dict, t: dict) -> list[Cell]:
    out = []
    nb = t["nearest"]
    h = nb.get("highway")
    if h:
        mx = req.get("highway_max_km") or 5
        s = lin(h["km"], mx, mx * 3)
        out.append(Cell("highway", h["km"], s, mx, status_of(s), f"Nearest motorway junction{' ' + h['name'] if h['name'] else ''} "
                        f"{h['km']:.1f} km in a straight line; want {mx:g} km or less", OSM, h["km"]))
    stops = [x for x in (nb.get("bus"), nb.get("rail_transit")) if x]
    if stops:
        best = min(stops, key=lambda x: x["km"])
        m = round(best["km"] * 1000)
        mx = req.get("transit_max_m") or 800
        s = lin(m, mx, mx * 3)
        out.append(Cell("transit", m, s, mx, status_of(s), f"Nearest {'station' if best is nb.get('rail_transit') else 'bus stop'} "
                        f"{best['name'] or ''} {m} m away; {t['bus_stops_800m']} bus stops within 800 m", OSM, m))
    else:
        out.append(Cell("transit", None, 0.0, req.get("transit_max_m") or 800, "fail",
                        "No bus stop within 1 km or station within 2 km in OpenStreetMap", OSM, None))
    sub = nb.get("substation")
    out.append(Cell("substation", sub["km"] if sub else None, lin(sub["km"], 2, 8) if sub else 30.0, 2,
                    status_of(lin(sub["km"], 2, 8) if sub else 30.0),
                    f"Nearest mapped substation {sub['km']:.1f} km" if sub else "No substation mapped within 3 km "
                    "(OpenStreetMap misses some)", OSM, sub["km"] if sub else None))
    hubs = [x for x in (nb.get("airport"), nb.get("port")) if x]
    if hubs:
        hb = min(hubs, key=lambda x: x["km"])
        s = lin(hb["km"], 25, 80)
        out.append(Cell("hub", hb["km"], s, 25, status_of(s), f"{hb['name']} {hb['km']:.0f} km in a straight line",
                        Source(layer="model", method="lookup", confidence="medium", note=near.HUB_NOTE), hb["km"]))
    return out


def score_flood(z: dict, mode: str) -> Cell:
    zone, sub = z.get("zone"), (z.get("subtype") or "")
    if z.get("in_sfha"):
        s, txt = 10.0, f"In FEMA's 1% annual chance flood zone ({zone})"
    elif "0.2" in sub:
        s, txt = 60.0, f"In FEMA's 0.2% annual chance zone ({zone}, shaded)"
    else:
        s, txt = 100.0, f"Outside FEMA's mapped flood hazard areas ({zone or 'no mapped zone'})"
    if mode == "any":
        return Cell("flood", zone or "none", None, None, "unknown", txt + "; flood risk is not scored", FEMA, s)
    return Cell("flood", zone or "none", s, None, status_of(s), txt, FEMA, s)


def score_class(c: Cand) -> Cell | None:
    k = (c.row or {}).get("class")
    if not k:
        return None
    s = {"A": 100.0, "B": 70.0, "C": 40.0, "F": 20.0}.get(k, 50.0)
    return Cell("building_class", k, s, None, status_of(s), f"Class {k} in the CoStar record (a market-relative grade)",
                Source(layer="costar", method="lookup", confidence="medium", note=f"CoStar property {c.row['id']}, buildingClass"), s)


def score_co_tenancy(r: dict) -> Cell:
    n = len(r["shops"]) + len(r["food"]) + len(r["services"])
    s = min(100.0, n * 4.0)
    anchors = ", ".join(f"{a['name']} {a['km']:.1f} km" for a in r["anchors"][:3]) or "no named anchor store within 1.5 km"
    return Cell("co_tenancy", n, s, 25, status_of(s), f"{len(r['shops'])} shops, {len(r['food'])} places to eat and "
                f"{len(r['services'])} services within 400 m; anchors: {anchors}", OSM, n)


def score_commute(cm: dict) -> Cell:
    m = cm["median"]
    s = lin(m, 30, 75)
    return Cell("commute", m, s, 30, status_of(s), f"Median estimated drive {m:.0f} min for {cm['people']} people, longest "
                f"{cm['max']:.0f} min (straight line x 1.3, no traffic)",
                Source(layer="model", method="simulation", confidence="low", note="commute_fit estimate"), m)


def from_tool(c: Cand, res: ToolResult, profile: str) -> list[Cell]:
    """Values a deep site tool measured, as cells."""
    m = {x.id: x for x in res.metrics}
    out = []
    if "court_depth" in m and m["court_depth"].value is not None:
        v = m["court_depth"].value
        s = lin(v, 39.6, 25)
        out.append(Cell("truck_court", v, s, 39.6, status_of(s), f"Truck court {v:.0f} m deep measured on the aerial "
                        f"(130 ft, 39.6 m, backs a 53 ft trailer)", m["court_depth"].source, v))
    if profile == "retail" and "parking_ratio" in m and m["parking_ratio"].value is not None and "parking" not in c.cells:
        v = m["parking_ratio"].value
        out.append(Cell("parking", v, None, None, "unknown", f"{v:g} per 1,000 ft² counted on the aerial", m["parking_ratio"].source, v))
    return out


# ---- candidates ----------------------------------------------------------------------------------------

def candidate(ctx, p: Place) -> Cand:
    s = ctx.site(p)
    row = kit.row(s.property_id)
    if row and row.get("type_id") in (11, 15, 16):
        row = None
    plan = None
    if p.scan:
        try:
            plan = ctx.plan(p.scan)
        except ToolError:
            plan = None
    return Cand(s.key, (row or {}).get("address") or s.address or s.key, s.lat, s.lon, s.sids, row, plan)


def search(i: Inputs, req: dict, origin: tuple[float, float] | None, pool: list[dict]) -> list[dict]:
    """Kit properties of the profile's types on the market (space marketed for lease) near the origin or in the city,
    whose available block fits the size range, ranked by the record-only criteria."""
    types = kit.PROFILE_TYPES[i.profile]
    lo, hi = req.get("size_min_sf"), req.get("size_max_sf")
    out = []
    for x in pool:
        if x.get("type_id") not in types or x.get("lat") is None:
            continue
        blk = (x.get("available") or {}).get("max_contiguous_sf")
        if not blk:
            continue
        if origin and near.km(origin[0], origin[1], x["lat"], x["lon"]) > i.search_km:
            continue
        if not origin and i.city and (x.get("city") or "").lower() != i.city.lower():
            continue
        if (lo and blk < lo * 0.8) or (hi and blk > hi * 4):
            continue
        c = Cand(f"p{x['id']}", x.get("address") or str(x["id"]), x["lat"], x["lon"], [], x)
        cells = [f(c, req) for f in (score_size, score_rent, score_clear, score_docks, score_parking)]
        known = [cl.score for cl in cells if cl and cl.score is not None]
        # a criterion with no record counts as 50, so a listing with fewer facts does not win on the ones it has
        out.append((sum(known) + 50 * (len(cells) - len(known)), len(known), x))
    out.sort(key=lambda t: (-t[0], -t[1]))
    return [x for _, _, x in out[:i.max_candidates]]


def evaluate(ctx, c: Cand, i: Inputs, req: dict, weights: dict, must: list[str], homes: list[dict] | None) -> None:
    for f in (score_size, score_rent, score_clear, score_docks, score_parking, score_step_free):
        cell = f(c, req)
        if cell:
            c.cells[cell.crit] = cell
    cl = score_class(c)
    if cl:
        c.cells[cl.crit] = cl
    if c.lat is not None and i.use_osm and any(k in weights for k in ("highway", "transit", "substation", "hub")):
        try:
            for cell in score_osm(c, req, near.transport(c.lat, c.lon)):
                c.cells[cell.crit] = cell
        except Exception as e:  # noqa: BLE001  OSM is slow or down: those cells stay unknown
            ctx.step(f"OpenStreetMap lookup failed for {c.name}: {str(e)[:100]}")
    if c.lat is not None and i.use_osm and "co_tenancy" in weights:
        try:
            c.cells["co_tenancy"] = score_co_tenancy(near.retail(c.lat, c.lon))
        except Exception as e:  # noqa: BLE001
            ctx.step(f"Shop lookup failed for {c.name}: {str(e)[:100]}")
    if c.lat is not None:
        try:
            from ..flood_rehearsal.public import fema_zone
            c.cells["flood"] = score_flood(fema_zone(c.lat, c.lon), i.flood)
        except Exception as e:  # noqa: BLE001
            ctx.step(f"Flood zone lookup failed for {c.name}: {str(e)[:100]}")
    if homes and c.lat is not None:
        from ..commute_fit import commute
        c.cells["commute"] = score_commute(commute(homes, c.lat, c.lon, 1.3))
    if i.deep:
        tid = {"industrial": "industrial_fit", "flex": "industrial_fit", "retail": "retail_site"}.get(i.profile)
        if tid:
            place = {"scan": c.sids[0]} if c.sids else {"property_id": c.row["id"]} if c.row else {"geo": [c.lon, c.lat]}
            try:
                res = run_tool(tid, {"place": place}, ctx)
                for cell in from_tool(c, res, i.profile):
                    c.cells[cell.crit] = cell
            except Exception as e:  # noqa: BLE001
                ctx.step(f"{tid} failed on {c.name}: {str(e)[:100]}")
    num = den = total_w = 0.0
    for k, w in weights.items():
        if w <= 0:
            continue
        total_w += w
        cell = c.cells.get(k)
        if cell and cell.score is not None:
            num += w * cell.score
            den += w
    c.coverage = round(100 * den / total_w) if total_w else 0
    for k in must:
        cell = c.cells.get(k)
        if cell is None or cell.score is None:
            c.unverified.append(k)
        elif cell.status == "fail":
            c.breakers.append(k)
    c.total = round(max(0.0, num / den - UNVERIFIED_PENALTY * len(c.unverified)), 1) if den else None


@tool(id="site_scorecard", title="Site scorecard", icon="trophy",
      summary="Ranks candidate buildings against your requirements and weights, with a score per criterion, the "
              "deal-breakers and the evidence for each cell.",
      model_description="The enterprise site-selection scorecard. A business gives a profile (office, industrial, retail, "
                        "flex), requirements (size range or headcount, budget per ft², docks, clear height, parking ratio, "
                        "step-free entrance, highway and transit distance, flood tolerance, employee home zips) and "
                        "optional weights; give 2 to 10 candidates (scans, CoStar properties, addresses, points) or none to "
                        "search CoStar listings near a place or in Houston or Los Angeles. Returns a ranked table, per-"
                        "criterion checks with evidence and source, and deal-breakers. `deep` also runs industrial_fit or "
                        "retail_site on each candidate.",
      personas=["industrial_tenant_rep", "retail_site_selector", "office_relocation", "commercial_underwriter",
                "costar_researcher"],
      requires=[{"layer": "costar.property"}, {"layer": "osm", "need": "optional", "fallback": "no distances"},
                {"layer": "matterport.rooms", "need": "optional", "fallback": "record values only"}],
      blocks=["VerdictHeader", "MetricRow", "RankedTable", "MiniChart", "CheckList", "EvidenceStrip", "AssumptionChips",
              "ActionBar", "StepLog"],
      table=[{"metric": "score", "label": "Score"}],
      annotations={"cost": "slow"},
      examples=["Find me a 40,000 to 80,000 ft² distribution warehouse in Houston under $12 a foot with 24 ft clear",
                "Compare these three office buildings for a 120-person team",
                "Score these retail sites for our next store"])
def run(ctx, i: Inputs) -> ToolResult:
    req = requirements(i)
    weights = {k: v for k, v in WEIGHTS[i.profile].items()}
    weights.update({k: float(v) for k, v in i.weights.items() if k in CRITERIA})
    if not i.employees:
        weights.pop("commute", None)
    if not i.step_free and i.profile in ("industrial", "flex"):
        weights.pop("step_free", None)
    if i.step_free:
        weights.setdefault("step_free", 2)
    if not i.deep:
        weights.pop("truck_court", None)
    must = list(i.must) if i.must is not None else [k for k in MUST[i.profile] if
                                                     (k != "rent" or req.get("budget_sf_yr")) and
                                                     (k != "size" or req.get("size_min_sf"))]
    if i.flood == "avoid" and "flood" not in must:
        must.append("flood")
    if i.step_free and "step_free" not in must:
        must.append("step_free")
    homes = None
    if i.employees:
        from ..commute_fit import parse_homes
        homes = parse_homes(i.employees)

    if i.candidates:
        if len(i.candidates) < 2:
            raise ToolError("Give at least two candidates to compare, or none to search.")
        cands = [candidate(ctx, p) for p in i.candidates]
        how = f"{len(cands)} candidates given"
    else:
        origin = None
        if i.near:
            s = ctx.site(i.near)
            origin = (s.lat, s.lon) if s.lat is not None else None
        if not origin and not i.city:
            raise ToolError("Give candidate buildings, or a place or a city (Houston or Los Angeles) to search.")
        try:
            pool = list(kit.rows().values())
        except LookupError as e:
            raise ToolError(f"The CoStar kit is not on this server, so there is nothing to search: {e}") from None
        found = search(i, req, origin, pool)
        if len(found) < 2:
            return ToolResult(scope=ScansScope(sids=[]), verdict=Verdict(
                status="unknown", text=f"The CoStar kit has {len(found)} {i.profile} propert{'y' if len(found) == 1 else 'ies'} "
                f"marketed for lease that fit; widen the size range or the search area."))
        cands = [Cand(f"p{x['id']}", x.get("address") or str(x["id"]), x["lat"], x["lon"], [], x) for x in found]
        how = f"{len(cands)} candidates found among CoStar {i.profile} listings " + \
              (f"within {i.search_km:g} km" if origin else f"in {i.city}")
    ctx.step(how)
    for c in cands:
        evaluate(ctx, c, i, req, weights, must, homes)
        ctx.step(f"{c.name}: score {c.total if c.total is not None else 'n/a'}, coverage {c.coverage}%"
                 + (f", deal-breakers: {', '.join(CRITERIA[k][0].lower() for k in c.breakers)}" if c.breakers else ""))
    cands.sort(key=lambda c: (bool(c.breakers), -(c.total or 0), -c.coverage))
    return build(cands, i, req, weights, must, how)


def build(cands: list[Cand], i: Inputs, req: dict, weights: dict, must: list[str], how: str) -> ToolResult:
    metrics, checks, findings, ps, actions = [], [], [], [], []
    cols = [k for k in COLUMNS[i.profile] if k in weights or k in ("rent", "size")]
    for rank, c in enumerate(cands, start=1):
        label = f"{rank}. {c.name}"
        metrics.append(Metric(id=f"{c.key}/score", label=label, value=c.total, unit="/100", source=SCORE))
        for k in cols:
            cell = c.cells.get(k)
            metrics.append(Metric(id=f"{c.key}/{k}", label=label, value=cell.display if cell and isinstance(cell.display, (int, float)) else None,
                                  unit=CRITERIA[k][1], source=cell.source if cell else SCORE))
        metrics.append(Metric(id=f"score.{c.key}", label=c.name, value=c.total, unit="/100", source=SCORE))
        for k, w in weights.items():
            cell = c.cells.get(k)
            fid = f"site_scorecard:{c.key}:{k}"
            st = cell.status if cell else "unknown"
            checks.append(Check(id=f"{c.key}.{k}", rule=f"{CRITERIA[k][0]}, {c.name}" + (" (must)" if k in must else ""),
                                measured=cell.value if cell and isinstance(cell.value, (int, float)) else None,
                                threshold=cell.threshold if cell else None, unit=CRITERIA[k][1], status=st,
                                standard=(cell.source.note if cell else "No evidence for this criterion"),
                                findings=[fid] if cell and (k in c.breakers or k in must) else []))
            if cell and (k in c.breakers or (k in must and st != "unknown")):
                findings.append(Finding(id=fid, title=f"{CRITERIA[k][0]} at {c.name}" + (" is a deal-breaker" if k in c.breakers else ""),
                                        status=st, detail=cell.evidence + (f". Score {cell.score:.0f}/100." if cell.score is not None else "."),
                                        anchor=geo(c.lon, c.lat) if c.lat is not None else None, source=cell.source))
        st = "fail" if c.breakers else "pass" if rank == 1 else "warn" if (c.total or 0) < 60 else "pass"
        good = [CRITERIA[k][0].lower() for k, cl in c.cells.items() if k in weights and cl.status == "pass"]
        weak = [CRITERIA[k][0].lower() for k, cl in c.cells.items() if k in weights and cl.status in ("warn", "fail")]
        missing = [CRITERIA[k][0].lower() for k in weights if k not in c.cells or c.cells[k].score is None]
        detail = (f"Rank {rank}, score {c.total if c.total is not None else 'n/a'}/100 from {c.coverage}% of the weighted "
                  f"criteria." + (f" Deal-breakers: {', '.join(CRITERIA[k][0].lower() for k in c.breakers)}." if c.breakers else "")
                  + (f" Strong: {', '.join(good)}." if good else "") + (f" Weak: {', '.join(weak)}." if weak else "")
                  + (f" No evidence: {', '.join(missing)}." if missing else "")
                  + (f" Must-haves not verified ({UNVERIFIED_PENALTY} points off each): "
                     f"{', '.join(CRITERIA[k][0].lower() for k in c.unverified)}." if c.unverified else "")
                  + " " + " ".join(f"{CRITERIA[k][0]}: {cl.evidence}." for k, cl in c.cells.items() if k in weights))
        findings.insert(rank - 1, Finding(id=f"site_scorecard:{c.key}:summary", title=f"#{rank} {c.name}", status=st, detail=detail,
                                          anchor=geo(c.lon, c.lat) if c.lat is not None else None, source=SCORE))
        if c.lat is not None:
            ps.append(pin(f"cand_{c.key}", c.lon, c.lat, f"#{rank}", st))
        place = {"scan": c.sids[0]} if c.sids and not c.row else {"property_id": c.row["id"]} if c.row else {"geo": [c.lon, c.lat]}
        if rank <= 3:
            actions.append(Action(id=f"comps_{c.key}", label=f"Comps for #{rank}", tool="market_comps", inputs={"place": place}))
            if i.profile in ("industrial", "flex"):
                actions.append(Action(id=f"ind_{c.key}", label=f"Warehouse check of #{rank}", tool="industrial_fit", inputs={"place": place}))
            if i.profile == "retail":
                actions.append(Action(id=f"ret_{c.key}", label=f"Retail site check of #{rank}", tool="retail_site", inputs={"place": place}))
    ok = [c for c in cands if not c.breakers]
    best = ok[0] if ok else None
    metrics[:0] = [
        Metric(id="candidates", label="Candidates", value=len(cands), unit="", source=SCORE),
        Metric(id="best_score", label="Best score", value=best.total if best else None, unit="/100", source=SCORE),
        Metric(id="deal_breakers", label="With deal-breakers", value=sum(bool(c.breakers) for c in cands), unit="", source=SCORE),
        Metric(id="best_coverage", label="Evidence coverage of the best", value=best.coverage if best else None, unit="%", source=SCORE),
    ]
    if best:
        text = (f"{best.name} ranks first of {len(cands)} {i.profile} candidates with {best.total}/100 "
                f"({best.coverage}% of the weighted criteria have evidence).")
        if len(ok) > 1:
            text += f" Next: {ok[1].name} ({ok[1].total}/100)."
        out = [c for c in cands if c.breakers]
        if out:
            text += f" {len(out)} fail a must-have: " + "; ".join(
                f"{c.name} ({', '.join(CRITERIA[k][0].lower() for k in c.breakers)})" for c in out[:3]) + "."
        status = "pass" if (best.total or 0) >= 70 and not best.unverified else "warn"
    else:
        text = f"All {len(cands)} candidates fail a must-have; the closest is {cands[0].name}."
        status = "fail"
    assumptions = [{"id": "column." + k, "label": CRITERIA[k][0] + (f" ({CRITERIA[k][1]})" if CRITERIA[k][1] else ""),
                    "value": CRITERIA[k][0]} for k in cols]
    assumptions[0:0] = [{"id": f"site.{k}", "label": k.replace("_", " "), "value": v, "editable": True}
                        for k, v in req.items() if v is not None]
    assumptions += [{"id": "weights", "label": "Weights", "value": ", ".join(f"{k} {w:g}" for k, w in weights.items())},
                    {"id": "must", "label": "Must-haves", "value": ", ".join(must) or "none"},
                    {"id": "search", "label": "Candidates", "value": how}]
    sids = [s for c in cands for s in c.sids][:50]
    return ToolResult(scope=ScansScope(sids=sids), verdict=Verdict(status=status, text=text), metrics=metrics,
                      checks=checks, findings=findings, overlays=pins(ps), assumptions=assumptions, actions=actions)
