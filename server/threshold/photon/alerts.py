"""Proactive alerts: for each chat, the building it last talked about is checked against the National Weather Service's
active alerts at that point. A new alert (flood, storm, heat, fire weather) is texted once, with what the person's own
results said about that building when there is one (the flood rehearsal's verdict for a flood). A shared iMessage line
can only message people who have texted it, so a refused send waits for their next message (router.Chat.say).

POST /api/photon/alerts/check runs one pass (a user timer calls it every 15 minutes)."""
from __future__ import annotations

import logging

from ..layers.catalog import AGENT, send
from .state import State

log = logging.getLogger("threshold.photon")
NWS = "https://api.weather.gov/alerts/active"
FLOODISH = ("Flood", "Hurricane", "Tropical Storm", "Storm Surge", "Coastal")


def at(lat: float, lon: float) -> list[dict]:
    body = send("GET", NWS, params={"point": f"{lat:.4f},{lon:.4f}"}, timeout=30,
                headers={**AGENT, "Accept": "application/geo+json"}).json()
    return [f["properties"] for f in body.get("features") or [] if f.get("properties")]


def where(sid: str) -> tuple[float, float] | None:
    from ..sources import index
    row = index.rows().get(sid) or {}
    try:
        return float(row["lat"]), float(row["lon"])
    except (KeyError, ValueError):
        return None


def line(p: dict, place: str, flood_verdict: str | None) -> str:
    out = [f"Weather alert at {place}: {p.get('event', 'alert')} ({p.get('severity', 'unknown').lower()} severity), "
           f"until {(p.get('ends') or p.get('expires') or '')[:16].replace('T', ' ')}.", (p.get("headline") or "")[:200]]
    if flood_verdict and any(w in (p.get("event") or "") for w in FLOODISH):
        out.append(f"Your flood check for this building said: {flood_verdict}")
    out.append("Source: National Weather Service. Reply \"alerts off\" to stop these.")
    return "\n".join(x for x in out if x)


def check(st: State, api=None, fetch=at) -> int:
    """One pass over every chat; the number of alerts sent."""
    from . import client
    from .router import Chat, session
    from .words import place_name
    api = api or client
    sent = 0
    for space, t in list(st.data["threads"].items()):
        sid = t.get("background_sid")
        if not sid or not t.get("agent") or t.get("alerts") is False:
            continue
        pt = where(sid)
        if not pt:
            continue
        try:
            alerts = fetch(*pt)
        except Exception:  # noqa: BLE001 - the weather service being down is not the person's problem
            log.exception("nws alerts")
            continue
        seen = set(t.get("alerts_seen", []))
        new = [a for a in alerts if a.get("id") and a["id"] not in seen]
        if not new:
            continue
        flood = None
        if t.get("workspace"):
            s = session(t["workspace"])
            last = next((r for r in reversed(s.doc.runs) if r.tool == "flood_rehearsal" and r.sid == sid and r.result), None)
            flood = last.result.verdict.text if last else None
        chat = Chat(space, t["agent"], t.get("platform", "imessage"), None, api, st)
        for a in new[:2]:
            chat.say(line(a, place_name(sid), flood), reply=False)
            sent += 1
        st.update(space, alerts_seen=[*seen, *[a["id"] for a in new]][-50:])
    return sent
