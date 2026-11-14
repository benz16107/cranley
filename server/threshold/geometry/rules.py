"""Rule packs: each standard is data (geometry/packs/<id>.json); this module measures and judges it.

A rule names a `measure` (one of MEASURES), a `threshold` (a number or "$param"), a `unit`, a `compare`
("at_least" or "at_most"), a `severity` ("required" fails the verdict, "advisory" only warns), the plain
`text`, and the `standard` it comes from. Results are 'likely pass', 'likely fail' or 'measure on site'
within the rule's tolerance (default SCAN_TOLERANCE_M), because the scan gives wall openings, not clear widths."""
from __future__ import annotations

import json
import math
import pathlib
from collections.abc import Callable

from ._plan import (
    SCAN_TOLERANCE_M,
    VERDICT_STATUS,
    cached,
    clear_width,
    floor_z,
    geo_source,
    implausible,
    judge,
    polygons,
    room_label,
    rooms_by_id,
    unavailable,
)
from .fit import carry, turning_space
from .graph import room_graph
from .routes import reach, route

PACK_DIR = pathlib.Path(__file__).parent / "packs"
SKIP_DOOR_LABELS = {"Closet", "Void", "Pantry"}
STAIR_STEP_M = 0.4
WORST = ["likely fail", "measure on site", "likely pass"]


def list_packs() -> list[dict]:
    return [{k: p[k] for k in ("id", "title", "summary", "params")} for p in map(load_pack, _pack_ids())]


def _pack_ids() -> list[str]:
    return sorted(f.stem for f in PACK_DIR.glob("*.json"))


def load_pack(pack_id: str) -> dict:
    f = PACK_DIR / f"{pack_id}.json"
    if not f.exists():
        raise KeyError(f"No rule pack {pack_id!r}; packs: {_pack_ids()}")
    return json.loads(f.read_text())


# ---- measures: each returns items {measured, anchor, label, detail, point?, result?} ----

def _graph(plan):
    return cached(plan, "graph", lambda: room_graph(plan))


def _targets(plan: dict, rule: dict) -> list[dict]:
    want = set(rule.get("targets") or [])
    polys = polygons(plan)
    return [r for r in plan.get("rooms") or [] if (r.get("label") in want if want else r.get("label") != "Void")
            and polys[r["id"]] is not None]


def _door_items(plan, rule, params, skip_labels=SKIP_DOOR_LABELS):
    g = _graph(plan)
    if not g["available"]:
        return None
    rooms = rooms_by_id(plan)
    for d in g["links"] + g["entrances"]:
        if d["kind"] == "invisible":
            continue
        labels = {rooms[r].get("label") for r in d.get("rooms") or [d["room"]]}
        if labels and labels <= skip_labels:
            continue
        yield d, " and ".join(sorted(room_label(rooms[r]) for r in d.get("rooms") or [d["room"]]))


def m_door_clear_width(plan, rule, params):
    items = _door_items(plan, rule, params)
    if items is None:
        return None
    return [{"measured": clear_width(d), "anchor": {"opening": d["opening"]}, "label": f"Door, {names}",
             "point": d["center"], "result": "measure on site" if implausible(d) else None,
             "detail": f"The scan records {d['width'] * 100:.0f} cm, narrower than any door: a data error in the "
                       f"wall graph, not a narrow door. Measure on site." if implausible(d) else
                       f"Opening {d['width']:.2f} m in the wall, about {clear_width(d):.2f} m clear once a door is hung."}
            for d, names in items]


def m_threshold_step(plan, rule, params):
    items = _door_items(plan, rule, params, skip_labels={"Void"})
    if items is None:
        return None
    fz = floor_z(plan)
    out = []
    for d, names in items:
        if d.get("sill") is None:
            continue
        step = abs(d["sill"] - fz.get(d["floor"], 0.0))
        stair = step > STAIR_STEP_M  # a stair opening or a door filed on the wrong floor, not a threshold
        out.append({"measured": step, "anchor": {"opening": d["opening"]}, "label": f"Sill, {names}",
                    "point": d["center"], "result": "measure on site" if stair else None,
                    "detail": f"Sill {step:.2f} m off this storey's floor level: probably stairs or a split "
                              f"level, check on site." if stair else
                              f"Sill {step * 100:.0f} cm from the floor level of this storey."})
    return out


def m_route_corridor_width(plan, rule, params):
    if not _graph(plan)["available"]:
        return None
    out = []
    for r in _targets(plan, rule):
        rt = route(plan, "entrance", r["id"], floor=r["floor"])
        if not rt["available"]:
            out.append({"measured": None, "anchor": {"room": r["id"]}, "label": f"Route to {room_label(r)}",
                        "detail": rt["reason"]})
            continue
        corridor = [c for c in rt["chokes"] if c["kind"] == "corridor"]
        leg_w = [l["min_width"] for l in rt["legs"] if l["min_width"] is not None]
        if corridor:
            worst = min(corridor, key=lambda c: c["width"])
            w, pt = worst["width"], worst["point"]
        else:
            w, pt = (min(leg_w) if leg_w else None), None
        out.append({"measured": w, "anchor": {"room": r["id"]}, "label": f"Route to {room_label(r)}", "point": pt,
                    "detail": f"{rt['length_m']:.1f} m from the entrance, through {len(rt['doors'])} doors; "
                              f"narrowest wall-to-wall width {w:.2f} m." if w is not None else
                              f"{rt['length_m']:.1f} m from the entrance; no walls close to the route."})
    return out


