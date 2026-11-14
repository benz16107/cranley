"""Smoke Clock: survivable time in each bedroom, bedroom doors open and closed, for a fire in a chosen room. Runs
NIST's CFAST two-zone fire model (public domain) on the measured rooms and doorways and reports CFAST's own outputs.

CFAST is not on PyPI. Build it once (about a minute):
    sudo apt-get install -y gfortran
    git clone --depth 1 --branch CFAST-7.7.7 https://github.com/firemodels/cfast.git
    cd cfast/Build/CFAST/gnu_linux && bash make_cfast.sh && cp cfast7_linux ~/.local/bin/cfast
or point $CFAST at the binary. Without it the tool says so and estimates nothing."""
from __future__ import annotations

import csv
import hashlib
import math
import os
import shutil
import subprocess

from pydantic import BaseModel

from ...config import CACHE
from ...geometry import room_graph
from ...geometry._plan import default_ceiling, floor_z, polygons
from .. import (
    Assumption,
    Check,
    Finding,
    Legend,
    LensOverlay,
    Metric,
    NotApplicable,
    RoomAnchor,
    ScanScope,
    Source,
    ToolError,
    ToolResult,
    Verdict,
    field,
    tool,
)
from ..fire_preplan.common import BEDROOM, floor_label, live_rooms, name, walls_ok

RUNS = CACHE / "tools" / "smoke_clock"
TIMEOUT_S = 900                    # CFAST at -O0 takes 3 to 11 minutes on a house; some plans go stiff
MIN_AREA_M2 = 2.5                  # closets and nooks under this are left out of the model
SIM_S = 900                        # 15 minutes
TARGET_Z = 1.5                     # tenability measured at a standing person's head
DOOR_H = 2.03                      # 80 in when the scan has no doorway height
UNDERCUT_M = 0.0127                # a closed door still leaks under it: 1/2 in undercut
FED_LIMIT = 0.3                    # ISO 13571 incapacitation for sensitive people
OD_LIMIT = 0.26                    # optical density per metre at which a lit sign is visible at about 5 m
GROWTH = {"slow": 0.00293, "medium": 0.01172, "fast": 0.0469, "ultrafast": 0.1876}   # kW/s², NFPA 72 t-squared
SIM = Source(layer="model", method="simulation", confidence="low",
             note="NIST CFAST 7.7.7 two-zone model on the measured rooms and doorways; the fire, materials, leakage "
                  "and closed windows are assumptions")


class Inputs(BaseModel):
    scan: str = field(source="selection.scan", description="Scan id")
    fire_room: str | None = field(None, ask="Which room does the fire start in?",
                                  description="Room id or room type (e.g. 'Living Room'); default: living room, "
                                              "then kitchen, then the largest room")
    growth: str = field("fast", pref="fire.growth", description="t-squared growth: slow, medium, fast or ultrafast")
    peak_kw: float = field(2000, pref="fire.peak_kw", unit="kW", gt=50, le=10000,
                           description="Peak heat release (an upholstered sofa is about 2 MW)")
    escape_min: float = field(3.0, pref="fire.escape_min", unit="min", gt=0, le=15,
                              description="Time people need to wake and get out")


def cfast_bin() -> str | None:
    p = os.environ.get("CFAST") or shutil.which("cfast") or os.path.expanduser("~/.local/bin/cfast")
    return p if p and os.path.exists(p) else None


def _pick_fire(plan: dict, want: str | None) -> dict | None:
    rooms = [r for r in live_rooms(plan) if polygons(plan).get(r["id"]) is not None]
    if want:
        hit = next((r for r in rooms if r["id"] == want), None) or \
            next((r for r in rooms if (r.get("label") or "").lower() == want.lower()), None)
        if hit is None:
            raise ToolError(f"No room '{want}' in this scan. Rooms: " + ", ".join(sorted({name(r) for r in rooms})))
        return hit
    for label in ("Living Room", "Family Room", "Kitchen"):
        hit = [r for r in rooms if r.get("label") == label]
        if hit:
            return max(hit, key=lambda r: polygons(plan)[r["id"]].area)
    return max(rooms, key=lambda r: polygons(plan)[r["id"]].area, default=None)


