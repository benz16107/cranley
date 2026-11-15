"""The person profile: what Cranley knows about one person, across their investigations.

The store already keeps a profile: every preference a workspace changes is merged into it key by key, and a new
workspace starts from it (`workspace.Session.create`). Each preference the person caused carries an `origin`
(workspace, its brief, when, how). This module is the person's view of that profile:

- `standing(key)`  is this about the person (their chair, their child's age) or about one building or one storm?
- `person(...)`    the document the "Cranley knows" page shows: each fact with where it came from and the op that
                   forgets it, and one measured row per investigation.
- `measure(...)`   what one investigation cost the person and gave them, counted from its op log.
- `because(doc)`   every place a workspace used the profile, as notes the web app shows as "because you" chips.
- `known(doc)`     the same facts as lines for the composer's prompt.

Every number here is counted from the op log or copied from a stored value. No model writes any of them.
"""
from __future__ import annotations

import functools
import time
from typing import Any

from . import prefs
from .catalog import catalog, personas
from .workspace import SESSION, BriefSet, LogEntry, Origin, PrefSet, QuestionAsk, RunStart, Workspace, replay

# Keys that are about one building, one storm or one turn. Everything else a person answers is about them.
SITUATIONAL = ("approval.", "label.", "doubt.", "mute.", "storm.", "daylight.", "bid.", "site.", SESSION)
SITUATIONAL_KEYS = {"flood.depth_m", "search.city"}
MATTERS = ("more.", "less.", "tool.off.")
MAX_SESSIONS = 6  # investigations the person's page measures, latest last

# The few inputs worth naming in the person's words (what the page calls it, what a chip calls it); the rest use
# the tool's own title.
LABELS = {"access.door_width_m": ("Doorway width you need", "doorway width"),
          "access.turning_diameter_m": ("Room you need to turn", "turning room"),
          "kids.youngest_age": ("Your youngest child's age", "youngest child's age"),
          "pets.dog_lb": ("Your dog's weight", "dog's weight"), "garage.vehicle": ("Your vehicle", "vehicle"),
          "driveway.vehicle": ("Your vehicle on the driveway", "vehicle"),
          "office.headcount": ("People who need a seat", "head count"),
          "commute.employees": ("Where your people live", "people's home areas"), "who.persona": ("Who you are", "role")}
VERB = {"answer": "you told me", "edit": "you set it", "removed": "you removed it", "feedback": "you marked it"}


def standing(key: str) -> bool:
    return not key.startswith(SITUATIONAL) and key not in SITUATIONAL_KEYS and ":" not in key


def group(key: str) -> str:
    """about (a fact about the person), matters (what they marked or removed) or building (one place only)."""
    return "matters" if key.startswith(MATTERS) else "about" if standing(key) else "building"


@functools.cache
def _inputs() -> dict[str, tuple[str, dict]]:
    """Preference key -> (tool id, that input's schema), first tool that has it."""
    out: dict[str, tuple[str, dict]] = {}
    for m in catalog().values():
        for s in m.inputs.get("properties", {}).values():
            if s.get("x-pref"):
                out.setdefault(s["x-pref"], (m.id, s))
    return out


def _title(tool: str | None) -> str:
    m = catalog().get(tool or "")
    return m.title if m else (tool or "the agent")


def label(key: str) -> tuple[str, str | None]:
    """(what the fact is called, its unit)."""
    _, s = _inputs().get(key, (None, {}))
    if key in LABELS:
        return LABELS[key][0], s.get("x-unit")
    words = str(s.get("title") or key.split(".")[-1]).replace("_", " ").lower()
    for unit in (" m", " ft", " lb", " km", " min"):  # "Min Width M": the unit is printed beside the value
        words = words.removesuffix(unit)
    return words.capitalize(), s.get("x-unit")


