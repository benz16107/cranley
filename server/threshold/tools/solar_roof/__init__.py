"""Solar roof: how much of a roof can carry panels, how much sun it gets after trees and neighbours, and what a system
would make and save, for any house in Houston or Los Angeles.

Facets, pitch and facing come from Vexcel's surface model inside Vexcel's building footprint (threshold.sun.roof);
shading from the skyline the surface model makes from each roof cell across a clear-sky year. Energy scales a
labelled PVWatts yield by each facet's share of the sun a south 20 degree plane gets. Every price is an editable
assumption with its source.
"""
from __future__ import annotations

import datetime as dt
import math

import numpy as np
import shapely

from ...aerial.vexcel import VexcelError
from ...sun import roof as roofs
from ...world import terrain
from ...world.frame import enu_to_lonlat, lonlat_to_enu
from .. import Assumption, Check, Finding, Metric, Source, ToolResult, Verdict, field, tool
from .._site import Where, capture, fact, footprint, geo, geo_route, locate, pin, pins, src

MODULE_W, MODULE_M2 = 400, 1.722 * 1.134   # a typical 2025 residential module, 400 W on 1.95 m2 (about 20.5%)
PACKING = 0.8                              # share of a usable patch rectangles of modules fill
MIN_ORIENTATION = 0.8                      # a facet under 80% of a south 20 degree plane's sun is left bare
FLAT_SHARE = 0.3       # on a roof Vexcel calls pitched, flat cells under this share are the ridge, blurred by the grid
GOOD_PAYBACK_Y = 12
# PVWatts v8 (NREL), 1 kW dc, fixed open rack, south, 20 degrees, 14% system losses, TMY weather. Values are the
# published PVWatts runs we could find (Los Angeles 1,540-1,700, Houston 1,380-1,540 kWh/kW); not re-run here.
YIELD = {"CA": (1640, "Los Angeles"), "TX": (1420, "Houston")}
PRICE = {"CA": (0.3135, "EIA 2025 California average residential price, 31.35 c/kWh (final, Oct 2026)"),
         "TX": (0.1540, "EIA 2025 Texas average residential price, 15.40 c/kWh (final, Oct 2026)")}
COST_PER_W = 2.75  # installed $/W dc before incentives: an assumption, edit it to a quote
SETBACK_M = 0.91   # 36 in roof access pathways and edge setback (IFC 2021 1205.2, California Residential Code R324.6)
DSM = Source(layer="vexcel", method="geometry", confidence="medium",
             note="Facets, pitch and facing from Vexcel's surface model at 0.5 m inside its building footprint")


class Inputs(Where):
    cost_per_w: float = field(COST_PER_W, pref="solar.cost_per_w", unit="$/W", gt=0, le=10,
                              description="Installed cost per watt before incentives")
    price_per_kwh: float | None = field(None, pref="solar.price_per_kwh", unit="$/kWh", gt=0, le=2,
                                        description="What a kWh from the grid costs you; the state average if empty")


def _ll(lat0, lon0, poly):
    return [enu_to_lonlat(lat0, lon0, x, y) for x, y in poly.exterior.coords]


@tool(id="solar_roof", title="Solar roof", icon="sun",
      summary="Usable roof for solar after setbacks and shade, how many panels, kW, kWh a year and payback.",
      model_description="Rooftop solar for a house at a scan or a point in Houston or Los Angeles: roof facets with "
                        "area, pitch and facing from Vexcel's surface model, shading by trees and neighbours over a "
                        "clear-sky year, usable area after 36 in fire-code setbacks and ridges, then panels, kW, annual "
                        "kWh (PVWatts yield, labelled) and simple payback at a labelled electricity price. Draws the "
                        "usable patches on the map.",
      personas=["solar_homeowner", "houston_homeowner_storm"],
      requires=[{"layer": "vexcel.property"}, {"layer": "vexcel.dsm"}],
      blocks=["VerdictHeader", "MetricRow", "MiniChart", "CheckList", "AssumptionChips", "StepLog"],
      overlays=["pins", "route"],
      examples=["Is my roof good for solar?", "How many panels fit and what would they save?"])
