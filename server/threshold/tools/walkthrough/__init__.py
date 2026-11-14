"""Walk-through: a quick safety census of a home that has no scan, from a short video the person records walking
through it. Frames go to the vision reader for the room type, whether a smoke alarm is on the ceiling, hazards and
belongings. It is a first look, not a survey: a room the camera did not show is not in it, and "not seen" is a lead
to check, never a finding of absence."""
from __future__ import annotations

from pydantic import BaseModel

from ...capture import frames as video
from .. import Assumption, Check, Finding, GeoAnchor, Metric, ToolError, ToolResult, Verdict, field, tool
from .._phone import scope, source
from ..types import Media

ROOMS = ["Bedroom", "Bathroom", "Kitchen", "Living Room", "Dining Room", "Hallway", "Stairs", "Entrance", "Garage",
         "Laundry", "Office", "Closet", "Outdoors", "Other"]
HAZARDS = ["loose rug or cord across a walkway", "cluttered walkway", "stairs without a handrail", "blocked exit door",
           "overloaded outlet or power strip", "space heater near fabric", "items stored on or beside a stove",
           "window blocked or barred", "none seen"]
ALARM_ROOMS = ("Bedroom", "Hallway")     # IRC R314.3: in each sleeping room and outside each sleeping area
STD = "IRC R314.3: a smoke alarm in each sleeping room, outside each sleeping area and on each storey"
BATCH = 4
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["frames"], "properties": {"frames": {
    "type": "array", "items": {"type": "object", "additionalProperties": False,
                               "required": ["index", "room", "ceiling_in_view", "smoke_alarm", "hazards", "belongings", "confidence"],
                               "properties": {
                                   "index": {"type": "integer"}, "room": {"type": "string", "enum": ROOMS},
                                   "ceiling_in_view": {"type": "boolean"},
                                   "smoke_alarm": {"type": "string", "enum": ["seen", "not seen", "ceiling not in view"]},
                                   "hazards": {"type": "array", "items": {"type": "string", "enum": HAZARDS}},
                                   "belongings": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                                                             "required": ["label", "value"], "properties": {
                                                                                 "label": {"type": "string"},
                                                                                 "value": {"type": "string", "enum": ["low", "medium", "high"]}}}},
                                   "confidence": {"type": "string", "enum": ["high", "medium", "low"]}}}}}}
PROMPT = ("These are frames, in order, from a video a person recorded walking through their own home. For each frame "
          "(index from 0): the kind of room; whether the ceiling is in view; whether a smoke alarm is visible on the "
          "ceiling or high on a wall ('seen' only when you can see the device itself, 'ceiling not in view' when you "
          "cannot see enough ceiling to say); hazards from the list ('none seen' when there are none); and up to four "
          "belongings worth replacing, each with a rough value class. A blurred frame gets low confidence.")


class Inputs(BaseModel):
    capture: str = field(description="Capture id of the walk-through video")
    geo: tuple[float, float] | None = field(None, description="[lon, lat] of the home, from the phone's fix")
    max_frames: int = field(8, ge=2, le=16, description="Frames read from the video")


def read_frames(capture: str, shots: list[tuple[float, bytes]], ask=None) -> list[dict]:
    """One reading per frame: the vision reader's answer plus the frame's index and time."""
    if ask is None:
        from ...vision.model import ask
    out = []
    for i in range(0, len(shots), BATCH):
        part = shots[i:i + BATCH]
        got = ask([b for _, b in part], PROMPT, SCHEMA, key=f"walkthrough/{capture}/{i}-{len(part)}")
        for j, f in enumerate(got["frames"][:len(part)]):
            out.append({**f, "index": i + j, "t": part[j][0]})
    return out


def census(frames: list[dict]) -> list[dict]:
    """Consecutive frames of the same kind of room are one room: {room, n, frames, alarm, hazards, belongings}."""
    rooms: list[dict] = []
    seen: dict[str, int] = {}
    for f in frames:
        if not rooms or rooms[-1]["room"] != f["room"]:
            seen[f["room"]] = seen.get(f["room"], 0) + 1
            rooms.append({"room": f["room"], "n": seen[f["room"]], "frames": []})
        rooms[-1]["frames"].append(f)
    for r in rooms:
        fs = r["frames"]
        # only a confident sighting counts as seen (the fire tools found the same in the scans' photos)
        if any(f["smoke_alarm"] == "seen" and f["confidence"] == "high" for f in fs):
            r["alarm"] = "seen"
        elif any(f["ceiling_in_view"] and f["smoke_alarm"] == "not seen" and f["confidence"] != "low" for f in fs):
            r["alarm"] = "not seen"
        else:
            r["alarm"] = "could not see"
        r["hazards"] = sorted({h for f in fs for h in f["hazards"] if h != "none seen"})
        r["belongings"] = [b for f in fs for b in f["belongings"]]
    return rooms


