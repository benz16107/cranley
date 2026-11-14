"""Learning from the op log. A user op that carries a lesson becomes a `pref.set` naming the event it came from;
later runs read the preferences. Everything learned is listed (`learned`) with an undo per item.

Keys:
  <x-pref key>             a threshold the user edited (pref.set by the user, e.g. access.door_width_m)
  label.<sid>.<room>       a corrected room label; tools see it through `with_labels`
  tool.off.<tool>          the user removed a tool; the composer leaves it out next time
  mute.<finding id>        the user rejected a finding; later runs do not add it again
"""
from __future__ import annotations

import copy
from collections.abc import Callable

from .workspace import FindingAdd, PrefSet, ToolDisable, Workspace


def _title(doc: Workspace, tool: str) -> str:
    from .catalog import catalog
    m = catalog().get(tool)
    return m.title if m else tool


def derive(before: Workspace, op) -> list[PrefSet]:
    """Preferences to learn from one user op (applied to `before`)."""
    match op:
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
    return f"You set {key} to {value}"


def learned(doc: Workspace) -> list[dict]:
    """The "What I have learned" list. `undo` is the op the web app sends to forget an item."""
    return [{"key": p.key, "value": p.value, "text": describe(p.key, p.value, p.reason), "cause": p.cause,
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
        fixes = {k.split(".", 2)[2]: v.value for k, v in doc.prefs.items() if k.startswith(f"label.{sid}.")}
        if not fixes:
            return p
        p = copy.deepcopy(p)
        for r in p["rooms"]:
            if r["id"] in fixes:
                r.update(label=fixes[r["id"]], label_source="user", label_confidence=1.0)
        p["has"]["room_labels"] = True
        return p
    return load


def as_text(doc: Workspace) -> str:
    """The learned list as lines for the agent's prompt."""
    return "\n".join(f"- {i['text']} ({i['key']} = {i['value']})" for i in learned(doc)) or "- nothing yet"