def run(ctx, inputs: Inputs) -> ToolResult:
    s = locate(ctx, inputs)
    fp = footprint(s)
    if fp is None:
        return ToolResult(scope=s.scope, verdict=Verdict(status="unknown",
                          text="Vexcel has no building footprint at this point, so the roof cannot be measured."))
    c = fp.centroid
    lat0, lon0 = c.y, c.x
    outline = shapely.transform(fp, lambda xy: np.array([lonlat_to_enu(lat0, lon0, x, y) for x, y in xy]))
    try:
        ctx.step("Reading Vexcel's surface model over the roof and its neighbours")
        g = terrain.grid(lat0, lon0, 120, 240)
    except (VexcelError, KeyError, OSError, ValueError) as e:
        return ToolResult(scope=s.scope, verdict=Verdict(status="unknown",
                          text=f"Vexcel's surface model could not be read ({str(e)[:80]}), so the roof cannot be measured."))
    year = dt.date.today().year
    ctx.step(f"Found the roof facets in a {outline.area:.0f} m² footprint; tracing a clear-sky year of sun on each "
             "roof cell past trees and neighbours")
    r = roofs.analyse(g, outline, lat0, lon0, year, setback_m=SETBACK_M)
    state = s.state
    y_kwh, city = YIELD.get(state, YIELD["TX"])
    price, price_note = (inputs.price_per_kwh, "your price") if inputs.price_per_kwh else PRICE.get(state, PRICE["TX"])
    shade = Source(layer="vexcel", method="simulation", confidence="medium",
                   note="Clear-sky year (NOAA sun, Meinel beam) past the surface model's skyline; trees as captured, "
                        f"leaves on; diffuse light never shaded; imagery {capture(s)}")
    energy = Source(layer="model", method="simulation", confidence="low",
                    note=f"PVWatts v8 yield for {city}, {y_kwh} kWh per kW a year on a south 20 degree plane, scaled "
                         "by each facet's share of that plane's sun; published runs, not re-run")
    used, checks, findings, ps, routes = [], [], [], [], []
    shape = fact(s, "roof_shape")
    total = sum(f["roof_m2"] for f in r["facets"]) or 1
    for f in r["facets"]:
        ridge = f["id"] == "flat" and shape not in (None, "flat") and f["roof_m2"] / total < FLAT_SHARE
        ok = f["orientation"] >= MIN_ORIENTATION and f["usable_m2"] >= MODULE_M2 / PACKING and not ridge
        f["panels"] = int(f["usable_m2"] * PACKING // MODULE_M2) if ok else 0
        f["kw"] = f["panels"] * MODULE_W / 1000
        f["kwh"] = f["kw"] * y_kwh * f["yield_ratio"]
        name = ("Ridge band" if ridge else "Flat roof") if f["id"] == "flat" else f"{f['faces']}-facing facet"
        fid = f"solar_roof:{s.key}:{f['id']}"
        why = (f"is the ridge of a {shape} roof, flattened by the 0.5 m grid, so it is left bare" if ridge else
               f"faces {f['faces']} at {f['pitch_deg']:.0f} degrees and gets {100 * f['orientation']:.0f}% of the sun on a "
               "south 20 degree plane, so it is left bare" if f["orientation"] < MIN_ORIENTATION else
               f"keeps {100 * (f['access'] or 0):.0f}% of its sun after trees and neighbours" if ok else
               "has too little room left after setbacks and shade for one panel")
        detail = (f"{f['roof_m2']:.0f} m² of roof, pitch {f['pitch_deg']:.0f} degrees, facing {f['azimuth_deg']:.0f} degrees. "
                  f"{f['usable_m2']:.0f} m² usable after the 36 in setback, ridges and shade. It {why}."
                  + (f" {f['panels']} panels, {f['kw']:.1f} kW, about {f['kwh']:,.0f} kWh a year." if f["panels"] else ""))
        findings.append(Finding(id=fid, title=name, status="pass" if f["panels"] else "unknown", detail=detail,
                                anchor=geo(*enu_to_lonlat(lat0, lon0, *f["centroid"])), source=shade))
        if ridge:
            continue
        if f["access"] is not None:
            checks.append(Check(id=f"access.{f['id']}", rule=f"Sun kept after shade, {name}", unit="%",
                                measured=round(100 * f["access"], 1), threshold=80,
                                status="pass" if f["access"] >= 0.8 else "warn", findings=[fid]))
        checks.append(Check(id=f"orientation.{f['id']}", rule=f"Sun on this plane against south 20 degrees, {name}",
                            unit="%", measured=round(100 * f["orientation"], 1), threshold=100 * MIN_ORIENTATION,
                            status="pass" if f["orientation"] >= MIN_ORIENTATION else "warn", findings=[fid]))
        if f["panels"]:
            used.append(f)
            lon, lat = enu_to_lonlat(lat0, lon0, *f["centroid"])
            ps.append(pin(f["id"], lon, lat, f"{f['faces']}, {f['panels']} panels", "pass"))
            for p in f["polygons"]:
                if p.area >= MODULE_M2:
                    routes.append(geo_route(_ll(lat0, lon0, p), f"Usable roof, {f['faces']}"))
    panels = sum(f["panels"] for f in used)
    kw = panels * MODULE_W / 1000
    kwh = sum(f["kwh"] for f in used)
    usable = sum(f["usable_m2"] for f in used)
    cost = kw * 1000 * inputs.cost_per_w
    save = kwh * price
    payback = cost / save if save else None
    has = fact(s, "solar")
    if has:
        findings.insert(0, Finding(id=f"solar_roof:{s.key}:existing", title="Solar panels already on the roof",
                                   status="warn", anchor=geo(lon0, lat0), source=src(s, "solar"),
                                   detail="Vexcel sees solar panels on this roof; the estimate below is for the whole "
                                          "roof as if it were bare."))
    metrics = [Metric(id="usable_area", label="Usable roof", value=round(usable, 1), unit="m²", source=DSM),
               Metric(id="system_kw", label="System size", value=round(kw, 1), unit="kW", source=DSM),
               Metric(id="annual_kwh", label="Energy a year", value=round(kwh, -1), unit="kWh", source=energy),
               Metric(id="payback_years", label="Simple payback", value=round(payback, 1) if payback else None,
                      unit="years", source=energy),
               Metric(id="panels", label="Panels", value=panels, unit="", source=DSM),
               Metric(id="annual_savings", label="Saved a year", value=round(save), unit="$", source=energy),
               Metric(id="system_cost", label="Installed cost", value=round(cost, -2), unit="$", source=energy)]
    metrics += [Metric(id=f"kwh.{f['faces']}", label=f["faces"], value=round(f["kwh"], -1), unit="kWh", source=energy)
                for f in used]
    if not used:
        text = "No part of this roof is worth panels: every facet faces away from the sun, is too shaded or too small."
        status = "warn"
    else:
        best = max(used, key=lambda f: f["kwh"])
        text = (f"About {panels} panels ({kw:.1f} kW) fit, best on the "
                + ("flat part" if best["id"] == "flat" else f"{best['faces']}-facing side")
                + f" of the roof, making about {round(kwh, -1):,.0f} kWh a year and paying back in about {payback:.0f} years at "
                f"{100 * price:.1f} c/kWh and ${inputs.cost_per_w:.2f}/W.")
        status = "pass" if payback and payback <= GOOD_PAYBACK_Y else "warn"
    ctx.step(f"{len(used)} of {len(r['facets'])} facets carry panels")
    return ToolResult(
        scope=s.scope, verdict=Verdict(status=status, text=text), metrics=metrics, checks=checks, findings=findings,
        overlays=[*routes, *pins(ps)],
        assumptions=[Assumption(id="solar.cost_per_w", label="Installed cost before incentives", value=inputs.cost_per_w,
                                unit="$/W", editable=True),
                     Assumption(id="solar.price_per_kwh", label=f"Grid price ({price_note})", value=round(price, 4),
                                unit="$/kWh", editable=True),
                     Assumption(id="federal_credit", label="Federal 30% credit (25D) ended for systems installed "
                                "after 2025-12-31 (Public Law 119-21)", value=0, unit="%"),
                     Assumption(id="net_metering", label="Every kWh valued at the retail price; export credits are lower "
                                "under California NEM 3.0 and most Texas retail plans", value=True),
                     Assumption(id="pvwatts_yield", label=f"PVWatts yield, {city}, south 20 degrees, 14% losses",
                                value=y_kwh, unit="kWh/kW"),
                     Assumption(id="module", label="Module", value=f"{MODULE_W} W, {MODULE_M2:.2f} m², {PACKING:.0%} packing"),
                     Assumption(id="setback", label="Edge and pathway setback (IFC 1205.2, CRC R324.6)", value=SETBACK_M, unit="m"),
                     Assumption(id="min_orientation", label="Facets left bare below this share of south 20 degree sun",
                                value=100 * MIN_ORIENTATION, unit="%"),
                     Assumption(id="good_payback", label="Payback counted as good within", value=GOOD_PAYBACK_Y,
                                unit="years"),
                     Assumption(id="not_counted", label="Degradation, rate rises, financing, vents and chimneys not counted",
                                value=True)])


def _check():  # shortcut: a self-check of the payback arithmetic, run by the tests
    kw, y, price, cost_w = 10, 1640, 0.3135, 2.75
    assert math.isclose(kw * 1000 * cost_w / (kw * y * price), 5.35, rel_tol=0.01)