def fmt(value: Any, unit: str | None = None) -> str:
    """A stored value as text. Only the format is ours: the digits are the stored ones."""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        value = f"{value:g}"
    if isinstance(value, (list, tuple)):
        value = ", ".join(fmt(v) for v in value) or "none"
    if isinstance(value, dict):
        value = str(value.get("kind") or value.get("title") or "")
    return f"{value} {unit}" if unit and unit not in ("None",) else str(value)


def why(o: Origin | dict | None, here: str | None = None, key: str = "", short: bool = False) -> str:
    """Where a fact came from, said to the person: "you told me on 14 Nov in “…”". `key` words a mark on a check;
    `short` leaves the investigation's name out, for a chip."""
    if not o:
        return "from an earlier investigation"
    o = o if isinstance(o, Origin) else Origin.model_validate(o)
    verb = "you marked one not relevant" if key.startswith("less.") else "you marked one useful" if key.startswith("more.") else VERB[o.how]
    if o.workspace == here:
        return f"{verb} in this investigation"
    when = time.strftime("%-d %b", time.localtime(o.at))
    return f"{verb} on {when}" + (f" in “{o.investigation}”" if o.investigation and not short else "")


def fact(p: dict, here: str | None = None) -> dict:
    """One profile preference as the person reads it. `p` is a stored preference (key, value, reason, origin, at)."""
    key, value = p["key"], p["value"]
    if key.startswith("tool.off."):
        text, shown, unit = "Left out", _title(key[len("tool.off."):]), None
    elif key.startswith(("more.", "less.")):
        text = "Useful to you" if key.startswith("more.") else "Not relevant to you"
        shown, unit = f"“{value.get('kind', '')}” checks from {_title(value.get('tool'))}", None
    elif key == "who.persona":
        who = personas().get(str(value))
        text, shown, unit = LABELS[key][0], who.title if who else str(value), None
    else:
        (text, unit), shown = label(key), fmt(value)
    _, schema = _inputs().get(key, (None, {}))
    return {"key": key, "group": group(key), "label": text, "value": value, "shown": shown, "unit": unit,
            "origin": p.get("origin"), "why": why(p.get("origin"), here, key), "said": p.get("reason") or "",
            "at": (p.get("origin") or {}).get("at") or p.get("at"),
            # a number or a short word can be edited in place; a list or a mark can only be forgotten
            "edit": ({"type": schema.get("type"), "min": schema.get("minimum", schema.get("exclusiveMinimum")),
                      "max": schema.get("maximum"), "options": schema.get("enum")}
                     if schema.get("type") in ("number", "integer", "string") and group(key) == "about" else None),
            "undo": {"op": "pref.set", "key": key, "value": None, "by": "user"}}


def carried(doc: Workspace) -> dict[str, Any]:
    """Preferences this workspace got from the profile: learned in another investigation and not changed here."""
    return {k: p for k, p in doc.prefs.items() if p.origin and p.origin.workspace != doc.id}


def known(doc: Workspace) -> list[str]:
    """What earlier investigations learned about the person, as prompt lines. Empty for a new person, so their
    prompt is the one it always was."""
    out = []
    for k, p in carried(doc).items():
        f = fact(p.model_dump(mode="json"), doc.id)
        if f["group"] == "building":
            continue
        out.append(f"- {f['label']}: {f['shown']}{' ' + f['unit'] if f['unit'] else ''} ({f['why']}"
                   + (f"; {p.reason}" if k == "who.persona" and p.reason else "") + ")")
    return out


def brought(doc: Workspace, log: list[LogEntry] | None = None) -> dict[str, Origin]:
    """Key -> origin of what the profile brought into this workspace. Read from the log when there is one (the
    entries `Session.create` wrote), so changing or forgetting a fact later does not rewrite what happened before."""
    if log is None:
        return {k: p.origin for k, p in carried(doc).items()}
    return {e.op.key: e.op.origin for e in log if isinstance(e.op, PrefSet) and e.op.by == "system"
            and e.op.origin and e.op.origin.workspace != doc.id}


