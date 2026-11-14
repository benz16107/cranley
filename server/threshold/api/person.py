"""The person's side of the agent: what is known about them across investigations, where a workspace used it, and
feedback on a check.

GET  /api/person/{profile}            the person document (agent/profile.py): facts with their source, and one
                                      measured row per investigation. ?workspace=<id> words sources relative to it;
                                      ?sessions=false leaves the measuring out.
GET  /api/workspace/{id}/because      where this workspace used the profile, as notes for "because you" chips.
POST /api/workspace/{id}/feedback     {finding, verdict: "useful" | "not_relevant"}: a `finding.add` by the user with
                                      feedback. "not_relevant" also hides the others of its kind; `hidden` counts them
                                      and `undo` is the log entry that takes it all back.

A fact is changed or forgotten with the ordinary `pref.set` op on the open workspace; the profile follows.
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..agent import prefs, profile
from ..agent.workspace import Feedback, FindingAdd, pick_store
from .agent import session, view

router = APIRouter(prefix="/api")


@router.get("/person/{id}")
def person_get(id: str, workspace: str | None = None, sessions: bool = True) -> dict:
    return profile.person(pick_store(), id, here=workspace, sessions=sessions)


@router.get("/workspace/{id}/because")
def because_get(id: str) -> dict:
    return profile.because(session(id).doc)


class FeedbackIn(BaseModel):
    finding: str
    verdict: Literal["useful", "not_relevant"]


@router.post("/workspace/{id}/feedback")
def feedback(id: str, body: FeedbackIn) -> dict:
    s = session(id)
    f = next((x for x in s.doc.findings if x.id == body.finding), None)
    if f is None:
        raise HTTPException(404, f"No check {body.finding} in this workspace")
    fb = Feedback(verdict="confirmed") if body.verdict == "useful" else Feedback(verdict="rejected", reason=prefs.NOT_RELEVANT)
    entries = s.submit(FindingAdd(finding=f.model_copy(update={"feedback": fb})), by="user")
    return {**view(s), "undo": entries[0].seq, "kind": prefs.kind(f.tool, f.title)[1],
            "hidden": sum(1 for e in entries[1:] if isinstance(e.op, FindingAdd))}