def compartments(plan: dict) -> tuple[dict[str, str], dict[str, dict]]:
    """Rooms joined by invisible walls are one open space, so one CFAST compartment; spaces under MIN_AREA_M2
    (closets) are left out, unless they join two spaces (a small hall), which joins its largest neighbour.
    Returns room id -> compartment id and compartment id -> {rooms, area, height, origin}."""
    polys, z = polygons(plan), floor_z(plan)
    ceiling = default_ceiling(plan) or 2.6
    rooms = {r["id"]: r for r in live_rooms(plan) if polys.get(r["id"]) is not None and polys[r["id"]].area > 0.3}
    parent = {k: k for k in rooms}

    def find(x):
        while parent[x] != x:
            x = parent[x]
        return x

    links = room_graph(plan)["links"]
    for link in links:
        a, b = link["rooms"]
        if link["kind"] == "invisible" and a in rooms and b in rooms:
            parent[find(a)] = find(b)
    # a small hall that joins two or more spaces carries the smoke between them: fold it into its largest neighbour
    # instead of leaving it out, or the bedroom past it is cut off from the fire
    area_of = lambda g: sum(polys[k].area for k in rooms if find(k) == g)
    for g in {find(k) for k in rooms}:
        if area_of(g) >= MIN_AREA_M2:
            continue
        near = {find(x) for link in links if link["kind"] != "invisible" for x in link["rooms"]
                if x in rooms and find(x) != g and any(find(y) == g for y in link["rooms"] if y in rooms)}
        if len(near) >= 2:
            parent[g] = max(near, key=area_of)
    groups: dict[str, list[str]] = {}
    for k in rooms:
        groups.setdefault(find(k), []).append(k)
    comp, info = {}, {}
    for members in groups.values():
        area = sum(polys[m].area for m in members)
        if area < MIN_AREA_M2:
            continue
        cid = f"C{len(info) + 1}"
        x0 = min(polys[m].bounds[0] for m in members)
        y0 = min(polys[m].bounds[1] for m in members)
        big = max(members, key=lambda m: polys[m].area)
        info[cid] = {"rooms": members, "area": area, "floor": rooms[big]["floor"],
                     "height": max(rooms[m].get("height") or ceiling for m in members),
                     "origin": (x0, y0, z.get(rooms[big]["floor"], 0.0)), "shape": polys[big]}
        for m in members:
            comp[m] = cid
    return comp, info


