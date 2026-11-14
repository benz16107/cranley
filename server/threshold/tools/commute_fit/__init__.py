"""Commute fit: how long employees would drive to each candidate office, from where they live (zip codes or points).

An estimate, labelled low reliability: the straight line from home to office times a road detour factor (1.3 by default),
driven at 35 km/h for the first 8 km (city streets) and 60 km/h beyond (freeway share of a longer trip), plus 6 minutes
to park and walk in. No traffic, no transit timetable. Zip codes stand for their Census ZCTA centre point (2024
Gazetteer, downloaded once into the data cache).
"""
from __future__ import annotations

import functools
import io
import statistics
import zipfile

import httpx
from pydantic import BaseModel

from ...config import CACHE
from .. import Check, Finding, Metric, Place, Source, ToolError, ToolResult, Verdict, field, tool
from ..types import ScansScope
from .._site import geo, pin, pins
from ..site_scorecard import near

GAZ_URL = "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2024_Gazetteer/2024_Gaz_zcta_national.zip"
EST = Source(layer="model", method="simulation", confidence="low",
             note="Straight line x detour factor at 35 km/h for 8 km then 60 km/h, plus 6 min to park; no traffic")
GAZ = Source(layer="model", method="lookup", confidence="medium", note="US Census 2024 ZCTA Gazetteer centre points")
CITY_KMH, FWY_KMH, CITY_KM, PARK_MIN = 35.0, 60.0, 8.0, 6.0


@functools.cache
def zips() -> dict[str, tuple[float, float]]:
    """zip -> (lat, lon) of the ZCTA's internal point."""
    d = CACHE / "census"
    txt = d / "2024_Gaz_zcta_national.txt"
    if not txt.exists():
        r = httpx.get(GAZ_URL, timeout=120, follow_redirects=True)
        r.raise_for_status()
        d.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            z.extractall(d)
    out = {}
    for line in txt.read_text().splitlines()[1:]:
        p = line.split("\t")
        if len(p) >= 7:
            out[p[0].strip()] = (float(p[5]), float(p[6]))
    return out


def minutes(straight_km: float, detour: float = 1.3) -> float:
    road = straight_km * detour
    return round(PARK_MIN + (min(road, CITY_KM) / CITY_KMH + max(road - CITY_KM, 0) / FWY_KMH) * 60, 1)


def parse_homes(items: list[str], lookup=None) -> list[dict]:
    """"77002", "77002:12" (12 people) or "-95.37,29.76" (lon,lat, optionally ":n") into [{label, lat, lon, n}]."""
    lookup = lookup or zips
    out = []
    for raw in items:
        s, _, n = raw.strip().partition(":") if raw.count(":") == 1 else (raw.strip(), "", "")
        n = int(n) if n.strip().isdigit() else 1
        if "," in s:
            lon, lat = (float(v) for v in s.split(","))
            out.append({"label": f"{lat:.3f}, {lon:.3f}", "lat": lat, "lon": lon, "n": n})
            continue
        z = s[:5]
        if z not in lookup():
            raise ToolError(f"Unknown zip code {s!r}: give a five-digit US zip or a lon,lat point.")
        lat, lon = lookup()[z]
        out.append({"label": z, "lat": lat, "lon": lon, "n": n})
    return out


def commute(homes: list[dict], lat: float, lon: float, detour: float) -> dict:
    """Per-home minutes and the head-weighted median, mean and worst."""
    per = [{**h, "min": minutes(near.km(h["lat"], h["lon"], lat, lon), detour)} for h in homes]
    flat = sorted(m for p in per for m in [p["min"]] * p["n"])
    return {"per": per, "median": statistics.median(flat), "mean": round(sum(flat) / len(flat), 1), "max": flat[-1],
            "people": len(flat)}


