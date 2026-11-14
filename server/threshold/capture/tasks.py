"""Phone tasks: what a person standing in the building can settle that the scan could not.

`tasks(doc, plans)` reads the latest finished run of each source tool in a workspace and turns its "measure on
site", "too close to call", "not seen" and wide-range results into things to do with a phone. `judge(task, ...)`
says what a measurement that came back means for the scan's result. Both are pure: no files, no network.

Source tool        What it leaves open                              Task kind
door_widths        the wall opening, not the clear width            width
step_free_route    data-error widths, close calls, possible steps   width, step, slope
bathroom_clearance the bathroom door's clear width                  width
life_safety_census a smoke alarm not seen, or a ceiling not read    alarm
flood_rehearsal    the floor's height above the ground outside      floor_height
daylight           which way a window really faces                  heading
"""
from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from ..geometry._plan import HUNG_DOOR_ALLOWANCE_M
from ..tools._access import STD

SOURCES = ("door_widths", "step_free_route", "bathroom_clearance", "life_safety_census", "flood_rehearsal", "daylight")
MAX_WINDOWS = 4   # window tasks per scan, sunniest rooms first
IN = 0.0254
LEVEL_VERTICAL_M, LEVEL_BEVEL_M = 0.25 * IN, 0.5 * IN   # ADA 2010 303.2, 303.3
TAPE_ERR_M = 0.005     # a tape measure read by a person
AGREE_M = 0.03         # the scan and the site agree when they differ by no more than this plus the method's error

HOW = {
    "width": "Open the door to 90 degrees. Measure from the face of the door to the stop on the latch side: that "
             "is the clear width a wheelchair or a sofa gets.",
    "step": "Measure the height of the step or threshold at this doorway, floor to top edge.",
    "slope": "Lay the phone on the ramp, long edge pointing up the slope, then turn it end for end when asked.",
    "alarm": "Stand in the room and photograph the ceiling. If you can see an alarm, say so; the photo is the proof.",
    "floor_height": "Stand at the front door, then at the street or the edge of the yard, then photograph the "
                    "door's threshold with the steps up to it in frame.",
    "heading": "Stand at the window and point the top of the phone straight out through the glass.",
}


def latest_runs(doc) -> dict[tuple[str, str], Any]:
    """(tool, scan) -> its latest finished run with a result."""
    out = {}
    for r in doc.runs:
        if r.tool in SOURCES and r.status == "done" and r.result and r.sid:
            out[(r.tool, r.sid)] = r
    return out


def _room_name(plan: dict, rid: str) -> str:
    rooms = plan.get("rooms") or []
    r = next((x for x in rooms if x["id"] == rid), None)
    label = (r or {}).get("label") or "Unlabelled room"
    same = [x["id"] for x in rooms if (x.get("label") or "Unlabelled room") == label]
    return f"{label} {same.index(rid) + 1}" if r and len(same) > 1 else label


def _where(plan: dict, opening: dict | None) -> str:
    """Where a doorway is, in room names a person can tell apart ("bedroom 2 to bathroom 1")."""
    if not opening:
        return "doorway"
    have = {r["id"] for r in plan.get("rooms") or []}
    names = [_room_name(plan, r).lower() if r in have else "unlabelled room" for r in opening.get("rooms") or []]
    if len(names) > 1:
        return " to ".join(names)
    # a doorway with one room leads outside or into space the scan did not cover; the plan says which when it knows
    return f"{names[0] if names else 'room'} to " + ("outside" if opening.get("exterior") is not False else "an unscanned space")


