"""Site reports: one investigation (any workspace) turned into the few pages a business keeps.

`build(doc, plan_of, captures)` reads the workspace's finished runs, its findings (with what people changed on site),
the phone's captures and the plans, and returns the report as plain data. `render.html(report)` draws it and
`pdf.from_html` prints it. Every number in it comes from a tool's result, a capture or a calculation here; none comes
from model text.

Report kinds pick the tools a field visit runs (`KINDS`). A report of a workspace with no kind covers every tool run.
"""
from __future__ import annotations

import datetime as dt
import math
from collections.abc import Callable
from typing import Any

from ..geometry._plan import floor_z

IN, FT2 = 0.0254, 0.09290304
ORDER = {"fail": 0, "warn": 1, "unknown": 2, "pass": 3}
STATUS_WORD = {"fail": "Fix", "warn": "Check", "unknown": "Not known", "pass": "OK"}

# tool id, inputs for a phone scan (no panoramas to read)
KINDS: dict[str, dict] = {
    "accessibility": {
        "title": "Accessibility audit",
        "lede": "Can a wheelchair user get in, reach every public room, turn round and use the restroom?",
        "tools": [("door_widths", {"min_width_m": 0.813}), ("step_free_route", {"read_panoramas": False}),
                  ("turning_space", {}), ("bathroom_clearance", {"read_panoramas": False})],
        "occupancy": False,
        "not_checked": [
            "Parking, the route from the street and any kerb ramp: the scan starts at the door.",
            "Door hardware (lever handles), the force needed to open doors and how fast closers shut them.",
            "Counter and table heights, reach ranges and knee space under sinks and counters.",
            "Grab bars, the toilet seat height, mirror and dispenser heights in the restroom.",
            "Signs, Braille, lighting and floor surfaces.",
            "Thresholds under 13 mm and floor slopes, unless they were measured with the phone and listed below.",
        ],
    },
    "fire": {
        "title": "Fire safety pre-plan",
        "lede": "How many people the space holds, how they get out, and what crews need to know before they arrive.",
        # smoke alarms come from the ceiling photos taken on the visit (the report's census covers every room people use);
        # life_safety_census reads bedroom panoramas, which a phone scan of a business has neither of
        "tools": [("fire_preplan", {"read_panoramas": False}), ("egress_routes", {})],
        "occupancy": True,
        "not_checked": [
            "Sprinklers, the fire alarm panel, extinguishers and their inspection tags, unless photographed below.",
            "Exit signs and emergency lighting, and whether exit doors open with one motion and no key.",
            "The building's construction type, fire separations and what is above or beside this space.",
            "Hydrants, the fire department connection, the utility shut-offs and the hood suppression system.",
            "Smoke alarms in rooms with no ceiling photo below.",
        ],
    },
    "fitout": {
        "title": "Fit-out and occupancy",
        "lede": "What the space measures, how many people it can seat, and what fits through its doors.",
        "tools": [("room_census", {}), ("door_widths", {"min_width_m": 0.813}), ("daylight", {}),
                  ("takeoff_bid", {"trade": "cleaning"})],
        "occupancy": True,
        "not_checked": [
            "Power, plumbing, gas and ventilation capacity, and where each enters the space.",
            "The lease line, landlord work, and what the building allows on its facade and signs.",
            "Ceiling height above a drop ceiling, structure, and anything behind finished walls.",
            "Floor finishes and their condition: the scan measures shape, not material.",
        ],
    },
}

# What to do about a finding, by tool. Plain advice for a business owner; a contractor or the code official decides.
FIX = {
    "door_widths": "Widen the opening, or rehang the door on offset (swing-clear) hinges, which gains about 5 cm.",
    "bathroom_clearance": "Widen the restroom door or rehang it on swing-clear hinges; keep 30 x 48 in clear beside "
                          "the door swing.",
    "step_free_route": "Remove the step or add a ramp no steeper than 1:12, and widen the narrowest door on the route.",
    "turning_space": "Clear a 60 in (1.5 m) circle: move tables, bins or shelving out of the turning space.",
    "egress_routes": "Keep the route to each exit clear and the exit doors unlocked from inside while people are in.",
    "fire_preplan": "Confirm this line on the walk-round and add it to the pre-plan.",
    "life_safety_census": "Check whether this room needs a smoke alarm or a heat detector (kitchens usually take a heat "
                          "detector), fit one, and test the ones there.",
    "daylight": "Check the room's use: a room people work in for long without a window needs good lighting and air.",
    "occupancy": "Ask the fire official for the posted occupant load, and keep seating within it.",
}

