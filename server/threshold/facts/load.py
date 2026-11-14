"""Fill the facts database from what is already on disk: the measures table (tool/access), the cached Matterport
models, the label overlay, the CoStar kit and the footprint fits. Nothing here calls an outside API.

Per scan: a `scan` row with its point, a `measures` row, one `room` row per room (area, doors, turning circle,
windows), its `door` rows, and seed facts (every measure, room facts, and the cheap record-versus-scan comparison
from record_vs_reality). Buildings group scans as /api/buildings does (CoStar property, else address).
"""
from __future__ import annotations

import csv
import io
import json
import math
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime

from ..config import CACHE
from ..tools.measure_search import table as mt
from . import db

FACT_COLS = ["at", "sid", "room", "field", "value_num", "value_text", "unit", "layer", "method", "confidence", "tool",
             "run", "evidence", "record_value", "record_path"]
M_PER_DEG_LAT = 110_540.0


def cached_plan(sid: str) -> dict | None:
    """The ScanPlan from the cached model, with the label overlay; None when the model is not cached. Skips wall
    recovery and the footprint refit, which can call Matterport and Vexcel, so this reads what the measures table
    measured."""
    from ..scanplan import normalize
    from ..sources import index
    from ..tools.room_labeller import store
    f = CACHE / "model" / f"{sid}.json"
    if not f.exists():
        return None
    return store.apply(normalize(json.loads(f.read_text()), index.rows().get(sid)))


def _footprint_wkt(sid: str, plan: dict) -> str | None:
    """The aerial building outline the scan was fitted to (east/north metres around the scan's point), as lon/lat."""
    f = CACHE / "georef_fit" / f"{sid}.json"
    g = plan.get("geo") or {}
    if not f.exists() or g.get("lat") is None:
        return None
    ring = json.loads(f.read_text()).get("footprint_enu") or []
    if len(ring) < 4:
        return None
    lat0, lon0 = g["lat"], g["lon"]
    k = M_PER_DEG_LAT * math.cos(math.radians(lat0))
    pts = [(lon0 + e / k, lat0 + n / M_PER_DEG_LAT) for e, n in ring]
    if pts[0] != pts[-1]:
        pts.append(pts[0])
    return "SRID=4326;POLYGON((" + ",".join(f"{x:.8f} {y:.8f}" for x, y in pts) + "))"


def room_rows(plan: dict) -> list[dict]:
    from ..geometry import turning_spaces
    from ..geometry._plan import clear_width
    from ..tools._access import implausible, links_of, quality
    q = quality(plan)
    doors: dict[str, list[float]] = {}
    if q.get("walls"):
        for d in links_of(plan).values():
            if d["kind"] == "invisible" or d.get("width") is None or implausible(d):
                continue
            for r in d.get("rooms") or ([d["room"]] if d.get("room") else []):
                doors.setdefault(r, []).append(clear_width(d))
    ts = turning_spaces(plan) if q.get("polygons") else {"available": False}
    turn = {t["room"]: t["diameter"] for t in ts.get("rooms", [])} if ts.get("available") else {}
    wins: dict[str, list[dict]] = {}
    for o in plan.get("openings") or []:
        if o["type"] == "window":
            for r in o.get("rooms") or []:
                wins.setdefault(r, []).append(o)
    out = []
    for r in plan.get("rooms") or []:
        if r.get("label") == "Void":
            continue
        ds, ws = doors.get(r["id"], []), wins.get(r["id"], [])
        out.append({"sid": plan["sid"], "room": r["id"], "floor": r.get("floor"), "label": r.get("label"),
                    "label_source": r.get("label_source"), "area": r.get("area"), "width": r.get("width"),
                    "depth": r.get("depth"), "height": r.get("height"), "doors": len(ds) if q.get("walls") else None,
                    "widest_door": round(max(ds), 3) if ds else None, "narrowest_door": round(min(ds), 3) if ds else None,
                    "turn_diameter": round(turn[r["id"]], 3) if r["id"] in turn else None,
                    "windows": len(ws) if q.get("walls") else None,
                    "glazed_area": round(sum((o.get("width") or 0) * (o.get("height") or 0) for o in ws), 2) if ws else None})
    return out


def comparisons(sid: str, plan: dict) -> list[dict]:
    """The cheap record-versus-scan rows (field_audit.rows_for over record_vs_reality.audit, no model or aerial)."""
    from ..tools.field_audit import rows_for
    from ..tools.record_vs_reality import audit, gather
    rec = gather.record(sid)
    if rec is None:
        return []
    return rows_for(sid, None, plan, audit(plan, rec, deep=False))


def _property(sid: str) -> tuple[int | None, str | None, float | None]:
    """(CoStar property id, property type, listed area in ft2) from the kit; Nones when the kit has nothing."""
    from ..sources import costar
    from ..tools.room_labeller.facts import PROPERTY_TYPES
    try:
        pid = costar.property_id_of(sid)
        prop = costar.get("commercial-property", pid) if pid else None
        if prop:
            return pid, PROPERTY_TYPES.get(prop.get("propertyType")), prop.get("grossBuildingAreaSquareFeet")
        ids = costar.resolve(sid)
        if ids["listing_ids"]:
            feat = costar.get("residential-listing-features", ids["listing_ids"][0]) or {}
            return None, "home", (feat.get("derivedValues") or {}).get("homeSquareFeet")
    except Exception:  # noqa: BLE001 - no kit, or a scan the kit does not know
        pass
    return None, None, None


