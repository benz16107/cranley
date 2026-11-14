"""Retail site: what a chain looks at before it signs for a shop.

Parking stalls counted on the aerial (parking_count) and the ratio per 1,000 ft² of the store; the main road the site
faces, its class and lanes, and how far the building sits back from it; anchors (supermarkets, big-box stores) within
1.5 km and shops, places to eat and services within the walk radius (co-tenancy); bus stops and the homes and offices
mapped within the radius (a walk-in proxy). All from OpenStreetMap except the stall count. Sign line of sight is not
checked: it would need the surface model along every approach.
"""
from __future__ import annotations

from pydantic import BaseModel

from .. import Check, Finding, Metric, Place, Source, ToolResult, Verdict, field, run_tool, tool
from .._site import geo, pin, pins
from ..industrial_fit import where_of
from ..market_comps import kit
from ..site_scorecard import near

OSM = Source(layer="model", method="lookup", confidence="medium",
             note=near.NOTE + "; shops and buildings OpenStreetMap has not mapped are missed")
ROAD_RANK = {"motorway": 6, "trunk": 5, "primary": 4, "secondary": 3, "tertiary": 2}


class Inputs(BaseModel):
    place: Place = field(source="selection.place", description="The site: a scan, a CoStar property, an address or a point")
    store_sf: float | None = field(None, pref="retail.store_sf", unit="ft²", gt=0,
                                   description="Store size, for the parking ratio; default the building's rentable area")
    parking_ratio_min: float = field(4.0, pref="site.parking_ratio_min", unit="per 1,000 ft²", ge=0, le=20,
                                     description="Stalls per 1,000 ft² the store needs")
    radius_m: int = field(400, pref="retail.radius_m", unit="m", ge=100, le=1500, description="Walk radius for neighbours")
    count_parking: bool = field(True, description="Count stalls on the aerial with parking_count (slow, cached)")


def frontage(roads: list[dict]) -> dict | None:
    """The highest-class busy road found (nearest among equals)."""
    named = [r for r in roads if r["kind"].removesuffix("_link") in ROAD_RANK]  # from nearby.busy_road_m: secondary or bigger
    if not named:
        return None
    return max(named, key=lambda r: (ROAD_RANK[r["kind"].removesuffix("_link")], -r["km"]))


@tool(id="retail_site", title="Retail site", icon="store",
      summary="Parking counted from the air and its ratio, the road the site faces, anchors and neighbouring shops, "
              "and walk-in proxies.",
      model_description="For a shop or restaurant site (scan, CoStar property or point): parking stalls counted on the "
                        "aerial (parking_count) and stalls per 1,000 ft² of the store; the main road it faces (class, lanes, "
                        "setback); anchor stores within 1.5 km and shops, food and services within a walk radius (co-"
                        "tenancy); bus stops and mapped homes and offices nearby as walk-in proxies. OpenStreetMap based.",
      personas=["retail_site_selector", "commercial_underwriter"],
      requires=[{"layer": "osm"}, {"layer": "vexcel.ortho", "need": "optional", "fallback": "no stall count"}],
      blocks=["VerdictHeader", "MetricRow", "CheckList", "EvidenceStrip", "AssumptionChips", "StepLog"],
      annotations={"cost": "slow"},
      examples=["Is this a good spot for our next store?", "How much parking does this retail site have per 1,000 ft²?"])
