"""City census: rollups across every building the facts database holds, by zip code, city, property type or
building. Reads the `fact_daily` continuous aggregate, so a building the agent measured a moment ago is counted."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from .. import Check, Metric, Source, ToolError, ToolResult, Verdict, field, tool
from ..types import ScansScope

SRC = Source(layer="matterport", method="geometry", confidence="medium",
             note="Latest recorded value per scan, from the facts database's continuous aggregate (fact_daily)")


class Inputs(BaseModel):
    preset: Literal["wheelchair_homes", "area_gap", "smoke_alarms", "step_free_bath", "bath_route_door"] | None = field(
        None, description="wheelchair_homes: share of homes a wheelchair can reach a bathroom in, by zip; area_gap: "
                          "measured over listed area minus one, median by property type; smoke_alarms: share of scans "
                          "with a smoke alarm seen, by building; step_free_bath; bath_route_door (median door width)")
    measure: str | None = field(None, description="Any recorded field instead of a preset (see /api/facts/fields), "
                                                "e.g. bath_turn, glazing_ratio, vs_record.beds")
    by: Literal["zip", "city", "property_type", "kind", "building"] | None = field(None, description="Group by")
    stat: Literal["share", "median", "mean"] | None = field(None, description="share: fraction above zero")
    city: str | None = field(None, description="Houston or Los Angeles")
    kind: Literal["house", "apartment_unit", "office", "amenity", "warehouse", "retail", "other"] | None = None
    min_scans: int = field(3, ge=1, le=100, description="Leave out groups with fewer scans")


@tool(id="city_census", title="City census", icon="chart",
      summary="Rolls up what has been measured across the city: share of homes a wheelchair can live in by zip code, "
              "listed-versus-measured area by property type, smoke alarm coverage by building.",
      model_description="Aggregate one measured field across all buildings in the facts database, grouped by zip, city, "
                        "property type, kind or building. Use for questions about many buildings at once ('which zip "
                        "codes have the most wheelchair-accessible homes', 'how far off are listed areas for "
                        "apartments'). Returns one check per group with the scans counted, share, mean and median, "
                        "and the SQL it ran. Each scan counts once, at its latest value.",
      personas=["costar_research_lead", "costar_researcher", "commercial_underwriter", "insurance_underwriter",
                "wheelchair_home_search", "apartment_manager"],
      requires=[{"layer": "threshold.facts"}],
      blocks=["VerdictHeader", "MetricRow", "CheckList", "MiniChart", "StepLog"],
      examples=["Which Houston zip codes have the highest share of homes a wheelchair can reach a bathroom in?",
                "Median gap between listed and measured area by property type"])
def run(ctx, inputs: Inputs) -> ToolResult:
    from ...facts import census as cs
    from ...facts import db
    if not db.available():
        raise ToolError("The facts database is not configured (TIGER_DATABASE_URL)")
    if not inputs.preset and not inputs.measure:
        raise ToolError("Give a preset or a field")
    kw = {k: v for k, v in {"by": inputs.by, "stat": inputs.stat}.items() if v}
    try:
        res = cs.preset(inputs.preset, city=inputs.city, kind=inputs.kind, min_scans=inputs.min_scans, **kw) \
            if inputs.preset else cs.census(inputs.measure, city=inputs.city, kind=inputs.kind,
                                            min_scans=inputs.min_scans, **{"by": "zip", "stat": "share", **kw})
    except ValueError as e:
        raise ToolError(str(e)) from None
    ctx.step(f"SQL on {res['source']} ({res['ms']} ms): {res['sql']}")
    rows, stat = res["rows"], res["stat"]
    label = res.get("label") or res["field"]
    counted = sum(r["scans"] for r in rows)
    checks = [Check(id=f"group.{i}", rule=f"{res['by']} {r['grp'] or 'unknown'}: {r['scans']} scans; share "
                                          f"{r['share']:.0%}, median {r['median']}, mean {r['mean']}",
                    measured=r[stat], threshold=None, unit="", status="pass")
              for i, r in enumerate(rows)]
    if not rows:
        text = (f"No group has {inputs.min_scans} or more scans with {label}. "
                f"{res['scans_with_field']} scans have this field recorded.")
    else:
        top = rows[0]
        text = (f"{label}: {len(rows)} groups by {res['by']}, {counted} scans. Highest {stat}: "
                f"{top['grp'] or 'unknown'} at {top[stat]:.2f} over {top['scans']} scans.")
    return ToolResult(scope=ScansScope(sids=[]), verdict=Verdict(status="pass" if rows else "unknown", text=text),
                      metrics=[Metric(id="groups", label="Groups", value=len(rows), unit="", source=SRC),
                               Metric(id="scans", label="Scans counted", value=counted, unit="", source=SRC),
                               Metric(id="ms", label="Query time", value=res["ms"], unit="ms", source=SRC)],
                      checks=checks)