def tasks(doc, plans: Callable[[str], dict], captures: list[dict] | None = None) -> list[dict]:
    """Every phone task the workspace's results call for, the done ones carrying their outcome."""
    out: dict[str, dict] = {}

    def add(kind: str, sid: str, key: str, title: str, why: str, tool: str, finding: str | None, **more) -> dict:
        tid = f"{kind}:{sid}:{key}"
        t = out.setdefault(tid, {"id": tid, "kind": kind, "sid": sid, "title": title, "why": why, "how": HOW[kind],
                                 "tools": [], "findings": [], "room": None, "opening": None, "scan_value": None,
                                 "threshold": None, "unit": more.pop("unit", "m"), "standard": None, "status": "open", "outcome": None,
                                 "capture": None})
        if tool not in t["tools"]:
            t["tools"].append(tool)
        if finding and finding not in t["findings"]:
            t["findings"].append(finding)
        more.pop("unit", None)
        for k, v in more.items():
            if v is not None and (t.get(k) is None or (k == "threshold" and v > t[k])):  # the stricter need wins
                t[k] = v
        return t

    for (tool, sid), run in latest_runs(doc).items():
        try:
            plan = plans(sid)
        except Exception:  # noqa: BLE001 - a scan that will not load has no tasks, the rest still do
            continue
        ops = {o["id"]: o for o in plan.get("openings") or []}
        need = run.inputs.get("min_width_m") or run.inputs.get("door_width_m")

        def width(oid: str, fid: str, why: str):
            o = ops.get(oid)
            w = (o or {}).get("width")
            add("width", sid, oid, f"Measure the doorway, {_where(plan, o)}", why, tool, fid, opening=oid,
                room=((o or {}).get("rooms") or [None])[0], threshold=need, standard=STD["door"],
                scan_value=round(max(0.0, w - HUNG_DOOR_ALLOWANCE_M), 3) if w and w >= 0.4 else None)

        for f in run.result.findings:
            tail = f.id.split(":", 2)[2] if f.id.count(":") >= 2 else ""
            if tool == "door_widths" and f.status != "pass" and tail in ops:
                width(tail, f.id, "The scan gives the opening in the wall. A hung door takes a few centimetres off it.")
            elif tool == "step_free_route" and tail.startswith(("data:", "door:")):
                width(tail.split(":", 1)[1], f.id, "The scan's width here is a data error." if tail.startswith("data:")
                      else "On your route and too close to your limit to call from the scan.")
            elif tool == "step_free_route" and tail.startswith("step:"):
                oid = tail.split(":", 1)[1]
                add("step", sid, oid, f"Measure the step at the doorway, {_where(plan, ops.get(oid))}",
                    "The scan sees a level change here but its sill heights scatter about 4 cm.", tool, f.id,
                    opening=oid, threshold=LEVEL_VERTICAL_M, standard=STD["level"])
            elif tool == "step_free_route" and tail.startswith("seen:"):
                ramp = "ramp" in f.title.lower()
                if ramp or "step" in f.title.lower():
                    seen = (f.detail or "").split(". ", 1)[0].strip().rstrip(".")  # the vision model's words: where it is
                    add("slope" if ramp else "step", sid, tail.split(":", 1)[1],
                        f"{'Check the slope' if ramp else 'Measure the step'}: {seen[0].lower()}{seen[1:]}" if seen
                        else "Check the slope of the ramp on your route" if ramp else "Measure the step seen on your route",
                        "A panorama shows it; nothing in the scan measures it.", tool, f.id,
                        threshold=None if ramp else LEVEL_VERTICAL_M, unit="%" if ramp else "m",
                        standard="ADA 2010 405.2: running slope 1:12 (8.33%) maximum" if ramp else STD["level"])
            elif tool == "bathroom_clearance" and re.search(r":door\.[^:]+$", f.id):
                width(f.id.rsplit(":door.", 1)[1], f.id, "The bathroom door's clear width decides whether you get in.")
            elif tool == "life_safety_census" and f.status in ("warn", "unknown") and tail and not tail.startswith(
                    ("level:", "no_labels")) and any(r["id"] == tail for r in plan.get("rooms") or []):
                name = _room_name(plan, tail)
                add("alarm", sid, tail, f"Photograph the ceiling in {name[0].lower() + name[1:]}",
                    "No smoke alarm was seen in the scan's photos." if f.status == "warn" else
                    "The scan's photos do not show this ceiling well enough to say.", tool, f.id, room=tail, unit="")
            elif tool == "flood_rehearsal" and tail == "floor_height":
                m = next((x for x in run.result.metrics if x.id == "floor_height"), None)
                add("floor_height", sid, "door", "Stand at the front door",
                    "The floor's height above the ground outside is the widest uncertainty in the flood result.",
                    tool, f.id, scan_value=m.value if m else None,
                    opening=f.anchor.opening if f.anchor is not None and hasattr(f.anchor, "opening") else None)
        if tool == "daylight":
            lit = sorted((c for c in run.result.checks if c.measured), key=lambda c: -c.measured)[:MAX_WINDOWS]
            sure = any(a.id == "compass_verified" and a.value for a in run.result.assumptions)
            for c in lit:
                name = _room_name(plan, c.id)
                add("heading", sid, c.id, f"Point the phone out of the window in {name[0].lower() + name[1:]}",
                    "Sun hours rest on the scan's compass rotation" + ("." if sure else ", which is not verified here."),
                    tool, None, room=c.id, scan_value=c.measured, unit="h")

    for c in captures or []:  # the latest capture that settled a task wins
        t = out.get(c.get("task") or "")
        if t and c.get("result"):
            t.update(status="done", outcome=c["result"], capture=c["id"])
    order = {"floor_height": 0, "width": 1, "step": 2, "slope": 3, "alarm": 4, "heading": 5}

    def worth(t: dict) -> tuple:
        """Within a kind: what more tools flagged first, then where a measurement is likeliest to change the answer
        (the scan's value closest to the limit; a data error, which has no scan value, before those)."""
        gap = abs(t["scan_value"] - t["threshold"]) if t["scan_value"] is not None and t["threshold"] is not None else -1.0
        return (-len(t["tools"]), gap if t["kind"] == "width" else 0.0, t["title"])
    return sorted(out.values(), key=lambda t: (t["status"] == "done", order[t["kind"]], *worth(t)))