def m_bed_to_bath_width(plan, rule, params):
    if not _graph(plan)["available"]:
        return None
    rooms = plan.get("rooms") or []
    polys = polygons(plan)
    out = []
    for bed in (r for r in rooms if r.get("label") == "Bedroom" and polys[r["id"]] is not None):
        routes = [route(plan, bed["id"], b["id"]) for b in rooms
                  if b.get("label") == "Bathroom" and b["floor"] == bed["floor"] and polys[b["id"]] is not None]
        routes = [r for r in routes if r["available"]]
        if not routes:
            out.append({"measured": None, "anchor": {"room": bed["id"]}, "label": "Bedroom to bathroom",
                        "detail": "No bathroom reachable on this floor in the wall graph."})
            continue
        rt = min(routes, key=lambda r: r["length_m"])
        widths = [c["width"] for c in rt["chokes"] if c["width"] is not None]
        widths += [l["min_width"] for l in rt["legs"] if l["min_width"] is not None]
        w = min(widths) if widths else None
        nb = rt["narrowest"]
        out.append({"measured": w, "anchor": {"room": bed["id"]}, "label": "Bedroom to bathroom",
                    "point": nb["point"] if nb else None,
                    "detail": f"{rt['length_m']:.1f} m with {len(rt['doors'])} doors; narrowest {w:.2f} m."
                    if w is not None else f"{rt['length_m']:.1f} m."})
    return out


def m_turning_diameter(plan, rule, params):
    out = []
    for r in _targets(plan, rule):
        t = turning_space(plan, r["id"])
        out.append({"measured": t["diameter"], "anchor": {"room": r["id"]}, "label": room_label(r),
                    "point": t["center"], "detail": f"Largest circle in the empty room: {t['diameter']:.2f} m."})
    return out


def m_reach_width(plan, rule, params):
    width = _value(rule["threshold"], params)
    rc = reach(plan, width)
    if not rc["available"]:
        return None
    out = []
    for r in rc["rooms"]:
        if r["void"]:
            continue
        if not r["connected"]:
            out.append({"measured": None, "anchor": {"room": r["room"]}, "label": r["label"],
                        "detail": "Not connected to an entrance in the wall graph (no door recorded, or upstairs)."})
            continue
        bw = r["bottleneck_width"]
        out.append({"measured": bw if bw is not None else 99.0, "anchor": {"room": r["room"]}, "label": r["label"],
                    "detail": f"Narrowest door on the widest way in: {bw:.2f} m clear." if bw is not None
                    else "Starting room."})
    return out


def m_carry_box(plan, rule, params):
    if not _graph(plan)["available"]:
        return None
    box = tuple(_value(v, params) for v in rule["box"])
    out = []
    for r in _targets(plan, rule):
        c = carry(plan, "entrance", r["id"], box, floor=r["floor"], flat=bool(rule.get("flat")))
        if not c["available"]:
            out.append({"measured": None, "anchor": {"room": r["id"]}, "label": f"To {room_label(r)}",
                        "detail": c["reason"]})
            continue
        parts = [(d["slack"], d["center"], f"door {d['clear_width']:.2f} m wide") for d in c["doors"]] + \
                [(k["slack"] if k["slack"] is not None else -math.inf, k["point"],
                  f"{k['angle_deg']:.0f} degree corner") for k in c["corners"]]
        if not parts:
            out.append({"measured": 99.0, "anchor": {"room": r["id"]}, "label": f"To {room_label(r)}",
                        "detail": "No door or corner on the way."})
            continue
        slack, pt, what = min(parts, key=lambda p: p[0])
        out.append({"measured": slack if slack != -math.inf else None, "anchor": {"room": r["id"]},
                    "label": f"To {room_label(r)}", "point": pt,
                    "result": c["result"] if slack == -math.inf else None,
                    "detail": f"Tightest spot: {what}, {slack * 100:+.0f} cm to spare." if slack != -math.inf
                    else f"Tightest spot: {what}; the object does not fit under the ceiling in any orientation."})
    return out


