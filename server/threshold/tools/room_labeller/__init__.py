"""Room labeller: an agent pass that walks a scan's panoramas and names every room, then writes the labels into
the overlay (store.py) that every other tool's plan carries. A person's correction wins and teaches: rooms of the
same scan, and similar rooms in sibling scans of the same property, that the correction makes doubtful are read
again with the corrected room shown as a reference."""
from __future__ import annotations

import time

from pydantic import BaseModel

from ...vision import reader
from .. import (
    Check,
    Finding,
    Legend,
    LensOverlay,
    Metric,
    Pin,
    PinsOverlay,
    RoomAnchor,
    ScanScope,
    Source,
    ToolError,
    ToolResult,
    Verdict,
    field,
    tool,
)
from ..types import Media
from . import facts, store

GEOM = Source(layer="matterport", method="geometry", confidence="high", note="Rooms and areas from the scan")
VISION = Source(layer="model", method="vision", confidence="medium", note="Vision model on the room's panorama")
MAX_RECHECK = 10


class Inputs(BaseModel):
    scan: str = field(source="selection.scan", description="Scan id")
    corrections: dict[str, str] = field({}, description="Room id -> the label a person says is right")
    include_labelled: bool = field(False, description="Also read rooms Matterport already labelled (to compare)")
    relabel: bool = field(False, description="Read rooms again even if the overlay already has a vision label")
    max_rooms: int = field(60, description="At most this many rooms are read by the model in one run", ge=1, le=200)


def vocabulary(sid: str) -> list[str]:
    return reader.HOME_LABELS if facts.scan_kind(sid) in ("house", "apartment_unit") else reader.COMMERCIAL_LABELS


def _entry(a: dict, **extra) -> dict:
    return {"label": a["label"], "confidence": a["confidence"], "label_source": "vision", "reason": a["reason"],
            "evidence": a["evidence"], "at": store.now(), **extra}


def _similar(fa: dict | None, fb: dict | None) -> bool:
    """Two rooms a correction to one should make us doubt about the other: area within a factor of two and,
    when both are known, the same number of doorways give or take one."""
    if not fa or not fb or not fa.get("area") or not fb.get("area"):
        return False
    if not 0.5 <= fa["area"] / fb["area"] <= 2:
        return False
    return fa["doors"] is None or fb["doors"] is None or abs(fa["doors"] - fb["doors"]) <= 1


