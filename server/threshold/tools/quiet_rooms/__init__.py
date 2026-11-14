"""Quiet rooms: ranks the bedrooms and office from quietest to loudest against outside transport noise.

Outside level: the US DOT National Transportation Noise Map (2020, LAeq 24 h) at the house, per source (road,
aviation, rail), read from its map tiles as a 5 or 10 dB class (`signals/noise_map.py`). Where a source is: the
nearest highway, major road, railway and airport from OpenStreetMap (`signals/osm_sources.py`). Per room:
  - which way its outside walls face, against the bearing to the source;
  - how many walls the straight line from the room to the source crosses before it leaves the house;
  - a facade facing the source gets the full outside level, a side facade 3 dB less, a room the house shields
    (no outside wall facing the source) 10 dB less, and a room with no outside wall 5 dB less again;
  - closed windows take 25 dB off (WHO 1999 gives about 15 dB for a window partly open).
Aircraft noise comes from above, so it gets no facade correction. These are labelled estimates for ranking rooms,
low reliability; a phone reading (noise_level) on site is the check.
"""
from __future__ import annotations

import math

import numpy as np
from pydantic import BaseModel
from shapely.geometry import Point
from shapely.ops import unary_union

from ...geometry._plan import wall_normal, walls_by_id
from ...geometry.georef import azimuth_of, compass, from_latlon, to_latlon
from ...signals import noise_map, osm_sources
from ...signals.plan2d import crossings, room_names, room_polys, segments
from .. import (
    Assumption,
    Check,
    Finding,
    GeoAnchor,
    Legend,
    LensOverlay,
    Metric,
    Pin,
    PinsOverlay,
    RoomAnchor,
    ScanScope,
    Source,
    ToolResult,
    Verdict,
    field,
    tool,
)

TARGET_WORDS = ("bedroom", "office", "den", "study", "loft")
SKIP = {"Garage", "Patio", "Porch", "Balcony", "Deck", "Closet", "Staircase", "Void", "Pool", "Yard", "Exterior"}
SIDE_DB, SHIELD_DB, INNER_DB = -3.0, -10.0, -5.0
WINDOW_DB = -25.0            # closed ordinary windows; about -15 dB with a window partly open (WHO 1999)
FACING_DEG, SIDE_DEG = 60.0, 120.0
NEAR_AIRPORT_M = 5000.0      # beyond this an airport below the map's floor is ignored
WHO = "WHO Guidelines for Community Noise (1999), table 4.1"
LIMIT = {"bedroom": 30.0}    # LAeq inside a bedroom at night; 35 elsewhere in a dwelling by day
LIMIT_DWELLING = 35.0
ERR_DB = 6.0
BACKGROUND_DBA = 20.0        # a closed quiet room's own background; traffic estimates below it are shown at it
MAP = Source(layer="model", method="lookup", confidence="medium", note=noise_map.NOTE)
EST = Source(layer="model", method="simulation", confidence="low",
             note="Outside level from the DOT noise map, turned per room by facade direction and walls in between; "
                  "rule-of-thumb corrections, not an acoustic model")
OSM = Source(layer="model", method="lookup", confidence="medium", note=osm_sources.NOTE)


class Inputs(BaseModel):
    scan: str = field(source="selection.scan", description="Scan id")
    windows_open: bool = field(False, pref="noise.windows_open", description="Sleep with a window partly open")


def _is(room, words):
    label = (room.get("label") or "").lower()
    return any(w in label.split() or label.startswith(w) for w in words)


def _mid(lv: dict) -> float | None:
    return None if lv["low"] is None else (lv["low"] + lv["high"]) / 2


def _sum_db(levels) -> float:
    return 10 * math.log10(sum(10 ** (v / 10) for v in levels))


@tool(id="quiet_rooms", title="Quiet rooms", icon="moon",
      summary="Ranks the bedrooms and office from quietest to loudest against road, rail and aircraft noise, from "
              "the national noise map, the nearest roads and which way each room faces.",
      model_description="Estimated outside transport noise per room for one scan: DOT National Transportation Noise "
                        "Map level at the house (road, aviation, rail), nearest highway, major road, railway and "
                        "airport from OpenStreetMap, each room's facade direction and the walls between it and the "
                        "source. Ranks bedrooms and offices quietest to loudest; per-room lens in dBA. Low reliability "
                        "estimate; needs the scan's geocoordinates.",
      personas=["light_sleeper"],
      requires=[{"layer": "matterport.walls"}, {"layer": "matterport.geo"}],
      blocks=["VerdictHeader", "MetricRow", "MiniChart", "CheckList", "FloorPlanMini", "AssumptionChips", "StepLog"],
      overlays=["lens", "pins"],
      examples=["Which bedroom is quietest?", "Is the office on the road side?", "Will planes keep me up?"])
