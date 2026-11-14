"""Learning from the op log. A user op that carries a lesson becomes a `pref.set` naming the event it came from;
later runs read the preferences. Everything learned is listed (`learned`) with an undo per item.

Keys:
  <x-pref key>             a threshold the user edited (pref.set by the user, e.g. access.door_width_m)
  label.<sid>.<room>       a corrected room label; tools see it through `with_labels`. A user correction spreads:
                           the same room in sibling scans of the property (same old label, size within 15%) gets
                           the new label, `because` = the correction's key
  doubt.<sid>.<room>       a room the correction makes doubtful (same old label, not matched); tools see a lower
                           label confidence and `label_doubt`
  tool.off.<tool>          the user removed a tool; the composer leaves it out next time
  mute.<finding id>        the user rejected a finding; later runs do not add it again
"""
from __future__ import annotations

import copy
from collections.abc import Callable

from .workspace import FindingAdd, PrefSet, ToolDisable, Workspace

MAX_SIBLINGS = 6     # sibling scans a correction re-checks
MAX_SPREAD = 20      # labels a correction may change or mark doubtful
SAME_SIZE = 0.15     # rooms match when their areas differ by at most this fraction


def _title(doc: Workspace, tool: str) -> str:
    from .catalog import catalog
    m = catalog().get(tool)
    return m.title if m else tool


def spread(before: Workspace, sid: str, room: str, new: str, plans: Callable[[str], dict],
           siblings: Callable[[str], list[str]] | None) -> list[PrefSet]:
    """What one room-label correction makes doubtful or changes elsewhere, bounded by MAX_SIBLINGS and MAX_SPREAD."""
    because = f"label.{sid}.{room}"
    view = with_labels(plans, before)
    try:
        here = view(sid)
    except Exception:
        return []
    r = next((x for x in here["rooms"] if x["id"] == room), None)
    old = r and r.get("label")
    if not r or not old or old == new:
        return []
    fixed = {k for k, v in before.prefs.items() if k.startswith("label.") and v.by == "user"}
    out = [PrefSet(by="system", key=f"doubt.{sid}.{x['id']}", value={"label": old, "because": because}, because=because,
                   reason=f"Room {x['id']} here is also labelled {old}; you said room {room} is a {new}, so check it")
           for x in here["rooms"] if x["id"] != room and x.get("label") == old and f"label.{sid}.{x['id']}" not in fixed]
    for s2 in [s for s in (siblings(sid) if siblings else []) if s != sid][:MAX_SIBLINGS]:
        try:
            rooms = view(s2)["rooms"]
        except Exception:
            continue
        same = [x for x in rooms if x.get("label") == old and f"label.{s2}.{x['id']}" not in fixed]
        size = [x for x in same if r.get("area") and x.get("area") and abs(x["area"] - r["area"]) <= SAME_SIZE * r["area"]]
        if len(size) == 1:
            out.append(PrefSet(by="system", key=f"label.{s2}.{size[0]['id']}", value=new, because=because,
                               reason=f"Changed from {old} to {new} in scan {s2}: you corrected the same room "
                                      f"({room}) in scan {sid}, and this one has the same label and size"))
        else:
            out += [PrefSet(by="system", key=f"doubt.{s2}.{x['id']}", value={"label": old, "because": because},
                            because=because, reason=f"Scan {s2}: room {x['id']} is labelled {old} like the room you "
                                                    f"corrected in scan {sid}; check it") for x in same[:3]]
    return out[:MAX_SPREAD]


def derive(before: Workspace, op, plans: Callable[[str], dict] | None = None,
           siblings: Callable[[str], list[str]] | None = None) -> list[PrefSet]:
    """Preferences to learn from one user op (applied to `before`)."""
    match op:
        case PrefSet() if op.key.startswith("label.") and op.key.count(".") >= 2:
            if op.value is None:  # forgetting a correction forgets what it spread
                return [PrefSet(by="system", key=k, value=None, reason=f"Forgotten with {op.key}")
                        for k, v in before.prefs.items() if v.because == op.key]
            _, sid, room = op.key.split(".", 2)
            return spread(before, sid, room, op.value, plans, siblings) if plans else []
        case ToolDisable():
            return [PrefSet(by="system", key=f"tool.off.{op.tool}", value=True,
                            reason=f"You removed {_title(before, op.tool)}" + (f": {op.reason}" if op.reason else ""))]
        case FindingAdd() if op.finding.feedback and op.finding.feedback.verdict == "rejected":
            f, why = op.finding, op.finding.feedback.reason
            return [PrefSet(by="system", key=f"mute.{f.id}", value={"tool": f.tool, "title": f.title},
                            reason=f"You rejected \"{f.title}\"" + (f": {why}" if why else ""))]
    return []


def describe(key: str, value, reason: str) -> str:
    if reason:
        return reason
    if key.startswith("label."):
        return f"You said this room is a {value}"
    if key.startswith("doubt."):
        return "A correction makes this room's label doubtful"
    return f"You set {key} to {value}"


def learned(doc: Workspace) -> list[dict]:
    """The "What I have learned" list. `undo` is the op the web app sends to forget an item."""
    return [{"key": p.key, "value": p.value, "text": describe(p.key, p.value, p.reason), "cause": p.cause,
             "because": p.because,
             "by": p.by, "at": p.at, "undo": {"op": "pref.set", "key": p.key, "value": None, "by": "user"}}
            for p in doc.prefs.values()]


def muted(doc: Workspace) -> set[str]:
    return {k[len("mute."):] for k in doc.prefs if k.startswith("mute.")}


def tools_off(doc: Workspace) -> set[str]:
    return {k[len("tool.off."):] for k in doc.prefs if k.startswith("tool.off.") and doc.prefs[k].value}


def with_labels(plans: Callable[[str], dict], doc: Workspace) -> Callable[[str], dict]:
    """A plan loader that applies the user's room label corrections."""
    def load(sid: str) -> dict:
        p = plans(sid)
        fixes = {k.split(".", 2)[2]: v for k, v in doc.prefs.items() if k.startswith(f"label.{sid}.")}
        doubts = {k.split(".", 2)[2]: v.value for k, v in doc.prefs.items() if k.startswith(f"doubt.{sid}.")}
        if not fixes and not doubts:
            return p
        p = copy.deepcopy(p)
        for r in p["rooms"]:
            if r["id"] in fixes:  # a label spread from a correction elsewhere is less certain than the person's own
                f = fixes[r["id"]]
                r.update(label=f.value, label_source="user", label_confidence=1.0 if f.by == "user" else 0.7)
            elif r["id"] in doubts:
                r.update(label_confidence=min(r.get("label_confidence") or 1.0, 0.3), label_doubt=doubts[r["id"]]["because"])
        p["has"]["room_labels"] = bool(fixes) or p["has"].get("room_labels")
        return p
    return load


def as_text(doc: Workspace) -> str:
    """The learned list as lines for the agent's prompt."""
    return "\n".join(f"- {i['text']} ({i['key']} = {i['value']})" for i in learned(doc)) or "- nothing yet"