def m_entry_floor_rooms(plan, rule, params):
    g = _graph(plan)
    floors = {e["floor"] for e in g.get("entrances") or []} if g["available"] else set()
    note = ""
    if not floors and plan.get("floors"):
        floors = {min(plan["floors"], key=lambda f: f.get("sequence") or 0)["id"]}
        note = " No entrance in the scan, so the lowest floor stands in for the entry floor."
    out = []
    for label in rule.get("targets") or []:
        n = sum(1 for r in plan.get("rooms") or [] if r.get("label") == label and r["floor"] in floors)
        out.append({"measured": n, "anchor": {}, "label": f"{label} on the entry floor",
                    "detail": f"{n} {label.lower()}(s) on the entry floor.{note}"})
    return out


def m_stairs_present(plan, rule, params):
    n = len(plan.get("floors") or [])
    return [{"measured": n, "anchor": {}, "label": "Stairs", "result": "measure on site" if n > 1 else "likely pass",
             "detail": f"{n} floors: check the stairs for handrails and lighting on site." if n > 1
             else "One floor in the scan, so no stairs inside."}]


MEASURES: dict[str, Callable] = {name[2:]: fn for name, fn in globals().items() if name.startswith("m_")}


# ---- evaluation ----

def _value(v, params: dict):
    return float(params[v[1:]]) if isinstance(v, str) and v.startswith("$") else v


def evaluate_pack(plan: dict, pack_id: str, params: dict | None = None) -> dict:
    """Evaluate one rule pack. Returns the Contract 3 parts a tool needs: verdict, checks, findings,
    assumptions (the pack's parameters, editable) and a pins overlay of every finding."""
    pack = load_pack(pack_id)
    vals = {k: p["default"] for k, p in pack.get("params", {}).items()} | (params or {})
    sid = plan.get("sid")
    checks, findings = [], []
    for rule in pack["rules"]:
        items = MEASURES[rule["measure"]](plan, rule, vals)
        thr = _value(rule["threshold"], vals)
        tol = rule.get("tolerance", SCAN_TOLERANCE_M)
        at_least = rule["compare"] == "at_least"
        cid = f"{pack_id}.{rule['id']}"
        if not items:
            res = "not available"
            reason = "This scan has no wall graph." if items is None else "Nothing in this scan for this rule to test."
            checks.append(_check(cid, rule, None, thr, res, tol, [], reason))
            continue
        judged = [(it, it.get("result") or judge(it["measured"], thr, tol, at_least)) for it in items]
        mv = [it["measured"] for it in items if it["measured"] is not None]
        measured = (min(mv) if at_least else max(mv)) if mv else None
        known = [r for _, r in judged if r != "not available"]  # unknown items stay as findings
        res = min(known, key=WORST.index) if known else "not available"
        fids = []
        for n, (it, r) in enumerate(judged):
            if r == "likely pass":
                continue
            fid = f"{cid}.{n}"
            fids.append(fid)
            anchor = {"sid": sid, **it["anchor"]}
            if "opening" not in anchor and "room" not in anchor and it.get("point"):
                anchor["point"] = [*it["point"][:2], it["point"][2] if len(it["point"]) > 2 else 0.0]
            findings.append({"id": fid, "title": f"{it['label']}: {r}", "status": VERDICT_STATUS[r],
                             "detail": it["detail"], "anchor": anchor, "media": [], "result": r,
                             "point": it.get("point"),
                             "source": geo_source(f"{rule['standard']}. Tolerance {tol * 100:.1f} cm.",
                                                  "medium" if r != "not available" else "low")})
        checks.append(_check(cid, rule, measured, thr, res, tol, fids, None, len(items)))
    pins = [{"id": f["id"], "anchor": f["anchor"], "label": f["title"], "status": f["status"]} for f in findings]
    req = [c for c in checks if c["severity"] == "required"]
    if any(c["result"] == "likely fail" for c in req):
        verdict = ("fail", "At least one required check likely fails.")
    elif all(c["result"] == "not available" for c in checks):
        verdict = ("unknown", "This scan cannot answer these checks.")
    elif any(c["result"] in ("likely fail", "measure on site", "not available") for c in checks):
        verdict = ("warn", "Nothing required clearly fails, but some checks need a tape measure or more data.")
    else:
        verdict = ("pass", "Every check likely passes on the scan geometry.")
    return {"pack": pack_id, "title": pack["title"], "verdict": {"status": verdict[0], "text": verdict[1]},
            "checks": checks, "findings": findings,
            "assumptions": [{"id": k, "label": p["label"], "value": vals[k], "unit": p["unit"], "editable": True}
                            for k, p in pack.get("params", {}).items()],
            "overlays": [{"kind": "pins", "pins": pins}] if pins else []}


def _check(cid, rule, measured, thr, res, tol, fids, reason, n=0):
    return {"id": cid, "rule": rule["text"], "measured": measured, "threshold": thr, "unit": rule["unit"],
            "status": VERDICT_STATUS[res], "result": res, "standard": rule.get("standard"), "tolerance": tol,
            "severity": rule["severity"], "compare": rule["compare"], "items": n, "findings": fids,
            **({"reason": reason} if reason else {})}


__all__ = ["MEASURES", "evaluate_pack", "list_packs", "load_pack", "unavailable"]
