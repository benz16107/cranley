"""Market comps: comparable commercial properties from the CoStar kit for one candidate building.

Comps are properties of the same type, of similar size, nearest first, with their asking rent (normalised to $ per ft²
per year), last single-property sale price per ft², class, year built and the share of the building marketed for lease.
The candidate is placed against them (its rent's percentile among the comps).

What the kit cannot give, said in every result: it holds only the 3,339 properties on CoStar's Matterport list, so
comps come from that list, not the whole market; asking rents are face rents, not signed or effective rents; space
marketed for lease is not vacancy; there is no market vacancy rate or absorption.
"""
from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel

from .. import (
    Check,
    Finding,
    Metric,
    NotApplicable,
    Place,
    Source,
    ToolError,
    ToolResult,
    Verdict,
    field,
    tool,
)
from .._site import geo, pin, pins
from . import kit

KIT = Source(layer="costar", method="lookup", confidence="medium",
             note="CoStar kit: asking rents of active lease spaces, normalised to $/ft²/yr (monthly x 12, zeros dropped)")
SALE = Source(layer="costar", method="lookup", confidence="medium",
              note="CoStar kit sale comps: single-property sales only, price / building ft²; price status in each finding")
DERIVED = Source(layer="model", method="geometry", confidence="medium", note="Computed from the comps above")
LIMITS = ("The kit holds only the 3,339 properties on CoStar's Matterport capture list, so these comps are drawn from that "
          "list, not the whole market. Rents are asking (face) rents, not signed or effective rents, and they mix service "
          "types (triple net excludes operating costs; full service includes them). Space marketed for lease is not "
          "vacancy, and the kit has no market vacancy rate, absorption or rent growth.")
PROFILE_TYPE = {"office": 5, "industrial": 2, "retail": 6, "flex": 7}


class Inputs(BaseModel):
    place: Place | None = field(None, source="selection.place", description="The candidate: a scan, a CoStar property, "
                                                                            "an address or a point")
    property_type: Literal["office", "industrial", "retail", "flex"] | None = field(
        None, description="Type to compare with when the place has no CoStar record (a bare point)")
    size_sf: float | None = field(None, gt=0, description="Size to compare with when the place has no record, ft²")
    radius_km: float = field(10, pref="comps.radius_km", unit="km", ge=1, le=60, description="Search radius for comps")
    size_band: float = field(2.5, pref="comps.size_band", ge=1.2, le=10,
                             description="Comps may be this many times smaller or larger than the candidate")
    max_comps: int = field(8, ge=3, le=20, description="At most this many comps")
    same_class: bool = field(False, description="Only comps of the candidate's building class")


def pick(subject: dict, pool: list[dict], lat: float, lon: float, *, radius_km: float, band: float, n: int,
         same_class: bool = False) -> tuple[list[dict], float]:
    """Comps for a subject row from a pool of rows: same type, size within the band, within the radius (widened up to
    three times while fewer than three are found). Ranked by distance and size difference. Returns (comps, radius)."""
    size = subject.get("rba")
    for r in (radius_km, radius_km * 2, radius_km * 4):
        cand = []
        for x in pool:
            if x["id"] == subject.get("id") or x.get("type_id") != subject.get("type_id") or x.get("lat") is None:
                continue
            if same_class and subject.get("class") and x.get("class") != subject["class"]:
                continue
            if size and x.get("rba") and not (size / band <= x["rba"] <= size * band):
                continue
            d = kit.km(lat, lon, x["lat"], x["lon"])
            if d <= r:
                gap = abs(math.log(x["rba"] / size)) if size and x.get("rba") else 1
                bare = 0 if kit.asking_rent(x) or kit.last_sale(x) else 0.75  # a comp with no price says little
                cand.append({**x, "km": round(d, 2), "_rank": d / r + gap / math.log(band) + bare})
        if len(cand) >= 3 or r == radius_km * 4:
            return sorted(cand, key=lambda x: x["_rank"])[:n], r
    return [], radius_km


def _money(x):
    return f"${x:,.2f}"


def place_row(ctx, place: Place | None, ptype: str | None, size_sf: float | None) -> tuple[dict, float, float, object, str]:
    """(subject row, lat, lon, scope, key) for a place, from its CoStar record or the type and size given."""
    if place is None:
        raise ToolError("Give the candidate building: a scan, a CoStar property id, an address or a point.")
    s = ctx.site(place)
    if s.lat is None:
        raise NotApplicable("This place has no location, so there are no comps near it.")
    row = kit.row(s.property_id)
    if row and row.get("type_id") in (11, 15, 16, None):
        row = None
    if not row:
        if not ptype:
            raise NotApplicable("This place has no commercial CoStar record. Say which type of space to compare with "
                                "(office, industrial, retail or flex).")
        row = {"id": None, "type_id": PROFILE_TYPE[ptype], "type": ptype.title(), "rba": size_sf, "address": s.address,
               "rents": [], "sales": [], "available": {}}
    return row, s.lat, s.lon, s.scope(), s.key


