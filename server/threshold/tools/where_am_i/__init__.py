"""Where am I: the phone's GPS fix finds the scanned building the person is standing in, or says there is none and
offers the tools that need only an aerial photo at that spot."""
from __future__ import annotations

import math

from pydantic import BaseModel

from .. import Action, Finding, GeoAnchor, Metric, Pin, PinsOverlay, ToolResult, Verdict, field, tool
from .._phone import media, source
from ..types import GeoScope

AT_M = 60          # a fix this close to a scanned address is that address (the same rule as a place given as a point)
NEAR_M = 2000      # farther than this is another neighbourhood: not offered
AERIAL_ONLY = [("roof_facts", "Roof facts here"), ("truck_access", "Truck access here"),
               ("parking_count", "Parking count here"), ("risk_sheet", "Risk sheet here")]


class Inputs(BaseModel):
    geo: tuple[float, float] = field(description="[lon, lat] of the phone's fix")
    accuracy_m: float | None = field(None, ge=0, description="The fix's horizontal accuracy as the phone reports it")
    capture: str | None = None


def _rows() -> dict[str, dict]:
    from ...sources import index
    return index.rows()


def metres(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    k = math.cos(math.radians((lat1 + lat2) / 2))
    return 6371000 * math.hypot(math.radians(lat2 - lat1), math.radians(lon2 - lon1) * k)


def nearest(lon: float, lat: float, rows: dict[str, dict] | None = None, limit: int = 5) -> list[dict]:
    """Scanned addresses within NEAR_M, nearest first: {address, city, lat, lon, distance_m, scans: [{sid, name, kind}]}."""
    here: dict[tuple, dict] = {}
    for r in (rows if rows is not None else _rows()).values():
        try:
            la, lo = float(r["lat"]), float(r["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        d = metres(lat, lon, la, lo)
        if d > NEAR_M:
            continue
        b = here.setdefault((r.get("address") or r["sid"], round(la, 5), round(lo, 5)),
                            {"address": r.get("address") or None, "city": r.get("city") or None, "lat": la, "lon": lo,
                             "distance_m": d, "scans": []})
        b["distance_m"] = min(b["distance_m"], d)
        b["scans"].append({"sid": r["sid"], "name": r.get("name") or r["sid"], "kind": r.get("kind")})
    return sorted(here.values(), key=lambda b: b["distance_m"])[:limit]


@tool(id="where_am_i", title="Where am I", icon="locate-fixed",
      summary="Finds the scanned building you are standing in from the phone's GPS, or says there is none here.",
      model_description="From a phone GPS fix [lon, lat]: the scanned buildings within 2 km, nearest first, and "
                        "whether the person is at one. Where there is no scan it offers the aerial-only tools "
                        "(roof_facts, truck_access, parking_count, risk_sheet) at that point.",
      requires=[{"layer": "phone.gps"}], blocks=["VerdictHeader", "MetricRow", "EvidenceStrip", "StepLog", "ActionBar"],
      overlays=["pins"], examples=["Which building am I in?", "Is this address scanned?"])
def run(ctx, inputs: Inputs) -> ToolResult:
    lon, lat = inputs.geo
    acc = inputs.accuracy_m
    found = nearest(lon, lat)
    reach = max(AT_M, acc or 0)
    ctx.step(f"Fix good to {acc:.0f} m" if acc is not None else "The phone gave no accuracy for this fix")
    ctx.step(f"{len(found)} scanned addresses within {NEAR_M / 1000:.0f} km")
    src = source("sensor", "high" if acc is not None and acc <= 20 else "medium" if acc is not None and acc <= AT_M else "low",
                 "Phone GPS" + (f", good to {acc:.0f} m" if acc is not None else ", accuracy not reported")
                 + "; indoors a fix can be tens of metres off")
    key = f"g{lon:.5f},{lat:.5f}"
    at = [b for b in found if b["distance_m"] <= reach]
    findings = [Finding(id=f"where_am_i:{key}:{b['scans'][0]['sid']}", title=b["address"] or b["scans"][0]["name"],
                        status="pass" if b in at else "unknown", anchor=GeoAnchor(geo=(b["lon"], b["lat"])), source=src,
                        detail=f"{b['distance_m']:.0f} m from your fix; {len(b['scans'])} scan"
                               f"{'s' if len(b['scans']) != 1 else ''}: " + ", ".join(s["name"] for s in b["scans"][:4])
                               + ("…" if len(b["scans"]) > 4 else ""), media=media(inputs.capture) if b in at[:1] else [])
                for b in found]
    pins = [Pin(id="me", anchor=GeoAnchor(geo=(lon, lat)), label="You", status="unknown")]
    pins += [Pin(id=f.id, anchor=f.anchor, label=f.title, status=f.status) for f in findings]
    metrics = [Metric(id="nearest_m", label="Nearest scanned address", value=round(found[0]["distance_m"]) if found else None,
                      unit="m", source=src),
               Metric(id="accuracy_m", label="Fix good to", value=round(acc) if acc is not None else None, unit="m", source=src),
               Metric(id="within_2km", label="Scanned addresses near", value=len(found), unit="", source=src)]
    if len(at) == 1:
        verdict = Verdict(status="pass", text=f"You are at {at[0]['address'] or at[0]['scans'][0]['name']}, which has "
                          f"{len(at[0]['scans'])} scan{'s' if len(at[0]['scans']) != 1 else ''}.")
    elif at:
        verdict = Verdict(status="warn", text=f"{len(at)} scanned addresses are within reach of your fix: pick the one "
                          "you are in.")
    elif found:
        verdict = Verdict(status="warn", text="No scanned building where you stand; the nearest is listed. The aerial "
                          "tools work here without a scan.")
    else:
        verdict = Verdict(status="unknown", text="No scanned building near here. The aerial tools work at this spot "
                          "without a scan.")
    actions = [] if at else [Action(id=t, label=label, tool=t, inputs={"place": {"geo": [lon, lat]}}) for t, label in AERIAL_ONLY]
    return ToolResult(scope=GeoScope(geo=(lon, lat)), verdict=verdict, metrics=metrics, findings=findings,
                      overlays=[PinsOverlay(pins=pins)], actions=actions)