# International Building Code 2021, Table 1004.5 (New Jersey's Uniform Construction Code adopts the IBC). Room label ->
# (function of space, square feet per occupant, net or gross). None: the room does not add occupants (accessory).
LOAD_FACTOR = {
    "Dining Room": ("Assembly, tables and chairs", 15, "net"),
    "Living Room": ("Assembly, tables and chairs", 15, "net"),
    "Seating": ("Assembly, tables and chairs", 15, "net"),
    "Kitchen": ("Kitchen, commercial", 200, "gross"),
    "Storage": ("Storage", 300, "gross"),
    "Office": ("Business", 150, "gross"),
    "Bathroom": None, "Hallway": None, "Laundry": None,
    "Bedroom": ("Residential", 200, "gross"),
}
ONE_EXIT_MAX = 49  # IBC 2021 Table 1006.2.1: an assembly space with one exit holds at most 49 people
IN_PER_OCCUPANT = 0.2  # IBC 2021 1005.3.2: egress width per occupant at doors
HUNG_DOOR_M = 0.05  # a hung door's leaf and stop take about this off the opening


def ft_in(m: float | None) -> str:
    if m is None:
        return "–"
    if m < 1.5:
        return f"{m:.2f} m ({m / IN:.0f} in)"
    return f"{m:.1f} m ({m / 0.3048:.1f} ft)" if m < 10 else f"{m:.0f} m ({m / 0.3048:.0f} ft)"


def area(m2: float | None) -> str:
    return "–" if m2 is None else f"{m2:.1f} m² ({m2 / FT2:,.0f} ft²)"


def value(v: float | None, unit: str) -> str:
    """A measured value with US units beside metres, the way a US business reads a tape."""
    if v is None:
        return "–"
    if unit == "m":
        return ft_in(v)
    if unit in ("m2", "m²"):
        return area(v)
    return f"{v:g} {unit}".strip()


def _plain(x: Any) -> Any:
    return x.model_dump(mode="json", by_alias=True) if hasattr(x, "model_dump") else x


def anchor_point(plan: dict, a: dict | None) -> tuple[str, list[float]] | None:
    """(floor, [x, y]) where a finding sits on the plan, or None when it has no place on it."""
    if not a or a.get("sid") != plan["sid"]:
        return None
    if a.get("opening"):
        o = next((o for o in plan["openings"] if o["id"] == a["opening"]), None)
        return (o["floor"], o["center"][:2]) if o else None
    if a.get("room"):
        r = next((r for r in plan["rooms"] if r["id"] == a["room"]), None)
        if not r:
            return None
        c = r.get("center") or _centroid(r.get("polygon") or [])
        return (r["floor"], c[:2]) if c else None
    if a.get("wall"):
        w = next((w for w in plan["walls"] if w["id"] == a["wall"]), None)
        return (w["floor"], [(w["a"][0] + w["b"][0]) / 2, (w["a"][1] + w["b"][1]) / 2]) if w else None
    if a.get("point"):
        p = a["point"]
        fz = floor_z(plan)  # scan z per floor; `elevation` is relative to the lowest floor, a point is scan z
        floor = min(plan["floors"], key=lambda f: abs(fz.get(f["id"], 0.0) - (p[2] if len(p) > 2 else 0)))["id"] \
            if plan.get("floors") else None
        return (floor, p[:2]) if floor else None
    return None


def _centroid(poly: list) -> list[float] | None:
    if len(poly) < 3:
        return None
    return [sum(p[0] for p in poly) / len(poly), sum(p[1] for p in poly) / len(poly)]


def latest_runs(doc: dict, sid: str | None, tools: list[str] | None) -> list[dict]:
    """The last finished run of each (tool, scan), in the kind's tool order when there is one."""
    last: dict[tuple, dict] = {}
    for r in doc["runs"]:
        if r["status"] != "done" or not r.get("result"):
            continue
        if sid and r.get("sid") != sid:
            continue
        if tools is not None and r["tool"] not in tools:
            continue
        last[(r["tool"], r.get("sid"))] = r
    rank = {t: i for i, t in enumerate(tools or [])}
    return sorted(last.values(), key=lambda r: (rank.get(r["tool"], 99), r.get("started") or 0))


