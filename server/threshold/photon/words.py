"""Every line Cranley sends, built from tool results and the workspace (rule 5: a number in a message comes from a
result's metric, check or verdict, never from model text). The model's own note is passed on only when it holds no
digits. Answers a person types are read here too, deterministically."""
from __future__ import annotations

import re
from typing import Any

from ..agent.composer import SIZE, TO_M
from ..report import value

STATUS_WORD = {"pass": "Yes", "warn": "Maybe", "fail": "No", "unknown": "Can't tell"}
MAX_RUNS = 4
YES = re.compile(r"^\s*(y|yes|yeah|yep|sure|ok|okay|go|go ahead|do it|approve|run it|👍)\b", re.IGNORECASE)
NO = re.compile(r"^\s*(n|no|nope|skip|don'?t|stop|cancel|👎)\b", re.IGNORECASE)

HELP = ("I'm Cranley. Ask me about a real building in plain words, for example:\n"
        "• \"Will an F-150 fit in the garage of a house in Houston?\"\n"
        "• \"I use a 70 cm wheelchair, find me a one-bedroom in Los Angeles I can get around\"\n"
        "Send a photo of a doorway with a bank card in it and I'll measure it. A photo of a ceiling: I'll check for a "
        "smoke alarm. A short video: I'll walk through it. A voice note works like a text.\n"
        "Reply to any answer to follow up on it. Say \"visit\" on site and I'll give you checks one at a time, "
        "\"report\" for a PDF, \"voice on\" to hear answers, \"new\" to start over.")


def title(tool: str) -> str:
    from ..agent.catalog import catalog
    m = catalog().get(tool)
    return m.title if m else tool.replace("_", " ")


def place_name(sid: str | None) -> str:
    """The building as a person would say it: its index address or name; never the scan id."""
    if not sid:
        return "the area"
    try:
        from ..sources import index
        row = index.rows().get(sid) or {}
    except Exception:  # noqa: BLE001 - a name is a nicety
        row = {}
    return row.get("address") or row.get("name") or (user_scans().get(sid) or {}).get("name") or "this building"


def user_scans() -> dict[str, dict]:
    """Scans people uploaded (iPhone RoomPlan, or the hand-made test home and cafe): sid -> meta."""
    import json
    from ..config import DATA
    out = {}
    for f in (DATA / "user_scans").glob("u_*/meta.json"):
        try:
            out[f.parent.name] = json.loads(f.read_text())
        except ValueError:
            continue
    return out


TEST_NAMES = {r"\b(sample|test|demo) (home|house)\b": "sample home", r"\b(test|sample|demo) (cafe|café|coffee shop)\b": "test cafe"}


def named_scan(text: str | None) -> str | None:
    """The made-up test home or cafe when the person names it ("the sample home"); the search index only has real
    scans, so the agent could not find these by name. The newest upload of that name wins."""
    if not text:
        return None
    want = next((v for k, v in TEST_NAMES.items() if re.search(k, text, re.I)), None)
    if not want:
        return None
    hits = [(m.get("created", ""), sid) for sid, m in user_scans().items() if (m.get("name") or "").lower().startswith(want)]
    return max(hits)[1] if hits else None


def scope_named(s, text: str | None) -> None:
    """Point the workspace at the test home or cafe when the text names it."""
    sid = named_scan(text)
    if sid:
        from ..agent.workspace import BriefSet, Scope
        s.submit(BriefSet(scope=Scope(sids=[sid])), by="user")


def metric_line(m: dict) -> str:
    v = "not measured" if m["value"] is None else value(m["value"], m["unit"])
    return f"{m['label']}: {v} ({m['source']['confidence']} confidence)"


def run_lines(run: dict) -> list[str]:
    """One answer per run: the verdict word and its own text, then up to three metrics."""
    r = run.get("result") or {}
    v = r.get("verdict") or {}
    if not v:
        return [f"{title(run['tool'])}: {run.get('error') or run.get('status')}"]
    head = f"{STATUS_WORD.get(v['status'], v['status'])}. {v['text']}"
    out = [f"{title(run['tool'])} at {place_name(run.get('sid'))}" if run.get("sid") else title(run["tool"]), head]
    out += [metric_line(m) for m in (r.get("metrics") or [])[:3]]
    fails = [c for c in r.get("checks") or [] if c["status"] == "fail"][:2]
    out += [f"Fails: {c['rule']} (measured {value(c['measured'], c['unit'])}, needs {value(c['threshold'], c['unit'])})"
            for c in fails if c.get("measured") is not None and c.get("threshold") is not None]
    return out