def judge(task: dict, value: float | None, err: float = TAPE_ERR_M, answer: str | None = None) -> dict:
    """What an on-site result means for a task: {verdict, status, value, err, text}.

    verdict: "confirmed" (the site agrees with the scan), "contradicted" (it does not), or "measured" (the scan
    had no usable value, so this is the first one). status is the task's check against its limit on the site value."""
    kind, need, scan = task["kind"], task.get("threshold"), task.get("scan_value")
    if kind == "alarm":  # answer: "present" | "absent" | "unclear", from the person or from the photo
        if answer == "present":
            return {"verdict": "contradicted", "status": "pass", "value": None, "err": None,
                    "text": "A smoke alarm is there. The scan's photos did not show it."}
        if answer == "absent":
            return {"verdict": "confirmed", "status": "fail", "value": None, "err": None,
                    "text": "No smoke alarm in this room, checked on site."}
        return {"verdict": "measured", "status": "unknown", "value": None, "err": None,
                "text": "The photo does not settle it. Look at the ceiling and say what is there."}
    if value is None:
        return {"verdict": "measured", "status": "unknown", "value": None, "err": err, "text": "No value came back."}
    if kind == "step":
        status = "pass" if value + err <= LEVEL_VERTICAL_M else "fail" if value - err > LEVEL_BEVEL_M else "warn"
        text = {"pass": "Within the 1/4 in a wheel takes without a bevel.",
                "warn": "Between 1/4 and 1/2 in, or too close to call: it needs a bevel.",
                "fail": "Over 1/2 in: this is a step and needs a ramp."}[status]
        # the scan suspected a step: finding one confirms it, finding a flat floor contradicts it
        return {"verdict": "confirmed" if value > LEVEL_VERTICAL_M else "contradicted", "status": status,
                "value": round(value, 4), "err": err, "text": text}
    # width: at least `need`, judged with the method's error; compared with the scan's estimate when it had one
    if need is None:
        status, text = "unknown", "Measured; no limit was set to judge it against."
    elif value - err >= need:
        status, text = "pass", "Wide enough, with the measurement's error allowed for."
    elif value + err < need:
        status, text = "fail", "Too narrow, with the measurement's error allowed for."
    else:
        status, text = "warn", "Within the measurement's error of your limit: measure again with a tape."
    if scan is None:
        verdict = "measured"
    else:
        verdict = "confirmed" if abs(value - scan) <= AGREE_M + err else "contradicted"
    return {"verdict": verdict, "status": status, "value": round(value, 3), "err": err, "text": text}
