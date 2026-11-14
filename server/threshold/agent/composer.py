"""Composer: one structured-output call turns a person's sentence into a persona, tools with reasons, and up to
four questions. Tool and persona ids are enums, so the model cannot invent one. The questions are not written
by the model: they are the chosen tools' required inputs that nothing fills yet (`x-ask`), deduplicated."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, create_model

from . import prefs
from .catalog import catalog, personas, resolve
from .llm import Model
from .workspace import BriefSet, Question, QuestionAsk, ToolEnable, Workspace, apply

MAX_QUESTIONS = 4
MAX_TOOLS = 6

SYSTEM = """You set up a workspace for a person who needs something from a building. Choose the persona preset closest
to them and the tools that serve their need, with one plain sentence each saying why, addressed to them ("you").
Start from the preset's tools; drop ones that do not fit what they said and add ones that do. Prefer ready tools;
include a planned tool only when it is central to the need. Write the summary as one line: who they are and what
they need, in their terms. Never state measurements or facts about any building."""


def schema(tool_ids: list[str], persona_ids: list[str]) -> type[BaseModel]:
    Pick = create_model("Pick", id=(Literal[tuple(tool_ids)], ...),
                        reason=(str, Field(description="One sentence to the person: why this tool is here")))
    return create_model("Composition", persona=(Literal[tuple(persona_ids)], ...),
                        summary=(str, Field(description="One line: who they are and what they need")),
                        tools=(list[Pick], Field(min_length=1, max_length=MAX_TOOLS)))


def prompt(text: str, doc: Workspace) -> tuple[str, list[str]]:
    off = prefs.tools_off(doc)
    tools = {k: m for k, m in catalog().items() if k not in off}
    lines = ["Person said: " + text, "", "Persona presets (id: who; tools):"]
    lines += [f"- {p.id}: {p.who} Tools: {', '.join(p.tools)}" for p in personas().values()]
    lines += ["", "Tools (id [status]: what it does):"]
    lines += [f"- {m.id} [{m.status}]: {m.summary}" for m in tools.values()]
    if off:
        lines += ["", "The person removed these before; do not choose them: " + ", ".join(sorted(off))]
    return "\n".join(lines), list(tools)


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


def compose(text: str, doc: Workspace, model: Model, run: str | None = None) -> list:
    """Ops that set the brief, enable tools and ask what the tools need. Nothing is applied here."""
    user, tool_ids = prompt(text, doc)
    c = model.structured(SYSTEM, user, schema(tool_ids, list(personas())))
    ops: list = [BriefSet(text=text, summary=c.summary, persona=c.persona, run=run)]
    seen, picks = set(), []
    for p in c.tools:
        if p.id not in seen:
            seen.add(p.id)
            picks.append(p)
            ops.append(ToolEnable(tool=p.id, reason=p.reason, status=catalog()[p.id].status, run=run))
    future = apply(doc, ops[0])
    ops += [QuestionAsk(question=q, run=run) for q in questions(future, [p.id for p in picks])
            if not any(x.key == q.key and x.answered for x in doc.questions)]
    return ops
