"""Measure search: find homes by what is measured inside them (door widths on the way to the bathroom, turning
circles, free wall lengths, floors...), over the measures table (table.py). Listing sites search by bedrooms and
price; this searches by the geometry of about two thousand scans."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .. import Action, Check, Finding, Metric, ScanScope, Source, ToolResult, Verdict, field, tool
from ..types import GeoAnchor, ScansScope, Strict
from . import table

Measure = Literal[tuple(table.FIELDS)]


class Criterion(Strict):
    measure: Measure = Field(description="; ".join(f"{k}: {v[0]}{' (' + v[1] + ')' if v[1] else ''}"
                                                   for k, v in table.FIELDS.items()))
    op: Literal[">=", "<=", ">", "<", "==", "!="] = ">="
    value: float | str = Field(description="Threshold; flags are 1 or 0")


class Inputs(BaseModel):
    criteria: list[Criterion] = field(ask="What must the home have? For example: doors to the bathroom at least "
                                          "0.81 m, a bedroom wall of at least 2.2 m, one floor.",
                                      description="Every criterion must hold")
    city: str | None = field(None, description="Houston or Los Angeles")
    kind: Literal["house", "apartment_unit"] | None = field(None, description="House or apartment")
    sort: Measure | None = field(None, description="Rank by this measure, highest first; default by margin")
    limit: int = field(20, ge=1, le=100, description="Rows to return")


SRC = Source(layer="matterport", method="geometry", confidence="medium",
             note="Measures table built from the wall graph of each scan; empty rooms, wall openings less 5 cm")


@tool(id="measure_search", title="Measure search", icon="search",
      summary="Finds homes by what is measured inside them: door widths on the way to the bathroom, turning space, "
              "wall lengths, floors, steps. No listing site can search this.",
      model_description="Search about two thousand Houston and Los Angeles homes by measured facts. Criteria are "
                        "(measure, op, value) and must all hold; returns the matching scans ranked by how comfortably "
                        "they pass, with each measured value and why it passed. Key measures: bath_route_door "
                        "(narrowest door from the entrance to the best bathroom), bed_route_door_min, bath_turn, "
                        "bed_wall, floors, step_free_bath, wheelchair_bath, ceiling_median, glazing_ratio.",
      personas=["wheelchair_user", "older_adult_family", "furniture_mover", "renter_listing"],
      requires=[{"layer": "threshold.measures"}],
      blocks=["VerdictHeader", "MetricRow", "RankedTable", "CheckList", "EvidenceStrip", "StepLog", "ActionBar"],
      overlays=[],
      examples=["Homes where a wheelchair can reach a bathroom through 0.81 m doors, on one floor",
                "Apartments with a bedroom wall of at least 2.2 m and a 1.5 m turning circle in the bathroom"])
def run(ctx, inputs: Inputs) -> ToolResult:
    if not table.DB.exists():
        return ToolResult(scope=ScansScope(sids=[]), verdict=Verdict(status="unknown", text=(
            "The measures table has not been built yet.")))
    crit = [c.model_dump() for c in inputs.criteria]
    res = table.search(crit, city=inputs.city, kind=inputs.kind, sort=inputs.sort, limit=inputs.limit)
    ctx.step(f"Searched {res['pool']} scans; {res['answerable']} can answer every criterion; {res['matches']} match")
    rows = res["rows"]
    sids = [r["sid"] for r in rows]
    checks, findings = [], []
    for i, r in enumerate(rows, 1):
        fid = f"measure_search:{r['sid']}:match"
        place = ", ".join(x for x in (r["kind"].replace("_", " ") if r["kind"] else None, r["city"]) if x)
        checks.append(Check(id=f"rank.{i}", rule=f"#{i} {r['name']} ({place}): " + "; ".join(r["why"]),
                            measured=r["score"], threshold=None, unit="", status="pass", findings=[fid]))
        findings.append(Finding(id=fid, title=f"Match {i}: {r['name']}", status="pass", detail="; ".join(r["why"]),
                                anchor=GeoAnchor(geo=(r["lon"], r["lat"])) if r["lat"] is not None else None,
                                source=SRC))
    share = res["answerable"] / res["pool"] if res["pool"] else 0
    built = res["built"]
    text = (f"{res['matches']} of {res['answerable']} homes that can be measured meet every criterion."
            if res["matches"] else f"No home among the {res['answerable']} that can be measured meets every criterion.")
    if share < 0.6:
        text += " Many scans have no wall graph and cannot answer."
    return ToolResult(
        scope=ScansScope(sids=sids) if len(sids) != 1 else ScanScope(sid=sids[0]),
        verdict=Verdict(status="pass" if rows else "warn", text=text), checks=checks, findings=findings,
        metrics=[Metric(id="matches", label="Homes that match", value=res["matches"], unit="", source=SRC),
                 Metric(id="answerable", label="Homes that can answer", value=res["answerable"], unit="", source=SRC),
                 Metric(id="searched", label="Homes searched", value=res["pool"], unit="", source=SRC),
                 Metric(id="table_scans", label="Scans in the table", value=built.get("scans"), unit="", source=SRC)],
        actions=[Action(id=f"route.{s}", label=f"Check the route in {r['name']}", tool="step_free_route",
                        inputs={"scan": s}) for s, r in list(zip(sids, rows))[:3]])
