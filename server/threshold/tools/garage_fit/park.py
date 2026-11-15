"""Park a vehicle in a surveyed garage: how many fit with doors open and squeezed, where, and the clearances."""
from __future__ import annotations

from dataclasses import dataclass

import shapely
from shapely.geometry import box

from . import geom
from .vehicles import GYM_PLATFORM_M, STAND_M, THINGS

MAX_CARS = 5


@dataclass
class Dims:
    label: str
    length: float
    width: float
    mirrors: float
    height: float   # with lift and roof load
    door: float
    ramp: float = 0.0
    towed: bool = False


def level(d: Dims, which: str) -> dict:
    """Clearances a layout must keep: 'fits' (doors open, walk round, mirrors out) or 'tight' (squeeze out, mirrors
    folded, bumper to the wall). Towed things have no doors: only room to walk past."""
    side = (d.door if not d.towed else 0.60) if which == "fits" else geom.SQUEEZE_M if not d.towed else 0.15
    return {"gap": side, "front": geom.FRONT_FITS_M if which == "fits" else geom.FRONT_TIGHT_M,
            "rear": geom.REAR_M if which == "fits" else geom.REAR_TIGHT_M,
            "span": d.mirrors + 2 * geom.MIRROR_MARGIN_M if which == "fits" else d.width + 2 * geom.BODY_MARGIN_M}


def _most(region, d: Dims, doors: list[dict], which: str) -> tuple[int, list | None]:
    lv = level(d, which)
    n, best = 0, None
    for k in range(1, MAX_CARS + 1):
        cars = geom.place(region, k, d.width, d.length, geom.gaps_for(k, lv["gap"], d.ramp), lv["front"], doors, lv["span"],
                          lv["rear"])
        if cars is None:
            break
        n, best = k, cars
    return n, best


def analyse(plan: dict, garage: dict, d: Dims, want: int | None) -> dict | None:
    """Everything garage_fit reports, as plain numbers. None when the garage has no outline to measure."""
    s = geom.survey(plan, garage["room"])
    if s is None:
        return None
    best = None
    for f in s["frames"]:
        region = f.geom(s["clear"]).buffer(0.002, join_style="mitre")  # flush with a wall: float noise said outside
        doors = s["doors"]
        fits, fits_cars = _most(region, d, doors, "fits")
        tight, tight_cars = _most(region, d, doors, "tight")
        score = (tight, fits)
        if best is None or score > best["score"]:
            best = {"score": score, "frame": f, "region": region, "raw": f.geom(s["clear"]), "fits": fits, "tight": tight,
                    "fits_cars": fits_cars, "tight_cars": tight_cars}
    f, region, doors = best["frame"], best["region"], s["doors"]
    n = want if want is not None else max(best["fits"], best["tight"], 1)
    if n == 0:
        status, cars, which = "pass", [], None
    elif best["fits"] >= n:
        status, which = "pass", "fits"
    elif best["tight"] >= n:
        status, which = "warn", "tight"
    else:
        status, which = "fail", None
    if which:
        lv = level(d, which)
        cars = geom.place(region, n, d.width, d.length, geom.gaps_for(n, lv["gap"], d.ramp), lv["front"], doors, lv["span"],
                          lv["rear"])
        cars = geom.spread(region, cars, d.width, d.length, doors, lv["span"]) if not d.ramp else cars
    elif n:
        cars = geom.overflow(region, n, d.width, d.length)
    size = geom.size_in(best["raw"], doors)  # measured on the floor itself, not the 2 mm search allowance
    door_h, door_measured = geom.door_limit(doors)
    ceil = s["ceiling"]
    return {"survey": s, "frame": f, "region": region, "raw": best["raw"], "doors": doors, "fits": best["fits"], "tight": best["tight"],
            "n": n, "status": status, "cars": cars, "which": which,
            "clear": geom.clearances(best["raw"], cars, d.width, d.length) if cars else [],
            "width": size["width"], "depth": size["depth"], "door_line": size["door_line"],
            "door_width": max((x["width"] for x in doors), default=None), "door_height": door_h,
            "door_height_measured": door_measured, "ceiling": ceil["value"], "ceiling_measured": ceil["measured"]}


def parked(a: dict, d: Dims) -> list[tuple[float, float, float, float]]:
    """(u, v, width, length) of every parked vehicle: the pair when two different ones are parked."""
    if a.get("pair"):
        return [(u, v, x.width, x.length) for (u, v), x in zip(a["pair"]["cars"], a["pair"]["order"])]
    return [(u, v, d.width, d.length) for u, v in a["cars"]]


def things(a: dict, d: Dims, uses: list[str]) -> list[dict]:
    """Room for each extra (bench, charger, motorcycle, bikes, rack) in the floor the parked cars leave, in order."""
    region = a["region"]
    ps = parked(a, d)
    taken = shapely.union_all([box(u - geom.SQUEEZE_M, v - geom.REAR_M, u + w + geom.SQUEEZE_M, v + l + 0.3)
                               for u, v, w, l in ps]) if ps else None
    cars = shapely.union_all([box(u, v, u + w, v + l) for u, v, w, l in ps]) if ps else None
    out = []
    for k in uses:
        (l, w, h), note = THINGS[k]
        need = (l, w + STAND_M) if k == "workbench" else (GYM_PLATFORM_M, GYM_PLATFORM_M) if k == "squat_rack" else \
            (0.4, 0.25) if k == "ev_charger" else (l, w)
        # a charger hangs on the wall above the door clearance: only the cars themselves are in its way
        spot = geom.free_spot(region, cars if k == "ev_charger" else taken, need)
        out.append({"id": k, "note": note, "need": need, "height": h, "spot": spot})
        if spot:
            g = shapely.Polygon(spot)
            taken = g if taken is None else taken.union(g)
    return out


def pair(a: dict, d1: Dims, d2: Dims) -> dict:
    """Two different vehicles side by side in an analysed garage: 'fits' (doors open on every side, walk round) or
    'tight' (squeeze out), either way round; 'fail' when neither layout fits. Positions and clearances."""
    region, doors = a["region"], a["doors"]
    for which in ("fits", "tight"):
        for x, y in ((d1, d2), (d2, d1)):
            lx, ly = level(x, which), level(y, which)
            cars = geom.place_pair(region, [(x.width, x.length, lx["span"]), (y.width, y.length, ly["span"])],
                                   [lx["gap"], max(lx["gap"], ly["gap"]), ly["gap"]], max(lx["front"], ly["front"]),
                                   doors, max(lx["rear"], ly["rear"]))
            if cars:
                return {"status": "pass" if which == "fits" else "warn", "which": which, "order": [x, y],
                        "cars": cars, "clear": geom.pair_clearances(a["raw"], cars, [(x.width, x.length),
                                                                                     (y.width, y.length)])}
    return {"status": "fail", "which": None, "order": [d1, d2], "cars": [], "clear": []}
