"""Amenity census: for an apartment community, which amenities its scans show, with counts of gym equipment and
laundry machines, each with the panorama that proves it, beside what the listing claims (scan titles and
photo captions)."""
from __future__ import annotations

import copy
import re

import numpy as np
from pydantic import BaseModel

from ...sources import costar
from ...vision import reader
from .. import (
    Check,
    Finding,
    Metric,
    NotApplicable,
    Pin,
    PinsOverlay,
    RoomAnchor,
    Source,
    ToolError,
    ToolResult,
    Verdict,
    field,
    tool,
)
from ..room_labeller import facts, label_scan
from ..types import AddressScope, Media, ScansScope

VISION = Source(layer="model", method="vision", confidence="medium", note="Room type from the room labeller")
RECORD = Source(layer="costar", method="lookup", confidence="high", note="CoStar property record and scan titles")

# room label -> amenity
AMENITY_OF = {"gym": "fitness center", "pool": "pool", "laundry": "laundry room", "lounge or clubroom": "lounge or clubroom",
              "business center": "business center", "mail room": "mail or package room", "playground": "playground",
              "media room": "media room", "conference room": "conference room", "leasing office": "leasing office",
              "open office": "coworking space", "private office": "coworking space", "phone booth": "coworking space",
              "outdoor area": "outdoor area"}
# words in a title or caption -> amenity
CLAIM_WORDS = [
    ("fitness center", r"fitness|gym|athletic|yoga|spin|cardio|exercise|wellness"),
    ("pool", r"\bpool|\bspa\b|swim"),
    ("laundry room", r"laundry"),
    ("lounge or clubroom", r"lounge|club ?(house|room)|clubhouse|resident (club|center)|social|sky ?lounge"),
    ("business center", r"business|cyber|e-lounge|wifi|wi-fi|library|computer"),
    ("coworking space", r"co-?work"),
    ("mail or package room", r"mail|package|parcel"),
    ("playground", r"playground|play ?area|tot lot|kids"),
    ("media room", r"theat|cinema|media|screen|movie"),
    ("conference room", r"conference|meeting"),
    ("outdoor area", r"courtyard|terrace|deck|rooftop|bbq|barbe|grill|picnic|garden|patio"),
    ("dog park or pet spa", r"\bdog|\bpet"),
    ("game room", r"game"),
    ("leasing office", r"leasing"),
]
COUNT = {
    "fitness center": ["treadmill", "elliptical or stair climber", "exercise bike or rower", "weight machine or cable station",
                       "weight bench", "squat or power rack", "dumbbell rack"],
    "laundry room": ["washer", "dryer", "stacked washer and dryer", "stacked pair of dryers"],
    "mail or package room": ["parcel locker bank", "mailbox bank"],
}


def plural(word: str, n: int) -> str:
    """The last word made plural: "2 squat or power racks", "3 weight benches"."""
    if n == 1 or word.endswith("s"):
        return word
    return word + ("es" if word.endswith(("ch", "sh", "x")) else "s")


def claimed(text: str) -> set[str]:
    return {a for a, pat in CLAIM_WORDS if re.search(pat, text or "", re.IGNORECASE)}


class Inputs(BaseModel):
    scan: str | None = field(None, source="selection.scan", description="Any scan of the community")
    property: int | None = field(None, description="CoStar property id of the community")
    max_scans_read: int = field(8, description="At most this many amenity scans are read by the model", ge=1, le=30)
    count_equipment: bool = field(True, description="Count gym equipment and laundry machines (one model call per view)")


def _whole_scan(plan: dict) -> dict:
    """A plan whose panoramas all stand in one room, for scans that have panoramas and no rooms."""
    p = copy.deepcopy(plan)
    pos = np.array([x["position"][:2] for x in p["panos"]], float) if p["panos"] else np.zeros((1, 2))
    p["rooms"] = [{"id": "whole-scan", "floor": (p["floors"] or [{}])[0].get("id"), "label": None, "polygon": [],
                   "area": None, "center": pos.mean(axis=0).tolist()}]
    for x in p["panos"]:
        x["room"] = "whole-scan"
    return p


def _spread(panos: list[dict], n: int) -> list[str]:
    """The central panorama and then the ones farthest from those already chosen."""
    if not panos:
        return []
    chosen = [panos[0]]
    while len(chosen) < min(n, len(panos)):
        rest = [p for p in panos if p not in chosen]
        chosen.append(max(rest, key=lambda p: min(np.hypot(p["position"][0] - c["position"][0], p["position"][1] - c["position"][1])
                                                     for c in chosen)))
    return [p["id"] for p in chosen]


