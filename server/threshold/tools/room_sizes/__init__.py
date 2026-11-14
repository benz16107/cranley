"""Room sizes: every room's floor area, width, depth and ceiling height, biggest first, for picking a room to use.

Width and depth are the sides of the smallest rectangle around the room's outline, so an L-shaped room reads larger
than its open floor. About 60% of rooms have no height in the scan; those take the plan's median and say so.
"""
from __future__ import annotations

import math

from pydantic import BaseModel

from ...geometry._plan import default_ceiling, indoor_rooms, polygons
from .. import Check, Metric, ScanScope, Source, ToolResult, Verdict, field, tool

GEO = Source(layer="matterport", method="geometry", confidence="high", note="Room outlines in the wall graph")
HEIGHT = Source(layer="matterport", method="geometry", confidence="medium",
                note="Matterport room heights stop near the camera's reach, about 4 m")
ASSUMED = Source(layer="matterport", method="geometry", confidence="low", note="No height in the scan; the plan's median")


class Inputs(BaseModel):
    scan: str = field(source="selection.scan", description="Scan id")
    min_area_m2: float = field(0, pref="space.min_area_m2", unit="m²", ge=0,
                               description="Flag rooms smaller than this (0: flag none)")


def _names(plan: dict) -> dict[str, str]:
    rooms = plan.get("rooms") or []
    out = {}
    for r in rooms:
        lab = r.get("label") or "Unlabelled room"
        same = [x["id"] for x in rooms if (x.get("label") or "Unlabelled room") == lab]
        out[r["id"]] = f"{lab} {same.index(r['id']) + 1}" if len(same) > 1 else lab
    return out


def sides(poly) -> tuple[float, float]:
    pts = list(poly.minimum_rotated_rectangle.exterior.coords)
    a, b = math.dist(pts[0], pts[1]), math.dist(pts[1], pts[2])
    return max(a, b), min(a, b)


@tool(id="room_sizes", title="Room sizes",
      summary="Every room's floor area, width, depth and ceiling height, biggest first.",
      model_description="Per-room floor area, width, depth and ceiling height of one scan, ranked by area, with the "
                        "largest room and the highest ceiling. For location scouts, stagers, event planners and anyone "
                        "choosing a room by size.",
      personas=["location_scout", "virtual_stager"], requires=[{"layer": "matterport.rooms"}],
      blocks=["VerdictHeader", "MetricRow", "RankedTable", "CheckList", "StepLog"],
      table=[{"metric": "area", "label": "Area, m²"}, {"metric": "width", "label": "Width, m"},
             {"metric": "depth", "label": "Depth, m"}, {"metric": "height", "label": "Ceiling, m"}],
      examples=["What's the biggest room, and how high is its ceiling?"])
def run(ctx, inputs: Inputs) -> ToolResult:
    sid = inputs.scan
    plan = ctx.plan(sid)
    polys, names, med = polygons(plan), _names(plan), default_ceiling(plan)
    rows = []
    for r in indoor_rooms(plan):
        p = polys.get(r["id"])
        if p is None:
            continue
        w, d = sides(p)
        rows.append((r, p.area, w, d, r.get("height") or med, bool(r.get("height"))))
    if not rows:
        return ToolResult(scope=ScanScope(sid=sid), verdict=Verdict(status="unknown", text="This scan has no room "
                                                                                           "outlines, so room sizes are unknown."))
    rows.sort(key=lambda x: -x[1])
    ctx.step(f"Measured {len(rows)} room outlines")
    metrics = []
    big, tall = rows[0], max(rows, key=lambda x: (x[5], x[4] or 0))
    metrics += [Metric(id="largest", label=f"Largest room ({names[big[0]['id']]})", value=round(big[1], 1), unit="m²", source=GEO),
                Metric(id="highest", label=f"Highest measured ceiling ({names[tall[0]['id']]})",
                       value=round(tall[4], 2) if tall[5] else None, unit="m", source=HEIGHT)]
    for r, area, w, d, h, measured in rows:
        n = names[r["id"]]
        metrics += [Metric(id=f"{r['id']}/area", label=n, value=round(area, 1), unit="m²", source=GEO),
                    Metric(id=f"{r['id']}/width", label=n, value=round(w, 2), unit="m", source=GEO),
                    Metric(id=f"{r['id']}/depth", label=n, value=round(d, 2), unit="m", source=GEO),
                    Metric(id=f"{r['id']}/height", label=n, value=round(h, 2) if h else None, unit="m",
                           source=HEIGHT if measured else ASSUMED)]
    checks = [Check(id=f"area:{r['id']}", rule=f"{names[r['id']]}: floor area", measured=round(a, 1),
                    threshold=inputs.min_area_m2 or None, unit="m²",
                    status="fail" if inputs.min_area_m2 and a < inputs.min_area_m2 else "pass")
              for r, a, *_ in rows]
    unmeasured = sum(not x[5] for x in rows)
    return ToolResult(scope=ScanScope(sid=sid),
                      verdict=Verdict(status="pass", text=f"{len(rows)} rooms measured; the largest is the {names[big[0]['id']]}."
                                      + (f" {unmeasured} room{' has' if unmeasured == 1 else 's have'} no ceiling height in the scan and show the plan's median."
                                         if unmeasured else "")),
                      metrics=metrics, checks=checks)
