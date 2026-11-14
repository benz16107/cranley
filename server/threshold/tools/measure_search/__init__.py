"""Measure search: find homes by what is measured inside them (door widths on the way to the bathroom, turning
circles, free wall lengths, floors...), over the measures table (table.py). Listing sites search by bedrooms and
price; this searches by the geometry of about two thousand scans."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .. import Action, Check, Finding, Metric, NotApplicable, ScanScope, Source, ToolError, ToolResult, Verdict, field, tool
from ..types import GeoAnchor, ScansScope, Strict
from . import table

Measure = Literal[tuple(table.FIELDS)]


class Criterion(Strict):
    measure: Measure = Field(description="; ".join(f"{k}: {v[0]}{' (' + v[1] + ')' if v[1] else ''}"
                                                   for k, v in table.FIELDS.items()))
    op: Literal[">=", "<=", ">", "<", "==", "!="] = ">="
    value: float | str = Field(description="Threshold; flags are 1 or 0")


class RoomMeasure(Strict):
    measure: Literal["area", "turn_diameter", "widest_door", "narrowest_door", "windows", "glazed_area", "height"]
    op: Literal[">=", "<=", ">", "<", "==", "!="] = ">="
    value: float


class RoomCriterion(Strict):
    label: str = Field(description="Room type as the plan labels it: Kitchen, Bathroom, Bedroom, Living Room, ...")
    where: list[RoomMeasure] = Field(default_factory=list, description="Every measure must hold in one such room")


# What a person can pick in a form; each is a fixed list of criteria. Anything else goes in `criteria`.
NEEDS: dict[str, tuple[str, list[dict]]] = {
    "wheelchair": ("A wheelchair reaches a bathroom from the entrance",
                   [{"measure": "wheelchair_bath", "op": "==", "value": 1}]),
    "step_free_bath": ("No step between the entrance and a bathroom", [{"measure": "step_free_bath", "op": "==", "value": 1}]),
    "one_floor_living": ("Bedroom and bathroom on the entrance floor, no doorway steps",
                         [{"measure": "bed_bath_entry_floor", "op": "==", "value": 1},
                          {"measure": "level_changes", "op": "==", "value": 0}]),
    "king_bed": ("A king bed fits: a bedroom wall of 3 m and 0.76 m doors to every bedroom",
                 [{"measure": "bed_wall", "op": ">=", "value": 3.0}, {"measure": "bed_route_door_min", "op": ">=", "value": 0.76}]),
    "upright_piano": ("An upright piano fits: a living room wall of 3 m and a 0.85 m entrance",
                      [{"measure": "living_wall", "op": ">=", "value": 3.0}, {"measure": "entrance_width", "op": ">=", "value": 0.85}]),
}


class Inputs(BaseModel):
    need: Literal[tuple(NEEDS)] | None = field(None, ask="What must the home allow? " + "; ".join(
        f"{k}: {v[0]}" for k, v in NEEDS.items()), pref="search.need", description="A common search, picked from a list")
    criteria: list[Criterion] = field([], description="Every criterion must hold; added to the need's own criteria")
    city: str | None = field(None, description="Houston or Los Angeles")
    kind: Literal["house", "apartment_unit"] | None = field(None, description="House or apartment")
    sort: Measure | None = field(None, description="Rank by this measure, highest first; default by margin")
    limit: int = field(20, ge=1, le=100, description="Rows to return")
    near: tuple[float, float] | None = field(None, description="Point to search around, (lat, lon)")
    within_km: float | None = field(None, gt=0, le=200, description="Only scans this close to `near`")
    rooms: list[RoomCriterion] = field([], description="Rooms the home must have, each meeting its measures "
                                                       "(e.g. a Kitchen with area >= 12). Needs the facts database.")


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
      personas=["wheelchair_user", "older_adult_family", "furniture_mover", "renter_listing", "wheelchair_home_search", "robot_maker"],
      requires=[{"layer": "threshold.measures"}],
      blocks=["VerdictHeader", "MetricRow", "RankedTable", "CheckList", "EvidenceStrip", "StepLog", "ActionBar"],
      overlays=[],
      examples=["Homes where a wheelchair can reach a bathroom through 0.81 m doors, on one floor",
                "Apartments with a bedroom wall of at least 2.2 m and a 1.5 m turning circle in the bathroom"])
def run(ctx, inputs: Inputs) -> ToolResult:
    from ...facts import db as facts_db
    if not table.DB.exists() and not facts_db.available():
        return ToolResult(scope=ScansScope(sids=[]), verdict=Verdict(status="unknown", text=(
            "The measures table has not been built yet.")))
    crit = (NEEDS[inputs.need][1] if inputs.need else []) + [c.model_dump() for c in inputs.criteria]
    if not crit and not inputs.rooms:
        raise NotApplicable("Say what the home must allow: pick a need (" + ", ".join(NEEDS) + ") or give criteria.")
    try:
        res = table.search(crit, city=inputs.city, kind=inputs.kind, sort=inputs.sort, limit=inputs.limit,
                           near=inputs.near, within_m=inputs.within_km * 1000 if inputs.within_km else None,
                           rooms=[r.model_dump() for r in inputs.rooms])
    except ValueError as e:
        raise ToolError(str(e)) from None
    ctx.step(f"Searched {res['pool']} scans; {res['answerable']} can answer every criterion; {res['matches']} match")
    if res.get("sql"):
        ctx.step(f"SQL ({res['ms']} ms): {res['sql']}")
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