def model_note(note: str | None) -> str | None:
    """The agent's note, only if it states no number (rule 5)."""
    return note.strip() if note and not re.search(r"\d", note) else None


def done_text(runs: list[dict], note: str | None, link: str | None) -> str:
    if not runs:
        body = ["I couldn't run a check for that. Try naming a city or an address, or what you need to fit."]
    else:
        body = []
        for r in runs[:MAX_RUNS]:
            body += run_lines(r) + [""]
        if len(runs) > MAX_RUNS:
            body.append(f"…and {len(runs) - MAX_RUNS} more checks in the full view.")
    n = model_note(note)
    if n:
        body.append(n)
    if link:
        body.append(f"Full view: {link}")
    body.append("Reply to this message to change anything.")
    return "\n".join(x for x in body).strip().replace("\n\n\n", "\n\n")


def question_text(q: dict) -> str:
    """A question the tools need answered, and how to answer it in a text."""
    inp = q.get("input") or {}
    if (inp.get("x-approval") or {}):
        return f"{q['text']}\nReply yes to go ahead, no to skip, or always."
    if q.get("answer") is not None:
        shown = value(q["answer"], inp.get("x-unit") or "") if isinstance(q["answer"], (int, float)) else q["answer"]
        return f"{q['text']} You said {shown}. Reply yes, or send the right value."
    if inp.get("enum"):
        return f"{q['text']} ({' / '.join(map(str, inp['enum']))})"
    if inp.get("type") == "boolean":
        return f"{q['text']} (yes or no)"
    if inp.get("x-unit") == "m":
        return f"{q['text']} (with a unit, like 76 cm or 30 in)"
    return q["text"]


class Unclear(ValueError):
    """The text does not answer the question; the message says what to send."""


def parse_answer(q: dict, text: str) -> Any:
    """The value a person's reply gives for a question, read from their own words."""
    inp = q.get("input") or {}
    t = text.strip()
    if inp.get("x-approval"):
        from ..agent.investigator import ALWAYS, RUN, SKIP
        if re.match(r"^\s*always\b", t, re.IGNORECASE):
            return ALWAYS
        if YES.match(t):
            return RUN
        if NO.match(t):
            return SKIP
        raise Unclear("Reply yes, no, or always.")
    if inp.get("type") == "boolean":
        if YES.match(t):
            return True
        if NO.match(t):
            return False
        raise Unclear("Reply yes or no.")
    if q.get("answer") is not None and YES.match(t):
        return q["answer"]
    if inp.get("enum"):
        hit = [o for o in inp["enum"] if str(o).lower() in t.lower()]
        if len(hit) == 1:
            return hit[0]
        raise Unclear("Reply with one of: " + ", ".join(map(str, inp["enum"])))
    if inp.get("type") in ("number", "integer"):
        if inp.get("x-unit") == "m":
            hits = SIZE.findall(t)
            if len(hits) != 1:
                raise Unclear("Send one size with its unit, like 76 cm or 30 in.")
            n, u = hits[0]
            v = round(float(n) * TO_M[u.lower()], 3)
        else:
            nums = re.findall(r"-?\d+(?:\.\d+)?", t)
            if len(nums) != 1:
                raise Unclear("Send one number.")
            v = float(nums[0])
        if inp.get("type") == "integer":
            v = round(v)
        lo, hi = inp.get("minimum"), inp.get("maximum")
        if (lo is not None and v < lo) or (hi is not None and v > hi):
            raise Unclear(f"That is outside what the check accepts ({lo} to {hi} {inp.get('x-unit') or ''}).".replace(" )", ")"))
        return v
    if not t:
        raise Unclear("Send a short answer.")
    return t


def speakable(text: str) -> str:
    """What the voice message says: the answer without the link and the reply hint."""
    keep = [l for l in text.splitlines() if l and not l.startswith(("Full view:", "Reply to this", "…and"))]
    s = " ".join(keep)
    s = s.replace("m²", " square metres").replace("ft²", " square feet").replace(" in)", " inches)").replace(" ft)", " feet)")
    return re.sub(r"\s+", " ", s)[:900]
