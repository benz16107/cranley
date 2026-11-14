"""Industrial fit: one check of a warehouse or flex building for a distribution or production tenant.

Clear height (record, and the largest room on the scan), truck doors (exterior openings 2.4 m or wider on the scan,
dock-high and drive-in doors from the aerial through loading_docks, and the record), truck court depth and trailer
parking through truck_access, sprinkler heads on the ceiling photos (ESFR only when the vision model is confident),
straight-line distance to highway on-ramps, rail, airports, ports and the nearest substation (OpenStreetMap), and the
FEMA flood zone.

A door seen from inside sits at the warehouse floor either way, so the scan cannot tell a dock-high door from a
drive-in one; the aerial reading (loading_docks) does that.
"""
from __future__ import annotations

from pydantic import BaseModel

from .. import Check, Finding, Metric, Place, Source, ToolResult, Verdict, field, run_tool, tool
from .._site import geo, pin, pins
from ..market_comps import kit
from ..site_scorecard import near

FT_PER_M = 3.28084
TRUCK_DOOR_M = 2.4  # 8 ft: the narrowest common dock door
REC = Source(layer="costar", method="lookup", confidence="medium", note="CoStar property record")
SCAN = Source(layer="matterport", method="geometry", confidence="high", note="Measured on the scan")
OSM = Source(layer="model", method="lookup", confidence="medium", note=near.NOTE + ", straight-line distance")
FEMA = Source(layer="model", method="lookup", confidence="medium", note="FEMA flood hazard areas (Esri's hosted copy of the NFHL)")
SPRINKLER_Q = ("Look at these ceiling photos of a warehouse or industrial space. Are fire sprinkler heads visible? If they "
               "are, could they be ESFR (early suppression fast response: large pendent heads, often with a wide deflector, "
               "close under the roof deck, on large-diameter mains)? Say 'esfr' only if you are confident from what is "
               "visible; otherwise 'standard' or 'unsure'. Count only what you can see.")
