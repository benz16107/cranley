"""Similar rooms: search inside buildings by meaning. Each indexed room has a vision-model description of its
panorama, embedded locally; StreamingDiskANN (pgvectorscale) finds the nearest, filtered by room type inside the
index, and measured facts (area, turning circle, city) filter in the same query. BM25 word matching
(pg_textsearch) can be blended in."""
from __future__ import annotations

from pydantic import BaseModel

from .. import (
    Check,
    Finding,
    Metric,
    RoomAnchor,
    Source,
    ToolError,
    ToolResult,
    Verdict,
    field,
    tool,
)
from ..types import Media, ScansScope

SRC = Source(layer="model", method="vision", confidence="medium",
             note="Similarity of vision-model room descriptions (embedded with bge-small); sizes are measured")


class Inputs(BaseModel):
    query: str | None = field(None, ask="Describe the room you are looking for",
                              description="e.g. 'sunlit kitchen with an island and white cabinets'")
    scan: str | None = field(None, source="selection.scan", description="With room: find rooms like this one")
    room: str | None = field(None, source="selection.room", description="Room id in `scan`")
    label: str | None = field(None, description="Room type: Kitchen, Bathroom, Bedroom, Living Room, ...")
    city: str | None = field(None, description="Houston or Los Angeles")
    min_area_m2: float | None = field(None, ge=0, unit="m2", description="Measured floor area at least")
    min_turn_m: float | None = field(None, ge=0, unit="m", description="Largest turning circle at least")
    words: float = field(0.3, ge=0, le=1, description="Weight of exact word matches (BM25) against meaning")
    limit: int = field(8, ge=1, le=30)


@tool(id="similar_rooms", title="Similar rooms", icon="search",
      summary="Finds rooms by what they look like ('a sunlit kitchen with an island'), with measured filters: "
              "over 12 m², in Houston, room for a wheelchair to turn.",
      model_description="Search a few hundred described rooms in Houston and Los Angeles by meaning, or find rooms "
                        "like a given one. Filters on room type, city and measured area and turning circle in the "
                        "same query. Returns rooms ranked by similarity, each with its description, measured area "
                        "and a panorama to look at. Descriptions come from a vision model; sizes from the floor plan.",
      personas=["renter_listing", "wheelchair_home_search", "costar_research_lead", "costar_researcher",
                "older_adult_family"],
      requires=[{"layer": "threshold.facts.rooms"}],
      blocks=["VerdictHeader", "EvidenceStrip", "CheckList", "StepLog"],
      examples=["A sunlit kitchen with an island, over 12 m², in Houston",
                "Bathrooms like this one with room to turn a wheelchair"])
def run(ctx, inputs: Inputs) -> ToolResult:
    from ...facts import db, rooms
    if not db.available():
        raise ToolError("The facts database is not configured (TIGER_DATABASE_URL)")
    try:
        res = rooms.similar(inputs.query, like=(inputs.scan, inputs.room) if inputs.scan and inputs.room else None,
                            label=inputs.label, city=inputs.city, min_area=inputs.min_area_m2,
                            min_turn=inputs.min_turn_m, words=inputs.words, limit=inputs.limit)
    except (LookupError, ValueError) as e:
        raise ToolError(str(e).strip("'\"")) from None
    ctx.step(f"Searched {res['indexed']} described rooms ({res['ms']} ms): {res['sql']}")
    rows = res["rows"]
    pano = {(r["sid"], r["room"]): p for r in rows for p in [db.rows(
        "SELECT pano FROM room_text WHERE sid = :s AND room = :r", s=r["sid"], r=r["room"])[0]["pano"]]}
    findings, checks = [], []
    for i, r in enumerate(rows, 1):
        fid = f"similar_rooms:{r['sid']}:{r['room']}"
        size = f"{r['area']:.1f} m²" if r["area"] else "area not measured"
        turn = f", turning circle {r['turn_diameter']:.2f} m" if r["turn_diameter"] else ""
        findings.append(Finding(id=fid, title=f"{i}. {r['label']} in {r['name']} ({r['city']})", status="pass",
                                detail=f"{size}{turn}. {r['description']}", anchor=RoomAnchor(sid=r["sid"], room=r["room"]),
                                source=SRC, media=[Media(kind="pano", ref=f"{r['sid']}/{pano[(r['sid'], r['room'])]}/1")]))
        checks.append(Check(id=f"rank.{i}", rule=f"#{i} {r['label']}, {r['city']}: {size}", measured=r["score"],
                            threshold=None, unit="", status="pass", findings=[fid]))
    sids = list(dict.fromkeys(r["sid"] for r in rows))
    text = (f"{len(rows)} rooms like '{res['query'][:80]}' among {res['indexed']} described rooms."
            if rows else f"No described room matches; {res['indexed']} rooms are indexed so far.")
    return ToolResult(scope=ScansScope(sids=sids), verdict=Verdict(status="pass" if rows else "unknown", text=text),
                      metrics=[Metric(id="indexed", label="Rooms indexed", value=res["indexed"], unit="", source=SRC),
                               Metric(id="ms", label="Query time", value=res["ms"], unit="ms", source=SRC)],
                      checks=checks, findings=findings)
