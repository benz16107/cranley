"""Composer: one structured-output call turns a person's sentence into a persona (or none), tools with reasons, what
the tools cannot do for them, and up to four questions. Tool and persona ids are enums, so the model cannot invent
one. The questions are not written by the model: they are the chosen tools' required inputs that nothing fills yet
(`x-ask`), deduplicated. `evaluate.py` scores it on forty briefs."""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, create_model

from . import prefs
from .catalog import catalog, personas, resolve
from .llm import Model
from .workspace import MEASURE, BriefSet, Question, QuestionAsk, ToolEnable, Workspace, apply

MAX_QUESTIONS = 4
MAX_TOOLS = 6

SYSTEM = """You set up a workspace for a person who needs something from a building. Choose the persona preset that
matches who they are and why they are looking, and the tools that serve their need, with one plain sentence each
saying why, addressed to them ("you").
- If a preset fits, start from its tools; drop ones that do not fit what they said and add ones that do.
- If no preset fits their situation (a sharing of tools is not enough: the preset's "who" must describe them), choose
  persona "none" and assemble the tools yourself from the list, by what each tool does.
- Prefer ready tools; include a planned tool only when it is central to the need. Two to five tools is usual.
- In "cannot", say in one plain sentence each what they need that no tool here does (at most three; empty when the
  tools cover it). Name the need, not a tool.
- Write the summary as one line: who they are and what they need, in their terms.
- If the person said a size a question below asks for (their sofa, chair or load), put the question's key and the
  person's exact words for that size in "stated". Never convert or type the number yourself.
Never state measurements or facts about any building. Write no numbers at all except ones the person said."""


def schema(tool_ids: list[str], persona_ids: list[str], keys: list[str] | None = None) -> type[BaseModel]:
    Pick = create_model("Pick", id=(Literal[tuple(tool_ids)], ...),
                        reason=(str, Field(description="One sentence to the person: why this tool is here")))
    extra = {}
    if keys:
        Stated = create_model("Stated", key=(Literal[tuple(keys)], ...),
                              quote=(str, Field(description="The person's exact words giving that size, e.g. '90 cm wide'")))
        extra["stated"] = (list[Stated], Field(default=[], max_length=4))
    return create_model("Composition", persona=(Literal[(*persona_ids, "none")], ...),
                        summary=(str, Field(description="One line: who they are and what they need")),
                        tools=(list[Pick], Field(min_length=1, max_length=MAX_TOOLS)),
                        cannot=(list[str], Field(default=[], max_length=3,
                                                 description="What they need that no tool here does, one sentence each")),
                        **extra)


def prompt(text: str, doc: Workspace, recalled: list[str] | None = None) -> tuple[str, list[str]]:
    off = prefs.tools_off(doc)
    tools = {k: m for k, m in catalog().items() if k not in off}
    lines = ["Person said: " + text, "", "Persona presets (id: who; tools):"]
    lines += [f"- {p.id}: {p.who} Tools: {', '.join(p.tools)}" for p in personas().values()]
    lines += ["", "Tools (id [status]: what it does):"]
    lines += [f"- {m.id} [{m.status}]: {m.summary}" for m in tools.values()]
    asks = askable(tools)
    if asks:
        lines += ["", "Questions the tools may ask (key: question):"] + [f"- {k}: {q}" for k, (q, _) in asks.items()]
    if off:
        lines += ["", "The person removed these before; do not choose them: " + ", ".join(sorted(off))]
    if recalled:  # from the store's memory: earlier people with a similar need
        lines += ["", "Similar needs from earlier sessions (how they were set up and what those people changed; "
                      "start from what fits this person, leave out what they removed):", *recalled]
    return "\n".join(lines), list(tools)


def askable(tools: dict) -> dict[str, tuple[str, str | None]]:
    """Preference key -> (question, unit) for the number inputs ready tools may ask for."""
    out = {}
    for m in tools.values():
        for s in m.inputs.get("properties", {}).values() if m.status == "ready" else ():
            if s.get("x-ask") and s.get("x-pref") and s.get("type") == "number":
                out.setdefault(s["x-pref"], (s["x-ask"], s.get("x-unit")))
    return out


TO_M = {"mm": 0.001, "cm": 0.01, "m": 1, "metre": 1, "meter": 1, "metres": 1, "meters": 1, "in": 0.0254, "inch": 0.0254,
        "inches": 0.0254, "\"": 0.0254, "ft": 0.3048, "foot": 0.3048, "feet": 0.3048, "'": 0.3048}
SIZE = re.compile(r"(\d+(?:\.\d+)?)\s*(mm|cm|metres|meters|metre|meter|m|inches|inch|in|\"|feet|foot|ft|')(?![a-z])", re.I)


def from_quote(quote: str, text: str, unit: str | None) -> float | None:
    """The value of a size the person said, computed from their own words; None unless the quote is in their text
    and gives one number with a length unit."""
    if unit != "m" or quote.lower() not in text.lower():
        return None
    hits = SIZE.findall(quote)
    if len(hits) != 1:
        return None
    n, u = hits[0]
    return round(float(n) * TO_M[u.lower()], 3)


def questions(doc: Workspace, tool_ids: list[str]) -> list[Question]:
    """Required inputs of the chosen ready tools that no preference, answer or preset fills."""
    out: dict[str, Question] = {}
    for tid in tool_ids:
        m = catalog().get(tid)
        if not m or m.status != "ready":
            continue
        for name, s in resolve(m, doc)[2]:
            if "x-ask" not in s:
                continue
            key = s.get("x-pref") or f"{tid}.{name}"
            if key in out:
                out[key].tools.append(tid)
            else:
                out[key] = Question(id=f"q_{key}", key=key, text=s["x-ask"], tools=[tid],
                                    input={k: v for k, v in s.items() if k not in ("x-ask", "title")})
    return list(out.values())[:MAX_QUESTIONS]


def compose(text: str, doc: Workspace, model: Model, run: str | None = None, recalled: list[str] | None = None) -> list:
    """Ops that set the brief, enable tools and ask what the tools need. Nothing is applied here."""
    user, tool_ids = prompt(text, doc, recalled)
    asks = askable({k: catalog()[k] for k in tool_ids})
    c = model.structured(SYSTEM, user, schema(tool_ids, list(personas()), list(asks)))
    said = {}
    for s in getattr(c, "stated", None) or []:
        v = from_quote(s.quote, text, asks[s.key][1])
        if v is not None:
            said[s.key] = v
    limits = [x for x in getattr(c, "cannot", None) or [] if not MEASURE.search(x)]
    ops: list = [BriefSet(text=text, summary=c.summary, persona=None if c.persona == "none" else c.persona,
                          limits=limits, run=run)]
    seen, picks = set(), []
    for p in c.tools:
        if p.id not in seen:
            seen.add(p.id)
            picks.append(p)
            ops.append(ToolEnable(tool=p.id, reason=p.reason, status=catalog()[p.id].status, run=run))
    future = apply(doc, ops[0])
    for q in questions(future, [p.id for p in picks]):
        if any(x.key == q.key and x.answered for x in doc.questions):
            continue
        if q.key in said:  # pre-filled from the person's words; they confirm it
            q.answer = said[q.key]
        ops.append(QuestionAsk(question=q, run=run))
    return ops