class Inputs(BaseModel):
    candidates: list[Place] = field(ask="Which buildings are you choosing between?", min_length=1, max_length=10,
                                    description="Candidate offices: scans, CoStar properties, addresses or points")
    employees: list[str] = field(ask="Where do your employees live? Zip codes, with a head count after a colon "
                                     "(77002:12), or lon,lat points.", pref="commute.employees", min_length=1)
    current: Place | None = field(None, description="Where the office is now, to show who gains or loses time")
    long_min: float = field(45, pref="commute.long_min", unit="min", ge=10, le=180,
                            description="A one-way commute longer than this counts as long")
    worse_min: float = field(15, pref="commute.worse_min", unit="min", ge=1, le=120,
                             description="A move that adds this much to someone's commute is flagged")
    detour: float = field(1.3, pref="commute.detour", ge=1.0, le=2.5, description="Road distance over straight-line distance")
    check_transit: bool = field(True, description="Count bus stops and rail stations near each candidate (OpenStreetMap)")


@tool(id="commute_fit", title="Commute fit", icon="clock",
      summary="Estimated drive time from where your people live to each candidate office: the median, who gets a long "
              "commute, and transit nearby.",
      model_description="For an office relocation: given employees' home zip codes (or points) and 1 to 10 candidate "
                        "buildings, estimates each person's one-way drive (straight line x detour, a low-reliability "
                        "estimate), the head-weighted median per candidate, who would commute longer than a limit or lose "
                        "time against the current office, and bus and rail stops near each candidate.",
      personas=["office_relocation", "office_tenant"],
      requires=[{"layer": "osm", "need": "optional", "fallback": "no transit count"}],
      blocks=["VerdictHeader", "MetricRow", "RankedTable", "MiniChart", "CheckList", "EvidenceStrip", "StepLog"],
      table=[{"metric": "median", "label": "Median min", "better": "lower"},
             {"metric": "long_pct", "label": "Long commutes %", "better": "lower"},
             {"metric": "max", "label": "Longest min", "better": "lower"},
             {"metric": "transit", "label": "Transit stops 800 m"}],
      examples=["Our people live in these zip codes; which office keeps commutes short?"])