def write_input(plan: dict, fire: dict, doors_closed: bool, growth: float, peak_kw: float) -> tuple[str, dict]:
    """A CFAST input file for the plan, and room id -> compartment id. Pure; no files touched."""
    comp, info = compartments(plan)
    if fire["id"] not in comp:
        raise ToolError(f"The fire room ({name(fire)}) is too small to model; pick another room.")
    holes = _stair_holes(plan, comp)
    z = floor_z(plan)
    for up, down, _ in holes:  # CFAST needs the lower ceiling to meet the upper floor at a ceiling vent
        lo = info[comp[down]]
        lo["height"] = max(z.get(info[comp[up]]["floor"], 0) - lo["origin"][2], 2.0)
    lines = [f"&HEAD VERSION = 7700, TITLE = 'Threshold smoke clock {plan['sid']}' /",
             f"&TIME SIMULATION = {SIM_S} PRINT = 60 SMOKEVIEW = 60 SPREADSHEET = 5 /",
             "&INIT PRESSURE = 101325 RELATIVE_HUMIDITY = 50 INTERIOR_TEMPERATURE = 20 EXTERIOR_TEMPERATURE = 20 /",
             "&MATL ID = 'GYPSUM' MATERIAL = 'Gypsum board' CONDUCTIVITY = 0.16 SPECIFIC_HEAT = 0.9 DENSITY = 790 "
             "THICKNESS = 0.016 EMISSIVITY = 0.9 /",
             "&MATL ID = 'WOOD' MATERIAL = 'Wood subfloor' CONDUCTIVITY = 0.12 SPECIFIC_HEAT = 1.2 DENSITY = 510 "
             "THICKNESS = 0.019 EMISSIVITY = 0.9 /"]
    for cid, c in info.items():
        w, d = _box(c["shape"], c["area"])
        lines.append(f"&COMP ID = '{cid}' WIDTH = {w:.3f} DEPTH = {d:.3f} HEIGHT = {c['height']:.3f} "
                     f"CEILING_MATL_ID = 'GYPSUM' WALL_MATL_ID = 'GYPSUM' FLOOR_MATL_ID = 'WOOD' "
                     f"ORIGIN = {c['origin'][0]:.3f}, {c['origin'][1]:.3f}, {c['origin'][2]:.3f} "
                     "LEAK_AREA_RATIO = 1.3E-4, 5.2E-5 /")
    g = room_graph(plan)
    bedrooms = {r["id"] for r in live_rooms(plan) if r.get("label") == BEDROOM}
    n = 0
    for link in g["links"]:
        a, b = link["rooms"]
        if link["kind"] == "invisible" or a not in comp or b not in comp or comp[a] == comp[b]:
            continue
        n += 1
        h = min(link.get("height") or DOOR_H, 2.4)
        shut = doors_closed and link["kind"] == "doorway" and (a in bedrooms or b in bedrooms)
        lines.append(f"&VENT TYPE = 'WALL' ID = 'V{n}' COMP_IDS = '{comp[a]}', '{comp[b]}' BOTTOM = 0 "
                     f"HEIGHT = {UNDERCUT_M if shut else h:.4f} WIDTH = {(link['width'] or 0.8):.3f} /")
    for e in g["entrances"]:
        if e["room"] in comp:  # exterior and unit doors closed: they leak under the door only
            n += 1
            lines.append(f"&VENT TYPE = 'WALL' ID = 'V{n}' COMP_IDS = '{comp[e['room']]}', 'OUTSIDE' BOTTOM = 0 "
                         f"HEIGHT = {UNDERCUT_M} WIDTH = {(e['width'] or 0.9):.3f} /")
    for up, down, area in holes:
        n += 1
        lines.append(f"&VENT TYPE = 'CEILING' ID = 'V{n}' COMP_IDS = '{comp[up]}', '{comp[down]}' AREA = {area:.2f} "
                     "SHAPE = 'SQUARE' /")
    fc = info[comp[fire["id"]]]
    fw, fd = _box(fc["shape"], fc["area"])
    t_peak = math.sqrt(peak_kw / growth)
    lines += [f"&FIRE ID = 'Fire' COMP_ID = '{comp[fire['id']]}' FIRE_ID = 'Sofa' LOCATION = {fw / 2:.2f}, {fd / 2:.2f} /",
              "&CHEM ID = 'Sofa' CARBON = 6.3 CHLORINE = 0 HYDROGEN = 7.1 NITROGEN = 1 OXYGEN = 2.1 "
              "HEAT_OF_COMBUSTION = 25300 RADIATIVE_FRACTION = 0.35 /",
              "&TABL ID = 'Sofa' LABELS = 'TIME', 'HRR', 'HEIGHT', 'AREA', 'CO_YIELD', 'SOOT_YIELD', 'HCN_YIELD', "
              "'HCL_YIELD', 'TRACE_YIELD' /"]
    for t in sorted({*range(0, int(t_peak), 20), int(t_peak), SIM_S}):
        q = min(growth * t * t, peak_kw)
        lines.append(f"&TABL ID = 'Sofa', DATA = {t}, {q:.1f}, 0.45, {max(0.1, min(2.0, q / 500)):.2f}, 0.03, 0.1, "
                     "0.003, 0, 0 /")
    for cid in sorted({comp[b] for b in bedrooms if b in comp}, key=lambda c: int(c[1:])):
        w, d = _box(info[cid]["shape"], info[cid]["area"])
        lines.append(f"&DEVC ID = 'T_{cid}' COMP_ID = '{cid}' LOCATION = {w / 2:.2f}, {d / 2:.2f}, {TARGET_Z} "
                     "TYPE = 'PLATE' MATL_ID = 'GYPSUM' SURFACE_ORIENTATION = 'CEILING' TEMPERATURE_DEPTH = 0.008 "
                     "DEPTH_UNITS = 'M' /")
    lines.append("&TAIL /")
    return "\n".join(lines) + "\n", comp


