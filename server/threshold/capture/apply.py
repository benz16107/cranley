"""What a capture does when it arrives.

A capture that answers a phone task settles that task: the value is judged, the findings the task came from are
updated in the workspace (status, the on-site value, the capture as evidence), and field_check runs again so its
panel shows the visit so far. A capture for a phone tool runs that tool into the workspace. Any other capture
becomes a plain evidence finding. Every path ends in workspace ops, so a desktop following the workspace sees it."""
from __future__ import annotations

from typing import Any

from ..agent import prefs
from ..agent.investigator import Investigation, attach
from ..agent.workspace import BriefSet, Feedback, FindingAdd, PrefSet, Scope, Session, ToolEnable, WsFinding, known_sids
from ..tools import ToolResult
from ..tools._phone import anchor, media, source
from ..tools.field_check import Outcome, Task, describe
from ..tools.registry import default_plan
from . import store
from .tasks import TAPE_ERR_M, judge, tasks

PHONE_TOOLS = ("field_check", "photo_measure", "slope_check", "noise_level", "where_am_i", "window_check", "floor_height",
               "walkthrough")
KIND_WORD = {"photo": "Photo", "video": "Video", "audio": "Voice note", "reading": "Reading"}
ALARM_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["ceiling_visible", "smoke_alarm_visible", "what", "confidence"],
                "properties": {"ceiling_visible": {"type": "boolean"}, "smoke_alarm_visible": {"type": "boolean"},
                               "what": {"type": "string", "description": "One sentence on what is on the ceiling"},
                               "confidence": {"type": "string", "enum": ["high", "medium", "low"]}}}


def plans_of(s: Session):
    return prefs.with_labels(s.plans or default_plan, s.doc)


def phone_tasks(s: Session) -> list[dict]:
    return tasks(s.doc, plans_of(s), store.listing(s.base.id))


def in_scope(s: Session, sid: str | None) -> None:
    """A scan the phone names joins the workspace's buildings, so tools may run on it."""
    if sid and sid not in known_sids(s.doc):
        sc = s.doc.brief.scope
        s.submit(BriefSet(scope=Scope(sids=[*sc.sids, sid], address=sc.address, places=sc.places)), by="user")


def run(s: Session, tool: str, inputs: dict) -> tuple[dict, ToolResult | None]:
    """Run a tool into the workspace as the phone's user. (the run's summary for the caller, its result)"""
    attach(s, s.plans or default_plan)
    if not any(t.id == tool and t.enabled for t in s.doc.tools):
        s.submit(ToolEnable(tool=tool, reason="Used from the phone on site."), by="user")
    out = Investigation(s).run(tool, inputs)
    rec = next((r for r in s.doc.runs if r.id == out.get("run")), None)
    return out, rec.result if rec else None


def metric(result: ToolResult, mid: str) -> float | None:
    return next((m.value for m in result.metrics if m.id == mid), None)


def alarm_in_photo(cid: str, ask=None) -> dict:
    if ask is None:
        from ..vision.model import ask
    return ask([store.image(cid, 1400)], "A person photographed a ceiling to show whether the room has a smoke alarm. Is "
               "enough ceiling visible to judge, and is a smoke alarm (a round or square device on the ceiling or high on "
               "a wall) visible?", ALARM_SCHEMA, key=f"phone_alarm/{cid}")


def measure_photo(s: Session, cap: dict, what: str, **more) -> tuple[dict, ToolResult | None, dict | None, str]:
    """Run photo_measure on a capture's photo. The points come from the phone when the person placed them (then
    `values.photo` names the photo they were placed on), else from the vision reader. (summary, result, points, who)"""
    from ..tools.photo_measure import find_points
    v = cap.get("values") or {}
    photo = v.get("photo") or (cap["id"] if cap["kind"] == "photo" else None)
    if not photo or store.get(photo)["workspace"] != s.base.id:
        return {"error": "Type the measurement, or take a photo with a sheet of paper or a card in it."}, None, None, "manual"
    pts, who = v.get("points"), "manual"
    if not pts:
        found = find_points(photo, v.get("reference", "letter"), what)
        if found["points"] is None:
            return {"error": "The photo does not show the reference and both ends clearly. Retake it square on, or place "
                             "the points by hand."}, None, None, "vision"
        pts, who = found["points"].model_dump(), "vision"
    out, res = run(s, "photo_measure", {"capture": photo, "reference": v.get("reference", "letter"), "what": what,
                                        "door_width_m": v.get("door_width_m"), "points": pts, "points_from": who,
                                        **{k: x for k, x in more.items() if x is not None}})
    return out, res, pts, who