def _unasked(doc: Workspace, mine: dict[str, Origin]) -> list[tuple[str, str]]:
    """(key, question) the enabled tools need that the person answered in an earlier investigation, so it was not
    asked again here. A persona's default is not their answer: without the profile they would have to say it again."""
    from .composer import questions
    mine = {k for k, o in mine.items() if o.how == "answer"}
    if not mine:
        return []
    tools = [t.id for t in doc.tools if t.enabled]
    bare = doc.model_copy(update={"prefs": {k: p for k, p in doc.prefs.items() if k not in mine}})
    asked = {q.key for q in doc.questions}
    return [(q.key, q.text) for q in questions(bare, tools, frozenset(mine)) if q.key in mine and q.key not in asked]


def _hidden(doc: Workspace) -> dict[str, list[str]]:
    """Kind -> titles of findings the tools reported that were kept back because the person marked that kind not
    relevant before the run."""
    off, have, out = prefs.less(doc), {f.id for f in doc.findings}, {}
    # the latest run of each tool on each place: a re-run reports the same checks again, and they count once
    latest = {(r.tool, r.sid or (r.place.key() if r.place else "")): r for r in doc.runs if r.status == "done" and r.result}
    for r in latest.values():
        for f in r.result.findings:
            key = prefs.kind(r.tool, f.title)[0]
            if key in off and f.id not in have:
                out.setdefault(key, []).append(f.title)
    return out


def measure(doc: Workspace, log: list[LogEntry]) -> dict:
    """What one investigation asked of the person and gave back, counted from its log."""
    asked = {e.op.question.key for e in log if isinstance(e.op, QuestionAsk) and not e.op.question.key.startswith("approval.")}
    mine = brought(doc, log)
    done = [r for r in doc.runs if r.status == "done" and r.result]
    first = min((r.finished for r in done if r.finished), default=None)
    # the clock starts when the person asked (their brief, or a tool they ran), not when the workspace was made
    began = min((e.at for e in log if (isinstance(e.op, BriefSet) and e.op.text) or isinstance(e.op, RunStart)), default=doc.created)
    seen = [f for f in doc.findings if not f.superseded_by]
    said = (doc.brief.summary or doc.brief.text).strip()
    return {"workspace": doc.id, "created": doc.created, "investigation": said[:80], "started": bool(doc.brief.text or doc.runs),
            "questions_asked": len(asked), "questions_not_asked": len(_unasked(doc, mine)),
            "inputs_from_profile": len({(r.tool, n) for r in doc.runs for n, k in r.inputs_from.items() if k in mine}),
            "tool_runs": len(done), "first_result_s": round(first - began, 1) if first else None,
            "checks_shown": len(seen), "checks_kept_back": sum(len(v) for v in _hidden(doc).values()),
            "marked_useful": sum(1 for f in seen if f.feedback and f.feedback.verdict == "confirmed"),
            "marked_not_relevant": sum(1 for f in seen if f.feedback and f.feedback.verdict == "rejected"
                                       and f.feedback.reason == prefs.NOT_RELEVANT)}


# The rows of "How Cranley has adapted to you": one value per investigation, in order.
ADAPTED = [("questions_asked", "Questions asked"), ("questions_not_asked", "Questions it did not need to ask"),
           ("inputs_from_profile", "Tool inputs filled from what it knows"),
           ("checks_kept_back", "Checks kept back as not relevant to you"),
           ("first_result_s", "Seconds to the first result")]