def read_scan(ctx, sid: str, count_equipment: bool) -> list[dict]:
    """The amenities one scan shows: [{amenity, sid, room, label, confidence, reason, evidence, counts}]."""
    plan = ctx.plan(sid)
    rooms = facts.live_rooms(plan)
    if rooms:
        out = label_scan(ctx, sid)
        plan, doc = out["plan"], out["doc"]
        spaces = [(r, doc["rooms"].get(r["id"]) or {"label": r.get("label"), "confidence": "high", "reason": "Matterport label",
                                                    "evidence": None}) for r in facts.live_rooms(plan) if r.get("label")]
    elif plan["panos"]:
        plan = _whole_scan(plan)
        a = reader.label_rooms(plan, ["whole-scan"], labels=reader.COMMERCIAL_LABELS, context=facts.context(sid))[0]
        spaces = [(plan["rooms"][0], a)]
    else:
        return []
    found = []
    for r, e in spaces:
        am = AMENITY_OF.get(e["label"])
        if not am:
            continue
        counts = {}
        if count_equipment and am in COUNT:
            panos = reader.room_panos(plan, r)
            ctx.step(f"Counting {am} equipment in {facts.scan_name(sid)} from {min(3, len(panos))} views")
            # Each view is a full 360 degrees, so the count is the best single view's, per item. Summing views
            # double-counted where detections could not be merged (no wall graph): 10 washers seen for about 8.
            for pid_ in _spread(panos, 3):
                one: dict[str, int] = {}
                for d in reader.find_objects(plan, labels=COUNT[am], panos=[pid_]):
                    one[d["label"]] = one.get(d["label"], 0) + 1
                for k, v in one.items():
                    counts[k] = max(counts.get(k, 0), v)
            if am == "laundry room":  # a washer-dryer stack is one of each; a dryer stack is two dryers
                n = counts.pop("stacked washer and dryer", 0)
                d2 = counts.pop("stacked pair of dryers", 0)
                if n or d2:
                    counts["washer"] = counts.get("washer", 0) + n
                    counts["dryer"] = counts.get("dryer", 0) + n + 2 * d2
        found.append({"amenity": am, "sid": sid, "room": None if r["id"] == "whole-scan" else r["id"], "label": e["label"],
                      "confidence": e["confidence"], "reason": e.get("reason"), "evidence": e.get("evidence"), "counts": counts})
    return found


# what to look for when a tour's title names an amenity its rooms were not labelled as
CUE = {"pool": "swimming pool", "fitness center": "treadmill, exercise bike or weight machine",
       "business center": "computer workstation", "coworking space": "work desk with office chair",
       "game room": "pool table, shuffleboard or game table", "laundry room": "washer or dryer",
       "mail or package room": "mailboxes or parcel lockers", "playground": "playground equipment",
       "media room": "theater seating facing a large screen", "outdoor area": "outdoor grill or patio furniture",
       "dog park or pet spa": "dog park or pet washing station", "lounge or clubroom": "sofa or lounge seating",
       "conference room": "conference table with chairs"}


def look_for(ctx, sid: str, am: str) -> dict | None:
    """Look for an amenity's telltale object in two spread-out views of a tour; a seen entry, or None."""
    plan = ctx.plan(sid)
    panos = [p for p in plan["panos"] if p.get("rotation")]
    if not panos:
        return None
    c = np.mean([p["position"][:2] for p in panos], axis=0)
    panos.sort(key=lambda p: float(np.hypot(p["position"][0] - c[0], p["position"][1] - c[1])))
    ctx.step(f"Looking for {CUE[am]} in {facts.scan_name(sid)}")
    dets = reader.find_objects(plan, labels=[CUE[am]], panos=_spread(panos, 2))
    if not dets:
        return None
    d = min(dets, key=lambda d: {"high": 0, "medium": 1, "low": 2}[d["finding"]["source"]["confidence"]])
    sid_, pano, face = d["finding"]["media"][0]["ref"].split("/")
    return {"amenity": am, "sid": sid, "room": d.get("room"), "label": "seen in the tour", "confidence": d["finding"]["source"]["confidence"],
            "reason": f"A {CUE[am]} is in view ({d['finding']['detail']}).", "evidence": {"sid": sid_, "pano": pano, "face": int(face)},
            "counts": {}}