def one(sid: str, measure: bool = False) -> dict:
    """Everything the database holds about one scan, computed in a worker process. `measure` also runs the
    measures table's own measurement (for cached scans the table was not built over)."""
    out = {"sid": sid, "rooms": [], "compare": [], "footprint": None, "error": None, "measures": None, "doors": []}
    out["property_id"], out["property_type"], out["listed_area"] = _property(sid)
    try:
        plan = cached_plan(sid)
    except Exception as e:  # noqa: BLE001 - the row says what broke
        out["error"] = f"plan: {type(e).__name__}: {e}"[:200]
        return out
    if plan is None:
        out["error"] = "model not cached"
        return out
    out["floors"] = len(plan.get("floors") or [])
    if measure:
        from ..sources import index
        from ..tools._access import quality
        r, q = index.rows().get(sid, {}), quality(plan)
        out["measures"] = {"sid": sid, "name": r.get("name"), "kind": r.get("kind"), "city": r.get("city"),
                           "address": r.get("address"), "lat": mt._f(r.get("lat")), "lon": mt._f(r.get("lon")),
                           "segment": r.get("segment"), "walls": int(bool(q.get("walls"))),
                           "polygons": int(bool(q.get("polygons"))), "labels": int(bool(q.get("labels"))),
                           "panos": len(plan.get("panos") or []), "error": None}
        try:
            out["measures"].update(mt.measure(plan))
            out["doors"] = [list(d) for d in mt.doors_of(plan)]
        except Exception as e:  # noqa: BLE001
            out["measures"]["error"] = f"measure: {type(e).__name__}: {e}"[:200]
    out["footprint"] = _footprint_wkt(sid, plan)
    for name, fn in (("rooms", room_rows), ("compare", lambda p: comparisons(sid, p))):
        try:
            out[name] = fn(plan)
        except Exception as e:  # noqa: BLE001
            out["error"] = f"{name}: {type(e).__name__}: {e}"[:200]
    return out


def _csv(rows: list[list]) -> io.StringIO:
    buf = io.StringIO()
    w = csv.writer(buf)
    for r in rows:
        w.writerow(["" if v is None else ("t" if v is True else "f" if v is False else v) for v in r])
    buf.seek(0)
    return buf


def copy(c, tbl: str, cols: list[str], rows: list[list]) -> None:
    if rows:
        c.run(f"COPY {tbl} ({', '.join(cols)}) FROM STDIN WITH (FORMAT csv, NULL '')", stream=_csv(rows))


def _point(lat, lon) -> str | None:
    return f"SRID=4326;POINT({lon} {lat})" if lat is not None and lon is not None else None


def _created(v: str | None) -> str | None:
    return v or None


def fact_rows(sid: str, m: dict, rooms: list[dict], compare: list[dict], at: str) -> list[list]:
    """Seed facts: each measure, room facts and the record comparisons."""
    out = []
    for k, (label, unit, kind, _) in mt.FIELDS.items():
        v = m.get(k)
        if v is None:
            continue
        num, txt = (None, v) if kind == "text" else (float(v), None)
        out.append([at, sid, None, k, num, txt, unit or None, "matterport", "geometry", "medium", "measure_search",
                    None, json.dumps({"table": "measures", "label": label}), None, None])
    for r in rooms:
        for k, unit in (("area", "m2"), ("turn_diameter", "m"), ("widest_door", "m"), ("narrowest_door", "m"),
                        ("windows", None)):
            if r.get(k) is not None:
                out.append([at, sid, r["room"], f"room.{k}", float(r[k]), r.get("label"), unit, "matterport", "geometry",
                            "medium" if k != "area" else "high", "facts.load", None, None, None, None])
    for c in compare:
        num = float(c["measured_value"]) if isinstance(c["measured_value"], (int, float)) else None  # bools to 1/0
        ev = {"ratio": c["ratio"], "reason": c["reason"], "scope": c["scope"], "evidence": c["evidence"],
              "origin": c["record_origin"], "record_unit": c["record_unit"]}
        out.append([at, sid, None, f"vs_record.{c['claim_key']}", num, c["verdict"], c["measured_unit"], "costar",
                    "lookup", c["confidence"], "record_vs_reality", None, json.dumps(ev, default=str),
                    json.dumps(c["record_value"], default=str), c["record_path"]])
        if c["field"] == "area" and c["ratio"]:  # measured over listed, minus one: the gap a rollup takes medians of
            out.append([at, sid, None, "area_gap", c["ratio"] - 1, c["verdict"], "ratio", "costar", "lookup",
                        c["confidence"], "record_vs_reality", None, json.dumps(ev, default=str),
                        json.dumps(c["record_value"], default=str), c["record_path"]])
    return out


