"""Size-up quiz: the questions a company officer answers from outside a house (how many floors, which side has the
kitchen, where the bedrooms and stairs are), shown with drone or oblique views of each side, with the measured
interior as the answer key and a scoring function. Pass `answers` to score a trainee.

Findings `size_up_quiz:<sid>:q<n>` are the questions (with the outside views as media); `size_up_quiz:<sid>:a<n>`
are the answer key, which an interface keeps hidden until the reveal."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from ...geometry import to_latlon
from ...geometry._plan import polygons
from .. import (
    Action,
    Assumption,
    Check,
    Finding,
    Metric,
    RoomAnchor,
    ScanScope,
    Source,
    ToolResult,
    Verdict,
    field,
    tool,
)
from ..fire_preplan.common import BEDROOM, live_rooms
from ..fire_preplan.site import COMPASS, SIDE_NAMES, bearing, metres, side_of
from ..types import Media

KEY = Source(layer="matterport", method="geometry", confidence="high",
             note="Answer key from the scan's rooms and floors, placed on the map by its geocoordinates")
VIEWS = Source(layer="drone", method="lookup", confidence="high", note="Drone photos chosen by camera bearing and gimbal")
FULL_M, ZERO_M = 3.0, 10.0          # a marked point within 3 m scores full marks, 10 m or more scores nothing
STAIRS = ("Staircase",)


class Inputs(BaseModel):
    scan: str = field(source="selection.scan", description="Scan id of a house")
    answers: dict[str, Any] | None = field(None, description="Trainee answers to score: {question id: answer}. "
                                                             "Choice and count questions take a value; point "
                                                             "questions take a list of [lon, lat]")


# ---- scoring (pure) -----------------------------------------------------------------------------

def _points_score(marks: list, key: list) -> tuple[float, str]:
    """Greedy nearest matching of marked [lon, lat] points to true ones. Each true point scores 1 if a mark is within
    FULL_M, falling to 0 at ZERO_M; each extra mark costs half a point. Normalised to 0..1."""
    if not key:
        return (1.0, "Nothing to find, and nothing marked.") if not marks else (0.0, "Nothing was there to mark.")
    left = list(marks or [])
    got, notes = 0.0, []
    for k in key:
        if not left:
            notes.append("missed one")
            continue
        d, m = min(((metres(k[1], k[0], p[1], p[0]), p) for p in left), key=lambda x: x[0])
        left.remove(m)
        got += max(0.0, min(1.0, (ZERO_M - d) / (ZERO_M - FULL_M)))
        notes.append(f"{d:.1f} m off")
    got -= 0.5 * len(left)
    if left:
        notes.append(f"{len(left)} extra")
    return max(0.0, got / len(key)), ", ".join(notes)


def score(questions: list[dict], answers: dict) -> dict:
    """Score answers against the key. Each question is worth `points`. Returns per question and the total."""
    out, total, best = [], 0.0, 0.0
    for q in questions:
        a = (answers or {}).get(q["id"])
        if a is None:
            frac, why = 0.0, "not answered"
        elif q["kind"] == "points":
            frac, why = _points_score(a, q["answer"])
        elif q["kind"] == "count":
            diff = abs(float(a) - float(q["answer"]))
            frac, why = max(0.0, 1 - diff / max(1.0, float(q["answer"]))), f"off by {diff:g}"
        else:
            ok = str(a).upper() in {str(x).upper() for x in [q["answer"], *q.get("accept", [])]}
            frac, why = (1.0, "right") if ok else (0.0, "wrong")
        out.append({"id": q["id"], "points": round(frac * q["points"], 2), "max": q["points"], "why": why})
        total += frac * q["points"]
        best += q["points"]
    return {"questions": out, "total": round(total, 2), "max": best}


# ---- building the quiz ---------------------------------------------------------------------------

def drone_views(sid: str, centre: tuple[float, float], sides: dict[str, str]) -> dict[str, dict]:
    """One drone photo per side: camera on that side, looking at the building, pitched down 10 to 50 degrees."""
    from ...sources import hackathon
    try:
        photos = hackathon.drone_list(sid, n=48)["photos"]
    except Exception:  # noqa: BLE001  no drone flight for this scan
        return {}
    lat0, lon0 = centre
    out = {}
    for letter, comp in sides.items():
        want = COMPASS.index(comp) * 90.0
        best = None
        for p in photos:
            if p.get("lat") is None or p.get("gimbal_yaw_deg") is None:
                continue
            cam = bearing(lat0, lon0, p["lat"], p["lon"])
            look = (cam + 180) % 360  # the camera should look back at the building
            off = abs((cam - want + 180) % 360 - 180)
            aim = abs((p["gimbal_yaw_deg"] - look + 180) % 360 - 180)
            pitch = p.get("gimbal_pitch_deg") or 0
            if off > 35 or aim > 30 or not -55 <= pitch <= -8:
                continue
            cost = off + aim + max(0.0, metres(lat0, lon0, p["lat"], p["lon"]) - 40) / 2  # closer shows the house
            if best is None or cost < best[0]:
                best = (cost, p)
        if best:
            out[letter] = {"kind": "drone", "ref": f"{sid}/{best[1]['name']}", "off_deg": round(best[0], 1)}
    return out


def oblique_views(lat: float, lon: float, sides: dict[str, str]) -> dict[str, dict]:
    """Vexcel obliques when there is no drone flight: `oblique-north` looks north, so it shows the south face."""
    from ...aerial import site
    try:
        _, dirs = site.oblique_directions(lat, lon)
    except Exception:  # noqa: BLE001
        return {}
    looks = {"S": "oblique-north", "N": "oblique-south", "W": "oblique-east", "E": "oblique-west"}
    # shortcut: Contract 3 media has no oblique kind; the ref names the product so a viewer can fetch it
    return {k: {"kind": "ortho", "ref": f"{looks[c]}@{lat:.6f},{lon:.6f}"} for k, c in sides.items() if looks[c] in dirs}


def build(plan: dict, acc: dict | None) -> dict:
    """Questions with answers from the measured interior. Needs the plan's geocoordinates for sides and points."""
    polys = polygons(plan)
    lv = live_rooms(plan)
    floors = sorted({r["floor"] for r in lv})
    qs = [{"id": "floors", "kind": "count", "text": "How many floors does this house have above ground?",
           "answer": len(floors), "points": 1, "unit": "floors", "explain": f"The scan has {len(floors)} floor{"s" if len(floors) > 1 else ""}."}]
    if acc is None or not plan.get("geo"):
        return {"questions": qs, "sides": None, "views": {}}
    centre = acc["footprint"].centroid if acc.get("footprint") is not None else None
    lat0, lon0 = (centre.y, centre.x) if centre is not None else (acc["lat"], acc["lon"])
    front = acc["front"]

    def where(r):
        c = polys[r["id"]].centroid
        lat, lon = to_latlon(plan, c.x, c.y)
        return lat, lon, side_of(bearing(lat0, lon0, lat, lon), front), metres(lat0, lon0, lat, lon)

    def accept(lat, lon) -> list[str]:  # near a corner, both sides that meet there count
        b = (bearing(lat0, lon0, lat, lon) - COMPASS.index(front) * 90) % 90
        if 30 < b < 60:
            return [side_of(bearing(lat0, lon0, lat, lon) - 20, front), side_of(bearing(lat0, lon0, lat, lon) + 20, front)]
        return []

    kitchens = [r for r in lv if r.get("label") == "Kitchen" and polys.get(r["id"]) is not None]
    if kitchens:
        k = max(kitchens, key=lambda r: polys[r["id"]].area)
        lat, lon, s, d = where(k)
        qs.append({"id": "kitchen_side", "kind": "choice", "choices": SIDE_NAMES, "points": 1,
                   "text": "Which side of the house is the kitchen on (A is the address side)?", "answer": s,
                   "accept": [x for x in accept(lat, lon) if x != s], "room": k["id"], "geo": [lon, lat],
                   "explain": f"The kitchen's centre is {d:.0f} m from the middle of the footprint, toward side {s}."})
    beds = [r for r in lv if r.get("label") == BEDROOM and polys.get(r["id"]) is not None]
    if beds:
        pts = [where(r) for r in beds]
        qs.append({"id": "bedroom_count", "kind": "count", "points": 1, "unit": "bedrooms",
                   "text": "How many bedrooms do you expect?", "answer": len(beds),
                   "explain": f"The scan has {len(beds)} rooms typed Bedroom."})
        qs.append({"id": "bedrooms", "kind": "points", "points": 3, "text": "Mark each bedroom on the aerial photo.",
                   "answer": [[p[1], p[0]] for p in pts], "rooms": [r["id"] for r in beds],
                   "explain": "Bedroom centres: " + ", ".join(f"side {p[2]}" for p in pts) + "."})
        counts = {s: sum(p[2] == s for p in pts) for s in SIDE_NAMES}
        top = max(counts.values())
        qs.append({"id": "bedroom_side", "kind": "choice", "choices": SIDE_NAMES, "points": 1,
                   "text": "Which side holds the most bedrooms (where you search first)?",
                   "answer": next(s for s in SIDE_NAMES if counts[s] == top),
                   "accept": [s for s in SIDE_NAMES if counts[s] == top][1:],
                   "explain": "Bedrooms by side: " + ", ".join(f"{s} {n}" for s, n in counts.items() if n) + "."})
        if len(floors) > 1:
            ordered = sorted(plan["floors"], key=lambda f: f.get("sequence") or 0)
            ground = ordered[0]["id"]
            on_ground = sum(r["floor"] == ground for r in beds)
            qs.append({"id": "bedrooms_upstairs", "kind": "count", "points": 1, "unit": "bedrooms",
                       "text": "How many bedrooms are above the ground floor?",
                       "answer": len(beds) - on_ground,
                       "explain": f"{len(beds) - on_ground} of {len(beds)} bedrooms are above the ground floor."})
    stairs = [r for r in lv if r.get("label") in STAIRS and polys.get(r["id"]) is not None]
    if stairs:
        pts = [where(r) for r in stairs]
        qs.append({"id": "stairs", "kind": "points", "points": 2, "text": "Mark where the interior stairs are.",
                   "answer": [[p[1], p[0]] for p in pts], "rooms": [r["id"] for r in stairs],
                   "explain": "Stair rooms toward side " + ", ".join(p[2] for p in pts) + "."})
    return {"questions": qs, "sides": acc["sides"], "front": front, "centre": (lat0, lon0)}


