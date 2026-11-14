"""City search: houses whose garage fits `count` of a vehicle. The measures table's garage columns pick the
candidates in SQL (the measure_search pattern); then every candidate's plan is re-parked with the full geometry,
so a garage with a column in the way or a door off to one side drops out."""
from __future__ import annotations

from .. import Assumption, Check, Finding, Metric, Source, ToolResult, Verdict
from ..types import GeoAnchor, ScansScope
from . import geom
from .park import analyse

SRC = Source(layer="matterport", method="geometry", confidence="medium",
             note="Measures table garage columns, then each candidate re-parked in its own wall graph (empty rooms)")
RANK = {"pass": 0, "warn": 1}


def search(ctx, inputs, d, base: list) -> ToolResult:
    from ...facts.load import cached_plan
    from ..measure_search import table
    n = inputs.count or 2
    city = None if inputs.search_city in (None, "any") else inputs.search_city
    name = d.label.split(",")[0].split(" (")[0]
    crit = [{"measure": "garage_width", "op": ">=", "value": round(n * d.width + (n + 1) * geom.SQUEEZE_M - 0.05, 2)},
            {"measure": "garage_depth", "op": ">=",
             "value": round(d.length + geom.REAR_TIGHT_M + geom.FRONT_TIGHT_M - 0.05, 2)}]
    if not table.DB.exists():
        return ToolResult(scope=ScansScope(sids=[]), verdict=Verdict(status="unknown", text=(
            "The measures table has not been built yet.")))
    res = table.search(crit, city=city, kind="house", limit=1000, path=table.DB)  # the garage columns live in SQLite
    ctx.step(f"Measures table: {res['answerable']} of {res['pool']} houses have a measured garage; "
             f"{res['matches']} are wide and deep enough on paper")
    hits = []
    for row in res["rows"]:
        plan = cached_plan(row["sid"])
        gs = geom.find_garages(plan) if plan else []
        a = analyse(plan, gs[0], d, n) if gs else None
        if a is None or a["status"] == "fail":
            continue
        dh, measured = a["door_height"], a["door_height_measured"]
        if measured and dh < d.height + geom.HEIGHT_TIGHT_M:
            continue
        sides = [x for c in a["clear"] for x in (c.get("left"), c.get("right")) if x is not None]
        hits.append({**row, "status": a["status"], "side": min(sides) if sides else None, "door": bool(a["doors"]),
                     "width": a["width"], "depth": a["depth"], "fits": a["fits"], "tight": a["tight"]})
    # a garage whose door the scan did not record is at best "check the door": rank it with the tight ones
    hits.sort(key=lambda h: (RANK[h["status"] if h["door"] else "warn"], not h["door"], -(h["side"] or 0)))
    ctx.step(f"Re-parked {n} x {name} in each candidate's plan: {len(hits)} fit "
             f"({sum(h['status'] == 'pass' and h['door'] for h in hits)} with doors open)")
    shown = hits[:inputs.limit]
    checks, findings = [], []
    for i, h in enumerate(shown, 1):
        fid = f"garage_fit:{h['sid']}:search"
        why = (f"{'doors open' if h['status'] == 'pass' else 'tight'}; garage {h['width']:.2f} x {h['depth']:.2f} m; "
               f"least room beside a vehicle {h['side']:.2f} m" + ("" if h["door"] else "; garage door not in the scan"))
        checks.append(Check(id=f"rank.{i}", rule=f"#{i} {h['name'] or h['sid']} ({h['city']}): {why}",
                            measured=round(h["side"], 3) if h["side"] is not None else None, threshold=None, unit="m",
                            status=h["status"] if h["door"] else "warn", findings=[fid]))
        findings.append(Finding(id=fid, title=f"Match {i}: {h['name'] or h['sid']}", status=h["status"], detail=why,
                                anchor=GeoAnchor(geo=(h["lon"], h["lat"])) if h.get("lat") is not None else None,
                                source=SRC))
    open_ = sum(h["status"] == "pass" and h["door"] for h in hits)
    nodoor = sum(not h["door"] for h in hits)
    where = city or "Houston and Los Angeles"
    many = f"{'two' if n == 2 else n} {name}s" if n > 1 else f"a {name}"
    text = (f"{len(hits)} scanned houses in {where} have a garage that fits {many}: {open_} with room to open the "
            f"doors, {len(hits) - open_ - nodoor} tight, and {nodoor} where the floor fits but the scan did not record "
            "the garage door." if hits else
            f"No scanned house in {where} has a garage that fits {many}.")
    text += f" {res['answerable']} of {res['pool']} houses have a garage the scan could measure."
    cells = [Metric(id=f"m{i}/{k}", label=h["name"] or h["sid"], unit="m", value=round(v, 2) if v is not None else None,
                    source=SRC)
             for i, h in enumerate(shown) for k, v in (("side", h["side"]), ("width", h["width"]), ("depth", h["depth"]))]
    return ToolResult(
        scope=ScansScope(sids=[h["sid"] for h in shown]), verdict=Verdict(status="pass" if hits else "warn", text=text),
        checks=checks, findings=findings, assumptions=base + [Assumption(id="search.sql", label="Candidates by SQL",
                                                                         value="; ".join(f"{c['measure']} {c['op']} {c['value']}" for c in crit))],
        metrics=[Metric(id="matches", label="Houses whose garage fits", value=len(hits), unit="", source=SRC),
                 Metric(id="doors_open", label="With room to open the doors", value=open_, unit="", source=SRC),
                 Metric(id="answerable", label="Houses with a measured garage", value=res["answerable"], unit="", source=SRC),
                 Metric(id="searched", label="Houses searched", value=res["pool"], unit="", source=SRC), *cells])