@tool(id="market_comps", title="Market comps", icon="scale",
      summary="Comparable properties from CoStar: asking rent, sale price per ft², class, year built and space for lease, "
              "and where this building sits against them.",
      model_description="Comparable commercial properties (same type, similar size, nearby) from the CoStar kit for one "
                        "candidate: asking rent per ft² per year, last sale price per ft², building class, year built, share "
                        "of the building marketed for lease; and the candidate's rent percentile among them. Says what the "
                        "kit does not contain (no market vacancy, asking not effective rents).",
      personas=["commercial_underwriter", "costar_researcher", "office_tenant", "industrial_tenant_rep",
                "retail_site_selector", "office_relocation"],
      requires=[{"layer": "costar.property"}],
      blocks=["VerdictHeader", "MetricRow", "RankedTable", "CheckList", "EvidenceStrip", "Note", "StepLog"],
      table=[{"metric": "rent", "label": "Asking $/ft²/yr", "better": "lower"},
             {"metric": "sale_psf", "label": "Sale $/ft²", "better": "lower"},
             {"metric": "rba", "label": "Size ft²"},
             {"metric": "year", "label": "Year built"},
             {"metric": "available_pct", "label": "For lease %", "better": "lower"},
             {"metric": "km", "label": "Distance km", "better": "lower"}],
      examples=["What do comparable warehouses rent for near this one?", "Is this office's asking rent above the market?",
                "Pull sale comps for this building"])
def run(ctx, inputs: Inputs) -> ToolResult:
    subj, lat, lon, scope, key = place_row(ctx, inputs.place, inputs.property_type, inputs.size_sf)
    ctx.step(f"Candidate: {subj.get('address') or key}, {subj['type'].lower()}"
             + (f", {subj['rba']:,.0f} ft²" if subj.get("rba") else ""))
    try:
        pool = list(kit.rows().values())
    except LookupError as e:
        return ToolResult(scope=scope, verdict=Verdict(status="unknown", text=f"The CoStar kit is not on this server: {e}"))
    comps, r = pick(subj, pool, lat, lon, radius_km=inputs.radius_km, band=inputs.size_band, n=inputs.max_comps,
                    same_class=inputs.same_class)
    ctx.step(f"Found {len(comps)} comps within {r:g} km" + (f" (widened from {inputs.radius_km:g} km)" if r != inputs.radius_km else ""))
    if not comps:
        return ToolResult(scope=scope, verdict=Verdict(status="unknown", text=f"The kit has no {subj['type'].lower()} "
                          f"properties of similar size within {r:g} km. " + LIMITS))
    return build(subj, comps, r, inputs, scope, key, lat, lon)