def occupancy(plan: dict) -> dict:
    """Occupant load by room from IBC Table 1004.5 and the scan's room areas, and the exits it needs."""
    rows, total = [], 0
    for r in plan["rooms"]:
        if r.get("label") == "Void":
            continue
        f = LOAD_FACTOR.get(r.get("label") or "", "unknown")
        a = r.get("area")
        if f == "unknown" or a is None:
            rows.append({"room": r.get("label") or "Unnamed room", "area": a, "use": "Not assigned: name the room",
                         "factor": None, "load": None})
            continue
        if f is None:
            rows.append({"room": r["label"], "area": a, "use": "Accessory: adds no occupants", "factor": None, "load": 0})
            continue
        use, ft2, basis = f
        load = math.ceil(a / FT2 / ft2)
        total += load
        rows.append({"room": r["label"], "area": a, "use": use, "factor": f"{ft2} ft² {basis}", "load": load})
    exits = [o for o in plan["openings"] if o["type"] != "window" and (o.get("exterior") or len(o.get("rooms") or []) == 1)]
    clear_in = sum(max(o["width"] - HUNG_DOOR_M, 0) for o in exits) / IN
    need = 2 if total > ONE_EXIT_MAX else 1
    return {"rows": rows, "total": total, "exits": len(exits), "exits_needed": need,
            "exit_widths": [o["width"] for o in exits], "door_capacity": math.floor(clear_in / IN_PER_OCCUPANT),
            "status": "fail" if len(exits) < need else "pass",
            "standard": "IBC 2021 Table 1004.5 (occupant load), Table 1006.2.1 (exits), 1005.3.2 (width)"}


def build(doc: Any, plan_of: Callable[[str], dict], captures: list[dict], *, kind: str | None = None,
          sid: str | None = None, alarm: Callable[[str], dict] | None = None, today: dt.date | None = None) -> dict:
    """The report as data. `doc` is the workspace (model or dict), `plan_of(sid)` its ScanPlans, `captures` the
    workspace's phone captures, `alarm(capture_id)` the photo reader for ceiling photos (None skips them)."""
    doc = _plain(doc)
    meta = (doc["brief"].get("facts") or {}).get("report") or {}
    kind = kind or meta.get("kind")
    spec = KINDS.get(kind or "")
    tools = [t for t, _ in spec["tools"]] if spec else None
    runs = latest_runs(doc, sid, tools)
    sids = [sid] if sid else list(dict.fromkeys([*(r["sid"] for r in runs if r.get("sid")), *doc["brief"]["scope"]["sids"]]))
    plans = {}
    for s in sids:
        try:
            plans[s] = plan_of(s)
        except Exception:  # noqa: BLE001 - a scan the server can no longer read is listed as not checked
            plans[s] = None

    run_ids = {r["id"] for r in runs}
    live = [f for f in doc["findings"] if not f.get("superseded_by") and (f.get("feedback") or {}).get("verdict") != "rejected"]
    by_id = {f["id"]: f for f in live if f.get("run") in run_ids}

    sections, items = [], []
    for r in runs:
        res = r["result"]
        fids = [f["id"] for f in res["findings"] if f["id"] in by_id]
        found = [by_id[i] for i in fids]
        checks = res.get("checks") or []
        check_of = {fid: c for c in checks for fid in c.get("findings") or []}
        for f in found:
            items.append({**f, "tool": r["tool"], "sid": r.get("sid"), "check": check_of.get(f["id"])})
        sections.append({"tool": r["tool"], "title": _title(r["tool"]), "sid": r.get("sid"), "verdict": res["verdict"],
                         "metrics": res.get("metrics") or [], "checks": checks, "assumptions": res.get("assumptions") or [],
                         "findings": [f["id"] for f in found], "overlays": res.get("overlays") or []})
    # what people recorded on site that no tool owns (photos, notes)
    ceiling = {f"phone:{c['id']}" for c in captures if (c.get("values") or {}).get("check") == "smoke_alarm"}  # shown as the census
    phone_notes = [f for f in live if f["id"].startswith("phone:") and f["id"] not in ceiling
                   and (not sid or (f.get("anchor") or {}).get("sid") in (sid, None))]

    occ = {s: occupancy(p) for s, p in plans.items() if p} if spec and spec["occupancy"] else {}
    for s, o in occ.items():
        if o["status"] == "fail":
            items.append({"id": f"occupancy:{s}", "tool": "occupancy", "sid": s, "status": "fail",
                          "title": f"{o['exits_needed']} exits needed, {o['exits']} found",
                          "detail": f"An occupant load of {o['total']} needs {o['exits_needed']} ways out.",
                          "anchor": None, "source": {"layer": "model", "method": "geometry", "confidence": "medium",
                                                      "note": "Room areas from the scan, factors from IBC Table 1004.5"},
                          "check": None})

    alarms = _alarms(captures, plans, alarm) if alarm is not None else []
    for a in alarms:
        if a["status"] in ("fail", "warn"):
            items.append({"id": f"alarm:{a['capture']}", "tool": "life_safety_census", "sid": a["sid"], "status": a["status"],
                          "title": f"No smoke alarm seen, {a['room_name']}", "detail": a["what"],
                          "anchor": {"sid": a["sid"], "room": a["room"]} if a["room"] else None,
                          "source": {"layer": "phone", "method": "vision", "confidence": a["confidence"],
                                     "note": "Ceiling photo taken on site, read by a vision model"}, "check": None})

    fix = _fix_first([i for i in items if i["status"] in ("fail", "warn")], tools or [])
    numbered = {}
    for n, it in enumerate(fix, 1):
        for fid in it["ids"]:
            numbered[fid] = n

    measured = [_measurement(c, plans) for c in captures if c.get("kind") == "reading" or (c.get("values") or {}).get("value_m")]
    counts = {k: sum(c["status"] == k for s in sections for c in s["checks"]) for k in ORDER}
    return {
        "kind": kind, "title": spec["title"] if spec else "Site report", "lede": spec["lede"] if spec else "",
        "business": meta.get("business") or "", "place": meta.get("place") or _place(plans, doc),
        "address": meta.get("address") or next((p.get("address") for p in plans.values() if p and p.get("address")), ""),
        "prepared_for": meta.get("contact") or "", "date": (today or dt.date.today()).isoformat(),
        "workspace": doc["id"], "sids": sids, "plans": plans, "sections": sections, "items": items,
        "fix_first": fix, "numbered": numbered, "occupancy": occ, "alarms": alarms, "measured": measured,
        "phone_notes": phone_notes, "counts": counts,
        "not_checked": _not_checked(spec, sections, plans, items, doc, runs, sid),
    }