def settle(s: Session, task: dict, cap: dict) -> dict:
    """The outcome of one task from one capture, or {"problem": ...} when the capture did not settle it."""
    v: dict[str, Any] = cap.get("values") or {}
    kind, sid = task["kind"], task["sid"]
    extra: dict[str, Any] = {}
    if kind in ("width", "step"):
        if v.get("value_m") is not None:
            o = judge(task, float(v["value_m"]), TAPE_ERR_M)
            return {**o, "method": "manual", "confidence": "high"}
        what = "the clear width of the doorway" if kind == "width" else "the height of the step, floor to its top edge"
        out, res, pts, who = measure_photo(s, cap, what, threshold_m=task["threshold"] if kind == "width" else None,
                                           standard=task.get("standard"), scan=sid, opening=task.get("opening"), room=task.get("room"))
        if res is None or metric(res, "length") is None:
            return {"problem": out.get("error") or (res.verdict.text if res else "The photo could not be measured."), "points": pts}
        o = judge(task, metric(res, "length"), metric(res, "error") or TAPE_ERR_M)
        return {**o, "method": who, "confidence": res.findings[0].source.confidence, "points": pts, "run": out.get("run")}
    if kind == "alarm":
        answer = v.get("answer")
        if answer in ("present", "absent"):
            return {**judge(task, None, answer=answer), "method": "manual", "confidence": "high"}
        if cap["kind"] != "photo":
            return {"problem": "Say whether there is an alarm, or photograph the ceiling."}
        seen = alarm_in_photo(cap["id"])
        if seen["smoke_alarm_visible"] and seen["confidence"] == "high":
            return {**judge(task, None, answer="present"), "method": "vision", "confidence": "high", "seen": seen["what"]}
        return {"problem": "The photo does not settle it" + (f" ({seen['what']})" if seen.get("what") else "")
                           + ". Look at the ceiling and say what is there."}
    if kind == "slope":
        out, res = run(s, "slope_check", {**{k: v[k] for k in ("reading_deg", "flipped_deg", "cross_deg", "cross_flipped_deg",
                                                              "spread_deg") if v.get(k) is not None},
                                         "mode": "ramp", "scan": sid, "capture": cap["id"]})
        if res is None:
            return {"problem": out.get("error") or "The reading could not be used."}
        return {"verdict": "measured", "status": res.verdict.status, "value": metric(res, "slope_pct"), "err": None,
                "text": res.verdict.text, "method": "sensor", "confidence": res.findings[0].source.confidence, "run": out.get("run")}
    if kind == "heading":
        heading = v.get("heading_deg", cap.get("heading_deg"))
        if heading is None:
            return {"problem": "No compass heading came with that. Turn on motion sensors and try again."}
        fix = cap.get("fix") or {}
        out, res = run(s, "window_check", {"scan": sid, "room": task["room"], "heading_deg": heading, "capture": cap["id"],
                                          "heading_accuracy_deg": v.get("heading_accuracy_deg", cap.get("heading_accuracy_deg")),
                                          "lat": fix.get("lat"), "lon": fix.get("lon")})
        if res is None:
            return {"problem": out.get("error") or "The heading could not be used."}
        st = res.verdict.status
        return {"verdict": {"pass": "confirmed", "fail": "contradicted"}.get(st, "measured"), "status": st,
                "value": metric(res, "sun_phone_h"), "err": None, "text": res.verdict.text, "method": "sensor",
                "confidence": res.findings[0].source.confidence, "run": out.get("run")}
    if kind == "floor_height":
        last = next((r for r in reversed(s.doc.runs) if r.tool == "flood_rehearsal" and r.sid == sid and r.status == "done"), None)
        depth = (last.inputs.get("depth_m") if last else None)
        out, res = run(s, "floor_height", {**{k: v[k] for k in ("steps", "riser_m", "door", "street", "baro_rise_m") if v.get(k) is not None},
                                          "scan": sid, "capture": cap["id"] if cap["kind"] == "photo" else None,
                                          **({"depth_m": depth} if depth is not None else {})})
        if res is None or metric(res, "floor_height") is None:
            return {"problem": out.get("error") or (res.verdict.text if res else "The floor height could not be worked out.")}
        if res.verdict.status == "pass" and last:  # narrower: the flood result on the desktop follows
            run(s, "flood_rehearsal", {**last.inputs, "scan": sid, "floor_height_m": metric(res, "floor_height")})
            extra["flood_rerun"] = True
        return {"verdict": "measured", "status": res.verdict.status, "value": metric(res, "floor_height"),
                "err": round((metric(res, "range_after") or 0) / 2, 3), "text": res.verdict.text, "method": "manual",
                "confidence": res.findings[0].source.confidence, "run": out.get("run"), **extra}
    return {"problem": f"Nothing here knows how to settle a {kind} task."}


def update_findings(s: Session, task: dict, outcome: dict, cap: dict) -> int:
    """Write the on-site result onto the findings the task came from. Returns how many changed."""
    t = Task.model_validate({**task, "status": "done", "outcome": outcome, "capture": cap["id"]})
    said, n = describe(t), 0
    for fid in task["findings"]:
        f = next((x for x in s.doc.findings if x.id == fid and not x.superseded_by), None)
        if f is None:
            continue
        o = t.outcome
        new = f.model_copy(update={
            "status": o.status if o.status != "unknown" else f.status,
            "detail": f.detail.split(" On site: ")[0] + " " + said,
            "source": source(o.method, o.confidence, "Checked on site with the phone; the scan's own figure is in the detail"),
            "media": [m for m in f.media if m.kind != "phone"] + media(cap["id"]),
            "feedback": Feedback(verdict="confirmed", reason="Confirmed on site") if o.verdict == "confirmed" else f.feedback})
        s.submit(FindingAdd(finding=WsFinding.model_validate(new.model_dump()), run=f.run), by="user")
        n += 1
    return n


