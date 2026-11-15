"""Adaptation evaluation: does Cranley ask less and show more of what matters as one person uses it more?

One person, three investigations on three buildings, through the real composer and the real agent. The models are
real; the person is a script, so the run can be repeated and their taste is fixed before it starts:

- their facts (`ANSWERS`), given only when a question asks for them;
- what they wave off (`WAVES_OFF`: kinds of check they mark "not relevant", once each) and the tool they remove;
- what they mark useful (`LIKES`, at most three checks an investigation);
- `matters(check)`: their fixed rule for whether a check on screen is worth their time. It is not shown to the agent.

Each investigation starts a new workspace on the same profile and is measured by `profile.measure`, the function the
"Cranley knows" page uses for a real person. Nothing here is written by a model: every figure is counted from the
op logs. Writes <out>/adaptation-eval.md and .json; the workspaces of the run stay beside them.

    cd server && uv run python -m threshold.agent.adapt_eval [--scans a,b,c] [--out DIR]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import time

from ..config import DATA
from . import prefs, profile
from .budget import Budget
from .investigator import SKIP, attach, turn
from .workspace import QuestionAnswer, Session

FIRST = ("I use a wheelchair and my chair is 70 cm wide. I am looking for a home I can get around in without "
         "building work. Is this one workable for me?")
LATER = "Is this one workable for me?"
ANSWERS = {"access.door_width_m": 0.7, "access.turning_diameter_m": 1.5}
WAVES_OFF = {"Grab bars", "Bathing"}        # fall-prevention checks; this person fits their own rails
REMOVES = ("tour", "room_census")           # the first of these the agent enabled is removed in the first visit
LIKES = {"Doorway narrower than you need", "Step at a doorway", "Too tight to turn"}
SCANS = ("<scan-id>", "<scan-id>", "<scan-id>")  # three houses with measured walls and doorways


def matters(f) -> bool:
    return prefs.kind(f.tool, f.title)[1] not in WAVES_OFF and f.tool not in REMOVES


def answer(q):
    """The person's answer: their own fact, else the value on offer, else the first choice."""
    if q.key in ANSWERS:
        return ANSWERS[q.key]
    if q.answer is not None:
        return q.answer
    if "default" in q.input:
        return q.input["default"]
    if q.input.get("enum"):
        return q.input["enum"][0]
    raise RuntimeError(f"the person has no answer for {q.key}: {q.text}")


def visit(n: int, sid: str, root: pathlib.Path, who: str) -> dict:
    s = attach(Session.create(who, root=root))
    t0 = time.time()
    out = turn(s, FIRST if n == 0 else LATER, [sid], budget=Budget(tool_runs=12))
    asked = []
    for _ in range(6):
        open_qs = [q for q in s.doc.questions if not q.answered]
        if not open_qs:
            break
        for q in open_qs:
            approval = q.key.startswith("approval.")
            asked += [] if approval else [q.text]
            s.submit(QuestionAnswer(id=q.id, value=SKIP if approval else answer(q)), by="user")  # slow steps are skipped
        out = turn(s, budget=Budget(tool_runs=12))
    wall = time.time() - t0
    # the person reads the checks: what is on screen before they touch anything
    seen = [f for f in s.doc.findings if not f.superseded_by]
    worth = sum(1 for f in seen if matters(f))
    liked = 0
    for f in seen:
        if prefs.kind(f.tool, f.title)[1] in LIKES and liked < 3:
            s.submit({"op": "finding.add", "finding": {**f.model_dump(), "feedback": {"verdict": "confirmed"}}}, by="user")
            liked += 1
    hidden_now = 0
    for head in sorted(WAVES_OFF):
        f = next((f for f in s.doc.findings if prefs.kind(f.tool, f.title)[1] == head and not f.feedback and not f.superseded_by), None)
        if f:
            entries = s.submit({"op": "finding.add", "finding": {**f.model_dump(), "feedback": {
                "verdict": "rejected", "reason": prefs.NOT_RELEVANT}}}, by="user")
            hidden_now += sum(1 for e in entries[1:] if e.op.op == "finding.add")
    removed = next((t.id for t in s.doc.tools if t.enabled and t.id in REMOVES), None) if n == 0 else None
    if removed:
        s.submit({"op": "tool.disable", "tool": removed, "reason": "not what I am here for"}, by="user")
    m = profile.measure(s.doc, s.log)
    m.pop("started")
    m.update(visit=n + 1, scan=sid, status=out.get("status"), questions=asked, turn_s=round(wall, 1),
             tools=[t.id for t in s.doc.tools if t.enabled or t.id == removed], removed=removed,
             checks_that_matter=worth, share_that_matter=round(worth / len(seen), 2) if seen else None,
             similar_hidden_by_one_click=hidden_now,
             because=[f"{x['text']} ({x['why']})" for x in profile.because(s.doc, s.log)["notes"] if x["kind"] != "first"])
    print(f"visit {n + 1} on {sid}: {m['questions_asked']} questions, {m['tool_runs']} tool runs, first result after "
          f"{m['first_result_s']} s, {worth} of {len(seen)} checks matter to the person", flush=True)
    return m