@tool(id="size_up_quiz", title="Size-up quiz", icon="target",
      summary="Training: read a house from outside (bedrooms, stairs, kitchen side, floors) and get graded against "
              "its measured interior.",
      model_description="Builds a size-up training exercise for one house: outside views of sides A to D (drone "
                        "photos, else oblique aerials), questions a company officer answers from outside, the answer "
                        "key from the measured interior, and scoring when `answers` are given.",
      personas=["fire_captain"],
      requires=[{"layer": "matterport.rooms"}, {"layer": "matterport.room_labels"},
                {"layer": "drone.photos", "need": "optional", "fallback": "vexcel obliques"},
                {"layer": "vexcel.ortho"}],
      blocks=["VerdictHeader", "EvidenceStrip", "CheckList", "MetricRow", "StepLog"], overlays=[],
      examples=["Give me a size-up drill on this house", "Score my size-up"])
def run(ctx, inputs: Inputs) -> ToolResult:
    sid = inputs.scan
    plan = ctx.plan(sid)
    scope = ScanScope(sid=sid)
    acc = None
    if plan.get("geo"):
        from ..fire_preplan.site import access
        try:
            acc = access(plan["geo"]["lat"], plan["geo"]["lon"], 70)
        except Exception as e:  # noqa: BLE001
            ctx.step(f"No aerial reading: {type(e).__name__}")
    quiz = build(plan, acc)
    qs = quiz["questions"]
    views = {}
    if quiz.get("sides"):
        views = drone_views(sid, quiz["centre"], quiz["sides"])
        src = VIEWS
        if len(views) < 2:
            views = oblique_views(*quiz["centre"], quiz["sides"])
            src = Source(layer="vexcel", method="lookup", confidence="high", note="Vexcel oblique aerials, one per side")
        ctx.step(f"Picked {len(views)} outside views; side A faces {quiz['front']}")
    else:
        src = VIEWS
    media = [Media(kind=v["kind"], ref=v["ref"]) for _, v in sorted(views.items())]
    findings = []
    for n, q in enumerate(qs, 1):
        findings.append(Finding(id=f"size_up_quiz:{sid}:q{n}", title=f"Question {n}", status="unknown",
                                detail=q["text"] + (f" Choices: {', '.join(q['choices'])}." if q.get("choices") else ""),
                                anchor=None, source=src, media=media))
        ans = q["answer"]
        shown = (f"{len(ans)} points (see anchor)" if q["kind"] == "points" else f"{ans}") + \
            (f" (also accepted: {', '.join(q['accept'])})" if q.get("accept") else "")
        anchor = RoomAnchor(sid=sid, room=q["room"]) if q.get("room") else \
            RoomAnchor(sid=sid, room=q["rooms"][0]) if q.get("rooms") else None
        findings.append(Finding(id=f"size_up_quiz:{sid}:a{n}", title=f"Answer {n}", status="pass",
                                detail=f"{shown}. {q['explain']}", anchor=anchor, source=KEY))
    checks, metrics = [], [Metric(id="questions", label="Questions", value=len(qs), unit="", source=KEY),
                           Metric(id="views", label="Outside views", value=len(views), unit="", source=src)]
    if inputs.answers is not None:
        sc = score(qs, inputs.answers)
        for q, s in zip(qs, sc["questions"]):
            checks.append(Check(id=q["id"], rule=q["text"], measured=s["points"], threshold=s["max"], unit="points",
                                status="pass" if s["points"] >= 0.75 * s["max"] else "warn" if s["points"] > 0 else "fail",
                                findings=[f"size_up_quiz:{sid}:a{qs.index(q) + 1}"]))
        metrics.insert(0, Metric(id="score", label="Score", value=sc["total"], unit=f"of {sc['max']:g}", source=KEY))
        pct = sc["total"] / sc["max"] if sc["max"] else 0
        verdict = Verdict(status="pass" if pct >= 0.75 else "warn" if pct >= 0.4 else "fail",
                          text=f"Scored {sc['total']:g} of {sc['max']:g} on {len(qs)} questions.")
    else:
        verdict = Verdict(status="unknown" if len(qs) < 2 else "pass", text=(
            f"Size-up drill ready: {len(qs)} questions with {len(views)} outside views; the answer key comes from "
            "the measured interior." if len(qs) > 1 else
            "Only the floor count can be asked: " + ("this scan has no typed bedrooms, kitchen or stairs to place on a "
            "side." if acc else "this scan has no geocoordinates or aerial reading to place rooms on a side.")))
    template = {q["id"]: ([] if q["kind"] == "points" else None) for q in qs}
    return ToolResult(
        scope=scope, verdict=verdict, metrics=metrics, checks=checks, findings=findings,
        assumptions=[Assumption(id="sides", label="Side A is the address side, B to D clockwise from above",
                                value=quiz.get("front")),
                     Assumption(id="point_scoring", label=f"A marked point scores fully within {FULL_M:g} m, nothing "
                                f"beyond {ZERO_M:g} m; extra marks cost half a point", value=True)],
        actions=[Action(id="score", label="Score my answers", tool="size_up_quiz",
                        inputs={"scan": sid, "answers": template})])
