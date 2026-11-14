"""Fire pre-plan: the pre-incident plan for one scan or a whole property, written from data that already exists and
organised by NFPA 1620 (2015) sections (now part of NFPA 1660, 2024). Every line carries its source and confidence;
"not seen" is never "absent". Also writes a one-page printable sheet."""
from __future__ import annotations

import datetime as dt
import hashlib
import re

from pydantic import BaseModel

from ...config import CACHE
from ...geometry import to_latlon
from ...geometry._plan import clear_width, rooms_by_id
from .. import (
    Action,
    Assumption,
    Check,
    Finding,
    Metric,
    OpeningAnchor,
    Pin,
    PinsOverlay,
    RoomAnchor,
    RuleOverlay,
    ScanScope,
    Source,
    ToolResult,
    Verdict,
    field,
    tool,
)
from ..types import GeoAnchor, Media, ScansScope, SelectRooms
from .common import BEDROOM, VisionBudget, floor_label, labels_ok, live_rooms, name, objects, scope_sids, walls_ok

STANDARD = "NFPA 1620 (2015)"
SHEETS = CACHE / "tools" / "fire_preplan"
COSTAR = lambda note: Source(layer="costar", method="lookup", confidence="high", note=note)  # noqa: E731
VX = lambda f: Source(**f["source"])  # noqa: E731
SCAN = Source(layer="matterport", method="geometry", confidence="high", note="Matterport scan: floors, rooms, openings")
SEEN = Source(layer="model", method="vision", confidence="medium",
              note="Vision model on the central panorama of each room; small objects are hit and miss")
NODATA = Source(layer="model", method="lookup", confidence="low", note="Not in any data source this tool reads")
OBJ = {"electrical panel": ("5.3.2.2", "Electrical panel"), "water heater": ("5.3.2.5", "Water heater"),
       "gas stove": ("5.3.2.8.2", "Gas appliance"), "sprinkler head": ("7.3.1", "Sprinkler head"),
       "smoke alarm": ("7.5", "Smoke alarm"), "exit sign": ("6.2.2", "Exit sign"),
       "fire extinguisher": ("7.6", "Fire extinguisher"), "kitchen hood": ("8", "Kitchen hood"),
       "stairs": ("6.2.2", "Stairs")}
SECTIONS = [("5.2", "Construction"), ("5.3", "Building systems and utilities"), ("5.4", "Site and access"),
            ("6", "Occupants and means of egress"), ("7", "Water supply and protection systems"), ("8", "Hazards")]
AMENITY = re.compile(r"pool|fitness|gym|lobby|leasing|clubhouse|club room|laundry|game room|amenit|lounge|"
                     r"business|theater|theatre|mail|roof|courtyard|common", re.I)
NOT_COVERED = [("corridor", "common corridors"), ("stair", "stairwells"), ("garage|parking", "parking garage"),
               ("mechanical|electrical|boiler|riser", "mechanical, electrical and sprinkler riser rooms"),
               ("roof", "the roof")]


class Inputs(BaseModel):
    scan: str | None = field(None, source="selection.scan", description="Scan id")
    whole_property: bool = field(False, description="Plan the whole CoStar property the scan belongs to")
    property_id: int | None = field(None, description="CoStar property id; plans every scan of it")
    read_panoramas: bool = field(True, description="Send unread panoramas to the vision model for utilities, "
                                                   "protection systems and hazards")
    max_scans_read: int = field(2, ge=0, le=12, description="At most this many unread scans go to the vision model")
    min_width_m: float = field(0.813, pref="access.door_width_m", unit="m", gt=0.3, le=3.0,
                               description="Clear width an exit door needs")


class Sheet:
    """The pre-plan as lines: (section, item, value, status, source, anchor, media). Drives findings and the HTML."""

    def __init__(self, key: str):
        self.key, self.lines = key, []

    def add(self, section: str, item: str, value: str, status: str, source: Source, anchor=None, media=None,
            fid: str | None = None):
        self.lines.append({"id": fid or f"fire_preplan:{self.key}:{section}:{len(self.lines)}", "section": section,
                           "item": item, "value": value, "status": status, "source": source, "anchor": anchor,
                           "media": media or []})

    def findings(self) -> list[Finding]:
        return [Finding(id=x["id"], title=f"§{x['section']} {x['item']}", status=x["status"], detail=x["value"],
                        anchor=x["anchor"], source=x["source"], media=x["media"]) for x in self.lines]