def _title(tool: str) -> str:
    try:
        from ..agent.catalog import catalog
        return catalog()[tool].title
    except Exception:  # noqa: BLE001
        return tool.replace("_", " ").capitalize()


def _place(plans: dict, doc: dict) -> str:
    return next((p.get("name") for p in plans.values() if p and p.get("name")), "") or doc["brief"].get("text") or ""


def _key(it: dict) -> tuple | None:
    a = it.get("anchor") or {}
    for k in ("opening", "room", "wall"):
        if a.get(k):
            return (a.get("sid"), k, a[k])
    return None


def _fix_first(items: list[dict], tools: list[str]) -> list[dict]:
    """Fails before checks, life safety before comfort; one entry per door or room even when two tools found it."""
    rank = {t: i for i, t in enumerate(["occupancy", "egress_routes", "life_safety_census", *tools])}
    groups: dict[Any, dict] = {}
    for it in sorted(items, key=lambda i: (ORDER[i["status"]], rank.get(i["tool"], 50))):
        k = _key(it) or it["id"]
        g = groups.get(k)
        if g is None:
            groups[k] = {**it, "ids": [it["id"]], "tools": [it["tool"]], "also": [],
                         "fix": FIX.get(it["tool"], "Check this on site.")}
        else:
            g["ids"].append(it["id"])
            if it["tool"] not in g["tools"]:
                g["tools"].append(it["tool"])
            g["also"].append(it)
    return list(groups.values())[:12]


TASK_WHAT = {"width": "Door clear width", "step": "Step or threshold height", "slope": "Ramp slope",
             "alarm": "Smoke alarm photo", "floor_height": "Floor above the street", "heading": "Window facing"}
SENSOR = {"arkit_lidar": "iPhone LiDAR", "barometer": "barometer", "compass": "compass", "tape": "tape measure"}