def person(store, profile: str, here: str | None = None, sessions: bool = True) -> dict:
    """The person document (`person/1`): who they are, what is known with its source, and how each investigation went."""
    facts, places, ids = [], 0, []
    for p in store.profile(profile):
        if p["key"].startswith(SESSION):
            ids.append(((p.get("value") or {}).get("created", 0), p["key"][len(SESSION):]))
        elif p.get("value") is None:
            continue
        elif group(p["key"]) == "building":
            places += 1
        else:
            facts.append(fact(p, here))
    measured = []
    for _, ws in sorted(ids)[-MAX_SESSIONS:] if sessions else []:
        try:
            d = store.load(ws)
        except LookupError:
            continue
        log = [LogEntry.model_validate(e) for e in d["log"]]
        m = measure(replay(Workspace(id=d["id"], profile=d["profile"], created=d["created"]), log), log)
        if m.pop("started"):
            measured.append(m)
    who = next((f for f in facts if f["key"] == "who.persona"), None)
    return {"schema": "person/1", "profile": profile,
            "who": {"persona": who["value"], "title": who["shown"], "said": who["said"]} if who else None,
            "facts": sorted((f for f in facts if f["key"] != "who.persona"), key=lambda f: (f["group"], -(f["at"] or 0))),
            "on_buildings": places, "investigations": len(ids), "sessions": measured,
            "adapted": [{"id": k, "label": text, "values": [m[k] for m in measured]} for k, text in ADAPTED] if len(measured) > 1 else []}


def because(doc: Workspace, log: list[LogEntry] | None = None) -> dict:
    """Where this workspace used what is known about the person. Each note: `kind` (input, not_asked, left_out,
    kept_back, first), `text` (what was done), `why` (where the knowledge came from; `when` is the same without the
    investigation's name), and what it is attached to (`runs`, `tool`, `findings`). `key` is the preference;
    `pref.set` with value null forgets it."""
    notes: list[dict] = []
    mine = brought(doc, log)

    def note(kind: str, key: str, text: str, o: Origin | None = None, **at) -> None:
        o = o or (doc.prefs[key].origin if key in doc.prefs else mine.get(key))  # default: where the value is from now
        notes.append({"kind": kind, "key": key, "text": text, "why": why(o, doc.id, key),
                      "when": why(o, doc.id, key, short=True), "origin": o.model_dump() if o else None, **at})

    used: dict[str, list[str]] = {}  # the person's own value in a tool input: from the profile, or said in this investigation
    for r in doc.runs:
        for key in r.inputs_from.values():
            if key in doc.prefs and doc.prefs[key].origin and group(key) == "about":
                used.setdefault(key, []).append(r.id)
    for key, runs in used.items():
        name, unit = label(key)
        note("input", key, f"Using your {LABELS[key][1] if key in LABELS else name.lower()}: {fmt(doc.prefs[key].value, unit)}", runs=runs, tools=sorted({r.tool for r in doc.runs if r.id in runs}),
             carried=doc.prefs[key].origin.workspace != doc.id)
    for key, text in _unasked(doc, mine):
        note("not_asked", key, f"Did not ask “{text.split('?')[0]}?”", mine[key])  # the earlier answer is why
    for key in mine:
        if key.startswith("tool.off.") and key in doc.prefs:
            note("left_out", key, f"Left out {_title(key[len('tool.off.'):])}", mine[key], tool=key[len("tool.off."):])
    for key, titles in _hidden(doc).items():
        if f"less.{key}" in doc.prefs:
            v = doc.prefs[f"less.{key}"].value
            note("kept_back", f"less.{key}", f"Kept back {len(titles)} “{v.get('kind', '')}” "
                                             f"{'check' if len(titles) == 1 else 'checks'}", tool=v.get("tool"), count=len(titles))
    liked = prefs.more(doc)
    for key in liked:
        ids = [f.id for f in doc.findings if not f.superseded_by and prefs.kind(f.tool, f.title)[0] == key
               and not (f.feedback and f.feedback.verdict == "rejected")]
        if ids:
            v = doc.prefs[f"more.{key}"].value
            note("first", f"more.{key}", f"“{v.get('kind', '')}” checks listed first", findings=ids, tool=v.get("tool"))
    return {"workspace": doc.id, "notes": notes, "from_profile": sum(1 for n in notes if n["kind"] != "input" or n.get("carried"))}
