"""Garage columns for the measures table (measure_search.table.FIELDS), so homes can be searched by their garage.

    uv run python -m threshold.tools.garage_fit.measures      # fill them in for the scans that have a garage

Vehicle-free sizes only (inside width and depth, widest vehicle door and its height, ceiling); garage_fit's search
turns a vehicle and a count into criteria on them and then re-parks the vehicles in each candidate's plan.
Reads cached plans only, so it calls no API.
"""
from __future__ import annotations

import sys

from . import geom

FIELDS = {
    "garage_width": ("Garage inside width", "m", "num", "Across the garage halfway in, at the inner wall faces"),
    "garage_depth": ("Garage inside depth", "m", "num", "From the vehicle door (or a wall) to the back wall"),
    "garage_door_width": ("Garage door width", "m", "num", "Widest car-wide opening in the garage"),
    "garage_door_height": ("Garage door height", "m", "num", "Only when the scan measured it"),
    "garage_ceiling": ("Garage ceiling", "m", "num", "The garage room's height in the scan"),
}


def garage_measures(plan: dict) -> dict:
    out = dict.fromkeys(FIELDS)
    gs = geom.find_garages(plan)
    s = geom.survey(plan, gs[0]["room"]) if gs else None
    if s is None:
        return out
    size = geom.size_in(s["frames"][0].geom(s["clear"]), s["doors"])
    hs = [d["height"] for d in s["doors"] if d["measured"]]
    r3 = lambda v: None if v is None else round(v, 3)
    out.update(garage_width=r3(size["width"]), garage_depth=r3(size["depth"]),
               garage_door_width=r3(max((d["width"] for d in s["doors"]), default=None)),
               garage_door_height=r3(min(hs)) if hs else None,
               garage_ceiling=r3(s["ceiling"]["value"]) if s["ceiling"]["measured"] else None)
    return out


def backfill(path=None) -> dict:
    """Add the columns to the SQLite measures table if missing and fill them for every scan with a garage."""
    from ...facts.load import cached_plan
    from ..measure_search import table
    con = table.connect(path)
    have = {r[1] for r in con.execute("PRAGMA table_info(measures)")}
    for k in FIELDS:
        if k not in have:
            con.execute(f"ALTER TABLE measures ADD COLUMN {k} REAL")
    sids = [r[0] for r in con.execute("SELECT sid FROM measures WHERE garages > 0 AND error IS NULL")]
    done = 0
    for sid in sids:
        plan = cached_plan(sid)
        if plan is None:
            continue
        m = garage_measures(plan)
        con.execute(f"UPDATE measures SET {', '.join(f'{k} = ?' for k in FIELDS)} WHERE sid = ?", [*m.values(), sid])
        done += m["garage_width"] is not None
    con.commit()
    return {"garage_scans": len(sids), "measured": done}


if __name__ == "__main__":
    print(backfill())
    sys.exit(0)
