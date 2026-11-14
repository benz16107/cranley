"""The measures table: about forty numbers per scan, measured by threshold.geometry, in SQLite under
$THRESHOLD_DATA_DIR/cache/measures/measures.sqlite, so many homes can be searched by what is inside them.

    uv run python -m threshold.tools.measure_search.table build [--file SIDS] [--workers 8]
    uv run python -m threshold.tools.measure_search.table stats

Plans come from the disk cache (prefetch them first with threshold.sources.prefetch); nothing here calls an API.
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
import statistics
import sys
import time
from concurrent.futures import ProcessPoolExecutor

from ...config import CACHE
from ...geometry import free_wall_runs, reach, route, takeoff, turning_spaces
from ...geometry._plan import clear_width
from .._access import (SILL_NOISE_M, STEP_M, elevations, graph, implausible, links_of, pick_entrance, quality,
                       sill_step, start_point, step_kind)

DIR = CACHE / "measures"
DB = DIR / "measures.sqlite"
WHEELCHAIR_M = 0.815

# id: (label, unit, kind, description). kind "num" | "count" | "flag" | "text"
FIELDS: dict[str, tuple[str, str, str, str]] = {
    "floor_area": ("Floor area", "m2", "num", "Walled rooms, voids left out"),
    "largest_room_area": ("Largest room", "m2", "num", "Floor area of the biggest room"),
    "largest_room_label": ("Largest room type", "", "text", "Label of the biggest room"),
    "rooms": ("Rooms", "", "count", "Rooms that are not voids"),
    "bedrooms": ("Bedrooms", "", "count", "Rooms labelled Bedroom"),
    "bathrooms": ("Bathrooms", "", "count", "Rooms labelled Bathroom"),
    "kitchens": ("Kitchens", "", "count", ""),
    "living_rooms": ("Living and family rooms", "", "count", ""),
    "dining_rooms": ("Dining rooms", "", "count", ""),
    "closets": ("Closets", "", "count", ""),
    "hallways": ("Hallways", "", "count", ""),
    "laundry": ("Laundry rooms", "", "count", ""),
    "garages": ("Garages", "", "count", ""),
    "offices": ("Offices", "", "count", ""),
    "staircases": ("Staircase rooms", "", "count", ""),
    "floors": ("Floors", "", "count", "Storeys in the scan"),
    "entrances": ("Entrances", "", "count", "Doorways with a room on one side only (outside or unscanned)"),
    "entrance_width": ("Main entrance clear width", "m", "num", "Wall opening less 5 cm for a hung door"),
    "doors": ("Doorways", "", "count", "Doorways and wall-less openings"),
    "narrowest_door": ("Narrowest doorway", "m", "num", "Clear width, data errors left out"),
    "median_door": ("Typical doorway", "m", "num", "Median clear width"),
    "implausible_doors": ("Door widths that are data errors", "", "count", "Recorded under 0.40 m"),
    "bath_route_door": ("Doors to the bathroom", "m", "num",
                        "Narrowest clear door on the widest way from the entrance to the best bathroom"),
    "bath_route_m": ("Walk to the bathroom", "m", "num", "Route length from the entrance to the nearest bathroom"),
    "bath_route_corridor": ("Corridor to the bathroom", "m", "num",
                            "Narrowest wall-to-wall width on the route to the nearest bathroom"),
    "bed_route_door_min": ("Doors to every bedroom", "m", "num",
                           "Narrowest clear door on the way to the hardest bedroom to reach"),
    "bed_route_door_max": ("Doors to the best bedroom", "m", "num",
                           "Narrowest clear door on the way to the easiest bedroom to reach"),
    "kitchen_route_door": ("Doors to the kitchen", "m", "num", "Narrowest clear door on the way to the kitchen"),
    "bath_turn": ("Bathroom turning circle", "m", "num", "Largest circle in the best bathroom, empty room"),
    "kitchen_turn": ("Kitchen turning circle", "m", "num", "Largest circle in the kitchen"),
    "bed_turn": ("Bedroom turning circle", "m", "num", "Largest circle in the best bedroom"),
    "largest_turn": ("Largest turning circle", "m", "num", "In any room"),
    "longest_wall": ("Longest free wall", "m", "num", "Straight wall with no door or window, any room"),
    "bed_wall": ("Longest bedroom wall", "m", "num", "Longest free wall in any bedroom (for a bed or desk)"),
    "living_wall": ("Longest living room wall", "m", "num", "Longest free wall in a living or family room"),
    "ceiling_median": ("Typical ceiling height", "m", "num", ""),
    "ceiling_min": ("Lowest ceiling", "m", "num", ""),
    "ceiling_max": ("Highest ceiling", "m", "num", ""),
    "windows": ("Windows", "", "count", ""),
    "glazed_area": ("Glazed area", "m2", "num", "Window width times height"),
    "glazing_ratio": ("Glazing to floor ratio", "", "num", "Glazed area over floor area"),
    "level_changes": ("Steps at doorways", "", "count", "Sills more than 5 cm off their floor's level"),
    "max_sill_step": ("Highest doorway step", "m", "num", ""),
    "bed_bath_entry_floor": ("Bedroom and bathroom on the entrance floor", "", "flag", ""),
    "wheelchair_rooms_share": ("Rooms a wheelchair reaches", "%", "num",
                               "Share of rooms reachable through doors of 0.815 m clear from the entrance"),
    "step_free_bath": ("Step-free way to a bathroom", "", "flag", "No doorway step on the way"),
    "wheelchair_bath": ("Wheelchair reaches a bathroom", "", "flag", "Step-free and 0.815 m doors all the way"),
}
META = ["sid", "name", "kind", "city", "address", "lat", "lon", "segment", "walls", "polygons", "labels", "panos",
        "error"]


def _mx(xs):
    xs = [x for x in xs if x is not None]
    return max(xs) if xs else None


def _mn(xs):
    xs = [x for x in xs if x is not None]
    return min(xs) if xs else None


def measure(plan: dict) -> dict:
    """Every FIELDS value for one plan; None where the scan cannot answer."""
    q = quality(plan)
    rs = [r for r in plan["rooms"] if r.get("label") != "Void"]
    lab = lambda *ls: [r for r in rs if r.get("label") in ls]
    out: dict = {k: None for k in FIELDS}
    out.update(rooms=len(rs), bedrooms=len(lab("Bedroom")), bathrooms=len(lab("Bathroom")), kitchens=len(lab("Kitchen")),
               living_rooms=len(lab("Living Room", "Family Room")), dining_rooms=len(lab("Dining Room")),
               closets=len(lab("Closet")), hallways=len(lab("Hallway")), laundry=len(lab("Laundry")),
               garages=len(lab("Garage")), offices=len(lab("Office")), staircases=len(lab("Staircase")),
               floors=len(plan.get("floors") or []))
    areas = [(r.get("area") or 0, r) for r in rs if r.get("walls") or not q.get("walls")]
    if areas:
        a, big = max(areas, key=lambda x: x[0])
        out["largest_room_area"], out["largest_room_label"] = round(a, 2) or None, big.get("label")
    hs = [r["height"] for r in rs if r.get("height")]
    if hs:
        out.update(ceiling_median=round(statistics.median(hs), 3), ceiling_min=round(min(hs), 3),
                   ceiling_max=round(max(hs), 3))
    if not q.get("walls"):
        out["floor_area"] = round(sum(r.get("area") or 0 for r in rs), 2) or None
        return out
    tk = takeoff(plan)
    if tk["available"]:
        t = tk["total"]
        out.update(floor_area=round(t["floor_area"], 2), windows=t["windows"], glazed_area=round(t["glazed_area"], 2),
                   glazing_ratio=round(t["glazing_ratio"], 3) if t["glazing_ratio"] else None)
    g = graph(plan)
    links = links_of(plan)
    passable = [d for d in links.values() if d["kind"] != "invisible"]
    out["doors"] = len(passable)
    good = [clear_width(d) for d in passable if not implausible(d) and d.get("width") is not None]
    out["implausible_doors"] = sum(implausible(d) for d in passable)
    out["narrowest_door"] = round(min(good), 3) if good else None
    out["median_door"] = round(statistics.median(good), 3) if good else None
    steps = [sill_step(plan, d) for d in passable]
    out["level_changes"] = sum(step_kind(s) != "none" for s in steps)
    out["max_sill_step"] = round(_mx(steps), 3) if _mx(steps) is not None else None
    ent = pick_entrance(plan)
    out["entrances"] = len(g.get("entrances") or [])
    if ent:
        out["entrance_width"] = round(clear_width(ent), 3) if ent.get("width") is not None else None
        on = [r for r in rs if r["floor"] == ent["floor"]]
        out["bed_bath_entry_floor"] = int(any(r.get("label") == "Bedroom" for r in on)
                                          and any(r.get("label") == "Bathroom" for r in on))
    if ent:
        # from the main entrance only: other one-sided doorways may be balconies or unscanned rooms
        ecw = clear_width(ent) if ent.get("width") is not None and not implausible(ent) else None
        estep = step_kind(sill_step(plan, ent)) != "none"
        rc = reach(plan, 0.0, start=ent["room"])
        wc = reach(plan, WHEELCHAIR_M, start=ent["room"], max_step=STEP_M + SILL_NOISE_M)
        sf = reach(plan, 0.0, start=ent["room"], max_step=STEP_M + SILL_NOISE_M)
        bw = {}
        for r in rc["rooms"]:
            if r["connected"]:
                b = r["bottleneck_width"] if r["bottleneck_width"] is not None else math.inf
                bw[r["room"]] = min(b, ecw) if ecw is not None else (b if b != math.inf else None)
        cap = lambda v: None if v is None else round(min(v, 9.99), 3)
        out["bath_route_door"] = cap(_mx(bw.get(r["id"]) for r in lab("Bathroom")))
        out["bed_route_door_min"] = cap(_mn(bw.get(r["id"]) for r in lab("Bedroom"))) \
            if lab("Bedroom") and all(bw.get(r["id"]) is not None for r in lab("Bedroom")) else None
        out["bed_route_door_max"] = cap(_mx(bw.get(r["id"]) for r in lab("Bedroom")))
        out["kitchen_route_door"] = cap(_mx(bw.get(r["id"]) for r in lab("Kitchen")))
        ok_in = ecw is not None and ecw >= WHEELCHAIR_M - 0.025 and not estep
        wc_ok = {r["room"] for r in wc["rooms"] if r["result"] == "likely pass"} if ok_in else set()
        sf_ok = {r["room"] for r in sf["rooms"] if r["connected"]} if not estep else set()
        counted = [r for r in wc["rooms"] if not r["void"]]
        out["wheelchair_rooms_share"] = round(100 * sum(r["room"] in wc_ok for r in counted) / len(counted), 1) \
            if counted else None
        baths = {r["id"] for r in lab("Bathroom")}
        if baths:
            out["wheelchair_bath"] = int(bool(baths & wc_ok))
            out["step_free_bath"] = int(bool(baths & sf_ok))
    if ent:
        best = None
        for b in lab("Bathroom"):
            if b["floor"] != ent["floor"]:
                continue
            rt = route(plan, start_point(plan, ent), b["id"], floor=b["floor"])
            if rt["available"] and (best is None or rt["length_m"] < best["length_m"]):
                best = rt
        if best:
            out["bath_route_m"] = round(best["length_m"], 2)
            cor = [c["width"] for c in best["chokes"] if c["kind"] == "corridor"]
            legs = [l["min_width"] for l in best["legs"] if l["min_width"] is not None]
            out["bath_route_corridor"] = round(min(cor or legs), 3) if (cor or legs) else None
    ts = turning_spaces(plan)
    if ts["available"]:
        dia = {t["room"]: t["diameter"] for t in ts["rooms"]}
        r3 = lambda v: None if v is None else round(v, 3)
        out["bath_turn"] = r3(_mx(dia.get(r["id"]) for r in lab("Bathroom")))
        out["kitchen_turn"] = r3(_mx(dia.get(r["id"]) for r in lab("Kitchen")))
        out["bed_turn"] = r3(_mx(dia.get(r["id"]) for r in lab("Bedroom")))
        out["largest_turn"] = r3(_mx(dia.get(r["id"]) for r in rs))
    walls = {}
    for r in rs:
        fw = free_wall_runs(plan, r["id"])
        if fw["available"]:
            walls[r["id"]] = fw["longest"]
    if walls:
        out["longest_wall"] = round(max(walls.values()), 3)
        out["bed_wall"] = _r3(_mx(walls.get(r["id"]) for r in lab("Bedroom")))
        out["living_wall"] = _r3(_mx(walls.get(r["id"]) for r in lab("Living Room", "Family Room")))
    return out


def _r3(v):
    return None if v is None else round(v, 3)


def doors_of(plan: dict) -> list[tuple]:
    if not quality(plan).get("walls"):
        return []
    return [(plan["sid"], oid, d["kind"], d.get("width"), int(implausible(d)), sill_step(plan, d), d["floor"])
            for oid, d in links_of(plan).items() if d["kind"] != "invisible"]


def _one(sid: str) -> tuple[dict, list[tuple]]:
    from ...sources import matterport as mp
    from ...sources.index import rows
    r = rows().get(sid, {})
    row = {"sid": sid, "name": r.get("name"), "kind": r.get("kind"), "city": r.get("city"), "address": r.get("address"),
           "lat": _f(r.get("lat")), "lon": _f(r.get("lon")), "segment": r.get("segment"), "error": None}
    try:
        plan = mp.plan(sid)
    except Exception as e:
        return {**row, "error": f"plan: {type(e).__name__}: {e}"[:200]}, []
    q = quality(plan)
    row.update(walls=int(bool(q.get("walls"))), polygons=int(bool(q.get("polygons"))), labels=int(bool(q.get("labels"))),
               panos=len(plan.get("panos") or []))
    try:
        row.update(measure(plan))
        return row, doors_of(plan)
    except Exception as e:  # one odd plan must not stop the build; the row says what broke
        return {**row, "error": f"measure: {type(e).__name__}: {e}"[:200]}, []


def _f(v):
    try:
        return float(v) if v not in (None, "") else None
    except ValueError:
        return None


def connect(path=None) -> sqlite3.Connection:
    con = sqlite3.connect(path or DB)
    con.row_factory = sqlite3.Row
    return con


def build(sids: list[str], workers: int = 8, path=None) -> dict:
    DIR.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    with ProcessPoolExecutor(workers) as ex:
        res = list(ex.map(_one, sids, chunksize=8))
    secs = time.time() - t0
    measured = sum(1 for row, _ in res if row.get("walls") and not row.get("error"))
    meta = {"built_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "seconds": round(secs, 1), "scans": len(sids),
            "measured_with_walls": measured, "errors": sum(1 for row, _ in res if row.get("error")),
            "fields": len(FIELDS), "workers": workers}
    write(res, meta, path)
    return meta


def write(res: list[tuple[dict, list[tuple]]], meta: dict, path=None) -> None:
    """Replace the table at `path` with these (row, doors) results, atomically."""
    path = path or DB
    cols = META + list(FIELDS)
    tmp = path.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    con = connect(tmp)
    types = {k: "TEXT" if FIELDS[k][2] == "text" else "REAL" for k in FIELDS}
    con.execute("CREATE TABLE measures (" + ", ".join(
        [f"{c} {'TEXT PRIMARY KEY' if c == 'sid' else 'REAL' if c in ('lat', 'lon') else 'INTEGER' if c in ('walls', 'polygons', 'labels', 'panos') else 'TEXT'}"
         for c in META] + [f"{k} {types[k]}" for k in FIELDS]) + ")")
    con.execute("CREATE TABLE doors (sid TEXT, opening TEXT, kind TEXT, width REAL, implausible INTEGER, step REAL, floor TEXT)")
    con.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
    con.executemany(f"INSERT INTO measures VALUES ({', '.join('?' * len(cols))})",
                    [[row.get(c) for c in cols] for row, _ in res])
    con.executemany("INSERT INTO doors VALUES (?, ?, ?, ?, ?, ?, ?)", [d for _, ds in res for d in ds])
    con.executemany("INSERT INTO meta VALUES (?, ?)", [(k, json.dumps(v)) for k, v in meta.items()])
    con.commit()
    con.close()
    tmp.replace(path)


def stats(path=None) -> dict:
    con = connect(path)
    meta = {r["key"]: json.loads(r["value"]) for r in con.execute("SELECT * FROM meta")}
    d = con.execute("SELECT count(*) n, sum(implausible) bad, count(DISTINCT sid) scans, "
                    "count(DISTINCT CASE WHEN implausible THEN sid END) bad_scans FROM doors").fetchone()
    by = con.execute("SELECT kind, count(*) n, sum(walls) w FROM measures GROUP BY kind").fetchall()
    return {**meta, "doors": d["n"], "implausible_doors": d["bad"], "scans_with_doors": d["scans"],
            "scans_with_an_implausible_door": d["bad_scans"],
            "by_kind": {r["kind"]: {"scans": r["n"], "with_walls": r["w"]} for r in by}}


def scan_ids(walls: bool = False, path=None) -> list[str]:
    if not (path or DB).exists():
        return []
    con = connect(path)
    q = "SELECT sid FROM measures" + (" WHERE walls = 1 AND error IS NULL" if walls else "")
    return [r["sid"] for r in con.execute(q)]


def main(argv=None) -> int:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("cmd", choices=["build", "stats"])
    a.add_argument("--file", default=str(DIR / "sids.txt"))
    a.add_argument("--workers", type=int, default=8)
    args = a.parse_args(argv)
    if args.cmd == "build":
        sids = [s.strip() for s in open(args.file) if s.strip() and not s.startswith("#")]
        print(json.dumps(build(sids, args.workers), indent=1))
    print(json.dumps(stats(), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())


OPS = {">=": "{} >= ?", "<=": "{} <= ?", ">": "{} > ?", "<": "{} < ?", "==": "{} = ?", "!=": "{} != ?"}


def parse(expr: str) -> dict:
    """'bath_route_door>=0.81' -> {measure, op, value}. Raises ValueError with a message for people."""
    for op in (">=", "<=", "==", "!=", ">", "<", "="):
        if op in expr:
            m, v = (x.strip() for x in expr.split(op, 1))
            op = "==" if op == "=" else op
            if m not in FIELDS:
                raise ValueError(f"unknown measure {m!r}")
            try:
                val = float(v) if FIELDS[m][2] != "text" else v
            except ValueError:
                raise ValueError(f"{m} needs a number, not {v!r}") from None
            return {"measure": m, "op": op, "value": val}
    raise ValueError(f"no comparison in {expr!r}; write e.g. bath_route_door>=0.81")


def _margin(c: dict, v) -> float:
    """How comfortably a value passes, 0 to 1: the excess over the threshold relative to the threshold."""
    if FIELDS[c["measure"]][2] in ("text", "flag") or c["op"] in ("==", "!="):
        return 0.0
    t = c["value"]
    scale = max(abs(t), 0.1 if FIELDS[c["measure"]][1] == "m" else 1.0)
    d = (v - t) if c["op"] in (">=", ">") else (t - v)
    return max(0.0, min(1.0, d / scale))


def search(criteria: list[dict], *, city: str | None = None, kind: str | None = None, sort: str | None = None,
           limit: int = 20, path=None) -> dict:
    """Scans meeting every criterion, best first. Each row has the measured value per criterion and why it passed.
    Also counts the scans that could not answer (a criterion's measure is unknown for them)."""
    for c in criteria:
        if c["measure"] not in FIELDS or c["op"] not in OPS:
            raise ValueError(f"bad criterion {c}")
    if sort and sort not in FIELDS:
        raise ValueError(f"unknown sort measure {sort!r}")
    con = connect(path)
    base, args = ["error IS NULL"], []
    if city:
        base.append("city LIKE ?")
        args.append(f"%{city}%")
    if kind:
        base.append("kind = ?")
        args.append(kind)
    pool = con.execute(f"SELECT count(*) FROM measures WHERE {' AND '.join(base)}", args).fetchone()[0]
    known = base + [f"{c['measure']} IS NOT NULL" for c in criteria]
    answerable = con.execute(f"SELECT count(*) FROM measures WHERE {' AND '.join(known)}", args).fetchone()[0]
    where = known + [OPS[c["op"]].format(c["measure"]) for c in criteria]
    rows = con.execute(f"SELECT * FROM measures WHERE {' AND '.join(where)}", args + [c["value"] for c in criteria])
    hits = []
    for r in rows:
        r = dict(r)
        why = [f"{FIELDS[c['measure']][0]} {_show(c['measure'], r[c['measure']])} {c['op']} "
               f"{_show(c['measure'], c['value'])}" for c in criteria]
        score = sum(_margin(c, r[c["measure"]]) for c in criteria) / max(len(criteria), 1)
        hits.append({"sid": r["sid"], "name": r["name"], "kind": r["kind"], "city": r["city"], "address": r["address"],
                     "lat": r["lat"], "lon": r["lon"], "score": round(score, 3), "why": why,
                     "values": {c["measure"]: r[c["measure"]] for c in criteria} |
                     ({sort: r[sort]} if sort else {})})
    key = (lambda h: (-(h["values"][sort] or 0), -h["score"])) if sort else (lambda h: -h["score"])
    hits.sort(key=key)
    return {"criteria": criteria, "pool": pool, "answerable": answerable, "matches": len(hits),
            "rows": hits[:limit], "built": {r["key"]: json.loads(r["value"]) for r in con.execute("SELECT * FROM meta")}}


def _show(m: str, v) -> str:
    unit = FIELDS[m][1]
    if FIELDS[m][2] == "flag":
        return "yes" if v else "no"
    if isinstance(v, float) and unit == "m":
        return f"{v:.2f} m"
    if isinstance(v, float) and v == int(v):
        return f"{int(v)}{' ' + unit if unit else ''}"
    return f"{v}{' ' + unit if unit and unit != '%' else unit}"