def run(ctx, inputs: Inputs) -> ToolResult:
    plan = ctx.plan(inputs.scan)
    scope = ScanScope(sid=inputs.scan)
    polys = room_polys(plan)
    if not plan.get("walls") or not polys:
        return ToolResult(scope=scope, verdict=Verdict(status="unknown", text=(
            "This scan has no wall graph with room outlines, so which way rooms face cannot be told.")))
    c = unary_union(list(polys.values())).centroid
    ll = to_latlon(plan, c.x, c.y)
    if ll is None:
        return ToolResult(scope=scope, verdict=Verdict(status="unknown", text=(
            "This scan has no geocoordinates, so distance and direction to roads cannot be worked out.")))
    lat, lon = ll
    rooms = {r["id"]: r for r in plan["rooms"]}
    names = room_names(plan, polys)
    living = [k for k in polys if rooms[k].get("label") not in SKIP]
    targets = [k for k in living if _is(rooms[k], TARGET_WORDS)] or living
    try:
        lv = noise_map.levels(lat, lon)
    except RuntimeError as e:
        return ToolResult(scope=scope, verdict=Verdict(status="unknown", text=f"The national noise map could not be reached ({e})."))
    ctx.step("Read the national noise map at the house: " + ", ".join(
        f"{k} {'below 45' if v['below_floor'] else f'{v['low']:.0f} to {v['high']:.0f}'} dBA" for k, v in lv.items()))
    osm_down = False
    try:
        near = osm_sources.nearest(lat, lon)
        ctx.step("Nearest " + ", ".join(f"{osm_sources.LABEL[k]} {v['distance_m']:.0f} m" for k, v in near.items() if v))
    except RuntimeError:
        near, osm_down = {k: None for k in osm_sources.KINDS}, True
        ctx.step("OpenStreetMap did not answer: directions to the sources are unknown")

    # each source: outside level at the house, and where it is (None for overhead aircraft)
    road_src = min((s for s in (near["highway"], near["major_road"]) if s),
                   key=lambda s: s["distance_m"] / (3 if s["kind"] == "highway" else 1), default=None)
    # shortcut: a highway is treated as three times as far-reaching as a major road (about 5 dB louder as a line
    # source); use traffic counts if a source for them appears
    sources = []
    for layer, where in (("road", road_src), ("rail", near["rail"]), ("aviation", near["airport"])):
        m = _mid(lv[layer])
        floor_only = m is None
        if floor_only:
            if where is None or (layer == "aviation" and where["distance_m"] > NEAR_AIRPORT_M):
                continue
            m = noise_map.FLOOR_DBA - 1  # below the map's lowest class: at most 45
        sources.append({"layer": layer, "outside": m, "at_most": floor_only, "where": where,
                        "directional": layer != "aviation" and where is not None})
    if not sources:
        return ToolResult(scope=scope, verdict=Verdict(status="unknown" if osm_down else "pass", text=(
            "The national noise map shows no road, rail or aircraft noise above 45 dBA at the house. " +
            ("OpenStreetMap did not answer, so nearby roads could not be checked; try again later." if osm_down else
             "No highway, major road, railway or airport is near. Room-to-room differences come from neighbours, not traffic."))),
            metrics=[Metric(id="outside", label="Outside transport noise", value=None, unit="dBA", source=MAP)])

    walls = walls_by_id(plan)
    segs = {f: segments(plan, f) for f in {rooms[k]["floor"] for k in living}}
    outlines = {f: unary_union([p for k, p in polys.items() if rooms[k]["floor"] == f]) for f in segs}
    window = -15.0 if inputs.windows_open else WINDOW_DB
    per = {}
    for k in living:
        poly, fl = polys[k], rooms[k]["floor"]
        outline = outlines[fl]
        cen = poly.representative_point() if not poly.contains(poly.centroid) else poly.centroid
        ext = []  # outward azimuth and length of this room's outside walls
        for w in walls.values():
            if w["floor"] != fl or w.get("type") == "invisible" or (w.get("rooms") or []) != [k]:
                continue
            nx, ny = wall_normal(w)
            mx, my = (w["a"][0] + w["b"][0]) / 2, (w["a"][1] + w["b"][1]) / 2
            if poly.contains(Point(mx + 0.3 * nx, my + 0.3 * ny)):
                nx, ny = -nx, -ny
            if outline.contains(Point(mx + 0.3 * nx, my + 0.3 * ny)):
                continue  # another room is on the far side: not an outside wall
            ext.append((azimuth_of(plan, nx, ny), w["length"]))
        main = max(ext, key=lambda e: e[1])[0] if ext else None
        lv_room, detail = [], []
        for s in sources:
            corr, n_walls, face = 0.0, None, None
            if s["directional"]:
                sx, sy = from_latlon(plan, s["where"]["lat"], s["where"]["lon"])
                d = math.hypot(sx - cen.x, sy - cen.y) or 1.0
                far = (cen.x + (sx - cen.x) / d * 60, cen.y + (sy - cen.y) / d * 60)
                n_walls = int(crossings((cen.x, cen.y), np.array([far]), segs[fl]).sum())
                bearing = azimuth_of(plan, sx - cen.x, sy - cen.y)
                offs = [abs((a - bearing + 180) % 360 - 180) for a, _ in ext]
                face = min(offs) if offs else None
                corr = 0.0 if face is not None and face <= FACING_DEG else SIDE_DB if face is not None and face <= SIDE_DEG \
                    else SHIELD_DB + (0.0 if ext else INNER_DB)
                detail.append({"layer": s["layer"], "bearing": bearing, "walls": n_walls, "facing_off": face,
                               "corr": corr, "distance": s["where"]["distance_m"]})
            lv_room.append(s["outside"] + corr + window)
        per[k] = {"raw": _sum_db(lv_room), "level": max(BACKGROUND_DBA, _sum_db(lv_room)), "main": main, "detail": detail}
    ranked = sorted(targets, key=lambda k: per[k]["raw"])  # rank on the uncapped estimate
    relative = all(s["at_most"] for s in sources)  # outside is only "below 45": differences mean more than levels
    loudest = max(per[k]["raw"] for k in living)
    lead = max(sources, key=lambda s: s["outside"])
    lead_name = {"road": (lead["where"] or {}).get("name", "road traffic"), "rail": (lead["where"] or {}).get("name", "rail"),
                 "aviation": (lead["where"] or {}).get("name", "aircraft")}[lead["layer"]]
    ctx.step(f"Loudest source: {lead_name}; ranked {len(ranked)} rooms")

    checks, findings, metrics = [], [], []
    for i, k in enumerate(ranked):
        p = per[k]
        limit = LIMIT["bedroom"] if "bedroom" in (rooms[k].get("label") or "").lower() else LIMIT_DWELLING
        est = p["level"]
        st = "pass" if est + ERR_DB <= limit else "warn" if est - ERR_DB > limit else "unknown"
        fid = f"quiet_rooms:{inputs.scan}:{k}"
        checks.append(Check(id=k, rule=f"Estimated indoor noise, {names[k]}", measured=round(est, 1), threshold=limit,
                            unit="dBA", status=st, standard=WHO, findings=[fid]))
        d0 = next((d for d in p["detail"] if d["layer"] == lead["layer"]), None) or (p["detail"][0] if p["detail"] else None)
        side = f"faces {compass(p['main'])}" if p["main"] is not None else "has no outside wall"
        src_name = next((s["where"]["name"] for s in sources if d0 and s["layer"] == d0["layer"]), "")
        where = (f"; {src_name} ({d0['layer']}) is to the {compass(d0['bearing'])}, "
                 f"{d0['distance']:.0f} m away, with {d0['walls']} wall{'s' if d0['walls'] != 1 else ''} in between"
                 if d0 else "; aircraft noise comes from above")
        findings.append(Finding(
            id=fid, title=f"{'Quietest' if i == 0 else 'Loudest' if i == len(ranked) - 1 else f'Rank {i + 1}'}: {names[k]}",
            status=st, source=EST, anchor=RoomAnchor(sid=inputs.scan, room=k),
            detail=((f"About {loudest - p['raw']:.0f} dB quieter than the loudest room" if loudest - p["raw"] >= 1
                     else "As loud as the loudest room") + f"; outside traffic is below the "
                    f"map's {noise_map.FLOOR_DBA:.0f} dBA floor, so indoors it is near background" if relative else
                    f"About {est:.0f} dBA inside with windows {'partly open' if inputs.windows_open else 'closed'} "
                    f"(give or take {ERR_DB:.0f} dB)") + f". The room {side}{where}."))
        metrics.append(Metric(id=f"indoor.{names[k]}", label=names[k], value=round(est, 1), unit="dBA", source=EST))
    out_lv = _sum_db([s["outside"] for s in sources])
    metrics = [Metric(id="outside", label=f"Outside at the house{' (at most)' if all(s['at_most'] for s in sources) else ''}",
                      value=round(out_lv, 1), unit="dBA", source=MAP),
               *[Metric(id=f"map_{s['layer']}", label=f"Noise map, {s['layer']}" + (" (below 45)" if s["at_most"] else ""),
                        value=None if s["at_most"] else s["outside"], unit="dBA", source=MAP) for s in sources],
               *[Metric(id=f"near_{k}", label=f"Nearest {osm_sources.LABEL[k]}: {v['name']}", value=round(v["distance_m"]),
                        unit="m", source=OSM) for k, v in near.items() if v],
               *metrics]
    quiet, loud = ranked[0], ranked[-1]
    gap = per[loud]["raw"] - per[quiet]["raw"]
    if len(ranked) == 1:
        text = f"One room to rank, the {names[quiet].lower()}; the main outside source is {lead_name}."
    elif gap >= 2:
        text = (f"The {names[quiet].lower()} should be the quietest and the {names[loud].lower()} the loudest of "
                f"{len(ranked)} rooms; the main outside source is {lead_name}.")
    else:
        text = f"The {len(ranked)} rooms come out within 2 dB of each other; the main outside source is {lead_name}."
    if lead["layer"] == "aviation" and not lead["at_most"]:
        text += " Aircraft noise comes from above and reaches every room alike."
    if all(s["at_most"] for s in sources):
        text += " The house is below the noise map's 45 dBA floor, so traffic here is modest."
    text += " Estimate from a national map and facade directions, low reliability; measure on site with the phone."
    vals = {k: round(per[k]["raw"] - loudest, 1) if relative else round(per[k]["level"], 1) for k in living}
    geo_pins = [Pin(id=f"src_{k}", anchor=GeoAnchor(geo=(v["lon"], v["lat"])), label=f"{osm_sources.LABEL[k].capitalize()}: {v['name']}",
                    status="warn") for k, v in near.items() if v]
    return ToolResult(
        scope=scope, verdict=Verdict(status="warn" if any(c.status == "warn" for c in checks) else "pass", text=text),
        metrics=metrics, checks=checks, findings=findings,
        overlays=[LensOverlay(values=vals, ramp="sequential", legend=Legend(
            title="Transport noise vs the loudest room" if relative else "Estimated indoor transport noise",
            unit="dB" if relative else "dBA", min=min(vals.values()), max=max(vals.values()))),
            *([PinsOverlay(pins=geo_pins)] if geo_pins else [])],
        assumptions=[Assumption(id="noise.windows_open", label="Windows partly open", value=inputs.windows_open, editable=True),
                     Assumption(id="window", label="Facade with windows reduces noise by", value=-window, unit="dB"),
                     Assumption(id="side", label="Side facade, relative to one facing the source", value=SIDE_DB, unit="dB"),
                     Assumption(id="shield", label="Room the house shields from the source", value=SHIELD_DB, unit="dB"),
                     Assumption(id="inner", label="Room with no outside wall, extra", value=INNER_DB, unit="dB"),
                     Assumption(id="background", label="Lowest level shown (a quiet room's own background)", value=BACKGROUND_DBA, unit="dBA"),
                     Assumption(id="map_class", label="Noise map level read as the middle of its class", value=True),
                     Assumption(id="floor", label="Upper floors and fences not modelled", value=True),
                     Assumption(id="error", label="Give or take", value=ERR_DB, unit="dB")])