ROWS = [("questions_asked", "Questions asked"), ("questions_not_asked", "Questions the profile answered"),
        ("inputs_from_profile", "Tool inputs filled from the profile"), ("tool_runs", "Tool runs"),
        ("first_result_s", "Seconds to the first result"), ("checks_shown", "Checks shown"),
        ("checks_that_matter", "Checks that matter to this person"), ("share_that_matter", "Share that matter"),
        ("checks_kept_back", "Checks kept back as not relevant"), ("marked_useful", "Marked useful by the person"),
        ("marked_not_relevant", "Marked not relevant by the person")]


def report(visits: list[dict], who: str, root: pathlib.Path) -> str:
    head = "| | " + " | ".join(f"Visit {v['visit']}" for v in visits) + " |"
    lines = ["# Adaptation evaluation", "",
             f"Run {time.strftime('%Y-%m-%d %H:%M')}. One scripted wheelchair user (profile `{who}`), three investigations on "
             "three houses, through the real composer and the real agent. Every figure is counted from the op logs by "
             "`threshold.agent.profile.measure`; no model wrote one.", "",
             f"First brief: \"{FIRST}\"", f"Later briefs: \"{LATER}\"", "",
             head, "|---|" + "---|" * len(visits)]
    lines += [f"| {text} | " + " | ".join("n/a" if v[k] is None else str(v[k]) for v in visits) + " |" for k, text in ROWS]
    lines += ["", "The person's rule for what matters was fixed before the run: a check matters unless it is a kind they "
              f"wave off ({', '.join(sorted(WAVES_OFF))}) or comes from a tool they removed. Slow steps that ask for approval "
              "were skipped. Seconds include the model's own latency, which varies run to run.", ""]
    for v in visits:
        lines += [f"## Visit {v['visit']}: scan {v['scan']}", "",
                  f"Tools: {', '.join(v['tools'])}." + (f" The person removed {v['removed']}." if v["removed"] else ""),
                  "Questions: " + ("; ".join(v["questions"]) if v["questions"] else "none") + ".",
                  f"One \"not relevant\" click hid {v['similar_hidden_by_one_click']} similar checks in this visit.", ""]
        lines += ["What it did because of the profile:", *[f"- {b}" for b in v["because"]], ""] if v["because"] else []
    lines += [f"Workspaces of this run: `{root}`.", ""]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scans", default=",".join(SCANS))
    ap.add_argument("--out", default=str(DATA / "reports"))
    a = ap.parse_args()
    out = pathlib.Path(a.out)
    who = f"eval_{time.strftime('%m%d_%H%M%S')}"
    root = out / "adaptation-eval" / who
    root.mkdir(parents=True, exist_ok=True)
    visits = [visit(i, sid, root, who) for i, sid in enumerate(a.scans.split(","))]
    (out / "adaptation-eval.json").write_text(json.dumps({"profile": who, "first": FIRST, "later": LATER, "visits": visits}, indent=1))
    (out / "adaptation-eval.md").write_text(report(visits, who, root))
    print(f"wrote {out / 'adaptation-eval.md'}")


if __name__ == "__main__":
    main()