def _box(p, area: float | None = None) -> tuple[float, float]:
    """Width and depth of a box with this floor area and the outline's bounding-box aspect ratio."""
    x0, y0, x1, y1 = p.bounds
    area = area or p.area
    w = math.sqrt(area * max(x1 - x0, 0.3) / max(y1 - y0, 0.3))
    return w, area / w


def _stair_holes(plan: dict, comp: dict) -> list[tuple[str, str, float]]:
    """An opening in the floor above each Staircase room, to the room over it: (upper room, lower room, area)."""
    from ..egress_routes import _order, _stairs
    order, out = _order(plan), []
    for f, nf in zip(order, order[1:]):
        pair = _stairs(plan, f, nf)
        if pair and pair[0] in comp and pair[1] in comp and comp[pair[0]] != comp[pair[1]]:
            lower, upper = pair
            out.append((upper, lower, min(polygons(plan)[lower].area, 3.0)))
    return out


def run_cfast(text: str) -> dict:
    """Run CFAST on an input (cached by its text). Returns the devices table: {column id: [values]} and times."""
    exe = cfast_bin()
    key = hashlib.sha1(text.encode()).hexdigest()[:16]
    d = RUNS / key
    out, done = d / "case_devices.csv", d / "ok"
    if not done.exists():
        d.mkdir(parents=True, exist_ok=True)
        (d / "case.in").write_text(text)
        try:
            r = subprocess.run([exe, "case.in"], cwd=d, capture_output=True, text=True, timeout=TIMEOUT_S)
        except subprocess.TimeoutExpired:
            raise NotApplicable(f"CFAST did not finish within {TIMEOUT_S // 60} minutes: its solver slowed to tiny time "
                            "steps on this plan") from None
        if "Normal exit" not in r.stdout + r.stderr:
            raise NotApplicable(f"CFAST stopped early, so no smoke timeline: {(r.stdout + r.stderr).strip()[-300:]}")
        done.touch()
    rows = list(csv.reader(out.open()))
    ids, comps = rows[0], rows[2]
    data = [[float(v) for v in row] for row in rows[4:] if row]
    cols = {f"{ids[i]}|{comps[i]}": [row[i] for row in data] for i in range(len(ids))}
    return {"time": [row[0] for row in data], "cols": cols, "dir": str(d)}


def untenable(res: dict, comp: str) -> dict:
    """First time each limit is crossed at the bedroom's target, from CFAST's device outputs."""
    t = res["time"]
    dev = f"T_{comp}"
    col = lambda short: next((v for k, v in res["cols"].items() if k.startswith(short + "_") and k.endswith("|" + dev)),  # noqa: E731
                             None)
    out = {}
    for name_, short, lim in (("toxic gases", "TRGFEDG", FED_LIMIT), ("heat", "TRGFEDH", FED_LIMIT),
                              ("smoke too thick to see", "TRGOBS", OD_LIMIT)):
        v = col(short)
        out[name_] = next((ti for ti, x in zip(t, v) if x >= lim), None) if v else None
    hits = {k: v for k, v in out.items() if v is not None}
    first = min(hits.items(), key=lambda kv: kv[1]) if hits else None
    return {"by": out, "time_s": first[1] if first else None, "cause": first[0] if first else None}