def _val(c: dict | None, unit_fmt=None) -> str | None:
    if not c:
        return None
    v = c["value"]
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return (f"{v:,}" if isinstance(v, int) and v > 9999 else f"{v}") + (f" {c['unit']}" if c.get("unit") else "")


def _record(sids: list[str]):
    from ...sources import costar
    for sid in sids:
        try:
            return costar.record(sid)
        except Exception:  # noqa: BLE001  no kit, no join, or not in the kit: try the next scan
            continue
    return None


def _where(plan: dict, rooms: dict, det: dict) -> str:
    r = rooms.get(det.get("in_room") or "")
    return f"{name(r)}, {floor_label(plan, r['floor'])}" if r else "room not placed"


def egress_summary(sh: Sheet, walled: list[tuple[dict, dict]]) -> None:
    """One line each across all unit scans: longest walk out, longest hose stretch, units with one doorway out."""
    src = Source(layer="matterport", method="geometry", confidence="medium",
                 note="Empty-room routes over each scan's wall graph")
    tag = lambda p: (p.get("name") or p["sid"])[:30]  # noqa: E731
    walks = [(max(w["length_m"] for w in a["routes"].values() if w["available"]), p) for p, a in walled
             if any(w["available"] for w in a["routes"].values())]
    hoses = [(max(h["length_m"] for h in a["hose"]), p) for p, a in walled if a["hose"]]
    single = [p for p, a in walled if len(a["exits"]) == 1]
    # openings under 0.45 m are slivers in the wall graph, not doors
    narrow = [(min(w for e in a["exits"] if (w := clear_width(e) or 0) >= 0.45), p) for p, a in walled
              if any((clear_width(e) or 0) >= 0.45 for e in a["exits"])]
    if walks:
        w, p = max(walks, key=lambda x: x[0])
        sh.add("6.2.2", "Longest walk out of a unit", f"{w:.1f} m in {tag(p)}; median across {len(walks)} unit "
               f"scans {sorted(x for x, _ in walks)[len(walks) // 2]:.1f} m.", "pass", src)
    if hoses:
        h, p = max(hoses, key=lambda x: x[0])
        sh.add("6.2.2", "Longest hose stretch inside a unit", f"{h:.0f} m from the unit door in {tag(p)}, plus the "
               "corridor and stairs, which no scan covers.", "pass", src)
    sh.add("6.2.2", "Units with one doorway out", f"{len(single)} of {len(walled)} unit scans: the unit door to an "
           "unscanned corridor or landing is the only way out besides windows.", "warn" if single else "pass", src)
    if narrow:
        n, p = min(narrow, key=lambda x: x[0])
        sh.add("6.2.2", "Narrowest unit door", f"About {n:.2f} m clear, {tag(p)}.", "pass", src)