@tool(id="walkthrough", title="Walk-through", icon="video",
      summary="A quick safety census of a home with no scan, from a short video you record walking through it: rooms, "
              "smoke alarms, hazards and belongings.",
      model_description="Read frames of a walk-through video of an unscanned home: room types, smoke alarms seen or not "
                        "seen per bedroom and hallway (IRC R314.3), trip and fire hazards, belongings. A first look; "
                        "rooms the camera missed are not in it. Needs a video capture from the phone app.",
      personas=["older_adult_family", "houston_homeowner_storm", "renter_listing"], requires=[{"layer": "phone.video"}],
      blocks=["VerdictHeader", "MetricRow", "CheckList", "EvidenceStrip", "AssumptionChips", "StepLog"],
      annotations={"cost": "slow"}, examples=["Check my own home for smoke alarms", "My home was never scanned"])
def run(ctx, inputs: Inputs, shots=None, ask=None) -> ToolResult:
    sc = scope(None, inputs.geo)
    try:
        shots = shots if shots is not None else video.extract(inputs.capture, inputs.max_frames)
    except LookupError as e:
        raise ToolError(str(e)) from None
    if not shots:
        return ToolResult(scope=sc, verdict=Verdict(status="unknown", text="No frame could be read from that video."))
    ctx.step(f"Took {len(shots)} frames from the video")
    read = read_frames(inputs.capture, shots, ask)
    rooms = [r for r in census(read) if r["room"] != "Outdoors"]
    ctx.step(f"The vision reader saw {len(rooms)} rooms")
    a = GeoAnchor(geo=inputs.geo) if inputs.geo else None
    checks, findings = [], []
    tally = {"seen": 0, "not seen": 0, "could not see": 0}
    for r in rooms:
        name = r["room"] if sum(1 for x in rooms if x["room"] == r["room"]) == 1 else f"{r['room']} {r['n']}"
        rid = f"{r['room'].lower().replace(' ', '_')}_{r['n']}"
        conf = "high" if all(f["confidence"] == "high" for f in r["frames"]) else "low" if any(f["confidence"] == "low" for f in r["frames"]) else "medium"
        src = source("vision", conf, f"Vision reader on {len(r['frames'])} video frame{'s' if len(r['frames']) != 1 else ''}; "
                     "a walk-through, not a scan")
        shot = [Media(kind="phone", ref=f"{inputs.capture}#{f['index']}") for f in r["frames"][:3]]
        if r["room"] in ALARM_ROOMS:
            tally[r["alarm"]] += 1
            st = {"seen": "pass", "not seen": "warn", "could not see": "unknown"}[r["alarm"]]
            fid = f"walkthrough:{inputs.capture}:alarm:{rid}"
            checks.append(Check(id=f"alarm.{rid}", rule=f"Smoke alarm seen, {name.lower()}", threshold=1, unit="seen",
                                measured=None if r["alarm"] == "could not see" else float(r["alarm"] == "seen"),
                                status=st, standard=STD, findings=[fid]))
            findings.append(Finding(id=fid, title=f"{name}, smoke alarm {r['alarm']}", status=st, anchor=a, source=src, media=shot,
                                    detail={"seen": "An alarm is visible in the video.",
                                            "not seen": "The ceiling is in view and no alarm shows. A lead to check, not a "
                                                        "finding of absence.",
                                            "could not see": "The video does not show enough of the ceiling. Film it again "
                                                             "looking up."}[r["alarm"]]))
        for h in r["hazards"]:
            fid = f"walkthrough:{inputs.capture}:hazard:{rid}:{h.split()[0]}"
            findings.append(Finding(id=fid, title=f"{name}: {h}", status="warn", anchor=a, source=src, media=shot,
                                    detail="Seen in the video. Look at it yourself before acting on it."))
    hazards = sum(len(r["hazards"]) for r in rooms)
    things = [b for r in rooms for b in r["belongings"]]
    src_all = source("vision", "medium", "Vision reader on video frames; rooms the camera missed are not counted")
    n_alarm = sum(tally.values())
    text = (f"{len(rooms)} rooms seen in the video. "
            + (f"Of {n_alarm} bedrooms and hallways, a smoke alarm was seen in {tally['seen']}, not seen in "
               f"{tally['not seen']}, and {tally['could not see']} could not be checked. " if n_alarm else
               "No bedroom or hallway was recognised, so smoke alarms could not be checked. ")
            + (f"{hazards} possible hazard{'s' if hazards != 1 else ''} to look at. " if hazards else "")
            + "This is a first look from a video, not a scan.")
    status = "warn" if tally["not seen"] or hazards else "unknown" if not n_alarm or tally["could not see"] else "pass"
    return ToolResult(
        scope=sc, verdict=Verdict(status=status, text=text), checks=checks, findings=findings,
        metrics=[Metric(id="rooms", label="Rooms seen", value=len(rooms), unit="", source=src_all),
                 Metric(id="alarms_seen", label="Alarms seen", value=tally["seen"], unit="", source=src_all),
                 Metric(id="alarms_not_seen", label="Alarms not seen", value=tally["not seen"], unit="", source=src_all),
                 Metric(id="hazards", label="Possible hazards", value=hazards, unit="", source=src_all),
                 Metric(id="belongings_high", label="High-value belongings", value=sum(b["value"] == "high" for b in things),
                        unit="", source=src_all)],
        assumptions=[Assumption(id="frames", label="Frames read from the video", value=len(shots)),
                     Assumption(id="not_seen_is_lead", label="Not seen means not found in the video, not absent", value=True),
                     Assumption(id="coverage", label="Rooms the camera did not show are not in this census", value=True)])