@tool(id="smoke_clock", title="Smoke clock", icon="timer",
      summary="Minutes of survivable air in each bedroom with its door open and closed, from NIST's fire model run on "
              "the measured rooms.",
      model_description="Runs NIST CFAST (two-zone fire model) on one scan's rooms and doorways for a fire in a chosen "
                        "room, twice: bedroom doors open, then closed. Returns per bedroom the time until toxic gas, "
                        "heat or smoke make it untenable at head height, a lens of minutes, and the assumptions.",
      personas=["fire_captain", "houston_homeowner_storm", "older_adult_family"],
      requires=[{"layer": "matterport.openings"}, {"layer": "matterport.room_labels"}],
      blocks=["VerdictHeader", "MetricRow", "MiniChart", "CheckList", "FloorPlanMini", "AssumptionChips", "StepLog"],
      overlays=["lens"], annotations={"cost": "slow"},
      examples=["How long do the kids have if the living room catches fire?", "Does closing the bedroom door help?"])
def run(ctx, inputs: Inputs) -> ToolResult:
    sid = inputs.scan
    plan = ctx.plan(sid)
    scope = ScanScope(sid=sid)
    if inputs.growth not in GROWTH:
        raise ToolError("growth is slow, medium, fast or ultrafast")
    if not walls_ok(plan):
        return ToolResult(scope=scope, verdict=Verdict(status="unknown", text=(
            "This scan has no wall graph, so the fire model has no doorways to move smoke through. It cannot be run "
            "here; the scan's rooms alone would make every room a sealed box.")))
    beds = [r for r in live_rooms(plan) if r.get("label") == BEDROOM and polygons(plan).get(r["id"]) is not None]
    if not beds:
        return ToolResult(scope=scope, verdict=Verdict(status="unknown", text=(
            "No room in this scan is typed as a bedroom, so there is no one to time. If it has bedrooms, run the "
            "Room labeller first to type its rooms from the panoramas.")))
    exe = cfast_bin()
    if not exe:
        return ToolResult(scope=scope, verdict=Verdict(status="unknown", text=(
            "NIST CFAST is not installed on this server, so no fire model was run and no estimate is given. "
            "Build steps are in the smoke_clock tool's docstring.")))
    fire = _pick_fire(plan, inputs.fire_room)
    multi = len({r["floor"] for r in live_rooms(plan)}) > 1
    where = lambda r: f"{name(r)} ({floor_label(plan, r['floor'])})" if multi else name(r)  # noqa: E731
    a = GROWTH[inputs.growth]
    ctx.step(f"Fire in {where(fire)}: {inputs.growth} growth to {inputs.peak_kw:.0f} kW")
    from concurrent.futures import ThreadPoolExecutor
    cases = {closed: write_input(plan, fire, closed, a, inputs.peak_kw) for closed in (False, True)}
    try:
        with ThreadPoolExecutor(2) as ex:  # the two cases are independent CFAST processes
            runs = dict(zip(cases, ex.map(lambda c: run_cfast(c[0]), cases.values())))
    except ToolError as e:
        return ToolResult(scope=scope, verdict=Verdict(status="unknown", text=f"{e}. No survivable times are given "
                                                       "for this scan; nothing is estimated in their place."))
    results = {closed: (runs[closed], cases[closed][1]) for closed in cases}
    ctx.step(f"Ran CFAST twice (bedroom doors open, then closed) on {len(set(cases[False][1].values()))} "
             "compartments")
    beds = [r for r in beds if r["id"] in cases[False][1]]
    checks, findings, metrics = [], [], []
    lens = {False: {}, True: {}}
    limit_s = inputs.escape_min * 60
    worst = None
    for r in sorted(beds, key=lambda r: r["id"]):
        tt = {}
        for closed in (False, True):
            res, comp = results[closed]
            u = untenable(res, comp[r["id"]])
            tt[closed] = u
            mins = round(u["time_s"] / 60, 1) if u["time_s"] is not None else None
            lens[closed][r["id"]] = mins if mins is not None else SIM_S / 60
            st = "pass" if mins is None or u["time_s"] >= limit_s else "fail"
            fid = f"smoke_clock:{sid}:{r['id']}"
            checks.append(Check(id=f"{r['id']}:{'closed' if closed else 'open'}",
                                rule=f"Survivable time, {name(r)} ({floor_label(plan, r['floor'])}), door "
                                     f"{'closed' if closed else 'open'}",
                                measured=mins, threshold=inputs.escape_min, unit="min", status=st,
                                standard="ISO 13571 FED 0.3 at 1.5 m; visibility about 5 m", findings=[fid]))
            metrics.append(Metric(id=f"{'closed' if closed else 'open'}.{name(r)} {r['id'][:4]}",
                                  label=f"{name(r)}, door {'closed' if closed else 'open'}", value=mins,
                                  unit="min", source=SIM))
        o, c = tt[False], tt[True]
        fmt = lambda u: (f"untenable at {u['time_s'] / 60:.1f} min ({u['cause']})" if u["time_s"] is not None  # noqa: E731
                         else f"still tenable at {SIM_S // 60} min")
        st = "fail" if o["time_s"] is not None and o["time_s"] < limit_s else "warn" if o["time_s"] is not None else "pass"
        findings.append(Finding(id=f"smoke_clock:{sid}:{r['id']}", title=f"{where(r)}, survivable time", status=st,
                                detail=f"Door open: {fmt(o)}. Door closed: {fmt(c)}.",
                                anchor=RoomAnchor(sid=sid, room=r["id"]), source=SIM))
        if o["time_s"] is not None and (worst is None or o["time_s"] < worst[1]):
            worst = (r, o["time_s"])
    opens = [v for v in lens[False].values()]
    closes = [v for v in lens[True].values()]
    fails = sum(c.status == "fail" for c in checks)
    text = (f"Fire in {where(fire)}, {inputs.growth} growth: with bedroom doors open the first bedroom becomes "
            f"untenable at {worst[1] / 60:.1f} min; " if worst else
            f"Fire in {where(fire)}: no bedroom became untenable within {SIM_S // 60} min with doors open; ") + \
        (f"with doors closed the shortest is {min(closes):.1f} min." if min(closes) < SIM_S / 60 else
         f"with doors closed every bedroom stays tenable for the full {SIM_S // 60} min.")
    status = "fail" if fails else "pass"
    return ToolResult(
        scope=scope, verdict=Verdict(status=status, text=text),
        metrics=[Metric(id="shortest_open", label="Shortest, doors open", value=min(opens), unit="min", source=SIM),
                 Metric(id="shortest_closed", label="Shortest, doors closed", value=min(closes), unit="min", source=SIM),
                 Metric(id="bedrooms", label="Bedrooms timed", value=len(beds), unit="", source=SIM)] + metrics,
        checks=checks, findings=findings,
        overlays=[LensOverlay(values=lens[False], ramp="sequential", legend=Legend(
                      title="Survivable minutes, bedroom doors open", unit="min", min=0, max=SIM_S / 60)),
                  LensOverlay(values=lens[True], ramp="sequential", legend=Legend(
                      title="Survivable minutes, bedroom doors closed", unit="min", min=0, max=SIM_S / 60))],
        assumptions=[Assumption(id="fire.growth", label="Fire growth (t-squared)", value=inputs.growth, editable=True),
                     Assumption(id="fire.peak_kw", label="Peak fire size", value=inputs.peak_kw, unit="kW", editable=True),
                     Assumption(id="fire.escape_min", label="Time needed to get out", value=inputs.escape_min,
                                unit="min", editable=True),
                     Assumption(id="fire_room", label=f"Fire starts in {name(fire)}", value=fire["id"]),
                     Assumption(id="fuel", label="Fuel: polyurethane sofa, CO yield 0.03, soot 0.1", value="polyurethane"),
                     Assumption(id="windows", label="Windows closed; exterior and unit doors closed with a 1/2 in "
                                "undercut; no HVAC", value=True),
                     Assumption(id="materials", label="Gypsum walls and ceilings, wood floors; leakage area 1.3e-4 of "
                                "wall area", value=True),
                     Assumption(id="rooms", label="Each room is a box with its measured floor area and height",
                                value=True),
                     Assumption(id="target", label="Tenability measured at 1.5 m in the middle of each bedroom",
                                value=TARGET_Z, unit="m"),
                     Assumption(id="cfast_runs", label="CFAST run folders", value=results[False][0]["dir"])])
