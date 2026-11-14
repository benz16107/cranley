"""Comparisons to a ToolResult (Contract 3). One check and one finding per claim, the same for every property type.

A check's `threshold` is the record's value and `measured` the data's, both in the record's unit; `standard` names
the record field the value came from. The finding carries the verdict word in its title, the sentence with the
numbers in its detail, and the evidence as anchor and media.
"""
from __future__ import annotations

from .. import types as T
from .compare import _fmt

STATUS = {"confirmed": "pass", "contradicted": "fail", "cannot verify": "unknown", "context": "unknown"}
TITLE = {"confirmed": "confirmed", "contradicted": "contradicted", "cannot verify": "cannot be verified",
         "context": "context only"}
ORIGIN = {"listing": "listing", "costar": "CoStar record", "scan title": "scan title", "listing text": "listing text"}


def _num(v):
    if isinstance(v, bool) or v is None:
        return None if v is None else float(v)
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, list) and v and all(isinstance(x, (int, float)) for x in v):
        return float(sum(v) / len(v))
    return None


def source(c: dict, note: str | None = None) -> T.Source:
    return T.Source(layer=c["layer"], method=c["method"], confidence=c["confidence"], note=note)


def anchor(sid: str, c: dict):
    a = c.get("anchor")
    if a:
        return a
    rooms = (c.get("rooms") or {}).get("counted") or []
    if rooms:
        return {"sid": sid, "room": max(rooms, key=lambda r: r["m2"])["room"]}
    if c.get("pins"):
        return {"sid": sid, "room": c["pins"][0]}
    return None


def check_and_finding(tool: str, sid: str, c: dict) -> tuple[T.Check, T.Finding]:
    status = STATUS[c["verdict"]]
    fid = f"{tool}:{sid}:{c['key']}"
    unit = c["claim"].get("unit") or c["measured"].get("unit") or ""
    said = ORIGIN.get(c["claim"]["origin"], c["claim"]["origin"])
    value = c["claim"]["value"] if c["key"].startswith("year") else _fmt(c["claim"]["value"], c["claim"].get("unit"))
    detail = f"{said[0].upper() + said[1:]} says {value}. {c['reason']}"
    check = T.Check(id=c["key"], rule=f"{c['label']}, {ORIGIN.get(c['claim']['origin'], c['claim']['origin'])} vs "
                                      f"{'scan' if c['layer'] == 'matterport' else 'aerial' if c['layer'] == 'vexcel' else 'panoramas'}",
                    measured=_num(c["measured"]["value"]), threshold=_num(c["claim"]["value"]),
                    unit=unit.replace("ft2", "ft²"), status=status, standard=c["claim"]["path"], findings=[fid], kind="claim")
    finding = T.Finding(id=fid, title=f"{c['label']} {TITLE[c['verdict']]}", status=status, detail=detail,
                        anchor=anchor(sid, c), source=source(c, f"Verdict: {c['verdict']}"),
                        media=c.get("media") or [])
    return check, finding


def overlays(sid: str, comps: list[dict]) -> list:
    out = []
    area = next((c for c in comps if c.get("rooms")), None)
    if area:
        counted = [r["room"] for r in area["rooms"]["counted"]]
        excluded = [r["room"] for r in area["rooms"]["excluded"]]
        if counted:
            out.append(T.RuleOverlay(select={"rooms": counted}, style="pass" if area["verdict"] == "confirmed" else "highlight"))
        if excluded:
            out.append(T.RuleOverlay(select={"rooms": excluded}, style="dim"))
    pins = []
    for c in comps:
        if c["verdict"] == "context":
            continue
        st = STATUS[c["verdict"]]
        for room in (c.get("pins") or [])[:12]:
            pins.append(T.Pin(id=f"{c['key']}:{room}", anchor={"sid": sid, "room": room}, label=c["label"], status=st))
        a = c.get("anchor")
        if a and "room" not in a:
            pins.append(T.Pin(id=f"{c['key']}:evidence", anchor=a, label=c["label"], status=st))
    if pins:
        out.append(T.PinsOverlay(pins=pins))
    return out


def verdict(comps: list[dict]) -> T.Verdict:
    n = {k: sum(1 for c in comps if c["verdict"] == k) for k in STATUS}
    bad = [c for c in comps if c["verdict"] == "contradicted"]
    strong = [c for c in bad if c["confidence"] != "low"]
    checked = n["confirmed"] + n["contradicted"]
    if not checked:
        return T.Verdict(status="unknown", text=f"None of the {len(comps)} claims could be checked against this scan.")
    status = "fail" if strong else "warn" if bad else "pass"
    lead = ", ".join(c["label"].lower() for c in (strong or bad)[:3])
    text = (f"{n['confirmed']} claim{'' if n['confirmed'] == 1 else 's'} confirmed, {n['contradicted']} contradicted, {n['cannot verify']} cannot be "
            "verified." + (f" Disagreements: {lead}." if bad else ""))
    return T.Verdict(status=status, text=text)


def metrics(comps: list[dict], area_ft2: float | None) -> list[T.Metric]:
    src = T.Source(layer="matterport", method="geometry", confidence="high", note="Counts of claims by verdict")
    out = [T.Metric(id=k.replace(" ", "_"), label=TITLE[k].capitalize(), value=sum(1 for c in comps if c["verdict"] == k),
                    unit="claims", source=src) for k in ("confirmed", "contradicted", "cannot verify")]
    if area_ft2:
        out.append(T.Metric(id="measured_area", label="Measured interior area", value=round(area_ft2), unit="ft²",
                            source=T.Source(layer="matterport", method="geometry", confidence="high",
                                            note="Walled rooms, without voids, garages, patios, balconies or basements")))
    return out


def build(tool: str, sid: str, comps: list[dict], scan: dict, area_ft2: float | None, extra_assumptions=(),
          actions=()) -> T.ToolResult:
    pairs = [check_and_finding(tool, sid, c) for c in comps]
    return T.ToolResult(
        scope=T.ScanScope(sid=sid), verdict=verdict(comps), metrics=metrics(comps, area_ft2),
        checks=[p[0] for p in pairs], findings=[p[1] for p in pairs], overlays=overlays(sid, comps),
        assumptions=[T.Assumption(id="scan_scope", label=f"The scan covers {scan['scope']}: {scan['why']}",
                                  value=scan["scope"]), *extra_assumptions],
        actions=list(actions))
