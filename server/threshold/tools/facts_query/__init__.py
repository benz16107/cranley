"""Facts query: the investigator answers an analytic question the fixed tools do not cover with one read-only SQL
query over the facts database. The SQL and every returned number are the evidence; the model chooses the query,
the database computes the values."""
from __future__ import annotations

from pydantic import BaseModel

from .. import Check, Metric, Source, ToolError, ToolResult, Verdict, field, tool
from ..types import ScansScope

SRC = Source(layer="matterport", method="lookup", confidence="medium",
             note="Read-only SQL over the facts database (role threshold_reader); see the query in the steps")


def _doc() -> str:
    from ...facts.ask import SCHEMA_DOC
    return SCHEMA_DOC


class Inputs(BaseModel):
    question: str = field(description="The question in plain words, shown with the answer")
    sql: str = field(description="One PostgreSQL SELECT (or WITH ... SELECT) over schema threshold. Aggregate in SQL; "
                                 "at most 200 rows come back. " + _doc())


@tool(id="facts_query", title="Ask the facts database", icon="database",
      summary="Answers questions across every scanned building that no fixed tool covers, with the SQL shown.",
      model_description="Run one read-only SQL query over the building facts database (Postgres with TimescaleDB, "
                        "PostGIS and pgvector) to answer an analytic question across many buildings: comparisons by "
                        "property type, zip or city, distributions, record-versus-measured disagreements, flood "
                        "exposure, usage. Write the SQL yourself from the schema in the `sql` input's description. "
                        "Returns the rows (each as a check, first numeric column as the value) and the SQL. Prefer "
                        "measure_search, city_census or similar_rooms when they fit.",
      personas=["costar_research_lead", "costar_researcher", "commercial_underwriter", "insurance_underwriter"],
      requires=[{"layer": "threshold.facts"}],
      blocks=["VerdictHeader", "CheckList", "StepLog"],
      examples=["Which property type has the worst listed-versus-measured area gap?",
                "How many Houston houses take water in more than half their rooms at 0.5 m?"])
def run(ctx, inputs: Inputs) -> ToolResult:
    from ...facts import ask, db
    if not db.available():
        raise ToolError("The facts database is not configured (TIGER_DATABASE_URL)")
    try:
        res = ask.run(inputs.sql)
    except ValueError as e:
        raise ToolError(f"Query refused: {e}") from None
    ctx.step(f"SQL as {res['role']} ({res['ms']} ms): {res['sql']}")
    cols = res["columns"]
    num = next((i for i, c in enumerate(cols) if any(isinstance(r[i], (int, float)) and not isinstance(r[i], bool)
                                                       for r in res["rows"])), None)
    checks = [Check(id=f"row.{i}", rule="; ".join(f"{c} = {v}" for c, v in zip(cols, r)),
                    measured=float(r[num]) if num is not None and isinstance(r[num], (int, float)) else None,
                    threshold=None, unit=cols[num] if num is not None else "", status="pass")
              for i, r in enumerate(res["rows"][:50])]
    sids = [r[cols.index("sid")] for r in res["rows"] if isinstance(r[cols.index("sid")], str)][:50] \
        if "sid" in cols else []
    text = f"{inputs.question.rstrip('?')}: {res['row_count']} rows" + (" (first 200 shown)" if res["truncated"] else "") + "."
    return ToolResult(scope=ScansScope(sids=sids), verdict=Verdict(status="pass" if res["rows"] else "unknown", text=text),
                      metrics=[Metric(id="rows", label="Rows", value=res["row_count"], unit="", source=SRC),
                               Metric(id="ms", label="Query time", value=res["ms"], unit="ms", source=SRC)],
                      checks=checks)
