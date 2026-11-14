"""Nearby: parks, playgrounds, schools, courts and fields, vets, shops and transit around a home, with the walk or
ride along the street network to the nearest of each. One profile (pets, kids, sports, everyday) or any categories
the person picks. `report()` is shared by pet_fit and kids_fit so all three answer the same way."""
from __future__ import annotations

from typing import Literal

from ... import nearby as engine
from .. import (
    Assumption,
    Check,
    Finding,
    Metric,
    Source,
    ToolResult,
    Verdict,
    field,
    tool,
)
from .._site import Where, geo, geo_route, locate, pin, pins

Category = Literal[tuple(engine.CATEGORIES)]
WALK_OK_MIN = 10        # a 10-minute walk: the usual "walkable" line (800 m at 80 m/min)
WALK_FAR_MIN = 20
DRIVE_OK_MIN = 20       # vets: people drive; an emergency vet within 20 minutes


def src(method: str = "geometry", confidence: str = "medium", note: str = "") -> Source:
    return Source(layer="model", method=method, confidence=confidence, note=f"{engine.NOTE}. {note}".strip())


def status_of(minutes: float | None, ok: float = WALK_OK_MIN, far: float = WALK_FAR_MIN) -> str:
    if minutes is None:
        return "unknown"
    return "pass" if minutes <= ok else "warn" if minutes <= far else "fail"


def report(tool_id: str, key: str, lat: float, lon: float, categories: list[str], mode: str = "walk",
           start: tuple[float, float] | None = None, k: int = 3, ok_min: float = WALK_OK_MIN,
           far_min: float = WALK_FAR_MIN, prefix: str = "near") -> dict:
    """Metrics, checks, findings and overlays for the nearest places in each category. On an Overpass failure,
    one unknown check that says so. {metrics, checks, findings, overlays, hits, error}."""
    out: dict = {"metrics": [], "checks": [], "findings": [], "overlays": [], "hits": {}, "error": None}
    try:
        got = engine.nearest(lat, lon, categories, mode=mode, k=k, start=start)
    except RuntimeError as e:
        out["error"] = str(e)
        out["checks"].append(Check(id=f"{prefix}.unavailable", rule="Places nearby (OpenStreetMap)", measured=None,
                                   threshold=None, unit="", status="unknown", findings=[]))
        return out
    meta = got.pop("_meta")
    verb = "walk" if mode == "walk" else "ride"
    ps = []
    for cat in categories:
        hits = got.get(cat) or []
        out["hits"][cat] = hits
        label = engine.CATEGORIES[cat][0]
        if not hits:
            out["checks"].append(Check(id=f"{prefix}.{cat}", rule=f"{label} within reach", measured=None,
                                       threshold=ok_min, unit="min", status="fail" if mode == "walk" else "warn",
                                       findings=[f"{tool_id}:{key}:{prefix}:{cat}"]))
            out["findings"].append(Finding(id=f"{tool_id}:{key}:{prefix}:{cat}", title=f"No {label.lower()} mapped nearby",
                                           status="warn", anchor=geo(*(start or (lon, lat))), source=src("lookup", "low"),
                                           detail=f"OpenStreetMap has no {label.lower()} within {engine.R_PLACES / 1000:.1f} km "
                                                  f"(vets within {engine.R_VETS / 1000:.0f} km). OSM can miss places; "
                                                  "absence here is not proof."))
            continue
        h = hits[0]
        car = h.get("by") == "car"
        lo, hi = (DRIVE_OK_MIN, 2 * DRIVE_OK_MIN) if car else (ok_min, far_min)
        st = status_of(h["minutes"], lo, hi)
        conf = "medium" if h["method"] == "network" else "low"
        how = ("along the street network" if h["method"] == "network" else
               f"estimated: straight line {h['straight_m']:.0f} m times {engine.DETOUR}, no street route found")
        fid = f"{tool_id}:{key}:{prefix}:{cat}"
        by = "drive" if car else verb
        out["metrics"].append(Metric(id=f"{prefix}_{by}.{cat}", label=label, value=h["minutes"], unit="min",
                                     source=src(note=how)))
        out["checks"].append(Check(id=f"{prefix}.{cat}", rule=f"{label} within a {lo:g}-minute {by}",
                                   measured=h["minutes"], threshold=lo, unit="min", status=st, findings=[fid]))
        crossing = (f" The way crosses {h['busy_crossings']} busy road{'s' if h['busy_crossings'] != 1 else ''}."
                    if h.get("busy_crossings") else "")
        others = "; ".join(f"{x['name']} {x['route_m']:.0f} m" for x in hits[1:])
        out["findings"].append(Finding(
            id=fid, title=f"Nearest {label.lower()}", status=st, anchor=geo(h["lon"], h["lat"]),
            source=src(confidence=conf, note=how),
            detail=f"{h['name']}: {h['route_m'] / 1000:.1f} km, about {h['minutes']:.0f} min "
                   + ("by car at city speed" if car else "on foot" if mode == "walk" else "by bike")))
        out["findings"][-1].detail += f" ({how}).{crossing}" + (f" Next: {others}." if others else "")
        if h["method"] == "network":
            out["overlays"].append(geo_route(h["path"], f"{'Drive' if car else verb.capitalize()} to the nearest {label.lower()}"))
        for x in hits:
            ps.append(pin(f"{prefix}_{cat}_{x['id'].replace('/', '_')}", x["lon"], x["lat"], f"{label}: {x['name']}",
                          status_of(x["minutes"], lo, hi)))
    out["overlays"] += pins(ps)
    out["meta"] = meta
    return out