def label_scan(ctx, sid: str, *, corrections: dict[str, str] | None = None, include_labelled: bool = False,
               relabel: bool = False, max_rooms: int = 60) -> dict:
    """Label the rooms of one scan and apply corrections. Returns what changed and the cost."""
    t0 = time.time()
    plan = store.apply(ctx.plan(sid))
    doc = store.load(sid)
    fx = facts.room_facts(plan)
    rooms = {r["id"]: r for r in facts.live_rooms(plan)}
    labels = vocabulary(sid)
    calls, changed = 0, []

    # 1. Corrections: the input's, and any user label the workspace put on the plan that the overlay lacks.
    fixes = {k: v for k, v in (corrections or {}).items() if k in rooms}
    for rid, r in rooms.items():
        e = doc["rooms"].get(rid)
        if r.get("label_source") == "user" and r.get("label") and not (e and e["label_source"] == "user" and e["label"] == r["label"]):
            fixes.setdefault(rid, r["label"])
    taught = []
    for rid, new in fixes.items():
        old = doc["rooms"].get(rid) or {}
        doc["rooms"][rid] = {"label": new, "confidence": "high", "label_source": "user", "at": store.now(),
                             "reason": "A person set this label", "evidence": old.get("evidence"), "was": old.get("label")}
        doc["corrections"].append({"room": rid, "from": old.get("label"), "to": new, "at": store.now()})
        taught.append((rid, old.get("label"), new, old.get("evidence")))
    if taught:
        ctx.step(f"Took {len(taught)} correction{'s' if len(taught) > 1 else ''} from you")

    # 2. First pass: rooms with no label yet.
    def wanted(rid: str) -> bool:
        r, e = rooms[rid], doc["rooms"].get(rid)
        if e and e["label_source"] == "user":
            return False
        if e and not relabel:
            return False
        return include_labelled or r.get("label") in (None, "Other") or r.get("label_source") == "vision"

    todo = [rid for rid in rooms if wanted(rid) and fx[rid]["panos"]][:max_rooms]
    no_pano = [rid for rid in rooms if wanted(rid) and not fx[rid]["panos"]]
    if todo:
        ctx.step(f"Reading {len(todo)} rooms from their panoramas")
        hints = {rid: facts.hint(fx[rid]) for rid in todo}
        for a in reader.label_rooms(plan, todo, labels=labels, context=facts.context(sid), hints=hints, views=3):
            doc["rooms"][a["room"]] = _entry(a, matterport_label=rooms[a["room"]].get("label")
                                             if rooms[a["room"]].get("label_source") == "matterport" else None)
        calls += len(todo)
    if no_pano and len(todo) < max_rooms:
        peek = no_pano[:max_rooms - len(todo)]
        ctx.step(f"Looking into {len(peek)} room{'s' if len(peek) > 1 else ''} with no panorama through a doorway")
        for a in reader.peek_rooms(plan, peek, labels=labels, context=facts.context(sid),
                                   hints={rid: facts.hint(fx[rid]) for rid in peek}):
            doc["rooms"][a["room"]] = _entry(a, peek=True)
        calls += len(peek)
        no_pano = [rid for rid in no_pano if rid not in doc["rooms"]]

    # 3. Re-check what each correction makes doubtful, here and in sibling scans of the property.
    rechecked = []
    for rid, old, new, ev in taught:
        if not ev:
            continue
        example = [{**ev, "label": new}]
        targets: list[tuple[str, list[str]]] = []
        mine = [k for k, e in doc["rooms"].items() if k != rid and e["label_source"] == "vision" and k in rooms
                and fx[k]["panos"] and _similar(fx.get(k), fx.get(rid)) and (e["label"] == old or (e["confidence"] != "high" and e["label"] != new))]
        targets.append((sid, mine))
        for s in facts.siblings(sid):
            sdoc = store.load(s)
            if not sdoc["rooms"] or not old:
                continue
            try:
                splan = store.apply(ctx.plan(s))
            except (ToolError, LookupError):  # a sibling that will not load is skipped, not fatal
                continue
            sfx = facts.room_facts(splan)
            targets.append((s, [k for k, e in sdoc["rooms"].items() if e["label_source"] == "vision" and e["label"] == old
                                and k in sfx and sfx[k]["panos"] and _similar(sfx.get(k), fx.get(rid))]))
        budget = MAX_RECHECK
        for s, ids in targets:
            ids = ids[:budget]
            if not ids:
                continue
            budget -= len(ids)
            splan = plan if s == sid else store.apply(ctx.plan(s))
            sdoc = doc if s == sid else store.load(s)
            sfx = fx if s == sid else facts.room_facts(splan)
            ctx.step(f"Re-checking {len(ids)} room{'s' if len(ids) > 1 else ''} in {'this scan' if s == sid else facts.scan_name(s)} "
                     f"that your correction to '{new}' makes doubtful")
            for a in reader.label_rooms(splan, ids, labels=labels, context=facts.context(s),
                                        hints={k: facts.hint(sfx[k]) for k in ids if k in sfx}, examples=example, views=3):
                before = sdoc["rooms"][a["room"]]["label"]
                sdoc["rooms"][a["room"]] = _entry(a, rechecked_after=rid, was=before)
                rechecked.append({"sid": s, "room": a["room"], "from": before, "to": a["label"]})
            calls += len(ids)
            if s != sid:
                store.save(sdoc)
    changed = [x for x in rechecked if x["from"] != x["to"]]
    store.save(doc)
    return {"doc": doc, "plan": store.apply(plan), "facts": fx, "read": todo, "no_pano": no_pano, "rechecked": rechecked,
            "changed": changed, "taught": taught, "calls": calls, "seconds": time.time() - t0}


def ensure_labels(ctx, sid: str, label_with_vision: bool = True) -> dict:
    """The plan with overlay labels, after labelling any unlabelled rooms first when allowed. For other tools."""
    plan = store.apply(ctx.plan(sid))
    if label_with_vision and any(r.get("label") in (None, "Other") for r in facts.live_rooms(plan)):
        plan = label_scan(ctx, sid)["plan"]
    return plan


@tool(id="room_labeller", title="Room labeller", icon="tag",
      summary="Names every room of a commercial space from its panoramas, shows what decided each call, and learns "
              "from your corrections.",
      model_description="Walk one scan's panoramas and label every room (open office, private office, conference room, "
                        "restroom, gym, laundry, ...), with confidence, the panorama that shows it and the reason. Writes "
                        "the labels so every other tool sees them. Pass `corrections` {room id: label} when the person "
                        "corrects a room; similar rooms here and in sibling scans are re-checked. Slow on first run "
                        "(one model call per room), cached after.",
      personas=["office_tenant", "costar_researcher", "apartment_manager"],
      requires=[{"layer": "matterport.panos"}, {"layer": "matterport.rooms"},
                {"layer": "costar.property", "need": "optional", "fallback": "labels without the property type"}],
      blocks=["VerdictHeader", "MetricRow", "EvidenceStrip", "FloorPlanMini", "StepLog"], overlays=["pins", "lens"],
      annotations={"read_only": False, "cost": "slow"},
      examples=["What rooms does this office have?", "Label the rooms in this suite", "That room is a kitchen, not storage"])