SPRINKLER_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["heads_visible", "type", "confidence", "note"],
                    "properties": {"heads_visible": {"type": "boolean"},
                                   "type": {"type": "string", "enum": ["esfr", "standard", "unsure", "none"]},
                                   "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                                   "note": {"type": "string"}}}


class Inputs(BaseModel):
    place: Place = field(source="selection.place", description="The building: a scan, a CoStar property, an address or a point")
    clear_min_ft: float = field(24, pref="site.clear_height_min_ft", unit="ft", ge=8, le=60, description="Clear height needed")
    docks_min: int = field(2, pref="site.docks_min", ge=0, le=500, description="Dock doors needed")
    court_min_m: float = field(39.6, pref="truck.court_min_m", unit="m", ge=10, le=80,
                               description="Truck court depth a 53 ft trailer needs (130 ft)")
    site_tools: bool = field(True, description="Run truck_access and loading_docks on the aerial (slow, cached)")
    read_panoramas: bool = field(True, description="Ask the vision model about sprinkler heads on up to three ceiling photos")


def scan_doors(plan: dict) -> list[dict]:
    """Exterior openings at least 2.4 m wide: likely truck doors (dock or drive-in), with width and height."""
    out = []
    for o in plan.get("openings") or []:
        if o.get("type") == "window" or len(o.get("rooms") or []) != 1 or (o.get("width") or 0) < TRUCK_DOOR_M:
            continue
        out.append({"id": o["id"], "width_m": round(o["width"], 2), "height_m": round(o["height"], 2) if o.get("height") else None,
                    "center": o.get("center"), "floor": o.get("floor")})
    return out


def scan_height(plan: dict) -> dict | None:
    """The ceiling height of the largest room (the warehouse floor, not the front offices), in feet; None when the
    scan did not measure it."""
    rooms = [r for r in plan.get("rooms") or [] if r.get("area")]
    if not rooms:
        return None
    r = max(rooms, key=lambda r: r["area"])
    return {"room": r["id"], "ft": round(r["height"] * FT_PER_M, 1), "area_m2": r["area"]} if r.get("height") else None


def sprinklers(plan: dict, n: int = 3) -> dict | None:
    """The vision model on the ceiling face of the panoramas in the largest rooms (cached per question)."""
    from ...vision.model import ask, jpeg
    from ...vision.reader import room_panos
    from ...sources import matterport as mp
    big = sorted((r for r in plan["rooms"] if room_panos(plan, r)), key=lambda r: -(r.get("area") or 0))[:n]
    if not big:
        return None
    panos = [room_panos(plan, r)[0]["id"] for r in big]
    imgs = [jpeg(mp.pano_face(plan["sid"], p, 0, "2k"), 1000) for p in panos]
    a = ask(imgs, SPRINKLER_Q, SPRINKLER_SCHEMA, key=f"industrial_fit/sprinklers/{plan['sid']}")
    return {**a, "panos": panos}


def where_of(place: Place, s) -> dict:
    """The truck tools take a scan, a property id or a point."""
    if place.scan:
        return {"scan": place.scan}
    if s.property_id:
        return {"property_id": s.property_id}
    return {"lat": s.lat, "lon": s.lon}


@tool(id="industrial_fit", title="Industrial fit", icon="warehouse",
      summary="Warehouse check: clear height, dock and drive-in doors, truck court and trailer parking, sprinklers, "
              "highway, rail, port and power nearby, and flood zone.",
      model_description="For a warehouse, distribution or flex building (scan, CoStar property or point): clear height "
                        "from the record and the scan, truck doors on the scan's exterior walls and from the aerial "
                        "(loading_docks), truck court depth for a 53 ft trailer and trailer parking (truck_access), sprinkler "
                        "heads on ceiling photos (ESFR only when confidently seen), straight-line distance to highway "
                        "on-ramps, rail, airports, ports and the nearest substation, and the FEMA flood zone.",
      personas=["industrial_tenant_rep", "commercial_underwriter", "truck_dispatcher"],
      requires=[{"layer": "costar.property", "need": "optional"}, {"layer": "vexcel.ortho", "need": "optional"},
                {"layer": "matterport.rooms", "need": "optional"}, {"layer": "osm", "need": "optional"}],
      blocks=["VerdictHeader", "MetricRow", "CheckList", "EvidenceStrip", "AssumptionChips", "StepLog"],
      annotations={"cost": "slow"},
      examples=["Does this warehouse work for 53 ft trailers?", "Clear height, docks and power for this building"])
def run(ctx, i: Inputs) -> ToolResult:
    s = ctx.site(i.place)
    key = s.key
    row = kit.row(s.property_id) or {}
    if row.get("type_id") in (11, 15, 16):
        row = {}
    ctx.step(f"{s.address or key}: " + (f"CoStar {row['type'].lower()} record" if row else "no commercial record"))
    metrics, checks, findings, ps = [], [], [], []
    anchor = geo(s.lon, s.lat) if s.lat is not None else None

    def add(cid, rule, measured, threshold, unit, status, fid=None, standard=None):
        checks.append(Check(id=cid, rule=rule, measured=measured, threshold=threshold, unit=unit, status=status,
                            standard=standard, findings=[fid] if fid else []))

    # clear height
    plan = None
    if i.place.scan:
        try:
            plan = ctx.plan(i.place.scan)
        except Exception:  # noqa: BLE001
            plan = None
    sh = scan_height(plan) if plan else None
    rec_ft = row.get("clear_ft")
    best_ft, how = (rec_ft, "record") if rec_ft else ((sh["ft"], "scan") if sh else (None, None))
    if rec_ft:
        metrics.append(Metric(id="clear_ft", label="Clear height (record)", value=rec_ft, unit="ft", source=REC))
    if sh:
        metrics.append(Metric(id="scan_height_ft", label="Largest room height on the scan", value=sh["ft"], unit="ft", source=SCAN))
    if best_ft is not None:
        st = "pass" if best_ft >= i.clear_min_ft else "warn" if best_ft >= i.clear_min_ft - 4 else "fail"
        add("clear_height", "Clear height", best_ft, i.clear_min_ft, "ft", st, f"industrial_fit:{key}:clear")
        findings.append(Finding(id=f"industrial_fit:{key}:clear", title="Clear height", status=st, anchor=anchor,
                                source=REC if how == "record" else SCAN,
                                detail=(f"The record gives {rec_ft:g} ft clear. " if rec_ft else "") +
                                       (f"The largest room on the scan is {sh['ft']:g} ft to its ceiling (the scan measures to "
                                        f"the ceiling or roof deck, not under the joists or sprinklers). " if sh else "") +
                                       f"Need {i.clear_min_ft:g} ft."))
    else:
        add("clear_height", "Clear height", None, i.clear_min_ft, "ft", "unknown")

    # truck doors: scan, record, aerial
    doors = scan_doors(plan) if plan and (plan.get("quality") or {}).get("openings", True) else []
    if plan:
        metrics.append(Metric(id="scan_truck_doors", label="Truck-width doors on the scan", value=len(doors), unit="", source=SCAN))
        if doors:
            findings.append(Finding(id=f"industrial_fit:{key}:scan_doors", title="Wide exterior doors on the scan", status="pass",
                                    anchor=anchor, source=SCAN,
                                    detail=f"{len(doors)} exterior openings {TRUCK_DOOR_M} m (8 ft) or wider: " +
                                           ", ".join(f"{d['width_m']:.1f} m wide" + (f" x {d['height_m']:.1f} m" if d["height_m"] else "")
                                                     for d in doors[:12]) + ". From inside, a dock door and a drive-in door "
                                           "both sit at floor level; the aerial check tells them apart."))
    if row.get("docks") is not None:
        metrics.append(Metric(id="record_docks", label="Dock doors (record)", value=row["docks"], unit="", source=REC))
    if row.get("drive_ins") is not None:
        metrics.append(Metric(id="record_drive_ins", label="Drive-in doors (record)", value=row["drive_ins"], unit="", source=REC))
    aerial_doors = court = trailers = None
    if i.site_tools and s.lat is not None:
        w = where_of(i.place, s)
        try:
            ld = run_tool("loading_docks", {**w, "inside": False}, ctx)
            m = {x.id: x.value for x in ld.metrics}
            aerial_doors = m.get("truck_doors")
            metrics.append(Metric(id="aerial_truck_doors", label="Truck doors seen from the air", value=aerial_doors, unit="",
                                  source=next(x.source for x in ld.metrics if x.id == "truck_doors")))
            for f in ld.findings[:3]:
                findings.append(f)
        except Exception as e:  # noqa: BLE001  the record and the scan still answer
            ctx.step(f"loading_docks did not run: {str(e)[:120]}")
        try:
            ta = run_tool("truck_access", {**w, "court_min_m": i.court_min_m}, ctx)
            m = {x.id: x for x in ta.metrics}
            court = m.get("court_depth")
            trailers = m.get("trailers_seen")
            for mid in ("court_depth", "entrance_width", "trailers_seen", "trailer_spaces"):
                if mid in m:
                    metrics.append(m[mid])
            checks += [c for c in ta.checks if c.id in ("court", "entrance", "low_clearance")]
            findings += [f for f in ta.findings if f.id.split(":")[-1] in ("court", "entrance", "low", "directions")]
            ps += [p for o in ta.overlays if o.kind == "pins" for p in o.pins]
        except Exception as e:  # noqa: BLE001
            ctx.step(f"truck_access did not run: {str(e)[:120]}")
    seen = [n for n in (row.get("docks"), aerial_doors, len(doors) if plan else None) if n is not None]
    n_docks = max(seen) if seen else None
    st = "unknown" if n_docks is None else "pass" if n_docks >= i.docks_min else "fail" if n_docks == 0 else "warn"
    add("docks", "Truck doors (most of record, aerial and scan)", n_docks, i.docks_min, "", st)

    # sprinklers
    if row.get("sprinklers"):
        metrics.append(Metric(id="record_sprinklers", label=f"Sprinklers (record): {row['sprinklers']}", value=1, unit="", source=REC))
    if plan and i.read_panoramas:
        try:
            sp = sprinklers(plan)
        except Exception as e:  # noqa: BLE001  the record still says what it says
            sp = None
            ctx.step(f"Sprinkler photos not read: {str(e)[:120]}")
        if sp:
            kind = "ESFR" if sp["type"] == "esfr" and sp["confidence"] == "high" else \
                "sprinkler heads" if sp["heads_visible"] else "no sprinkler heads seen"
            st = "pass" if sp["heads_visible"] else "warn"
            findings.append(Finding(id=f"industrial_fit:{key}:sprinklers", title="Sprinklers on the ceiling photos", status=st,
                                    anchor=anchor, source=Source(layer="model", method="vision", confidence=sp["confidence"],
                                                                 note=f"Vision model on {len(sp['panos'])} ceiling photos"),
                                    media=[{"kind": "pano", "ref": f"{plan['sid']}/{p}/0"} for p in sp["panos"]],
                                    detail=f"{kind[0].upper() + kind[1:]}: {sp['note']}" +
                                           ("" if kind == "ESFR" or sp["type"] != "esfr" else
                                            " The model suggested ESFR but not with high confidence, so it is not claimed.") +
                                           (f" The record says: {row['sprinklers']}." if row.get("sprinklers") else "")))

    # location: highways, rail, hubs, power, flood
    if s.lat is not None:
        try:
            t = near.transport(s.lat, s.lon)
            nb = t["nearest"]
            for k, label, lim in (("highway", "Highway on-ramp", 3), ("rail", "Rail line", 2), ("substation", "Power substation", 3),
                                  ("airport", "Cargo airport", 40), ("port", "Container port", 60)):
                x = nb.get(k)
                if x:
                    metrics.append(Metric(id=f"near.{k}", label=label, value=x["km"], unit="km",
                                          source=OSM if k not in ("airport", "port") else
                                          Source(layer="model", method="lookup", confidence="medium", note=near.HUB_NOTE)))
                    ps.append(pin(f"near_{k}", x["lon"], x["lat"], label.lower(), "pass" if x["km"] <= lim else "warn"))
            findings.append(Finding(id=f"industrial_fit:{key}:location", title="Highways, rail, ports and power", status="pass",
                                    anchor=anchor, source=OSM,
                                    detail="; ".join(f"{k.replace('_', ' ')} {v['name'] + ' ' if v.get('name') else ''}{v['km']:.1f} km"
                                                     for k, v in nb.items() if k in ("highway", "rail", "substation", "airport", "port"))
                                           + ". Straight-line distances; a substation nearby does not mean capacity is free: "
                                           "ask the utility." + ("" if "substation" in nb else " No substation is mapped within 3 km.")
                                           + (f" The record gives {row['amps']} A service." if row.get("amps") else "")
                                           + (" The record notes rail access." if row.get("rail") else "")))
            h = nb.get("highway")
            add("highway", "Highway on-ramp within 3 km", h["km"] if h else None, 3, "km",
                "unknown" if not h else "pass" if h["km"] <= 3 else "warn")
        except Exception as e:  # noqa: BLE001
            ctx.step(f"OpenStreetMap lookup failed: {str(e)[:120]}")
        try:
            from ..flood_rehearsal.public import fema_zone
            z = fema_zone(s.lat, s.lon)
            st = "fail" if z["in_sfha"] else "warn" if "0.2" in (z.get("subtype") or "") else "pass"
            add("flood", "Outside FEMA's 1% annual chance flood zone", None, None, "", st, f"industrial_fit:{key}:flood")
            findings.append(Finding(id=f"industrial_fit:{key}:flood", title="FEMA flood zone", status=st, anchor=anchor, source=FEMA,
                                    detail=(f"Zone {z['zone']}" if z.get("zone") else "Outside FEMA's 1% annual chance flood zones (the "
                                            "layer maps only those, so a 0.2% zone is not shown)")
                                           + (f", {z['subtype'].lower()}" if z.get("subtype") else "")
                                           + (". Inside the special flood hazard area: flood insurance and racking above the "
                                              "base flood elevation matter." if z["in_sfha"] else ".")))
        except Exception as e:  # noqa: BLE001
            ctx.step(f"Flood zone lookup failed: {str(e)[:120]}")

    if s.lat is not None:
        ps.insert(0, pin("building", s.lon, s.lat, "building", "pass"))
    bad = [c for c in checks if c.status == "fail"]
    warn = [c for c in checks if c.status == "warn"]
    status = "fail" if bad else "warn" if warn else "pass" if checks else "unknown"
    parts = []
    if best_ft is not None:
        parts.append(f"{best_ft:g} ft clear ({how})")
    if n_docks is not None:
        parts.append(f"{n_docks:g} truck doors")
    if court is not None and court.value is not None:
        parts.append(f"a {court.value:.0f} m truck court")
    text = (f"{s.address or key}: " + (", ".join(parts) if parts else "little is known") + "." +
            (f" Short of need: {'; '.join(c.rule.lower() for c in bad + warn)}." if bad or warn else ""))
    return ToolResult(scope=s.scope(), verdict=Verdict(status=status, text=text), metrics=metrics, checks=checks,
                      findings=findings, overlays=pins(ps),
                      assumptions=[{"id": "site.clear_height_min_ft", "label": "Clear height needed", "value": i.clear_min_ft, "unit": "ft", "editable": True},
                                   {"id": "site.docks_min", "label": "Truck doors needed", "value": i.docks_min, "editable": True},
                                   {"id": "truck.court_min_m", "label": "Court depth needed", "value": i.court_min_m, "unit": "m", "editable": True},
                                   {"id": "truck_door_width", "label": "Truck door if this wide", "value": TRUCK_DOOR_M, "unit": "m"}])