def assumptions(mode: str, ok_min: float = WALK_OK_MIN) -> list[Assumption]:
    speed = engine.WALK_M_MIN if mode == "walk" else engine.CYCLE_M_MIN
    return [Assumption(id="nearby.speed", label=f"{'Walking' if mode == 'walk' else 'Cycling'} pace", value=speed, unit="m/min"),
            Assumption(id="nearby.ok_min", label="Counted as close", value=ok_min, unit="min"),
            Assumption(id="nearby.detour", label="Detour factor when no street route is found", value=engine.DETOUR),
            Assumption(id="nearby.source", label="Places and streets", value="OpenStreetMap, as mapped by volunteers")]


class Inputs(Where):
    profile: Literal["pets", "kids", "sports", "everyday"] | None = field(
        None, ask="What should be near the home? pets, kids, sports or everyday (grocery, pharmacy, transit, coffee)",
        pref="nearby.profile", description="A ready-made set of categories")
    categories: list[Category] = field([], pref="nearby.categories", description="Categories to look for, added to the profile's. Sports: "
                                                       + ", ".join(engine.SPORTS))
    mode: Literal["walk", "cycle"] = field("walk", pref="nearby.mode", description="Walking or cycling time")
    ok_min: float = field(WALK_OK_MIN, pref="nearby.ok_min", unit="min", gt=0, le=60,
                          description="Minutes counted as close")


@tool(id="nearby", title="Nearby", icon="map-pin",
      summary="Parks, playgrounds, schools, sports courts and fields, vets, shops and transit near a home, with the walk "
              "or ride to the nearest of each along the streets.",
      model_description="Places near a scan, CoStar property or point from OpenStreetMap (cached), by profile (pets: dog "
                        "parks, vets, emergency vets, trails; kids: playgrounds, parks, schools by level, libraries, pools, "
                        "childcare; sports: tennis, pickleball, basketball, soccer, baseball, pools, gyms, climbing, golf, "
                        "skate parks, tracks, bike paths, ice rinks; everyday: grocery, pharmacy, transit, coffee) or any "
                        "categories. Walking or cycling minutes along the street network, busy roads crossed, pins and "
                        "routes on the map.",
      personas=["parent_young_kids", "teen_soccer_family", "racket_player", "dog_owner_home", "cat_owner_apartment",
                "senior_dog_owner"],
      requires=[{"layer": "osm.places"}], blocks=["VerdictHeader", "MetricRow", "CheckList", "MiniChart", "AssumptionChips", "StepLog"],
      overlays=["pins", "route"],
      examples=["Is there a playground within a 10-minute walk?", "How far is the nearest pickleball court?",
                "Where is the closest emergency vet?"])
def run(ctx, inputs: Inputs) -> ToolResult:
    s = locate(ctx, inputs)
    cats = list(dict.fromkeys((engine.PROFILES[inputs.profile]["categories"] if inputs.profile else []) + inputs.categories))
    if not cats:
        cats = engine.PROFILES["everyday"]["categories"]
    ctx.step(f"Looking up {len(cats)} kinds of places around {s.address or s.key} in OpenStreetMap (cached after the first time)")
    r = report("nearby", s.key, s.lat, s.lon, cats, inputs.mode, ok_min=inputs.ok_min, far_min=2 * inputs.ok_min)
    if r["error"]:
        return ToolResult(scope=s.scope, verdict=Verdict(status="unknown", text=f"{r['error']}. Try again in a few minutes."),
                          checks=r["checks"])
    ctx.step(f"Routed over {r['meta']['network_nodes']} street nodes")
    close = [c for c in r["checks"] if c.status == "pass"]
    missing = [c for c in r["checks"] if c.status == "fail"]
    names = lambda cs: ", ".join(engine.CATEGORIES[c.id.split(".", 1)[1]][0].lower() for c in cs)
    text = (f"{len(close)} of {len(cats)} kinds of places are within a {inputs.ok_min:g}-minute {inputs.mode}"
            + (f": {names(close)}." if close else ".") + (f" Far or missing: {names(missing)}." if missing else ""))
    status = "pass" if len(close) == len(cats) else "warn" if close else "fail"
    return ToolResult(scope=s.scope, verdict=Verdict(status=status, text=text), metrics=r["metrics"], checks=r["checks"],
                      findings=r["findings"], overlays=r["overlays"], assumptions=assumptions(inputs.mode, inputs.ok_min))