def run(ctx, inputs: Inputs) -> ToolResult:
    sid = inputs.scan
    out = label_scan(ctx, sid, corrections=inputs.corrections, include_labelled=inputs.include_labelled,
                     relabel=inputs.relabel, max_rooms=inputs.max_rooms)
    plan, doc = out["plan"], out["doc"]
    rooms = facts.live_rooms(plan)
    findings, pins, conf = [], [], {}
    for r in rooms:
        e = doc["rooms"].get(r["id"])
        if not e:
            if r.get("label_source") == "matterport":
                continue
            findings.append(Finding(id=f"room_labeller:{sid}:{r['id']}", title="Room without a label", status="unknown",
                                    detail="No panorama stands in this room or sees into it, so it was not read. "
                                           "Label it yourself to teach me.",
                                    anchor=RoomAnchor(sid=sid, room=r["id"]), source=GEOM))
            pins.append(Pin(id=r["id"], anchor=RoomAnchor(sid=sid, room=r["id"]), label="no panorama", status="unknown"))
            continue
        user = e["label_source"] == "user"
        ev = e.get("evidence")
        status = "pass" if user or e["confidence"] == "high" else "warn"
        detail = (f"You labelled this room '{e['label']}'." if user else
                  f"{e['reason']} Confidence {e['confidence']}. Measured: {facts.hint(out['facts'][r['id']])}.")
        if e.get("peek"):
            detail = "Seen through a doorway from outside the room. " + detail
        if e.get("was") and e["was"] != e["label"]:
            detail += f" Was '{e['was']}'" + (" before a correction to a similar room." if e.get("rechecked_after") else ".")
        findings.append(Finding(
            id=f"room_labeller:{sid}:{r['id']}", title=f"{e['label'].capitalize()}", status=status, detail=detail,
            anchor=RoomAnchor(sid=sid, room=r["id"]),
            source=Source(layer="model", method="vision", confidence=e["confidence"],
                          note=(ev and f"Panorama {ev['pano']} face {ev['face']}") or None) if not user else
            Source(layer="model", method="lookup", confidence="high", note="Your correction"),
            media=[Media(kind="pano", ref=f"{ev['sid']}/{ev['pano']}/{ev['face']}")] if ev else []))
        pins.append(Pin(id=r["id"], anchor=RoomAnchor(sid=sid, room=r["id"]), label=e["label"], status=status))
        conf[r["id"]] = 1.0 if user else store.CONFIDENCE[e["confidence"]]

    labelled = [r for r in rooms if r.get("label")]
    by: dict[str, int] = {}
    for r in labelled:
        by[r["label"]] = by.get(r["label"], 0) + 1
    vis = [e for e in doc["rooms"].values() if e["label_source"] == "vision"]
    metrics = [Metric(id="rooms", label="Rooms", value=len(rooms), unit="", source=GEOM),
               Metric(id="labelled", label="Rooms with a label", value=len(labelled), unit="", source=VISION),
               Metric(id="high_confidence", label="Vision labels at high confidence",
                      value=round(100 * sum(e["confidence"] == "high" for e in vis) / len(vis)) if vis else None, unit="%", source=VISION),
               Metric(id="model_calls", label="Rooms read by the model this run", value=out["calls"], unit="", source=VISION),
               Metric(id="seconds", label="Seconds this run", value=round(out["seconds"], 1), unit="s", source=VISION)]
    metrics += [Metric(id=f"count.{k}", label=k, value=v, unit="rooms", source=VISION) for k, v in sorted(by.items(), key=lambda kv: -kv[1])]
    share = len(labelled) / len(rooms) if rooms else 0
    checks = [Check(id="coverage", rule="Every room has a label", measured=round(100 * share), threshold=100, unit="%",
                    status="pass" if share == 1 else "warn")]
    overlays = []
    if pins:
        overlays.append(PinsOverlay(pins=pins))
    if conf:
        overlays.append(LensOverlay(values=conf, ramp="sequential",
                                    legend=Legend(title="Label confidence", unit="", min=0, max=1)))
    kinds = ", ".join(f"{v} {k}" for k, v in sorted(by.items(), key=lambda kv: -kv[1])[:5]) or "none"
    text = f"{len(labelled)} of {len(rooms)} rooms labelled: {kinds}."
    if out["changed"]:
        text += f" Your correction changed {len(out['changed'])} other room{'s' if len(out['changed']) > 1 else ''}."
    elif out["rechecked"]:
        text += f" Re-checked {len(out['rechecked'])} similar rooms after your correction; none changed."
    if out["no_pano"]:
        text += f" {len(out['no_pano'])} could not be seen from any panorama."
    q = facts.quality(plan)
    if not q["walls"]:
        text += " No wall graph: labels come from panoramas alone, without doors or windows."
    return ToolResult(scope=ScanScope(sid=sid), verdict=Verdict(status="pass" if share == 1 else "warn", text=text),
                      metrics=metrics, checks=checks, findings=findings, overlays=overlays)
