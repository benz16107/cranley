"""Permit history: building permits and code enforcement at and near an address, by type and year.

Los Angeles: LADBS building permits issued since 2010 (two data.lacity.org datasets) within a radius, the ones at the
address itself, and LADBS code enforcement cases (open and closed) on the same street number and name. Houston
publishes no permit list with locations; its 311 service requests near the address (dumping, nuisance lots, dangerous
buildings, drainage) are the closest public record, and they are reports, not findings.
"""
from __future__ import annotations

import re
from collections import Counter

from pydantic import BaseModel

from ...layers import lookup
from ...layers.sources import houston
from .. import (
    Check,
    Finding,
    GeoAnchor,
    Metric,
    NotApplicable,
    Pin,
    PinsOverlay,
    Place,
    Source,
    ToolResult,
    Verdict,
    field,
    tool,
)

LA = "data.lacity.org"
PERMITS = {"pi9x-tg5x": "2020 to now", "dyxf-7hc4": "2010 to 2019"}
CASES = {"u82d-eh7z": "open", "rken-a55j": "closed"}
FIELDS = "permit_nbr,primary_address,permit_type,permit_sub_type,work_desc,issue_date,valuation,status_desc,lat,lon"
CODE_WORDS = re.compile(r"nuisance|dangerous|building|junk|weed|dump|abandon|graffiti|drain|flood|code|vacant|\\bsigns?\\b", re.IGNORECASE)
STREET = re.compile(r"^\s*(\d+)\s+(?:([NSEW])\s+)?(.+?)\s+(ST|AVE|BLVD|DR|PL|WAY|RD|LN|CT|TER|CIR|PKWY|HWY|SQ|TRL)\b", re.IGNORECASE)


class Inputs(BaseModel):
    place: Place = field(source="selection.place")
    radius_m: float = field(150, ge=20, le=800, description="How far round the address to count permits or requests")


def source(note: str, confidence: str = "high") -> Source:
    return Source(layer="model", method="lookup", confidence=confidence, note=note)


def street_parts(address: str | None) -> dict | None:
    """'6801 HOLLYWOOD BLVD, LOS ANGELES' -> {stno: '6801', predir: '', stname: 'HOLLYWOOD'}."""
    m = STREET.match(address or "")
    return {"stno": m.group(1), "predir": (m.group(2) or "").upper(), "stname": m.group(3).upper()} if m else None


def at_address(row: dict, parts: dict | None, lat: float, lon: float) -> bool:
    addr = (row.get("primary_address") or "").upper()
    if parts and addr.startswith(parts["stno"] + " ") and parts["stname"] in addr:
        return True
    try:
        return lookup.metres(lat, lon, float(row["lat"]), float(row["lon"])) <= 15
    except (KeyError, TypeError, ValueError):
        return False


def _la(ctx, site, inputs) -> ToolResult:
    lat, lon, r = site.lat, site.lon, inputs.radius_m
    rows, full = [], []
    for ds, span in PERMITS.items():
        got = lookup.socrata(LA, ds, {"$select": FIELDS, "$where": f"within_circle(geolocation, {lat:.6f}, {lon:.6f}, {r:.0f})",
                                      "$order": "issue_date DESC", "$limit": 1000})
        rows += got
        full += [span] if len(got) >= 1000 else []
        ctx.step(f"{len(got)} LADBS permits within {r:.0f} m, issued {span}")
    parts = street_parts(site.address)
    cases = []
    if parts:
        where = f"stno='{parts['stno']}' AND stname='{parts['stname'].replace(chr(39), '')}'"
        for ds, state in CASES.items():
            for c in lookup.socrata(LA, ds, {"$where": where, "$limit": 200}):
                if not parts["predir"] or (c.get("predir") or "").upper() in ("", parts["predir"]):
                    cases.append({**c, "state": state})
        ctx.step(f"{len(cases)} code enforcement cases on {parts['stno']} {parts['stname']}")
    here = [x for x in rows if at_address(x, parts, lat, lon)]
    src = source(f"LADBS building permits on data.lacity.org ({', '.join(PERMITS)}), within {r:.0f} m")
    csrc = source("LADBS code enforcement cases on data.lacity.org (u82d-eh7z open, rken-a55j closed), matched on street number and name", "medium")
    anchor = GeoAnchor(geo=(lon, lat))
    years = Counter((x.get("issue_date") or "")[:4] for x in rows if x.get("issue_date"))
    kinds = Counter(x.get("permit_type") or "Other" for x in rows)
    metrics = [Metric(id="permits_here", label="Permits at the address", value=len(here), unit="", source=src),
               Metric(id="permits_near", label=f"Permits within {r:.0f} m", value=len(rows), unit="", source=src),
               Metric(id="cases_here", label="Code enforcement cases", value=len(cases), unit="", source=csrc),
               Metric(id="new_buildings_near", label="New-building permits nearby", value=sum(k.startswith("Bldg-New") for k in
                                                                                             (x.get("permit_type") or "" for x in rows)), unit="", source=src)]
    metrics += [Metric(id=f"year.{y}", label=y, value=n, unit="permits", source=src) for y, n in sorted(years.items())]
    checks = [Check(id=f"type.{k}", rule=f"Permits nearby: {k}", measured=n, threshold=None, unit="permits", status="unknown")
              for k, n in kinds.most_common(8)]
    findings = []
    for x in here[:15]:
        val = x.get("valuation")
        findings.append(Finding(id=f"permit_history:{site.key}:{x.get('permit_nbr')}", title=f"{x.get('permit_type') or 'Permit'} at the address",
                                status="unknown", anchor=anchor, source=src,
                                detail=f"{(x.get('issue_date') or '')[:10]}, {x.get('permit_sub_type') or ''}; {(x.get('work_desc') or '')[:220]}"
                                       + (f" Valuation ${float(val):,.0f}." if val else "") + (f" {x['status_desc']}." if x.get("status_desc") else "")))
    for c in cases[:15]:
        findings.append(Finding(id=f"permit_history:{site.key}:case.{c.get('apno')}", title=f"Code enforcement case, {c['state']}",
                                status="warn" if c["state"] == "open" else "unknown", anchor=anchor, source=csrc,
                                detail=f"Case {c.get('apno')}, type {c.get('aptype') or 'not given'}, opened {(c.get('adddttm') or '')[:10]}"
                                       + (f", closed {c['resdttm'][:10]}" if c.get("resdttm") else "") + "."))
    pins = [Pin(id=f"permit.{x.get('permit_nbr')}", anchor=GeoAnchor(geo=(float(x["lon"]), float(x["lat"]))),
                label=f"{(x.get('issue_date') or '')[:4]} {x.get('permit_type') or ''}", status="unknown")
            for x in rows[:40] if x.get("lat") and x.get("lon")]
    open_cases = sum(c["state"] == "open" for c in cases)
    text = (f"{len(here)} permit{'s' if len(here) != 1 else ''} at the address and {len(rows)} within {r:.0f} m since 2010; "
            f"{open_cases} open and {len(cases) - open_cases} closed code enforcement case{'s' if len(cases) != 1 else ''}.")
    if not parts:
        text += " The address has no street number and name, so code cases were not looked up."
    if full:
        text += f" Only the latest 1,000 permits were read for {' and '.join(full)}; use a smaller radius for a full count."
    return ToolResult(scope=site.scope(), verdict=Verdict(status="warn" if open_cases else "pass", text=text), metrics=metrics,
                      checks=checks, findings=findings, overlays=[PinsOverlay(pins=pins)] if pins else [])


