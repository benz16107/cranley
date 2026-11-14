"""Area profile: who lives around a place, from the census tract it stands in, next to its county.

American Community Survey 5-year estimates (Esri's hosted copy of the Census Bureau's tables): population and
density, median household income, median age, children and people 65 and over, households, renters, rent and home
value. The comparison is the county, because the hosted tables have no city level. A tract holds about 4,000 people,
so the profile describes the neighbourhood, not the building.
"""
from __future__ import annotations

from pydantic import BaseModel

from ...layers import lookup
from ...layers.sources import census
from .. import (
    Finding,
    GeoAnchor,
    Metric,
    NotApplicable,
    Place,
    Source,
    ToolResult,
    Verdict,
    field,
    tool,
)

FIELDS = census.FIELDS + ",B01001_001M,B19049_001M,B01002_001M"
# what each row of the profile reads, as (id, label, unit, value of a row)
ROWS = (
    ("population", "People in the tract", "", lambda a: a.get("B01001_001E")),
    ("density", "People per km²", "per km²", census.density),
    ("income", "Median household income", "USD", lambda a: a.get("B19049_001E")),
    ("age", "Median age", "years", lambda a: a.get("B01002_001E")),
    ("under18", "Under 18", "%", lambda a: a.get("B01001_calc_pctLT18E")),
    ("over65", "65 and over", "%", lambda a: a.get("B01001_calc_pctGE65E")),
    ("households", "Households", "", lambda a: a.get("B25003_001E")),
    ("renters", "Households renting", "%", census.renters),
    ("rent", "Median rent", "USD a month", lambda a: a.get("B25058_001E")),
    ("home_value", "Median home value", "USD", lambda a: a.get("B25077_001E")),
)
SAY = {"income": ("higher income", "lower income", "income"), "age": ("older", "younger", "age"),
       "density": ("denser", "less dense", "density"), "renters": ("more renters", "fewer renters", "share renting")}


class Inputs(BaseModel):
    place: Place = field(source="selection.place")


def moe_share(est, moe) -> float | None:
    return abs(moe) / est if est and moe not in (None, -555555555) else None


def source(note: str, confidence: str = "medium") -> Source:
    return Source(layer="model", method="lookup", confidence=confidence, note=note)


def amount(x, unit: str) -> str:
    return f"${x:,}" if unit == "USD" else f"{x:g}%" if unit == "%" else f"{x:,} {unit}"


def compare(key: str, tract, county) -> str:
    """'higher than the county' and the like, or '' when the two are within a tenth of each other."""
    if key not in SAY or tract is None or not county:
        return ""
    up, down, same = SAY[key]
    if abs(tract - county) / county < 0.1:
        return f"{same} about the same as the county"
    return f"{up if tract > county else down} than the county"


@tool(id="area_profile", title="Area profile", icon="users",
      summary="Who lives around a building: population, density, income, age mix and households for its census tract, "
              "next to the county.",
      model_description="Census profile of the tract around a place in Houston or Los Angeles (ACS 5-year): population, "
                        "density, median household income, median age, under 18 and 65+ shares, households, renters, "
                        "median rent and home value, each with the county value for comparison. Use for questions about "
                        "the neighbourhood's people or market, not about the building.",
      requires=[{"layer": "public.census_acs"}], blocks=["VerdictHeader", "MetricRow", "CheckList", "Note", "StepLog"],
      examples=["Who lives around here?", "Is this a family neighbourhood?", "What do people earn around this shop?"])
def run(ctx, inputs: Inputs) -> ToolResult:
    site = lookup.locate(ctx, inputs.place)
    if site.lat is None:
        raise NotApplicable("This place has no location, so there is no census tract to read.")
    ctx.step(f"Found {site.address or site.key} ({site.located_by})")
    tracts = lookup.arcgis_at(census.TRACT, site.lon, site.lat, FIELDS)
    if not tracts:
        raise NotApplicable("No census tract covers this point (it may be on water or outside the US).")
    t = tracts[0]["properties"]
    counties = lookup.arcgis_at(census.COUNTY, site.lon, site.lat, "*")
    c = counties[0]["properties"] if counties else {}
    edited = lookup.service_date(census.TRACT)
    ctx.step(f"Read {t.get('NAME')} and {c.get('NAME') or 'its county'} from the ACS tables")
    county = c.get("NAME") or "the county"
    rel = moe_share(t.get("B19049_001E"), t.get("B19049_001M"))
    conf = "low" if (rel or 0) > 0.3 or (t.get("B01001_001E") or 0) < 1500 else "medium"
    note = (f"ACS 5-year estimates, {t.get('NAME')} ({t.get('GEOID')}), {t.get('County') or county}; Esri's copy "
            f"{'updated ' + edited if edited else 'of the latest release'}")
    src, csrc = source(note, conf), source(f"ACS 5-year estimates, {county}", "high")
    metrics, findings, said = [], [], []
    for key, label, unit, value in ROWS:
        v, cv = value(t), value(c) if c else None
        if v is None:
            continue
        metrics.append(Metric(id=key, label=label, value=v, unit=unit, source=src))
        if cv is not None:
            metrics.append(Metric(id=f"county.{key}", label=f"{label}, {county}", value=cv, unit=unit, source=csrc))
        words = compare(key, v, cv)
        if words:
            said.append(words)
            findings.append(Finding(id=f"area_profile:{site.key}:{key}", title=words[0].upper() + words[1:], status="unknown",
                                    detail=f"{label}: {amount(v, unit)} in the tract, {amount(cv, unit)} in {county}.",
                                    anchor=GeoAnchor(geo=(site.lon, site.lat)), source=src))
    moe = t.get("B19049_001M")
    if moe and moe > 0 and t.get("B19049_001E"):
        findings.append(Finding(id=f"area_profile:{site.key}:margin", title="Survey margin of error", status="unknown",
                                detail=f"The tract's median household income is ${t['B19049_001E']:,} give or take ${moe:,} "
                                       "(90% margin of error). Small differences from the county may not be real.",
                                anchor=GeoAnchor(geo=(site.lon, site.lat)), source=src))
    text = f"{t.get('NAME')}, {t.get('County') or county}: " + ("; ".join(said[:3]) if said else "census profile read") + "."
    return ToolResult(scope=site.scope(), verdict=Verdict(status="pass" if metrics else "unknown", text=text),
                      metrics=metrics, findings=findings)
