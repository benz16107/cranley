"""Direct sun through each window of a scan on given days, with neighbours and trees from the surface model.

A window gets direct sun at a moment when the sun is up, within 90 degrees of the way the window faces (from the
wall graph turned by the scan's verified compass rotation, geometry.georef.facing) and above the surface model's
horizon seen from the window's middle. The window's height comes from the scan: its sill and height above its own
floor, plus that floor's height above the lowest floor, plus an assumed 0.2 m from the soil to the lowest floor.
"""
from __future__ import annotations

import datetime as dt

import numpy as np

from ..geometry import georef
from ..geometry._plan import floor_z
from ..world.site import FLOOR_ABOVE_GROUND_M
from . import horizon as hz
from .path import day_path, off_normal

OUT_M = 0.3  # trace from just outside the glass


def window_points(plan: dict) -> list[dict]:
    """Every exterior window with its compass facing, east/north position about the geo anchor and height above
    the ground in metres. Empty when the scan has no geocoordinates or no windows."""
    f = georef.facing(plan)
    if not f["available"]:
        return []
    fz = floor_z(plan)
    low = min(fz.values(), default=0.0)
    ops = {o["id"]: o for o in plan.get("openings") or []}
    out = []
    for w in f["openings"]:
        if w["type"] != "window":
            continue
        o = ops[w["opening"]]
        fl = fz.get(o["floor"], low)
        mid = (o.get("sill") if o.get("sill") is not None else fl + 0.9) - fl + (o.get("height") or 1.2) / 2
        en = georef.to_enu(plan, *o["center"])
        az = np.radians(w["azimuth_deg"])
        out.append({**w, "floor": o["floor"], "e": en[0] + OUT_M * np.sin(az), "n": en[1] + OUT_M * np.cos(az),
                    "above_ground_m": round(FLOOR_ABOVE_GROUND_M + (fl - low) + mid, 2),
                    "glass_m2": round((o.get("width") or 0) * (o.get("height") or 0), 2)})
    return out


def window_sun(plan: dict, days: list[dt.date], g: dict | None = None, step_min: int = 10) -> dict:
    """{available, windows: [{..., horizon, days: {iso: {hours, blocked_hours, minutes, front, spans}}}], obstruction}.
    `minutes` are the local minutes of the day with direct sun, `front` those with the sun in front of the window,
    shaded or not. `g` is the surface model grid round the scan's geo anchor (horizon.grid); None traces with no obstruction."""
    wins = window_points(plan)
    if not wins:
        f = georef.facing(plan)
        return {"available": False, "reason": f.get("reason") or "The wall graph records no exterior windows."}
    lat, lon = plan["geo"]["lat"], plan["geo"]["lon"]
    paths = {d.isoformat(): day_path(lat, lon, d, step_min) for d in days}
    for w in wins:
        if g is not None:
            ground = hz.local_ground(g, w["e"], w["n"])
            w["horizon"] = hz.horizon(g, w["e"], w["n"], ground + w["above_ground_m"], facing=w["azimuth_deg"])
        w["days"] = {}
        for iso, path in paths.items():
            if not path:
                w["days"][iso] = {"hours": 0.0, "blocked_hours": 0.0, "minutes": set(), "front": set(), "spans": []}
                continue
            t = [p[0] for p in path]
            az, el = np.array([p[1] for p in path]), np.array([p[2] for p in path])
            front = off_normal(az, w["azimuth_deg"]) < 90
            shade = hz.blocked(w["horizon"], az, el) if g is not None else np.zeros(len(az), bool)
            lit = front & ~shade
            mins = {t[i].hour * 60 + t[i].minute for i in np.flatnonzero(lit)}
            ahead = {t[i].hour * 60 + t[i].minute for i in np.flatnonzero(front)}
            w["days"][iso] = {"hours": round(lit.sum() * step_min / 60, 2),
                              "blocked_hours": round((front & shade).sum() * step_min / 60, 2),
                              "minutes": mins, "front": ahead, "spans": spans(sorted(mins), step_min)}
    return {"available": True, "windows": wins, "obstruction": g is not None, "step_min": step_min,
            "sunrise_sunset": {iso: (p[0][0].strftime("%H:%M"), (p[-1][0] + dt.timedelta(minutes=step_min)).strftime("%H:%M"))
                               if p else None for iso, p in paths.items()}}


def spans(minutes: list[int], step: int) -> list[list[str]]:
    """Runs of consecutive slots as [["HH:MM", "HH:MM"], ...]."""
    out, cur = [], None
    for m in minutes:
        if cur and m - cur[1] <= step:
            cur[1] = m
        else:
            cur = [m, m]
            out.append(cur)
    f = lambda m: f"{m // 60:02d}:{m % 60:02d}"  # noqa: E731
    return [[f(a), f(b + step)] for a, b in out]