def _houston(ctx, site, inputs) -> ToolResult:
    lat, lon, r = site.lat, site.lon, inputs.radius_m
    rows = [x["properties"] for x in lookup.arcgis_at(houston.SR311, lon, lat, "CASE_NUMBER,CASE_TYPE,DEPARTMENT,STATUS,CREATED_ON,ADDRESS",
                                                       radius_m=r, geometry=True, limit=1000, ttl_s=3600)]
    ctx.step(f"{len(rows)} recent 311 requests within {r:.0f} m")
    src = source("City of Houston 311 recent service requests (mycity2.houstontx.gov)", "medium")
    kinds = Counter(x.get("CASE_TYPE") or "Other" for x in rows)
    code = [x for x in rows if CODE_WORDS.search(x.get("CASE_TYPE") or "")]
    anchor = GeoAnchor(geo=(lon, lat))
    findings = [Finding(id=f"permit_history:{site.key}:no_permits", title="Houston permits are not published by location",
                        status="unknown", anchor=anchor, source=source("City of Houston", "high"),
                        detail="The Houston Permitting Center's own search (by address or project number) holds the permit "
                               "history; the city publishes no permit list with locations to read here.")]
    for x in sorted(code, key=lambda x: -(x.get("CREATED_ON") or 0))[:15]:
        findings.append(Finding(id=f"permit_history:{site.key}:311.{x.get('CASE_NUMBER')}", title=f"311: {x.get('CASE_TYPE')}",
                                status="warn" if (x.get("STATUS") or "").lower() not in ("closed", "resolved") else "unknown",
                                anchor=anchor, source=src,
                                detail=f"Opened {lookup.day(x.get('CREATED_ON'))}, {x.get('STATUS') or 'status not given'}, "
                                       f"{(x.get('ADDRESS') or '').title()} ({x.get('DEPARTMENT') or ''})."))
    metrics = [Metric(id="requests_near", label=f"311 requests within {r:.0f} m", value=len(rows), unit="", source=src),
               Metric(id="code_requests_near", label="About property condition", value=len(code), unit="", source=src)]
    checks = [Check(id=f"type.{k}", rule=f"311 requests: {k}", measured=n, threshold=None, unit="requests", status="unknown")
              for k, n in kinds.most_common(8)]
    text = (f"Houston publishes no permit locations; {len(rows)} recent 311 requests within {r:.0f} m, {len(code)} about "
            "property condition, dumping or drainage.")
    return ToolResult(scope=site.scope(), verdict=Verdict(status="unknown", text=text), metrics=metrics, checks=checks,
                      findings=findings)


@tool(id="permit_history", title="Permit history", icon="file-check",
      summary="What was permitted at and near an address, by type and year, and any code enforcement cases (Los Angeles); "
              "recent 311 reports nearby in Houston.",
      model_description="Building permits since 2010 at and within a radius of a Los Angeles address (LADBS open data), "
                        "counted by year and type, with the permits at the address itself and LADBS code enforcement "
                        "cases on that street number. In Houston, which publishes no permit locations, recent 311 "
                        "service requests nearby. Use for 'what was built or permitted here' and 'any violations'.",
      requires=[{"layer": "public.permits"}], blocks=["VerdictHeader", "MetricRow", "MiniChart", "CheckList", "StepLog"],
      overlays=["pins"], examples=["What was permitted here?", "Any code violations at this address?", "Is the block being redeveloped?"])
def run(ctx, inputs: Inputs) -> ToolResult:
    site = lookup.locate(ctx, inputs.place)
    if site.lat is None:
        raise NotApplicable("This place has no location, so there is nothing to look up round it.")
    ctx.step(f"Found {site.address or site.key} ({site.located_by})")
    city = lookup.city_at(site.lon, site.lat)
    if city == "la":
        return _la(ctx, site, inputs)
    if city == "hou":
        return _houston(ctx, site, inputs)
    raise NotApplicable("Permit history is read for Los Angeles and Houston only.")