def _measurement(c: dict, plans: dict) -> dict:
    """One phone capture as a row: what was measured, where, the value with its error, how, and what it changed."""
    v = c.get("values") or {}
    val, unit = v.get("value_m"), v.get("unit") or "m"
    task = c.get("task") or ""  # "<kind>:<sid>:<opening or room>"
    kind, ref = task.split(":")[0], task.rpartition(":")[2]
    what = TASK_WHAT.get(kind) or (c.get("tool") or "Reading").replace("_", " ").capitalize()
    if v.get("baro_rise_m") is not None:
        val, what = v["baro_rise_m"], "Floor above the street"
    if c.get("heading_deg") is not None and val is None:
        val, unit, what = c["heading_deg"], "°", "Window facing"
    plan = plans.get(c.get("scan") or "") or {}
    names = {r["id"]: r.get("label") or "a room" for r in plan.get("rooms") or []}
    opening = next((o for o in plan.get("openings") or [] if o["id"] in (c.get("opening"), ref)), None)
    if opening:
        rooms = [names.get(r, "a room") for r in opening.get("rooms") or []]
        where = " to ".join(rooms) + (" to outside" if len(rooms) == 1 else "")
    else:
        where = names.get(c.get("room") or "", "")
    res = c.get("result") if isinstance(c.get("result"), dict) else {}
    said = res.get("text") or (res.get("outcome") or {}).get("text")
    sensor = v.get("sensor") or ("tape" if val is not None else None)
    return {"id": c["id"], "what": what, "where": where, "value": val, "unit": unit,
            "method": SENSOR.get(sensor, sensor or c.get("kind")), "err_m": v.get("err_m"), "at": c.get("at"),
            "result": said, "photo": bool(c.get("file"))}


def _alarms(captures: list[dict], plans: dict, alarm: Callable[[str], dict]) -> list[dict]:
    """Smoke alarm census from ceiling photos: one line per photographed room, and one per room with no photo."""
    out, seen_rooms = [], set()
    for c in captures:
        if (c.get("values") or {}).get("check") != "smoke_alarm" or not c.get("file"):
            continue
        plan = plans.get(c.get("scan") or "") or {}
        room = next((r for r in plan.get("rooms") or [] if r["id"] == c.get("room")), None)
        try:
            a = alarm(c["id"])
        except Exception as e:  # noqa: BLE001 - the photo is still evidence; say the reader failed
            a = {"ceiling_visible": False, "smoke_alarm_visible": False, "what": f"The photo reader failed ({type(e).__name__}).",
                 "confidence": "low"}
        status = "pass" if a.get("smoke_alarm_visible") else ("warn" if a.get("ceiling_visible") else "unknown")
        seen_rooms.add((c.get("scan"), c.get("room")))
        out.append({"capture": c["id"], "sid": c.get("scan"), "room": c.get("room"),
                    "room_name": (room or {}).get("label") or "a room", "status": status, "what": a.get("what") or "",
                    "confidence": a.get("confidence") or "low"})
    if out:
        for s, p in plans.items():
            for r in (p or {}).get("rooms") or []:
                if (s, r["id"]) not in seen_rooms and LOAD_FACTOR.get(r.get("label") or "", 1) is not None:
                    out.append({"capture": None, "sid": s, "room": r["id"], "room_name": r.get("label") or "Unnamed room",
                                "status": "unknown", "what": "No ceiling photo taken.", "confidence": "low"})
    return out


def _not_checked(spec, sections, plans, items, doc, runs, sid) -> list[str]:
    out = list(spec["not_checked"]) if spec else []
    for s, p in plans.items():
        if p is None:
            out.append(f"Scan {s} could not be read.")
            continue
        out += [n[0].upper() + n[1:] + ("" if n.endswith(".") else ".") for n in (p.get("quality") or {}).get("notes") or []]
    for it in items:
        if it["status"] == "unknown" and it["tool"] != "fire_preplan":
            out.append(f"{it['title']}: {it['detail']}")
    for sec in sections:
        for c in sec["checks"] if sec["tool"] != "fire_preplan" else []:  # the pre-plan's lines are listed in full
            if c["status"] == "unknown":
                out.append(f"{c['rule']}: the data could not answer it.")
        if sec["verdict"]["status"] == "unknown" and not sec["findings"]:
            out.append(f"{sec['title']}: {sec['verdict']['text']}")
    done = {(r["tool"], r.get("sid")) for r in runs}
    for r in doc["runs"]:
        if r["status"] == "error" and (not sid or r.get("sid") == sid) and (r["tool"], r.get("sid")) not in done:
            out.append(f"{_title(r['tool'])} did not run: {r.get('error') or 'it failed'}.")
    if spec:
        ran = {r["tool"] for r in runs}
        out += [f"{_title(t)} has not run yet." for t, _ in spec["tools"] if t not in ran]
    return list(dict.fromkeys(out))