def run(ctx, i: Inputs) -> ToolResult:
    s = ctx.site(i.place)
    key = s.key
    if s.lat is None:
        return ToolResult(scope=s.scope(), verdict=Verdict(status="unknown", text="This place has no location."))
    row = kit.row(s.property_id) or {}
    size = i.store_sf or row.get("rba")
    anchor = geo(s.lon, s.lat)
    metrics, checks, findings, ps = [], [], [], [pin("site", s.lon, s.lat, "site", "pass")]

    stalls = None
    if i.count_parking:
        try:
            pc = run_tool("parking_count", where_of(i.place, s), ctx)
            m = {x.id: x for x in pc.metrics}
            best = m.get("stalls") if m.get("stalls") and m["stalls"].value is not None else m.get("lot_estimate")
            if best and best.value is not None:
                stalls = best.value
                metrics.append(Metric(id="stalls", label=best.label, value=stalls, unit="", source=best.source))
            findings += pc.findings[:2]
        except Exception as e:  # noqa: BLE001  the record ratio still answers
            ctx.step(f"parking_count did not run: {str(e)[:120]}")
    if stalls is None and row.get("parking_spaces"):
        stalls = row["parking_spaces"]
        metrics.append(Metric(id="stalls", label="Spaces in the record", value=stalls, unit="",
                              source=Source(layer="costar", method="lookup", confidence="medium", note=f"CoStar property {row['id']}")))
    if stalls is not None and size:
        ratio = round(1000 * stalls / size, 2)
        metrics.append(Metric(id="parking_ratio", label="Stalls per 1,000 ft²", value=ratio, unit="per 1,000 ft²",
                              source=Source(layer="model", method="geometry", confidence="medium",
                                            note=f"{stalls:g} stalls over {size:,.0f} ft² ({'given' if i.store_sf else 'rentable area in the record'})")))
        st = "pass" if ratio >= i.parking_ratio_min else "warn" if ratio >= i.parking_ratio_min * 0.75 else "fail"
        checks.append(Check(id="parking_ratio", rule="Parking ratio", measured=ratio, threshold=i.parking_ratio_min,
                            unit="per 1,000 ft²", status=st, standard="Typical retail planning ratio 4 to 5 per 1,000 ft²"))
    else:
        checks.append(Check(id="parking_ratio", rule="Parking ratio", measured=None, threshold=i.parking_ratio_min,
                            unit="per 1,000 ft²", status="unknown",
                            standard="Needs a stall count and a store size"))

    try:
        r = near.retail(s.lat, s.lon, i.radius_m)
    except Exception as e:  # noqa: BLE001
        ctx.step(f"OpenStreetMap lookup failed: {str(e)[:120]}")
        r = None
    if r:
        f = frontage(r["roads"])
        if f:
            metrics.append(Metric(id="road_setback", label=f"Distance to {f['name'] or f['kind']}", value=round(f["km"] * 1000),
                                  unit="m", source=OSM))
            st = "pass" if ROAD_RANK.get(f["kind"].removesuffix("_link"), 0) >= 3 and f["km"] <= 0.2 else "warn"
            checks.append(Check(id="frontage", rule="A secondary road or bigger within 200 m", measured=round(f["km"] * 1000),
                                threshold=200, unit="m", status=st, findings=[f"retail_site:{key}:frontage"]))
            findings.append(Finding(id=f"retail_site:{key}:frontage", title="The road the site faces", status=st, anchor=anchor,
                                    source=OSM, detail=f"{f['name'] or 'An unnamed road'}, a {f['kind'].replace('_', ' ')} road"
                                    + (f" with {f['lanes']} lanes" if f.get("lanes") else "") + f", {f['km'] * 1000:.0f} m from "
                                    "the building's point. Traffic counts are not in OpenStreetMap; the road class stands in. "
                                    "Sign line of sight from the road is not checked."))
        else:
            checks.append(Check(id="frontage", rule="A secondary road or bigger within 200 m", measured=None, threshold=200, unit="m",
                                status="warn", standard="No secondary or bigger road mapped within 2 km"))
        n = len(r["shops"]) + len(r["food"]) + len(r["services"])
        metrics += [Metric(id="neighbours", label=f"Shops, food and services within {i.radius_m} m", value=n, unit="", source=OSM),
                    Metric(id="anchors", label="Named anchor stores within 1.5 km", value=len(r["anchors"]), unit="", source=OSM),
                    Metric(id="mix.shops", label="Shops", value=len(r["shops"]), unit="", source=OSM),
                    Metric(id="mix.food", label="Places to eat", value=len(r["food"]), unit="", source=OSM),
                    Metric(id="mix.services", label="Services", value=len(r["services"]), unit="", source=OSM),
                    Metric(id="bus_stops", label=f"Bus stops within {i.radius_m} m", value=r["bus_stops"], unit="", source=OSM),
                    Metric(id="homes_mapped", label=f"Home buildings mapped within {i.radius_m} m", value=r["home_buildings"], unit="", source=OSM)]
        st = "pass" if n >= 20 else "warn" if n >= 5 else "fail"
        checks.append(Check(id="co_tenancy", rule=f"Neighbouring businesses within {i.radius_m} m", measured=n, threshold=20,
                            unit="", status=st, findings=[f"retail_site:{key}:mix"]))
        top = sorted({x["kind"] for x in r["shops"] + r["food"] + r["services"] if x["kind"]},
                     key=lambda k: -sum(x["kind"] == k for x in r["shops"] + r["food"] + r["services"]))[:8]
        named = [x["name"] for x in r["shops"] + r["food"] + r["services"] if x["name"]][:10]
        findings.append(Finding(id=f"retail_site:{key}:mix", title="Co-tenancy: who is next door", status=st, anchor=anchor, source=OSM,
                                detail=f"{len(r['shops'])} shops, {len(r['food'])} places to eat, {len(r['services'])} services "
                                       f"within {i.radius_m} m. Commonest kinds: {', '.join(k.replace('_', ' ') for k in top) or 'none'}."
                                       + (f" Named: {', '.join(named)}." if named else "")))
        if r["anchors"]:
            findings.append(Finding(id=f"retail_site:{key}:anchors", title="Anchor stores nearby", status="pass", anchor=anchor,
                                    source=OSM, detail="; ".join(f"{a['name']} ({a['kind'].replace('_', ' ')}) {a['km']:.1f} km"
                                                                 for a in r["anchors"][:6]) + "."))
            for a in r["anchors"][:6]:
                ps.append(pin(f"anchor_{a['id']}", a["lon"], a["lat"], a["name"][:24], "pass"))
        walk = r["home_buildings"] + r["office_buildings"]
        findings.append(Finding(id=f"retail_site:{key}:walkin", title="Walk-in proxies", status="pass" if walk >= 50 or r["bus_stops"] >= 3 else "warn",
                                anchor=anchor, source=OSM,
                                detail=f"{r['home_buildings']} home and {r['office_buildings']} office buildings and {r['bus_stops']} "
                                       f"bus stops mapped within {i.radius_m} m. Mapping is uneven: a low count can mean few "
                                       "buildings or few mapped ones. No pedestrian counts are available."))
    bad = [c for c in checks if c.status in ("fail", "warn")]
    status = "fail" if any(c.status == "fail" for c in checks) else "warn" if bad else "pass"
    m = {x.id: x.value for x in metrics}
    parts = [f"{m['stalls']:g} stalls" + (f" ({m['parking_ratio']:g} per 1,000 ft²)" if "parking_ratio" in m else "")] if "stalls" in m else []
    if "neighbours" in m:
        parts.append(f"{m['neighbours']:g} businesses within {i.radius_m} m and {m['anchors']:g} anchors within 1.5 km")
    text = f"{s.address or key}: " + ("; ".join(parts) or "little is known") + "." + \
        (f" Weak: {'; '.join(c.rule.lower() for c in bad)}." if bad else "")
    return ToolResult(scope=s.scope(), verdict=Verdict(status=status, text=text), metrics=metrics, checks=checks,
                      findings=findings, overlays=pins(ps),
                      assumptions=[{"id": "site.parking_ratio_min", "label": "Parking ratio needed", "value": i.parking_ratio_min, "editable": True},
                                   {"id": "retail.radius_m", "label": "Walk radius", "value": i.radius_m, "unit": "m", "editable": True},
                                   {"id": "store_size", "label": "Store size", "value": size, "unit": "ft²"}])
