"""The phone line: an ElevenLabs agent answers calls to the Photon number over SIP and calls these tools. A check runs
in the caller's own workspace (the same one their texts use, found by their number), so the call and the chat are one
conversation. When Photon reports call.ended, the caller gets the answer by text: the card, the lines and the link.

Tools (POST /voice/tool/<name> on the webhook service, forwarded here):
  start_check {question, caller_id}   starts a turn in the background; answers at once
  get_answer  {caller_id}             waits up to WAIT_S for that turn; returns `say`, lines built from tool results
  answer_question {answer, caller_id} the caller's answer to a question the check asked
The agent is told to read `say` as written: the numbers in it come from the calculation (rule 5)."""
from __future__ import annotations

import concurrent.futures
import logging
import threading
import time

from . import client, words
from .state import State

log = logging.getLogger("threshold.photon")
WAIT_S = 50  # a turn takes about a minute; one or two polls, under the relay's 65 s and ElevenLabs' 60 s
_pool = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="voice")
_jobs: dict[str, concurrent.futures.Future] = {}
_lock = threading.Lock()


def _st() -> State:
    from .router import state
    return state()


def _norm(n: str | None) -> str:
    d = "".join(c for c in (n or "") if c.isdigit())
    return f"+{d}" if len(d) > 10 else (f"+1{d}" if len(d) == 10 else (n or "unknown"))


def _call(caller: str) -> dict:
    """The caller's record: their workspace, carried over from their text thread when they have one."""
    st = _st()
    calls = st.data["calls"]
    rec = calls.get(caller)
    if not rec:
        hit = st.by_handle(caller)
        rec = calls[caller] = {"workspace": hit[1].get("workspace") if hit else None, "runs": [], "started": time.time()}
        st.save()
    return rec


def _turn(caller: str, text: str | None) -> dict:
    from ..mcp import core
    from .router import open_questions, session
    rec = _call(caller)
    # a new question gets a fresh workspace (a composed one starts no new tools); an answer continues the open one
    s = session(None if text else rec.get("workspace"))
    rec["workspace"] = s.base.id
    words.scope_named(s, text)
    out = core.ask(text or "", workspace_id=s.base.id)
    rec["runs"] = list(dict.fromkeys([*rec["runs"], *[r["id"] for r in out.get("runs") or []]]))[-10:]
    rec["questions"] = open_questions(s)[:1]
    _st().save()
    return out


def _start(caller: str, text: str | None) -> None:
    with _lock:
        _jobs[caller] = _pool.submit(_turn, caller, text)


def spoken(caller: str, out: dict) -> str:
    """What the agent reads: the open question, or each run's verdict and first metric, from the results."""
    from .router import session
    rec = _call(caller)
    if rec.get("questions"):
        q = rec["questions"][0]
        return "The check needs one thing first. " + words.question_text(q).split("\n")[0]
    s = session(rec["workspace"])
    ids = {r["id"] for r in out.get("runs") or []}
    runs = [r.model_dump(mode="json") for r in s.doc.runs if r.id in ids]
    if not runs:
        return "I couldn't run a check for that. Try naming the city or the street address."
    lines_head = f"At {words.place_name(runs[0].get('sid'))}." if runs[0].get("sid") else ""
    lines = []
    for r in runs[:2]:
        res = r.get("result") or {}
        v = res.get("verdict") or {}
        m = (res.get("metrics") or [])[:1]
        said = f"{words.title(r['tool'])}: {words.STATUS_WORD.get(v.get('status'), '')}. {v.get('text', '')}"
        if m and not any(ch.isdigit() for ch in v.get("text", "")):  # a verdict with no number gets its first metric
            said += f" {words.metric_line(m[0]).split(' (')[0]}."
        lines.append(said)
    if len(runs) > 2:
        lines.append(f"And {len(runs) - 2} more checks.")
    return words.speakable("\n".join([lines_head, *lines])) + " I'll text you the plan and the details when we hang up."


def tool(name: str, body: dict) -> dict:
    caller = _norm(body.get("caller_id") or body.get("system__caller_id"))
    if name == "start_check":
        q = (body.get("question") or "").strip()
        if not q:
            return {"say": "What would you like me to check?"}
        _start(caller, q)
        return {"say": "Checking now. It takes about half a minute.", "status": "running"}
    if name == "answer_question":
        rec = _call(caller)
        if not rec.get("questions"):
            return {"say": "There's no open question."}
        from ..agent.workspace import QuestionAnswer
        from .router import session
        q = rec["questions"][0]
        try:
            v = words.parse_answer(q, str(body.get("answer") or ""))
        except words.Unclear as e:
            return {"say": str(e)}
        session(rec["workspace"]).submit(QuestionAnswer(id=q["id"], value=v), by="user")
        rec["questions"] = []
        _start(caller, None)
        return {"say": "Got it. Running the check.", "status": "running"}
    if name == "get_answer":
        job = _jobs.get(caller)
        if not job:
            return {"say": "Nothing is running. What should I check?", "status": "idle"}
        try:
            out = job.result(timeout=WAIT_S)
        except concurrent.futures.TimeoutError:
            return {"say": "Still working on it.", "status": "running"}
        except Exception as e:
            log.exception("voice turn")
            return {"say": f"The check failed on my side ({type(e).__name__}).", "status": "error"}
        return {"say": spoken(caller, out), "status": "done"}
    return {"say": "I can't do that one.", "status": "unknown_tool"}


def after_call(event: dict, st: State, api=client) -> None:
    """call.ended: text the caller what the call found, on the thread they already have with Cranley."""
    from .router import Chat, answer_runs, session
    o = (event.get("data") or {}).get("object") or {}
    caller = _norm((o.get("caller") or {}).get("handle"))
    if o.get("direction") not in (None, "inbound"):
        return
    rec = st.data["calls"].pop(caller, None)
    st.save()
    hit = st.by_handle(caller)
    if not rec or not rec.get("runs") or not hit:
        log.info("call ended for %s: nothing to text (%s)", caller, "no thread" if not hit else "no runs")
        return
    space, t = hit
    s = session(rec["workspace"])
    st.update(space, workspace=s.base.id)
    runs = [r.model_dump(mode="json") for r in s.doc.runs if r.id in set(rec["runs"])]
    chat = Chat(space, t["agent"], t.get("platform", "imessage"), None, api, st)
    chat.say("From our call just now:", reply=False)
    answer_runs(chat, st, s, runs)
