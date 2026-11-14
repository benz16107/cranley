"""Measure search in Postgres: the same criteria and result shape as measure_search.table.search, plus a distance
filter (PostGIS, spatial index) and room-level criteria (a kitchen over 12 m2, a bathroom with a 1.5 m turning circle).
Each result carries the SQL it ran, so the answer can show its evidence."""
from __future__ import annotations

import json
import time

from ..tools.measure_search import table as mt
from . import db

ROOM_MEASURES = {"area": ("Room area", "m2"), "turn_diameter": ("Turning circle", "m"),
                 "widest_door": ("Widest door", "m"), "narrowest_door": ("Narrowest door", "m"),
                 "windows": ("Windows", ""), "glazed_area": ("Glazed area", "m2"), "height": ("Ceiling", "m")}


def _room_clause(i: int, rc: dict, args: dict) -> str:
    """EXISTS a room of the label meeting every measure in rc['where']."""
    if not rc.get("label"):
        raise ValueError("a room criterion needs a label, e.g. Kitchen")
    parts = ["r.sid = s.sid", f"r.label ILIKE :rl{i}"]
    args[f"rl{i}"] = rc["label"]
    for j, c in enumerate(rc.get("where") or []):
        if c["measure"] not in ROOM_MEASURES or c["op"] not in mt.OPS:
            raise ValueError(f"bad room criterion {c}")
        parts.append(mt.OPS[c["op"]].format(f"r.{c['measure']}").replace("?", f"CAST(:rv{i}_{j} AS double precision)"))
        args[f"rv{i}_{j}"] = float(c["value"])
    return "EXISTS (SELECT 1 FROM room r WHERE " + " AND ".join(parts) + ")"


def search(criteria: list[dict], *, city: str | None = None, kind: str | None = None, sort: str | None = None,
           limit: int = 20, near: tuple[float, float] | None = None, within_m: float | None = None,
           rooms: list[dict] | None = None) -> dict:
    for c in criteria:
        if c["measure"] not in mt.FIELDS or c["op"] not in mt.OPS:
            raise ValueError(f"bad criterion {c}")
    if sort and sort not in mt.FIELDS:
        raise ValueError(f"unknown sort measure {sort!r}")
    if within_m is not None and near is None:
        raise ValueError("within needs a point to measure from")
    base, args = ["m.error IS NULL"], {}
    if city:
        base.append("s.city ILIKE :city")
        args["city"] = f"%{city}%"
    if kind:
        base.append("s.kind = :kind")
        args["kind"] = kind
    if near is not None:
        args["lat"], args["lon"] = near
        if within_m is not None:
            base.append("ST_DWithin(s.geom, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, :within)")
            args["within"] = float(within_m)
    for i, rc in enumerate(rooms or []):
        base.append(_room_clause(i, rc, args))
    known = base + [f"m.{c['measure']} IS NOT NULL" for c in criteria]
    base_args = dict(args)
    where = list(known)
    for i, c in enumerate(criteria):
        typ = "text" if mt.FIELDS[c["measure"]][2] == "text" else "double precision"  # 2.0 against a smallint column
        where.append(mt.OPS[c["op"]].format(f"m.{c['measure']}").replace("?", f"CAST(:v{i} AS {typ})"))
        args[f"v{i}"] = c["value"]
    frm = "FROM scan s JOIN measures m USING (sid)"
    dist = "ST_Distance(s.geom, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography)" if near else "NULL"
    cols = sorted({c["measure"] for c in criteria} | ({sort} if sort else set()))
    sql = (f"SELECT s.sid, s.name, s.kind, s.city, s.address, ST_Y(s.geom::geometry) AS lat, "
           f"ST_X(s.geom::geometry) AS lon, {dist} AS distance_m"
           + "".join(f", m.{c}" for c in cols) + f" {frm} WHERE {' AND '.join(where)}")
    t0 = time.perf_counter()
    counts = db.rows(f"SELECT count(*) FILTER (WHERE {' AND '.join(known)}) AS answerable, count(*) AS pool {frm} "
                     f"WHERE {' AND '.join(base)}", **base_args)[0]
    hits = []
    for r in db.rows(sql, **args):
        why = [f"{mt.FIELDS[c['measure']][0]} {mt._show(c['measure'], r[c['measure']])} {c['op']} "
               f"{mt._show(c['measure'], c['value'])}" for c in criteria]
        if r["distance_m"] is not None:
            why.append(f"{r['distance_m'] / 1000:.1f} km away")
        score = sum(mt._margin(c, r[c["measure"]]) for c in criteria) / max(len(criteria), 1)
        hits.append({"sid": r["sid"], "name": r["name"], "kind": r["kind"], "city": r["city"], "address": r["address"],
                     "lat": r["lat"], "lon": r["lon"], "score": round(score, 3), "why": why,
                     "distance_m": round(r["distance_m"]) if r["distance_m"] is not None else None,
                     "values": {c: r[c] for c in cols}})
    key = (lambda h: (-(h["values"][sort] or 0), -h["score"])) if sort else \
        (lambda h: (-h["score"], h["distance_m"] or 0))
    hits.sort(key=key)
    meta = (db.rows("SELECT value FROM meta WHERE key = 'load'") or [{"value": {}}])[0]["value"]
    meta = json.loads(meta) if isinstance(meta, str) else meta
    return {"criteria": criteria, "rooms": rooms or [], "pool": counts["pool"], "answerable": counts["answerable"],
            "matches": len(hits), "rows": hits[:limit], "engine": "postgres",
            "ms": round((time.perf_counter() - t0) * 1000, 1), "sql": sql, "params": args,
            "built": {"scans": meta.get("scans"), "built_at": meta.get("measures_built_at"), "loaded_at": meta.get("at")}}