def tell_agent(s: Session, task: dict, outcome: dict, cap: dict) -> None:
    """Put the on-site result where every later agent turn reads it: the workspace's learned list, which goes into
    the agent's prompt and shows on the desktop under "What I have learned" with an undo."""
    t = Task.model_validate({**task, "status": "done", "outcome": outcome, "capture": cap["id"]})
    s.submit(PrefSet(key=f"site.{task['id']}", value={"verdict": outcome["verdict"], "status": outcome["status"],
                                                     "value": outcome.get("value"), "unit": task.get("unit")},
                     reason=f"Checked on site with the phone. {task['title']}: {describe(t)}"), by="user")


def refresh_field_check(s: Session, sid: str) -> dict:
    mine = [t for t in phone_tasks(s) if t["sid"] == sid]
    out, _ = run(s, "field_check", {"scan": sid, "tasks": mine})
    return out


def note(s: Session, cap: dict) -> None:
    """A capture that feeds no task and no tool: plain evidence, pinned where it was taken."""
    fix = cap.get("fix") or {}
    geo = (fix["lon"], fix["lat"]) if fix.get("lat") is not None else None
    title = KIND_WORD[cap["kind"]] + " from the phone"
    s.submit(FindingAdd(finding=WsFinding(
        id=f"phone:{cap['id']}", title=title, status="unknown", detail=cap.get("note") or "", tool=None,
        anchor=anchor(cap.get("scan"), cap.get("room"), cap.get("opening"), geo),
        source=source("manual", "high", "Taken on site with the phone"), media=media(cap["id"]))), by="user")


def tool_inputs(s: Session, cap: dict) -> dict:
    """A phone tool's inputs from a capture: its values, where it was taken, and the capture as evidence."""
    from ..agent.catalog import catalog
    props = catalog()[cap["tool"]].inputs.get("properties", {})
    v = dict(cap.get("values") or {})
    fix = cap.get("fix") or {}
    if cap["tool"] == "noise_level":  # every room measured in this visit, so the lens covers them all
        v = {"readings": [{**(c.get("values") or {}), "capture": c["id"]} for c in store.listing(s.base.id)
                          if c.get("tool") == "noise_level" and c.get("scan") == cap.get("scan")]}
    given = {**v, "capture": cap["id"], "scan": cap.get("scan"), "room": cap.get("room"), "opening": cap.get("opening"),
             "geo": [fix["lon"], fix["lat"]] if fix.get("lat") is not None else None, "accuracy_m": fix.get("accuracy_m"),
             "lat": fix.get("lat"), "lon": fix.get("lon"), "heading_deg": v.get("heading_deg", cap.get("heading_deg")),
             "heading_accuracy_deg": v.get("heading_accuracy_deg", cap.get("heading_accuracy_deg"))}
    return {k: x for k, x in given.items() if k in props and x is not None}


def handle(s: Session, cap: dict) -> dict:
    """Do what this capture is for. Returns what the phone shows next."""
    in_scope(s, cap.get("scan"))
    if cap.get("task"):
        task = next((t for t in phone_tasks(s) if t["id"] == cap["task"]), None)
        if task is None:
            note(s, cap)
            return {"problem": "That task is no longer in this workspace; the capture was kept as evidence."}
        outcome = settle(s, task, cap)
        if "problem" in outcome:
            if cap["file"]:  # the photo is still evidence; a reading that settled nothing is not
                note(s, cap)
            return outcome
        Outcome.model_validate(outcome)
        store.update(cap["id"], result=outcome)
        changed = update_findings(s, task, outcome, cap)
        tell_agent(s, task, outcome, cap)
        refresh_field_check(s, task["sid"])
        return {"outcome": outcome, "updated_findings": changed}
    if cap.get("tool") in PHONE_TOOLS and cap["tool"] != "field_check":
        pts = None
        if cap["tool"] == "photo_measure":
            v = cap.get("values") or {}
            out, res, pts, _ = measure_photo(s, cap, v.get("what") or "the width between the two marked ends",
                                             scan=cap.get("scan"), room=cap.get("room"), opening=cap.get("opening"))
        else:
            out, res = run(s, cap["tool"], tool_inputs(s, cap))
        if res is None:
            if cap["file"]:
                note(s, cap)
            return {"problem": out.get("error") or "The tool did not run.", "points": pts}
        did = {"run": out.get("run"), "status": res.verdict.status, "text": res.verdict.text,
               "metrics": [m.model_dump(mode="json") for m in res.metrics[:4]]}
        store.update(cap["id"], result=did)
        return {**did, "points": pts}
    note(s, cap)
    return {}