@tool(id="amenity_census", title="Amenity census", icon="dumbbell",
      summary="Finds and counts a community's amenities in its scans (gym equipment, laundry machines, pool, lounge, "
              "business centre, mail room, playground) and sets them beside what the listing claims.",
      model_description="For one apartment community (a scan of it, or its CoStar property id), read its amenity scans and "
                        "list each amenity seen with evidence and counts (gym equipment, washers and dryers, parcel lockers), "
                        "beside the listing's claims (scan titles, photo captions). Flags claims no scan shows and amenities "
                        "the listing never mentions. Slow on first run.",
      personas=["apartment_manager", "costar_researcher", "renter_listing"],
      requires=[{"layer": "costar.property"}, {"layer": "matterport.panos"}],
      blocks=["VerdictHeader", "MetricRow", "CheckList", "MiniChart", "EvidenceStrip", "StepLog"],
      overlays=["pins"], annotations={"cost": "slow"},
      examples=["What amenities does this community really have?", "How many treadmills are in the gym?"])
def run(ctx, inputs: Inputs) -> ToolResult:
    pid = inputs.property or (facts.property_id(inputs.scan) if inputs.scan else None)
    if not pid:
        raise NotApplicable("This scan does not belong to an apartment community in the CoStar kit, so there are no shared "
                            "amenities to count. Pick a scan of a community, or give its property id.")
    sids = costar.scans_of_property(pid)
    address = costar.joins()["property_address"].get(pid) or str(pid)
    names = {s: facts.scan_name(s) for s in sids}
    kinds = {s: facts.scan_kind(s) for s in sids}
    units = [s for s in sids if kinds[s] in ("apartment_unit", "house")]
    cands = sorted((s for s in sids if s not in units), key=lambda s: kinds[s] != "amenity")
    read, skipped = cands[:inputs.max_scans_read], cands[inputs.max_scans_read:]
    ctx.step(f"{len(sids)} scans of {address}: {len(units)} units, {len(cands)} shared spaces; reading {len(read)}")

    seen: list[dict] = []
    for s in read:
        try:
            seen += read_scan(ctx, s, inputs.count_equipment)
        except ToolError:
            ctx.step(f"Could not load {names[s]}")

    # Claims: scan titles (the operator named each tour), photo captions, and the record's amenity id count.
    prop = costar.get("commercial-property", pid) or {}
    title_claims = {s: claimed(names[s]) for s in sids if s not in units}
    caption_claims: dict[str, list[str]] = {}
    for a in prop.get("attachments") or []:
        for am in claimed(a.get("caption") or ""):
            caption_claims.setdefault(am, []).append(a.get("caption"))
    claims = {am for c in title_claims.values() for am in c} | set(caption_claims)
    ctx.step(f"The listing names {len(claims)} kinds of amenity in tour titles and photo captions")

    by_am: dict[str, list[dict]] = {}
    for x in seen:
        by_am.setdefault(x["amenity"], []).append(x)
    # A tour titled for an amenity that its rooms were not labelled as: look for the amenity itself in that tour.
    for am in sorted(claims - set(by_am)):
        for s in [s for s, c in title_claims.items() if am in c and s in read and am in CUE]:
            hit = look_for(ctx, s, am)
            if hit:
                by_am.setdefault(am, []).append(hit)
                break
    findings, checks, pins, metrics = [], [], [], []
    for am, xs in sorted(by_am.items()):
        best = min(xs, key=lambda x: {"high": 0, "medium": 1, "low": 2}[x["confidence"]])
        counts: dict[str, int] = {}
        for x in xs:
            for k, v in x["counts"].items():
                counts[k] = counts.get(k, 0) + v
        where = sorted({names[x["sid"]] for x in xs})
        counted = ", ".join(f"{v} {plural(k, v)}" for k, v in counts.items())
        src = [w for w in (("tour title" if any(am in title_claims.get(x["sid"], set()) for x in xs) or
                            any(am in c for c in title_claims.values()) else None),
                           ("photo caption" if am in caption_claims else None)) if w]
        status = "pass" if src else "warn"
        fid = f"amenity_census:{pid}:{am.replace(' ', '_')}"
        ev = best["evidence"]
        findings.append(Finding(
            id=fid, title=am.capitalize(), status=status,
            detail=f"Seen in {', '.join(where)}: {best['reason'] or best['label']}" +
                   (f" Counted in the best of up to three 360-degree views, so machines hidden from every single view are missed: {counted}." if counted else "") +
                   (f" The listing names it ({', '.join(src)})." if src else " The listing does not name it: an amenity to market."),
            anchor=RoomAnchor(sid=best["sid"], room=best["room"]) if best["room"] else None,
            source=Source(layer="model", method="vision", confidence=best["confidence"],
                          note="Room type and equipment counts from the vision model; counts can miss machines hidden from every view"),
            media=[Media(kind="pano", ref=f"{ev['sid']}/{ev['pano']}/{ev['face']}")] if ev else []))
        if best["room"]:
            pins.append(Pin(id=f"{best['sid']}:{best['room']}", anchor=RoomAnchor(sid=best["sid"], room=best["room"]),
                            label=am + (f", {counted}" if counted else ""), status=status))
        for k, v in counts.items():
            metrics.append(Metric(id=f"count.{k.replace(' ', '_')}", label=k.capitalize(), value=v, unit="",
                                  source=Source(layer="model", method="vision", confidence="medium",
                                                note=f"Counted in {', '.join(where)}")))
    for am in sorted(claims):
        named = [names[s] for s, c in title_claims.items() if am in c]
        caps = caption_claims.get(am, [])
        said = "; ".join(x for x in (f"tour titled {', '.join(named[:3])}" if named else "",
                                     f"photo captioned {caps[0]!r}" if caps else "") if x)
        if am in by_am:
            st, measured = "pass", 1
        else:
            unread = [s for s, c in title_claims.items() if am in c and s in skipped]
            read_titled = [s for s, c in title_claims.items() if am in c and s in read]
            st = "unknown" if unread or not read_titled else "warn"
            measured = None if st == "unknown" else 0
            fid = f"amenity_census:{pid}:claim_{am.replace(' ', '_')}"
            detail = (f"The listing claims it ({said}). " +
                      ("Its tour was not read in this run; raise the scan limit to check it." if unread else
                       "No scan read shows it: the tour of that name shows something else." if read_titled else
                       "No scan of the community covers it, so it cannot be checked from the scans."))
            findings.append(Finding(id=fid, title=f"Claimed, not seen: {am}", status=st, detail=detail, anchor=None, source=RECORD))
        checks.append(Check(id=f"claim.{am.replace(' ', '_')}", rule=f"Listing claims {am} ({said})", measured=measured,
                            threshold=1, unit="seen", status=st))
    unlisted = [am for am in by_am if am not in claims]
    amen_ids = len(prop.get("amenities") or [])
    metrics = [Metric(id="seen", label="Amenities seen in the scans", value=len(by_am), unit="", source=VISION),
               Metric(id="claimed", label="Amenities the listing names", value=len(claims), unit="", source=RECORD),
               Metric(id="confirmed", label="Claims the scans confirm", value=len(set(by_am) & claims), unit="", source=VISION),
               Metric(id="scans_read", label="Shared-space scans read", value=len(read), unit="", source=VISION),
               *metrics]
    if amen_ids:
        metrics.append(Metric(id="record_amenity_ids", label="Amenity codes on the CoStar record (no catalog to decode)",
                              value=amen_ids, unit="", source=RECORD))
    missing = [c for c in checks if c.status == "warn"]
    status = "warn" if missing else "pass" if by_am else "unknown"
    text = (f"{address}: {len(by_am)} amenities seen in {len(read)} scans ({', '.join(sorted(by_am)) or 'none'}); "
            f"{len(set(by_am) & claims)} of {len(claims)} listed amenities confirmed.")
    if not read:
        text = (f"{address}: its {len(sids)} scan{'s are' if len(sids) != 1 else ' is a'} unit{'s' if len(sids) != 1 else ''}, "
                f"none of a shared space, so the {len(claims)} amenities the listing names cannot be checked.")
    if missing:
        text += f" {len(missing)} claimed but not seen."
    if unlisted:
        text += f" Not in the listing: {', '.join(unlisted)}."
    if skipped:
        text += f" {len(skipped)} shared-space scans not read (limit {inputs.max_scans_read})."
    scope = ScansScope(sids=read) if read else AddressScope(address=address)
    return ToolResult(scope=scope, verdict=Verdict(status=status, text=text), metrics=metrics, checks=checks,
                      findings=findings, overlays=[PinsOverlay(pins=pins)] if pins else [])
