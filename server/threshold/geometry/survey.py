"""Run every geometry function over the ScanPlan fixtures and print which ones answer, with timings.

    cd server && uv run python -m threshold.geometry.survey
"""
from __future__ import annotations

import datetime as dt
import json
import time

from threshold.config import DATA

from . import (
    carry,
    evaluate_pack,
    facing,
    free_wall_runs,
    list_packs,
    reach,
    room_graph,
    route,
    sun_on_windows,
    takeoff,
    to_latlon,
    turning_spaces,
    water,
)
from ._plan import floor_z

FIXTURES = DATA / "fixtures" / "scanplan"


def _target(plan: dict) -> dict | None:
    named = [r for r in plan["rooms"] if r["walls"] and r.get("label") not in (None, "Void")]
    pool = named or [r for r in plan["rooms"] if r["walls"]]
    return max(pool, key=lambda r: r.get("area") or 0) if pool else None


def _all_runs(plan: dict) -> dict:
    rs = [free_wall_runs(plan, r["id"]) for r in plan["rooms"]]
    return {"available": any(r["available"] for r in rs), "runs": rs}


def survey_plan(plan: dict) -> dict[str, tuple[bool, str, float]]:
    """Function name -> (answered, short note, seconds)."""
    t = _target(plan)
    fl = t["floor"] if t else None
    lowest = min(floor_z(plan).values(), default=0.0)
    calls = {
        "room_graph": lambda: room_graph(plan),
        "route": lambda: route(plan, "entrance", t["id"], floor=fl) if t else {"available": False, "reason": "no rooms with walls"},
        "reach": lambda: reach(plan, 0.8128),
        "turning": lambda: turning_spaces(plan),
        "carry": lambda: carry(plan, "entrance", t["id"], (2.0, 0.85, 0.8), floor=fl) if t else {"available": False, "reason": "no rooms with walls"},
        "wall_runs": lambda: _all_runs(plan),
        **{f"pack:{p['id']}": (lambda pid=p["id"]: evaluate_pack(plan, pid)) for p in list_packs()},
        "takeoff": lambda: takeoff(plan),
        "latlon": lambda: {"available": to_latlon(plan, 0.0, 0.0) is not None},
        "facing": lambda: facing(plan),
        "sun": lambda: sun_on_windows(plan, dt.date(2026, 11, 14)),
        "water": lambda: water(plan, lowest + 0.3),
    }
    out = {}
    for name, fn in calls.items():
        t0 = time.perf_counter()
        r = fn()
        dt_s = time.perf_counter() - t0
        ok = r.get("available", True) and (r.get("verdict", {}).get("status") != "unknown")
        out[name] = (bool(ok), _note(name, r), dt_s)
    return out


def _note(name: str, r: dict) -> str:
    if not r.get("available", True):
        return r.get("reason", "")[:60]
    if name == "room_graph":
        return f"{len(r['links'])} links, {len(r['entrances'])} entrances, {len(r['components'])} components"
    if name == "route":
        n = r["narrowest"]
        return f"{r['length_m']:.1f} m, narrowest {n['width']:.2f} m {n['kind']}" if n else f"{r['length_m']:.1f} m"
    if name == "reach":
        return f"{sum(x['result'] == 'likely pass' for x in r['rooms'])}/{len(r['rooms'])} rooms at 0.81 m"
    if name == "carry":
        return r["result"]
    if name.startswith("pack:"):
        return r["verdict"]["status"]
    if name == "takeoff":
        return f"{r['total']['floor_area']:.0f} m2, {r['total']['windows']} windows"
    if name == "facing":
        return f"{len(r['openings'])} exterior openings"
    if name == "water":
        return f"{sum(x['depth'] > 0 for x in r['rooms'])} rooms wet at +0.3 m"
    return ""


def main() -> None:
    files = sorted(FIXTURES.glob("*.json"))
    if not files:
        print(f"No fixtures in {FIXTURES}")
        return
    rows, worst = [], 0.0
    for f in files:
        plan = json.loads(f.read_text())
        res = survey_plan(plan)
        worst = max(worst, sum(v[2] for v in res.values()))
        rows.append((plan["sid"], len(plan.get("walls") or []), res))
    names = list(rows[0][2])
    print("sid          walls  " + "  ".join(n.replace("pack:", "")[:8].ljust(8) for n in names))
    for sid, nw, res in rows:
        print(f"{sid}  {nw:5d}  " + "  ".join(("yes" if res[n][0] else "-").ljust(8) for n in names))
    print(f"\nslowest scan, all functions together: {worst:.2f} s\n")
    for sid, _, res in rows:
        print(sid, "; ".join(f"{n}: {v[1]}" for n, v in res.items() if v[1]))


if __name__ == "__main__":
    main()