def load(sids: list[str] | None = None, workers: int = 8) -> dict:
    """Replace the scans, buildings, measures, rooms, doors and seed facts. Facts from tool runs are kept."""
    from ..sources import costar, index
    t0 = time.time()
    src = mt.connect()
    meas = {r["sid"]: dict(r) for r in src.execute("SELECT * FROM measures")}
    built = {r["key"]: json.loads(r["value"]) for r in src.execute("SELECT * FROM meta")}
    doors = [list(r) for r in src.execute("SELECT * FROM doors")]
    if sids is None:  # every scan in the measures table, plus every other scan whose model is cached
        sids = list(meas) + sorted({f.stem for f in (CACHE / "model").glob("*.json")} - set(meas))
    with ProcessPoolExecutor(workers) as ex:
        per = {r["sid"]: r for r in ex.map(one, sids, [s not in meas for s in sids], chunksize=8)}
    for s in sids:
        if s not in meas and per[s]["measures"]:
            meas[s] = per[s]["measures"]
            doors += per[s]["doors"]
    sids = [s for s in sids if s in meas]
    t_compute = time.time() - t0
    try:
        pid_of = costar.property_id_of
        costar.joins()
    except Exception:  # noqa: BLE001 - without the kit, group by the index column
        pid_of = None
    bid = {}
    groups = {}
    for b in index.buildings(pid_of):
        for s in b["scans"]:
            bid[s["sid"]] = b["id"]
        groups[b["id"]] = b
    rows = index.rows()
    at = datetime.fromisoformat(built["built_at"]).replace(tzinfo=UTC).isoformat() if built.get("built_at") \
        else datetime.now(UTC).isoformat()
    b_rows, seen = [], set()
    for s in sids:
        b = groups.get(bid.get(s))
        if not b or b["id"] in seen:
            continue
        seen.add(b["id"])
        p = per[s]
        fps = [per[x["sid"]]["footprint"] for x in b["scans"] if x["sid"] in per and per[x["sid"]]["footprint"]]
        b_rows.append([b["id"], b["property_id"], b["address"], b["city"], rows[s].get("postal_code") or None,
                       p["property_type"] or rows[s]["kind"], p["listed_area"], _point(b["lat"], b["lon"]),
                       fps[0] if fps else None])
    s_rows, m_rows, r_rows, f_rows = [], [], [], []
    mcols = ["sid", "error"] + list(mt.FIELDS)
    rcols = ["sid", "room", "floor", "label", "label_source", "area", "width", "depth", "height", "doors", "widest_door",
             "narrowest_door", "turn_diameter", "windows", "glazed_area"]
    for s in sids:
        m, r, p = meas[s], rows.get(s, {}), per[s]
        s_rows.append([s, bid.get(s) if bid.get(s) in seen else None, m["name"], m["kind"], m["segment"], m["city"],
                       r.get("postal_code") or None, m["address"], _point(m["lat"], m["lon"]), bool(m["walls"]),
                       bool(m["polygons"]), bool(m["labels"]), m["panos"], p.get("floors"), _created(r.get("created"))])
        m_rows.append([int(m[c]) if m.get(c) is not None and mt.FIELDS.get(c, ("", "", ""))[2] in ("count", "flag")
                       else m.get(c) for c in mcols])
        r_rows += [[x[c] for c in rcols] for x in p["rooms"]]
        f_rows += fact_rows(s, m if not m.get("error") else {}, p["rooms"], p["compare"], at)
    with db.transaction() as c:
        c.run("DELETE FROM fact WHERE tool IN ('measure_search', 'facts.load', 'record_vs_reality') AND run IS NULL")
        for t in ("room_text", "door", "room", "measures", "flood_depth", "flood_run"):
            c.run(f"DELETE FROM {t}")
        c.run("DELETE FROM scan")
        c.run("DELETE FROM building")
        copy(c, "building", ["id", "property_id", "address", "city", "zip", "property_type", "listed_area_ft2", "geom",
                             "footprint"], b_rows)
        copy(c, "scan", ["sid", "building_id", "name", "kind", "segment", "city", "zip", "address", "geom", "walls",
                         "polygons", "labels", "panos", "floors", "created"], s_rows)
        copy(c, "measures", mcols, m_rows)
        copy(c, "room", rcols, r_rows)
        copy(c, "door", ["sid", "opening", "kind", "width", "implausible", "step", "floor"],
             [d[:4] + [bool(d[4])] + d[5:] for d in doors if d[0] in set(sids)])
        copy(c, "fact", FACT_COLS, f_rows)
        c.run("INSERT INTO meta VALUES ('load', CAST(:v AS jsonb)) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
              v=json.dumps({"at": datetime.now(UTC).isoformat(), "scans": len(sids), "measures_built_at": built.get("built_at")}))
    errors = [p["error"] for p in per.values() if p["error"]]
    return {"scans": len(sids), "buildings": len(b_rows), "rooms": len(r_rows), "facts": len(f_rows),
            "footprints": sum(1 for b in b_rows if b[-1]), "errors": len(errors),
            "error_kinds": sorted({e.split(":")[0] for e in errors}), "compute_s": round(t_compute, 1),
            "total_s": round(time.time() - t0, 1)}