def build(ctx, inputs: Inputs) -> tuple[ToolResult, dict]:
    sids, pid = scope_sids(inputs.scan, inputs.whole_property, inputs.property_id)
    multi = len(sids) > 1
    key = f"p{pid}" if multi else sids[0]
    sh = Sheet(key)
    budget = VisionBudget(inputs.max_scans_read if inputs.read_panoramas else 0)
    plans = []
    for sid in sids:
        try:
            plans.append(ctx.plan(sid))
        except Exception as e:  # noqa: BLE001
            ctx.step(f"Skipped scan {sid}: {e}")
    if not plans:
        return ToolResult(scope=ScanScope(sid=sids[0]), verdict=Verdict(status="unknown", text="No scan could be read.")), {}
    ctx.step(f"Read {len(plans)} scan plans" + (f" for property {pid}" if pid else ""))

    # ---- the record: occupancy and construction -------------------------------------------------
    rec = _record([p["sid"] for p in plans])
    claims = (rec or {}).get("claims") or {}
    prop = (rec or {}).get("property") or {}
    cs = lambda k: COSTAR(f"CoStar {claims[k]['path']}")  # noqa: E731
    ctx.step("Read the CoStar record" if rec else "No CoStar record for these scans")
    addr = (prop.get("primaryAddress") or {})
    title = prop.get("buildingName") or (plans[0].get("address") or plans[0].get("name") or plans[0]["sid"])
    if multi and addr:
        title = f"{prop.get('buildingName') or ''} {addr.get('streetNumber', '')} {addr.get('streetName', '')} " \
                f"{addr.get('streetType', '')}, {addr.get('city', '')}".strip()
    units = claims.get("units")
    kind = ("Apartment community" if units else "Residential" if plans[0].get("segment") == "residential"
            else "Commercial")
    sh.add("6.1", "Occupancy", kind + (f", {_val(units)} units" if units else ""), "pass",
           cs("units") if units else Source(layer="matterport", method="lookup", confidence="medium",
                                             note="Scan segment from the scan index"))
    for k, item in (("stories", "Stories above grade"), ("year_built", "Year built"),
                    ("year_renovated", "Year renovated"), ("gross_area", "Gross building area"),
                    ("living_area", "Living area"), ("height", "Building height")):
        if k in claims:
            sh.add("5.2.1", item, _val(claims[k]), "pass", cs(k))
    if not any(k in claims for k in ("year_built", "stories")):
        sh.add("5.2.1", "Area, height and age", "No CoStar record found for these scans.", "unknown", NODATA)
    if "construction_material" in claims:
        sh.add("5.2.2.1", "Construction", _val(claims["construction_material"]), "pass", cs("construction_material"))
    else:
        sh.add("5.2.2.1", "Construction", "Not in the record; check on site.", "unknown", NODATA)
    nb = (prop.get("propertyApartment") or {}).get("numBuildings")
    if nb:
        sh.add("5.2.1", "Buildings on the property", str(nb), "pass",
               COSTAR("CoStar propertyApartment.numBuildings"))

    # ---- the scans: layout, egress, objects ----------------------------------------------------------
    from ..egress_routes import analyse
    seen: dict[str, list[tuple[dict, dict]]] = {}
    read_rooms, unread, walled, bedrooms = 0, [], [], 0
    pins = []
    exits_ll = []
    for plan in plans:
        sid = plan["sid"]
        rooms = rooms_by_id(plan)
        lv = live_rooms(plan)
        bedrooms += sum(r.get("label") == BEDROOM for r in lv)
        tag = f"{(plan.get('name') or sid)[:36]}: " if multi else ""
        if not multi:
            by_floor: dict[str, list[str]] = {}
            for r in lv:
                by_floor.setdefault(r["floor"], []).append(name(r))
            for f, names in by_floor.items():
                counts = {n: names.count(n) for n in sorted(set(names))}
                sh.add("5.2.2.5", f"Layout, {floor_label(plan, f)}",
                       ", ".join(f"{c} {n.lower()}{'s' if c > 1 and not n.endswith('s') else ''}" if c > 1 else n.lower()
                                 for n, c in counts.items()) + ".", "pass", SCAN)
        if walls_ok(plan):
            a = analyse(plan, inputs.min_width_m)
            walled.append((plan, a))
            for e in a["exits"]:
                ll = to_latlon(plan, *e["center"]) if plan.get("geo") else None
                exits_ll.append((plan, e, ll))
            stairs = [r for r in lv if r.get("label") == "Staircase"]
            if len(plan.get("floors") or []) > 1 and not multi:
                sh.add("6.2.2", f"{tag}Interior stairs", (f"{len(stairs)} stair rooms in the scan" if stairs else
                       "No stair room is typed in the scan; stairs connect the floors somewhere") + ".",
                       "pass" if stairs else "unknown", SCAN)
        found = objects(plan, budget)
        if found is None:
            unread.append(plan)
        else:
            read_rooms += len({d.get("in_room") for d in found} | {r["id"] for r in lv})
            for d in found:
                if d["label"] in OBJ and d["finding"]["source"]["confidence"] != "low":
                    seen.setdefault(d["label"], []).append((plan, d))
    ctx.step(f"Measured egress on {len(walled)} scans with a wall graph; read panoramas of "
             f"{len(plans) - len(unread)} scans ({len(budget.read)} new)")

    # entrances and egress
    units_walled = [(p, a) for p, a in walled if not AMENITY.search(p.get("name") or "")]
    if multi and units_walled:
        egress_summary(sh, units_walled)
        two = [p for p, _ in walled if len(p.get("floors") or []) > 1]
        if two:
            typed = sum(any(r.get("label") == "Staircase" for r in p["rooms"]) for p in two)
            sh.add("6.2.2", "Units on two or more floors", f"{len(two)} unit scans (townhouse or loft plans); "
                   f"{typed} have a typed stair room.", "pass", SCAN)
    for plan, a in walled[:1] if not multi else []:
        sid = plan["sid"]
        tag = f"{(plan.get('name') or sid)[:36]}: " if multi else ""
        if a["exits"]:
            ws = sorted((clear_width(e) or 0 for e in a["exits"]), reverse=True)
            sh.add("6.2.2", f"{tag}Doorways out", f"{len(a['exits'])} doorways lead outside or to unscanned space; "
                   "widest about " + f"{ws[0]:.2f} m clear" + (f", narrowest {ws[-1]:.2f} m" if len(ws) > 1 else "")
                   + ".", "pass", Source(layer="matterport", method="geometry", confidence="medium",
                                         note="Wall graph opening less a 5 cm door allowance; each may lead to an "
                                              "unscanned room"),
                   anchor=OpeningAnchor(sid=sid, opening=a["exits"][0]["id"]))
        ok = [w for w in a["routes"].values() if w["available"]]
        if ok:
            longest = max(w["length_m"] for w in ok)
            one_way = sum(1 for r in live_rooms(plan) if a["degree"].get(r["id"]) == 1 and r.get("label") == BEDROOM)
            sh.add("6.2.2", f"{tag}Longest walk out", f"{longest:.1f} m to the nearest doorway out"
                   + (f"; {one_way} bedrooms have one door" if one_way else "") + ".", "pass",
                   Source(layer="matterport", method="geometry", confidence="medium",
                          note="Empty-room route over the wall graph"))
        if a["hose"]:
            h = max(a["hose"], key=lambda h: h["length_m"])
            sh.add("6.2.2", f"{tag}Hose stretch inside", f"{h['length_m']:.0f} m from a doorway to the far corner "
                   f"of {name(rooms_by_id(plan).get(h['room']))}, the farthest point.", "pass",
                   Source(layer="matterport", method="geometry", confidence="medium" if not h["walk"]["stairs"] else
                          "low", note="Route over the wall graph plus the straight run to the room's far corner"),
                   anchor=RoomAnchor(sid=sid, room=h["room"]))
    if multi and walled and not units_walled:
        sh.add("6.2.2", "Means of egress", "No unit scan here has a wall graph, so unit doorways and routes are not "
               "measured. Use the floor plan images.", "unknown", SCAN)
    if not walled:
        sh.add("6.2.2", "Means of egress", "No scan here has a wall graph, so doorways and routes are not measured. "
               "Use the floor plan images.", "unknown", SCAN)
    if bedrooms:
        sh.add("6.1", "Sleeping rooms", f"{bedrooms} bedrooms across the scans: search these first.", "pass", SCAN)

    # objects: utilities, protection, hazards
    read_note = (f"in the panoramas of {len(plans) - len(unread)} of {len(plans)} scans"
                 if multi else "in the scan's panoramas") if len(unread) < len(plans) else None
    for label, (sec, item) in OBJ.items():
        hits = seen.get(label, [])
        if hits:
            sure = [(p, d) for p, d in hits if d["finding"]["source"]["confidence"] == "high"]
            places = sorted({(f"{(p.get('name') or p['sid'])[:24]}: " if multi else "") +
                             _where(p, rooms_by_id(p), d) for p, d in (sure or hits)})
            plan0, d0 = (sure or hits)[0]
            hazard = label in ("gas stove", "water heater")
            count = (f"{len(sure)} seen" + (f", {len(hits) - len(sure)} more possible" if len(hits) > len(sure) else "")
                     if sure else f"{len(hits)} possible, none clear")
            sh.add(sec, item, f"{count}: " + "; ".join(places[:6]) + ("; ..." if len(places) > 6 else "") + ".",
                   "warn" if hazard else "pass" if sure else "unknown",
                   SEEN if sure else Source(**{**SEEN.model_dump(), "confidence": "low"}),
                   anchor=d0["finding"]["anchor"], media=[Media(**m) for _, d in (sure or hits)[:4]
                                                          for m in d["finding"]["media"][:1]])
            if not multi:
                for p, d in hits:
                    if d["finding"]["anchor"].get("point"):
                        pins.append(Pin(id=d["finding"]["id"], anchor=d["finding"]["anchor"], label=item,
                                        status="warn" if hazard else "pass" if (p, d) in sure else "unknown"))
        elif read_note and label in ("electrical panel", "water heater", "sprinkler head", "smoke alarm",
                                     "fire extinguisher", "gas stove"):
            sh.add(sec, item, f"Not seen {read_note}. Not seen is not absent: check on site.", "unknown",
                   Source(layer="model", method="vision", confidence="low",
                          note="One panorama per room read; closets, garages and outside are often not photographed"))
    if len(unread) == len(plans):
        sh.add("5.3.2", "Utilities and protection seen", "Panoramas were not read in this run, so shutoffs, panels "
               "and alarms are not listed.", "unknown", NODATA)
    sh.add("5.3.2.8.2", "Gas shutoff location", "Not in the data. The gas meter and its shutoff are outside; find it "
           "on the walk-around.", "unknown", NODATA)
    if "has_sprinklers" in claims or "sprinkler_type" in claims:
        v = (_val(claims.get("sprinkler_type")) or "") if claims.get("sprinkler_type") else None
        sh.add("7.3.1", "Sprinkler system (record)", ("Yes" if (claims.get("has_sprinklers") or {}).get("value", True)
               else "No") + (f", {v} system" if v else "") + ". Riser location not in the data.",
               "pass", cs("sprinkler_type" if "sprinkler_type" in claims else "has_sprinklers"))
    else:
        sh.add("7.3.1", "Sprinkler system (record)", "The record does not say.", "unknown", NODATA)
    if "passenger_elevators" in claims:
        sh.add("5.3.3", "Elevators", _val(claims["passenger_elevators"]) + " passenger elevators.", "pass",
               cs("passenger_elevators"))
    elif multi and ((claims.get("stories") or {}).get("value") or 0) > 3:
        sh.add("5.3.3", "Elevators", "Not in the record.", "unknown", NODATA)
    for sec, item, text in (("7.2.7", "Fire hydrants", "Not in this data (hydrants are about five pixels wide at "
                             "7.5 cm). Use the city's hydrant layer."),
                            ("7.3.2", "Standpipes and FDC", "Not in this data; locate the fire department connection "
                             "on the walk-around.")):
        if multi or ((claims.get("stories") or {}).get("value") or 1) > 2 or sec == "7.2.7":
            sh.add(sec, item, text, "unknown", NODATA)

    # ---- the air: roof, site, access ----------------------------------------------------------------
    geo = (addr.get("latitude"), addr.get("longitude")) if multi and addr.get("latitude") else None
    if geo is None:
        g = next((p["geo"] for p in plans if p.get("geo")), None)
        geo = (g["lat"], g["lon"]) if g else None
    acc = None
    if geo:
        from .site import ACCESS_SRC, access, bearing, metres, side_of
        try:
            acc = access(geo[0], geo[1], 160 if multi else 70)
        except Exception as e:  # noqa: BLE001  aerial data missing for this point
            ctx.step(f"Aerial reading failed: {type(e).__name__}")
    if acc:
        ctx.step("Read the roof and site from the Vexcel orthophoto and facts")
        facts = {f["id"]: f for f in acc["facts"]["facts"]}

        def fact(fid, sec, item, fmt=lambda v, u: f"{v}{' ' + u if u and u != 'count' else ''}", warn=None):
            f = facts.get(fid)
            if f is not None:
                sh.add(sec, item, fmt(f["value"], f["unit"]) + ".", "warn" if warn and warn(f["value"]) else "pass",
                       VX(f), anchor=GeoAnchor(geo=(acc["lon"], acc["lat"])))

        roof = [facts[k] for k in ("roof_material", "roof_shape", "roof_height") if k in facts]
        if roof:
            h = facts.get("roof_height")
            sh.add("5.2.2.3", "Roof", " ".join(str(facts[k]["value"]) for k in ("roof_shape", "roof_material")
                                                if k in facts).capitalize() + " roof"
                   + (f", {h['value']} m above ground" if h else "") + ".", "pass", VX(roof[0]),
                   anchor=GeoAnchor(geo=(acc["lon"], acc["lat"])))
        objs = [(facts.get(f"roof_{o}"), w) for o, w in (("ac_unit", "AC units"), ("skylight", "skylights"),
                                                          ("chimney", "chimneys"), ("satellite_dish", "dishes"))]
        if any(x for x, _ in objs):
            got = [f"{x['value']} {w}" for x, w in objs if x and x["value"]]
            sh.add("5.2.2.3", "Roof objects", ", ".join(got) + ": check before cutting a vent hole." if got else
                   "No AC units, skylights or chimneys seen.", "warn" if got else "pass",
                   VX(next(x for x, _ in objs if x)), anchor=GeoAnchor(geo=(acc["lon"], acc["lat"])))
        fact("roof_condition", "5.2.2.3", "Roof condition", fmt=lambda v, u: f"Vexcel score {v} (scale not published)")
        fact("building_type", "6.1", "Building type from the air", fmt=lambda v, u: str(v).replace("_", " "))
        fact("footprint_area", "5.2.1", "Building footprint")
        fact("solar", "8", "Solar panels on the roof", fmt=lambda v, u: "yes: energised conductors on the roof"
             if v else "none seen", warn=bool)
        fact("pool", "8", "Pool on the parcel", fmt=lambda v, u: "yes" if v else "none seen")
        sides_txt = ", ".join(f"{k} = {v}" for k, v in acc["sides"].items())
        asrc = Source(**{**ACCESS_SRC, "confidence": acc["confidence"]})
        sh.add("5.4.1", "Sides", f"Side A (address side) faces {acc['front']}; {sides_txt}. Street on "
               f"{', '.join(acc['street_sides']) or 'no side seen'}.", "pass", asrc,
               anchor=GeoAnchor(geo=acc["centre"]))
        e = acc["engine"]
        sh.add("5.4.1", "First engine", f"Park on side A at the marked spot, about {e['from_building_m']:.0f} m from "
               "the building." if e["from_building_m"] is not None else "Park at the marked spot.", "pass", asrc,
               anchor=GeoAnchor(geo=e["lonlat"]))
        if acc["driveways"]:
            sh.add("5.4.1", "Driveways", f"{len(acc['driveways'])} onto the lot.", "pass", asrc,
                   anchor=GeoAnchor(geo=acc["driveways"][0]))
        obst = acc["barriers"] + acc["overhead"]
        sh.add("5.4.2", "Obstacles to apparatus", ("; ".join(sorted({o["kind"] for o in obst})) + " marked on the "
               "aerial.") if obst else "None seen on the aerial photo; overhead wires are hard to see from above.",
               "warn" if obst else "pass", asrc, anchor=GeoAnchor(geo=obst[0]["lonlat"]) if obst else None)
        sh.add("5.4.1", "Access note", acc["note"], "pass", asrc)
        if exits_ll and acc["footprint"] is not None:
            fc = acc["footprint"].centroid
            by_side: dict[str, int] = {}
            for plan, ex, ll in exits_ll:
                if ll:
                    s = side_of(bearing(fc.y, fc.x, ll[0], ll[1]), acc["front"])
                    by_side[s] = by_side.get(s, 0) + 1
            if by_side and not multi:
                sh.add("6.2.2", "Doorways by side", ", ".join(f"side {k}: {v}" for k, v in sorted(by_side.items()))
                       + ".", "pass", Source(layer="matterport", method="geometry", confidence="medium",
                                            note="Scan placed on the map by its geocoordinates (checked against "
                                                 "Vexcel footprints on four houses)"))
                near = min((metres(ll[0], ll[1], e["lonlat"][1], e["lonlat"][0]) for _, _, ll in exits_ll if ll),
                           default=None)
                if near is not None and walled and walled[0][1]["hose"]:
                    inside = max(h["length_m"] for h in walled[0][1]["hose"])
                    sh.add("6.2.2", "Hose from the engine", f"About {near + inside:.0f} m: {near:.0f} m straight from "
                           f"the engine spot to the nearest doorway plus {inside:.0f} m inside.", "pass",
                           Source(layer="model", method="geometry", confidence="low",
                                  note="Straight line outside (no path around obstacles) plus the measured route in"))
    else:
        sh.add("5.4.1", "Site and access", "No aerial reading for this location.", "unknown", NODATA)

    # ---- coverage for a property --------------------------------------------------------------------
    if multi:
        names = [(p.get("name") or "") for p in plans]
        amen = [n for n in names if AMENITY.search(n)]
        sh.add("4.3", "Scans used", f"{len(plans)} scans: {len(plans) - len(amen)} units and {len(amen)} common "
               f"spaces ({', '.join(sorted(set(amen))[:6])}).", "pass", SCAN)
        gaps = [label for pat, label in NOT_COVERED if not any(re.search(pat, n, re.I) for n in names)]
        sh.add("4.3", "Not covered by any scan", ", ".join(gaps).capitalize() + ". These matter most in an apartment "
               "fire; walk them.", "warn", SCAN)
        if units:
            sh.add("4.3", "Unit coverage", f"{len(plans) - len(amen)} unit scans for {_val(units)} units: each scan is "
                   "a floor plan type, not a particular unit.", "pass", cs("units"))
        if unread:
            sh.add("4.3", "Panoramas not read", f"{len(unread)} scans were not sent to the vision model in this run.",
                   "unknown", NODATA)

    # ---- assemble -----------------------------------------------------------------------------------
    findings = sh.findings()
    checks = []
    for sec, label in SECTIONS:
        lines = [x for x in sh.lines if x["section"].split(".")[0] == sec.split(".")[0] and
                 (x["section"].startswith(sec) or "." not in sec)]
        known = [x for x in lines if x["status"] != "unknown"]
        checks.append(Check(id=f"section:{sec}", rule=f"§{sec} {label}: lines with data", measured=len(known),
                            threshold=len(lines), unit="lines", standard=STANDARD,
                            status="unknown" if not known else "pass" if len(known) == len(lines) else "warn",
                            findings=[x["id"] for x in lines]))
    hazards = [x for x in sh.lines if x["status"] == "warn"]
    unknown = [x for x in sh.lines if x["status"] == "unknown"]
    overlays = []
    if not multi and walled:
        plan0 = walled[0][0]
        beds = [r["id"] for r in live_rooms(plan0) if r.get("label") == BEDROOM]
        if beds:
            overlays.append(RuleOverlay(select=SelectRooms(rooms=beds), style="highlight"))
        ent = [Pin(id=f"exit:{e['id']}", anchor=OpeningAnchor(sid=plan0["sid"], opening=e["id"]), label="Doorway out",
                   status="unknown") for e in walled[0][1]["exits"]]
        if pins or ent:
            overlays.append(PinsOverlay(pins=pins + ent))
    scope = ScansScope(sids=[p["sid"] for p in plans]) if multi else ScanScope(sid=plans[0]["sid"])
    stories = (claims.get("stories") or {}).get("value")
    text = (f"Pre-plan for {title}: {len([x for x in sh.lines if x['status'] != 'unknown'])} lines filled from the "
            f"data, {len(hazards)} hazards or obstacles to note, {len(unknown)} items to confirm on the walk-around.")
    metrics = [Metric(id="lines", label="Lines filled", value=len(sh.lines) - len(unknown), unit="", source=SCAN),
               Metric(id="to_confirm", label="To confirm on site", value=len(unknown), unit="", source=NODATA),
               Metric(id="hazards", label="Hazards noted", value=len(hazards), unit="", source=SEEN)]
    if stories:
        metrics.append(Metric(id="stories", label="Stories", value=stories, unit="", source=cs("stories")))
    if walled and walled[0][1]["hose"]:
        metrics.append(Metric(id="hose_inside", label="Hose stretch inside",
                              value=round(max(h["length_m"] for h in walled[0][1]["hose"]), 1), unit="m", source=SCAN))
    result = ToolResult(
        scope=scope, verdict=Verdict(status="warn" if hazards else "pass" if len(unknown) < len(sh.lines) / 2 else
                                     "unknown", text=text),
        metrics=metrics, checks=checks, findings=findings, overlays=overlays,
        assumptions=[Assumption(id="standard", label=f"Sections follow {STANDARD}, now part of NFPA 1660 (2024)",
                                value=STANDARD),
                     Assumption(id="not_seen", label="Not seen in the photos is not absent", value=True),
                     Assumption(id="draft", label="A first draft for an inspector to confirm on site", value=True)]
        + ([Assumption(id="property_id", label="CoStar property", value=pid)] if pid else []),
        actions=[Action(id="egress", label="Show every way out", tool="egress_routes", inputs={"scan": walled[0][0]["sid"]})]
        if walled else [])
    ctx_data = {"title": title, "kind": kind, "lines": sh.lines, "acc": acc,
                "walled": (units_walled if multi else walled)[:12], "plans": plans,
                "seen": seen, "multi": multi, "key": key, "pid": pid}
    return result, ctx_data