def run(ctx, inputs: Inputs) -> ToolResult:
    homes = parse_homes(inputs.employees)
    ctx.step(f"Placed {sum(h['n'] for h in homes)} people at {len(homes)} home locations")
    base = None
    if inputs.current:
        s = ctx.site(inputs.current)
        base = commute(homes, s.lat, s.lon, inputs.detour) if s.lat is not None else None
    metrics, checks, findings, ps, ranked = [], [], [], [], []
    for p in inputs.candidates:
        s = ctx.site(p)
        if s.lat is None:
            findings.append(Finding(id=f"commute_fit:{s.key}:where", title="Candidate has no location", status="unknown",
                                    detail="This place carries no coordinates.", anchor=None, source=EST))
            continue
        c = commute(homes, s.lat, s.lon, inputs.detour)
        long_n = sum(h["n"] for h in c["per"] if h["min"] > inputs.long_min)
        row = {"key": s.key, "name": s.address or s.key, "c": c, "long_pct": round(100 * long_n / c["people"]), "s": s}
        if inputs.check_transit:
            try:
                t = near.transport(s.lat, s.lon)
                row["transit"] = t["bus_stops_800m"] + (1 if (t["nearest"].get("rail_transit") or {}).get("km", 9) <= 0.8 else 0)
                row["rail"] = t["nearest"].get("rail_transit")
            except Exception as e:  # noqa: BLE001  transit is extra; the drive estimate stands without it
                ctx.step(f"Transit lookup failed for {row['name']}: {str(e)[:100]}")
        ranked.append(row)
        ctx.step(f"{row['name']}: median {c['median']:.0f} min")
    if not ranked:
        raise ToolError("None of the candidates has a location.")
    ranked.sort(key=lambda r: (r["c"]["median"], r["long_pct"]))
    for i, r in enumerate(ranked):
        k, c = r["key"], r["c"]
        metrics += [Metric(id=f"{k}/median", label=r["name"], value=c["median"], unit="min", source=EST),
                    Metric(id=f"{k}/long_pct", label=r["name"], value=r["long_pct"], unit="%", source=EST),
                    Metric(id=f"{k}/max", label=r["name"], value=c["max"], unit="min", source=EST),
                    Metric(id=f"median.{k}", label=r["name"], value=c["median"], unit="min", source=EST)]
        if "transit" in r:
            metrics.append(Metric(id=f"{k}/transit", label=r["name"], value=r["transit"], unit="",
                                  source=Source(layer="model", method="lookup", confidence="medium", note=near.NOTE)))
        st = "pass" if r["long_pct"] == 0 else "warn" if r["long_pct"] <= 20 else "fail"
        checks.append(Check(id=f"{k}.long", rule=f"Share of people over {inputs.long_min:g} min, {r['name']}",
                            measured=r["long_pct"], threshold=0, unit="%", status=st, findings=[f"commute_fit:{k}:summary"]))
        longest = sorted(c["per"], key=lambda h: -h["min"])[:3]
        detail = (f"Rank {i + 1}. Median {c['median']:.0f} min, mean {c['mean']:.0f}, longest {c['max']:.0f} "
                  f"(from {', '.join(f'{h['label']} {h['min']:.0f} min' for h in longest)}).")
        worse = []
        if base:
            by = {h["label"]: h["min"] for h in base["per"]}
            worse = [h for h in c["per"] if h["min"] - by[h["label"]] >= inputs.worse_min]
            detail += (f" Against the current office (median {base['median']:.0f} min), "
                       f"{sum(h['n'] for h in worse)} people gain {inputs.worse_min:g}+ min"
                       + (f": {', '.join(h['label'] for h in worse[:6])}." if worse else "."))
        if "transit" in r:
            detail += f" {r['transit']} bus stops or stations within 800 m" + (
                f"; nearest rail station {r['rail']['name'] or 'unnamed'} at {r['rail']['km']:.1f} km." if r.get("rail") else "; no rail station within 2 km.")
        findings.append(Finding(id=f"commute_fit:{k}:summary", title=f"Commutes to {r['name']}", status=st, detail=detail,
                                anchor=geo(r["s"].lon, r["s"].lat), source=EST))
        ps.append(pin(f"cand_{i}", r["s"].lon, r["s"].lat, f"#{i + 1}", st))
    best = ranked[0]
    metrics[:0] = [Metric(id="people", label="People placed", value=ranked[0]["c"]["people"], unit="", source=GAZ),
                   Metric(id="best_median", label="Best median commute", value=best["c"]["median"], unit="min", source=EST)]
    if base:
        metrics.insert(2, Metric(id="current_median", label="Current median commute", value=base["median"], unit="min", source=EST))
    text = (f"{best['name']} gives the shortest median drive of the {len(ranked)} candidates ({best['c']['median']:.0f} min, "
            f"{best['long_pct']}% over {inputs.long_min:g} min). Drive times are straight-line estimates without traffic.")
    return ToolResult(scope=ScansScope(sids=[x for r in ranked for x in r["s"].sids][:50]),
                      verdict=Verdict(status="pass" if best["long_pct"] <= 20 else "warn", text=text),
                      metrics=metrics, checks=checks, findings=findings, overlays=pins(ps),
                      assumptions=[{"id": "commute.detour", "label": "Road detour factor", "value": inputs.detour, "editable": True},
                                   {"id": "commute.long_min", "label": "Long commute", "value": inputs.long_min, "unit": "min", "editable": True},
                                   {"id": "speeds", "label": "Speeds", "value": f"{CITY_KMH:g} km/h first {CITY_KM:g} km, then {FWY_KMH:g} km/h, +{PARK_MIN:g} min"}])