def build(subj: dict, comps: list[dict], r: float, inputs: Inputs, scope, key: str, lat: float, lon: float) -> ToolResult:
    metrics, checks, findings, ps = [], [], [], [pin("subject", lon, lat, "candidate", "pass")]
    rent_s, sale_s = kit.asking_rent(subj), kit.last_sale(subj)
    comp_rents, comp_sales = [], []
    for i, c in enumerate(comps):
        k = f"c{c['id']}"
        rent, sale = kit.asking_rent(c), kit.last_sale(c)
        avail = (c.get("available") or {}).get("sf")
        pct = round(100 * avail / c["rba"], 1) if avail and c.get("rba") else (0.0 if c.get("rba") else None)
        label = f"{c.get('address') or c['id']}" + (f" (class {c['class']})" if c.get("class") else "")
        src = Source(layer="costar", method="lookup", confidence="medium", note=f"CoStar property {c['id']}")
        metrics.append(Metric(id=f"{k}/rent", label=label, value=rent["rate"] if rent else None, unit="$/ft²/yr", source=KIT))
        metrics += [Metric(id=f"{k}/sale_psf", label=label, value=sale["psf"] if sale else None, unit="$/ft²", source=SALE),
                    Metric(id=f"{k}/rba", label=label, value=c.get("rba"), unit="ft²", source=src),
                    Metric(id=f"{k}/year", label=label, value=c.get("year_built"), unit="", source=src),
                    Metric(id=f"{k}/available_pct", label=label, value=pct, unit="%", source=KIT),
                    Metric(id=f"{k}/km", label=label, value=c["km"], unit="km", source=DERIVED)]
        if rent:
            comp_rents.append(rent["rate"])
        if sale:
            comp_sales.append(sale["psf"])
        bits = [f"{c['type']}, {c['rba']:,.0f} ft²" if c.get("rba") else c["type"], f"{c['km']:.1f} km away"]
        if c.get("year_built"):
            bits.append(f"built {c['year_built']}")
        if rent:
            bits.append(f"asking {_money(rent['rate'])}/ft²/yr ({rent['service']}, {rent['spaces']} space"
                        f"{'s' if rent['spaces'] != 1 else ''}{', sublease' if rent['sublease'] else ''})")
        else:
            bits.append("no asking rent in the kit")
        if sale:
            bits.append(f"sold {sale['date']} for ${sale['price']:,} ({_money(sale['psf'])}/ft², price {sale['status']})")
        if avail:
            bits.append(f"{avail:,} ft² marketed for lease")
        if c.get("clear_ft"):
            bits.append(f"{c['clear_ft']:g} ft clear")
        if c.get("docks"):
            bits.append(f"{c['docks']} docks")
        findings.append(Finding(id=f"market_comps:{key}:{c['id']}", title=f"Comp {i + 1}: {c.get('address') or c['id']}",
                                status="pass", detail="; ".join(bits) + ".", anchor=geo(c["lon"], c["lat"]), source=src))
        ps.append(pin(f"comp_{c['id']}", c["lon"], c["lat"], f"comp {i + 1}", "pass"))
    med_rent, med_sale = kit.median(comp_rents), kit.median(comp_sales)
    metrics[:0] = [m for m in (
        Metric(id="comps", label="Comps", value=len(comps), unit="", source=DERIVED),
        Metric(id="median_rent", label="Comp median asking rent", value=round(med_rent, 2) if med_rent else None, unit="$/ft²/yr", source=KIT),
        Metric(id="median_sale_psf", label="Comp median sale price", value=round(med_sale, 2) if med_sale else None, unit="$/ft²", source=SALE),
        Metric(id="subject_rent", label="This building's asking rent", value=rent_s["rate"] if rent_s else None, unit="$/ft²/yr", source=KIT),
        Metric(id="median_year", label="Comp median year built", value=kit.median([c.get("year_built") for c in comps]), unit="", source=DERIVED),
    )]
    verdict_bits = [f"{len(comps)} {subj['type'].lower()} comps within {r:g} km"]
    status = "pass"
    if rent_s and comp_rents:
        p = kit.percentile(rent_s["rate"], comp_rents)
        gap = (rent_s["rate"] - med_rent) / med_rent
        st = "warn" if gap > 0.15 else "pass"
        status = st
        metrics.append(Metric(id="rent_percentile", label="Rent percentile among comps", value=p, unit="%", source=DERIVED))
        checks.append(Check(id="rent_vs_comps", rule="Asking rent against the comp median", measured=rent_s["rate"],
                            threshold=round(med_rent, 2), unit="$/ft²/yr", status=st, kind="claim",
                            standard=f"Median of {len(comp_rents)} comp asking rents; above 15% over is a warning",
                            findings=[f"market_comps:{key}:rent"]))
        findings.insert(0, Finding(id=f"market_comps:{key}:rent", title="This building's asking rent against the comps",
                                   status=st, anchor=geo(lon, lat), source=KIT,
                                   detail=f"Asking {_money(rent_s['rate'])}/ft²/yr ({rent_s['service']}) against a comp median "
                                          f"of {_money(med_rent)} from {len(comp_rents)} comps with a rent: {gap:+.0%}, "
                                          f"percentile {p}. Service types differ between listings; compare like with like."))
        verdict_bits.append(f"its asking rent is {abs(gap):.0%} {'above' if gap > 0 else 'below'} their median")
    elif comp_rents:
        verdict_bits.append(f"{len(comp_rents)} have an asking rent; this building has none in the kit")
    else:
        verdict_bits.append("none has an asking rent in the kit")
        status = "warn"
    if sale_s and comp_sales:
        gap = (sale_s["psf"] - med_sale) / med_sale
        checks.append(Check(id="sale_vs_comps", rule="Last sale price per ft² against the comp median", measured=sale_s["psf"],
                            threshold=round(med_sale, 2), unit="$/ft²", status="pass", kind="claim",
                            standard=f"Median of {len(comp_sales)} comp sales (dates differ: {sale_s['date']} for this building)"))
        verdict_bits.append(f"it last sold at {abs(gap):.0%} {'above' if gap > 0 else 'below'} the comps' median per ft²")
    findings.append(Finding(id=f"market_comps:{key}:limits", title="What the CoStar kit does not hold", status="unknown",
                            detail=LIMITS, anchor=geo(lon, lat), source=KIT))
    return ToolResult(scope=scope, verdict=Verdict(status=status, text="; ".join(verdict_bits) + "."),
                      metrics=metrics, checks=checks, findings=findings, overlays=pins(ps),
                      assumptions=[{"id": "comps.radius_km", "label": "Search radius", "value": r, "unit": "km", "editable": True},
                                   {"id": "comps.size_band", "label": "Size band", "value": inputs.size_band, "unit": "x", "editable": True},
                                   {"id": "rent_basis", "label": "Rent basis", "value": "asking, $/ft²/yr, area-weighted over direct spaces"}])