def save_sheet(result: ToolResult, data: dict) -> str | None:
    from .sheet import render
    if not data:
        return None
    html = render(result, data)
    h = hashlib.sha1(html.encode()).hexdigest()[:8]
    f = SHEETS / f"{data['key']}.html"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(html)
    return f"fire_preplan/{data['key']}.html#{h}"


@tool(id="fire_preplan", title="Fire pre-plan", icon="flame",
      summary="Writes the pre-incident plan from the scans, the aerial photo and the property record, with a "
              "one-page printable sheet.",
      model_description="Pre-incident plan (NFPA 1620 sections) for one scan or a whole CoStar property: occupancy and "
                        "construction, roof hazards, sides A to D and where the first engine parks, doorways out and "
                        "hose stretch, interior layout, utilities and protection systems seen in the panoramas, "
                        "hazards, and what no scan covers. Every line has a source; returns a printable HTML sheet.",
      personas=["fire_captain", "apartment_manager", "insurance_underwriter"],
      requires=[{"layer": "matterport.rooms"}, {"layer": "matterport.openings", "need": "optional"},
                {"layer": "vexcel.ortho", "need": "optional"}, {"layer": "costar.property", "need": "optional"},
                {"layer": "matterport.panoramas", "need": "optional"}],
      blocks=["VerdictHeader", "MetricRow", "CheckList", "EvidenceStrip", "FloorPlanMini", "StepLog", "Note",
              "ActionBar"],
      overlays=["pins", "rule"], annotations={"cost": "slow"},
      examples=["Write the pre-plan for this building", "Pre-plan the whole apartment complex"])
def run(ctx, inputs: Inputs) -> ToolResult:
    result, data = build(ctx, inputs)
    ref = save_sheet(result, data)
    if ref:
        ctx.step("Wrote the printable pre-plan sheet")
        # shortcut: Contract 3 media has no "document" kind; the sheet rides as an ortho item until the lead adds one
        result.findings.insert(0, Finding(
            id=f"fire_preplan:{data['key']}:sheet", title="Printable pre-plan sheet", status="pass",
            detail=f"One page: aerial with sides and the engine spot, plan drawing, facts table. Written "
                   f"{dt.date.today().isoformat()}.", anchor=None,
            source=Source(layer="model", method="lookup", confidence="high", note="Rendered from the lines above"),
            media=[Media(kind="ortho", ref=ref)]))
    return result
