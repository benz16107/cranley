"""One received message to one action. Every chat runs in its own workspace, the same kind the web app opens, so the
desktop shows what the chat did as it happens. A native reply to an earlier answer goes back to that answer's workspace.

What a message can be:
  words           a question about a building: the composer and the investigator answer (core.ask)
  a reply         to an answer: a follow-up in that answer's workspace; to a question: its answer
  "yes"/"no"      to an approval the agent asked for (a smoke simulation, a vision read)
  a photo         settles the current site check, or measures a doorway (photo_measure), or checks a ceiling for a smoke alarm
  a video         a walkthrough
  a voice note    transcribed, then treated as words
  commands        help, new, visit, report, voice on/off
"""
from __future__ import annotations

import contextlib
import logging
import re
import threading
import time
from typing import Any

from . import card, client, speech, words
from .state import State

log = logging.getLogger("threshold.photon")
VISIT_KINDS = ("width", "step", "alarm")          # what a person can settle by text or photo
ALARM_WORDS = re.compile(r"\b(alarm|smoke|detector|ceiling)\b", re.IGNORECASE)
COMMAND = re.compile(r"^\s*(help|hi|hello|hey|start|/start|new|start over|reset|visit|on site|report|pdf|voice on|voice off|stop visit|alerts on|alerts off)\s*[.!?]*\s*$", re.IGNORECASE)
REFUSED = ("SHARED_LINE_INBOUND_REQUIRED", "SPACE_NOT_SENDABLE")
NAME = re.compile(r"\bcranley\b", re.I)
FEEDBACK = re.compile(r"^\s*(👍|👎|❤️|❤|♥️|save|shortlist|not useful|wrong)\s*$", re.I)
_state: State | None = None


def state() -> State:
    global _state
    if _state is None:
        _state = State()
    return _state


class Chat:
    """Where replies go: one Space, as the agent user that received the message."""

    def __init__(self, space: str, agent: str, platform: str, parent: str | None = None, api=client, st: State | None = None):
        self.space, self.agent, self.platform, self.parent, self.api, self.st = space, agent, platform, parent, api, st

    def say(self, text: str, reply: bool = True) -> str:
        try:
            return self.api.text(self.space, self.agent, text, self.parent if reply else None)
        except client.PhotonError as e:
            # a shared iMessage line may refuse a late send; the words wait for the person's next message
            if e.code not in REFUSED or self.st is None:
                raise
            t = self.st.thread(self.space)
            self.st.update(self.space, pending=[*t.get("pending", []), text][-5:])
            log.info("photon: %s refused (%s); kept for the next message", self.space, e.code)
            return ""

    def image(self, png: bytes, name: str = "cranley.png", caption: str | None = None) -> str:
        return self.api.attachment(self.space, self.agent, png, "image/png", name, self.parent,
                                   caption if self.platform == "telegram" else None)

    def file(self, data: bytes, content_type: str, name: str) -> str:
        return self.api.attachment(self.space, self.agent, data, content_type, name, self.parent)

    @contextlib.contextmanager
    def typing(self):
        """Typing dots while work runs, refreshed every few seconds. Where a channel has none, nothing happens."""
        stop = threading.Event()

        def beat():
            while not stop.is_set():
                try:
                    self.api.typing(self.space, self.agent, True)
                except Exception:  # noqa: BLE001 - OPERATION_UNAVAILABLE on channels without typing
                    return
                stop.wait(4)
        th = threading.Thread(target=beat, daemon=True)
        th.start()
        try:
            yield
        finally:
            stop.set()
            with contextlib.suppress(Exception):
                self.api.typing(self.space, self.agent, False)


# ---- workspaces ----

def session(ws: str | None):
    from ..api import agent as api
    if ws:
        try:
            return api.session(ws)
        except Exception:  # noqa: BLE001 - a workspace that no longer exists: start a fresh one
            pass
    from ..agent.investigator import attach
    from ..agent.workspace import Session
    s = attach(Session.create("default"))
    with api._lock:
        api._sessions[s.base.id] = s
    return s


def link(ws: str) -> str | None:
    from ..config import env
    base = env().get("PHOTON_APP_URL")
    return f"{base.rstrip('/')}/app/investigations/{ws}" if base else None


def open_questions(s) -> list[dict]:
    return [q.model_dump(mode="json") for q in s.doc.questions if not q.answered]


# ---- entry ----

def handle(event: dict, st: State | None = None, api=client) -> None:
    """A Photon event, verified and forwarded by the webhook service."""
    st = st or state()
    kind = event.get("type")
    if kind == "call.ended":
        from . import voice
        voice.after_call(event, st, api)
        return
    if kind != "message.received":
        return
    m = (event.get("data") or {}).get("object") or {}
    sender = m.get("sentBy") or {}
    if not m.get("id") or sender.get("kind") == "agent" or not st.first_time(m["id"]):
        return
    from ..config import env
    allow = [h.strip() for h in env().get("PHOTON_ALLOW", "").split(",") if h.strip()]
    if allow and sender.get("handle") not in allow:  # during testing: only people the lead cleared get answers
        log.info("photon: %s is not on PHOTON_ALLOW; not answering", sender.get("handle"))
        return
    space, agent = m["space"]["id"], (m.get("receivedBy") or {}).get("id")
    t = st.update(space, handle=sender.get("handle"), platform=m.get("platform"), agent=agent, touched=time.time())
    chat = Chat(space, agent, m.get("platform", ""), m["id"], api, st)
    waiting = t.get("pending") or []
    if waiting:
        st.update(space, pending=[])
        for text in waiting:
            chat.say("Earlier answer, sent now:\n" + text, reply=False)
    try:
        route(m, t, chat, st)
    except Exception as e:
        log.exception("photon message %s failed", m["id"])
        with contextlib.suppress(Exception):
            chat.say(f"Something broke on my side ({type(e).__name__}). Try again in a minute.")


def parts(content: dict) -> list[dict]:
    return content.get("parts") if content.get("type") == "group" else [content]


def route(m: dict, t: dict, chat: Chat, st: State) -> None:
    ps = parts(m.get("content") or {})
    text = " ".join(p["text"] for p in ps if p.get("type") == "text" and p.get("text")).strip()
    atts = [p if p.get("type") == "attachment" else {**p, "metadata": {**(p.get("metadata") or {}), "voice": True}}
            for p in ps if p.get("type") in ("attachment", "voice")]  # Telegram voice notes arrive as `voice`
    replied = st.answer(chat.space, m.get("parentMessageId"))
    ws = (replied or {}).get("workspace") or t.get("workspace")
    if (m.get("space") or {}).get("kind") == "group" and not (replied or COMMAND.match(text) or NAME.search(text)):
        return  # in a group chat, Cranley speaks when spoken to: its name, a reply to it, or a command
    if replied and FEEDBACK.match(text):
        feedback(chat, st, replied, text.strip())
        return

    for a in atts:
        ct, data = chat.api.download(a["attachmentId"])
        caption = ((a.get("metadata") or {}).get("caption") or text or "").strip()
        if ct.startswith("audio/") or (a.get("metadata") or {}).get("voice"):
            heard = speech.transcribe(data, ct or "audio/mp4")
            if not heard:
                chat.say("I couldn't make out that voice note. Try again, or type it.")
                return
            chat.say(f"Heard: \"{heard}\"")
            text = heard
            continue
        if ct.startswith(("image/", "video/")):
            media(chat, st, t, ws, data, ct, caption)
            return
        if "vcard" in ct or "vcf" in ct or "text/" in ct:  # "Send My Current Location" is a vCard with a Maps link
            text = (text + " " + data[:20000].decode("utf-8", "ignore")).strip()
            continue
        chat.say("I read photos, videos, voice notes and locations. For anything else, tell me in words.")
        return

    if not text:
        return
    c = COMMAND.match(text)
    if c:
        command(c.group(1).lower(), chat, st, t, ws)
        return
    pt = location(text)
    if pt:
        near(chat, st, ws, *pt)
        return
    s = session(ws)
    st.update(chat.space, workspace=s.base.id)
    if t.get("visit") and visit_reading(chat, st, t, s, text):
        return
    qs = open_questions(s)
    if qs:
        answer(chat, st, s, qs, text)
        return
    ask(chat, st, s, text)


def command(cmd: str, chat: Chat, st: State, t: dict, ws: str | None) -> None:
    if cmd in ("help", "hi", "hello", "hey", "start", "/start"):
        chat.say(words.HELP)
    elif cmd in ("new", "start over", "reset"):
        st.update(chat.space, workspace=None, visit=None)
        chat.say("Starting fresh. What do you need from a building?")
    elif cmd in ("voice on", "voice off"):
        st.update(chat.space, voice=cmd == "voice on")
        chat.say("I'll send each answer as a voice message too." if cmd == "voice on" else "Text only from now on.")
    elif cmd in ("report", "pdf"):
        report(chat, st, ws)
    elif cmd in ("visit", "on site"):
        visit_start(chat, st, ws)
    elif cmd in ("alerts on", "alerts off"):
        st.update(chat.space, alerts=cmd == "alerts on")
        chat.say("I'll text you weather alerts for the building we last talked about." if cmd == "alerts on"
                 else "No more alerts.")
    elif cmd == "stop visit":
        st.update(chat.space, visit=None)
        chat.say("Visit stopped. The checks you settled are saved in the workspace.")


# ---- feedback by reply: Beta delivers no tapbacks, so a reply of an emoji on an answer is the vote ----

def feedback(chat: Chat, st: State, replied: dict, text: str) -> None:
    from ..agent.workspace import PrefSet, ShortlistAdd
    s = session(replied["workspace"])
    runs = {r.id: r for r in s.doc.runs}
    rid = replied.get("run") or next(iter(replied.get("runs") or []), None)
    run = runs.get(rid)
    sid = replied.get("sid") or (run.sid if run else None)
    if text.lower() in ("👎", "not useful", "wrong"):
        if not run:
            chat.say("Noted.")
            return
        s.submit(PrefSet(key=f"tool.off.{run.tool}", value=True, reason="Thumbs down on its answer in the chat"), by="user")
        chat.say(f"Noted: I'll leave {words.title(run.tool)} out of this conversation from now on.")
        return
    if not sid:
        chat.say("Noted.")
        return
    if sid not in s.doc.shortlist:
        s.submit(ShortlistAdd(sid=sid, note=f"Liked in the chat ({text})"), by="user")
    names = [words.place_name(x) for x in s.doc.shortlist]
    chat.say(f"Saved {words.place_name(sid)} to your shortlist ({len(names)}): " + "; ".join(names))


# ---- a shared location ----

LOC = re.compile(r"(?:[?&](?:ll|q|sll)=|@)(-?\d{1,2}\.\d{3,}),\s*(-?\d{1,3}\.\d{3,})")


def location(text: str) -> tuple[float, float] | None:
    """Coordinates from an Apple or Google Maps link (a shared location, or a pasted link)."""
    m = LOC.search(text)
    return (float(m.group(1)), float(m.group(2))) if m else None


def nearest(lat: float, lon: float) -> tuple[str, float] | None:
    """The scanned building closest to a point, and how far it is in metres."""
    import math
    from ..sources import index
    best = None
    for sid, r in index.rows().items():
        try:
            la, lo = float(r["lat"]), float(r["lon"])
        except (KeyError, ValueError):
            continue
        d = 6371000 * 2 * math.asin(math.sqrt(math.sin(math.radians(la - lat) / 2) ** 2 + math.cos(math.radians(lat))
                                              * math.cos(math.radians(la)) * math.sin(math.radians(lo - lon) / 2) ** 2))
        if best is None or d < best[1]:
            best = (sid, d)
    return best


def near(chat: Chat, st: State, ws: str | None, lat: float, lon: float) -> None:
    from ..agent.workspace import BriefSet, Scope
    hit = nearest(lat, lon)
    if not hit:
        chat.say("I have no scanned buildings to compare that location with.")
        return
    sid, d = hit
    if d > 5000:
        chat.say(f"The nearest building I have scanned is {d / 1000:.0f} km away ({words.place_name(sid)}). I cover parts "
                 "of Houston and Los Angeles.")
        return
    s = session(None)  # a new place is a new workspace; the old one stays where it was
    s.submit(BriefSet(scope=Scope(sids=[sid])), by="user")
    st.update(chat.space, workspace=s.base.id, visit=None)
    dist = f"{d:.0f} m" if d < 1000 else f"{d / 1000:.1f} km"
    msg = chat.say(f"The nearest scanned building is {words.place_name(sid)}, {dist} from you. What do you need to know "
                   "about it? (Will something fit, can a wheelchair get around, how it floods.)")
    st.remember(chat.space, msg, s.base.id, sid=sid)


# ---- asking ----

def ask(chat: Chat, st: State, s, text: str | None) -> None:
    from ..mcp import core
    with chat.typing():
        out = core.ask(text or "", workspace_id=s.base.id)
    deliver(chat, st, s, out)


def answer(chat: Chat, st: State, s, qs: list[dict], text: str) -> None:
    """The reply answers the first open question; then the turn carries on."""
    from ..agent.workspace import QuestionAnswer
    q = qs[0]
    try:
        v = words.parse_answer(q, text)
    except words.Unclear as e:
        chat.say(f"{e} ({q['text']})")
        return
    s.submit(QuestionAnswer(id=q["id"], value=v), by="user")
    if len(qs) > 1:
        msg = chat.say(words.question_text(qs[1]))
        st.remember(chat.space, msg, s.base.id, question=qs[1]["id"])
        return
    ask(chat, st, s, None)


def deliver(chat: Chat, st: State, s, out: dict) -> None:
    """The turn's outcome as messages: questions, approvals, or the answer with its picture and voice."""
    status = out.get("status")
    if status in ("questions", "approval"):
        qs = open_questions(s)
        if qs:
            lead = "Before I run the checks:" if status == "questions" else "This step is slow or reads photos, so I'm asking first:"
            msg = chat.say(lead + "\n" + words.question_text(qs[0]))
            st.remember(chat.space, msg, s.base.id, question=qs[0]["id"])
            return
    if status == "needs_scope":
        chat.say("Which building, city or address? Or tell me what you're looking for and where.")
        return
    ids = {r["id"] for r in out.get("runs") or []}
    runs = [r.model_dump(mode="json") for r in s.doc.runs if r.id in ids]
    answer_runs(chat, st, s, runs, out.get("note"))


def primary(runs: list[dict]) -> dict | None:
    """The run worth a picture: a finished one on a scan with findings, failures first."""
    done = [r for r in runs if r.get("status") == "done" and r.get("result") and r.get("sid")]
    order = {"fail": 0, "warn": 1, "pass": 2, "unknown": 3}
    return min(done, key=lambda r: (order.get(r["result"]["verdict"]["status"], 4), -len(r["result"].get("findings") or [])),
               default=None)


def answer_runs(chat: Chat, st: State, s, runs: list[dict], note: str | None = None) -> None:
    from ..tools.registry import default_plan
    text = words.done_text(runs, note, link(s.base.id))
    pick = primary(runs)
    if pick:
        try:
            plan = (s.plans or default_plan)(pick["sid"])
            png = card.card(pick, plan)
            msg = chat.image(png, caption=None)
            st.remember(chat.space, msg, s.base.id, run=pick["id"], sid=pick["sid"])
            set_background(chat, st, pick, plan)
        except Exception:
            log.exception("card for %s", pick["id"])
    msg = chat.say(text)
    st.remember(chat.space, msg, s.base.id, runs=[r["id"] for r in runs][:10])
    if st.thread(chat.space).get("voice"):
        speak(chat, text)


def speak(chat: Chat, text: str) -> None:
    try:
        chat.api.voice(chat.space, chat.agent, speech.speak(words.speakable(text)))
    except Exception:
        log.exception("voice answer")


def set_background(chat: Chat, st: State, run: dict, plan: dict) -> None:
    """iMessage: the chat's background becomes the plan of the building being discussed, once per building."""
    t = st.thread(chat.space)
    if chat.platform != "imessage" or t.get("background_sid") == run["sid"]:
        return
    try:
        chat.api.background(chat.space, chat.agent, card.background(plan, run["result"]))
        st.update(chat.space, background_sid=run["sid"])
    except Exception as e:  # noqa: BLE001 - a shared line may refuse; the answer matters, not the wallpaper
        log.info("background refused: %s", e)
        st.update(chat.space, background_sid=run["sid"])


# ---- photos and videos ----

def to_jpeg(data: bytes, ct: str) -> bytes:
    """HEIC from an iPhone becomes JPEG (Pillow here cannot read HEIC); other images pass through."""
    if "heic" not in ct and "heif" not in ct and data[4:12] not in (b"ftypheic", b"ftypheix", b"ftypmif1", b"ftyphevc"):
        return data
    import subprocess
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        src, out = Path(d) / "in.heic", Path(d) / "out.jpg"
        src.write_bytes(data)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(src), str(out)], check=True, timeout=60)
        return out.read_bytes()


def media(chat: Chat, st: State, t: dict, ws: str | None, data: bytes, ct: str, caption: str) -> None:
    from ..capture import apply, store
    s = session(ws)
    st.update(chat.space, workspace=s.base.id)
    task = current_task(s, t)
    is_video = ct.startswith("video/")
    if not is_video:
        data = to_jpeg(data, ct)
    meta: dict[str, Any] = {"kind": "video" if is_video else "photo", "note": caption[:2000] or None}
    if is_video:
        meta["tool"] = "walkthrough"
    elif task:
        meta.update(task=task["id"], scan=task["sid"], room=task.get("room"), opening=task.get("opening"))
    elif ALARM_WORDS.search(caption):
        return alarm_photo(chat, s, data, caption)
    else:
        meta.update(tool="photo_measure", values={"what": caption or "the clear width of the doorway", "reference": "card"})
    with chat.typing():
        try:
            cap = store.save(s.base.id, store.Meta.model_validate(meta), data)
        except store.Rejected as e:
            chat.say(str(e))
            return
        did = apply.handle(s, cap)
    if task:
        return visit_outcome(chat, st, t, s, task, did)
    if did.get("problem"):
        hint = "" if is_video else " Put a bank card flat against the door frame, stand square on, and send it again."
        chat.say(did["problem"] + hint)
        return
    run = next((r.model_dump(mode="json") for r in s.doc.runs if r.id == did.get("run")), None)
    answer_runs(chat, st, s, [run] if run else [])


def alarm_photo(chat: Chat, s, data: bytes, caption: str) -> None:
    from ..capture import apply, store
    with chat.typing():
        cap = store.save(s.base.id, store.Meta(kind="photo", note=caption[:2000] or None), data)
        apply.note(s, cap)
        seen = apply.alarm_in_photo(cap["id"])
    if not seen.get("ceiling_visible"):
        chat.say("I can't see enough of the ceiling to tell. Step back and photograph the whole ceiling.")
    elif seen.get("smoke_alarm_visible"):
        chat.say(f"I see a smoke alarm ({seen.get('confidence')} confidence): {seen.get('what')}. Press its test button "
                 "to be sure it works.")
    else:
        chat.say(f"I don't see a smoke alarm on this ceiling ({seen.get('confidence')} confidence): {seen.get('what')}.")


# ---- site visits, one check at a time ----

def site_tasks(s) -> list[dict]:
    from ..capture import apply
    return [x for x in apply.phone_tasks(s) if x["kind"] in VISIT_KINDS and x["status"] != "done"]


def current_task(s, t: dict) -> dict | None:
    v = t.get("visit") or {}
    return next((x for x in site_tasks(s) if x["id"] == v.get("task")), None) if v else None


def visit_start(chat: Chat, st: State, ws: str | None) -> None:
    if not ws:
        chat.say("Ask me about a building first. When a check needs someone on site, say \"visit\" and I'll walk you "
                 "through it.")
        return
    s = session(ws)
    todo = site_tasks(s)
    if not todo:
        chat.say("Nothing here needs checking on site: every check settled from the scan.")
        return
    chat.say(f"{len(todo)} checks need someone on site. I'll send them one at a time; reply with a measurement or a "
             "photo. Say \"stop visit\" to stop.", reply=False)
    next_task(chat, st, s, todo[0])


def next_task(chat: Chat, st: State, s, task: dict) -> None:
    st.update(chat.space, visit={"task": task["id"]})
    msg = chat.say(f"{task['title']}\n{task['how']}", reply=False)
    st.remember(chat.space, msg, s.base.id, task=task["id"])


def visit_reading(chat: Chat, st: State, t: dict, s, text: str) -> bool:
    """A typed reading for the current site check. False when the text is not one (it is then a question)."""
    from ..agent.composer import SIZE, TO_M
    from ..capture import apply, store
    task = current_task(s, t)
    if not task or len(text.split()) > 8 or "?" in text:  # a question that mentions a size is still a question
        return False
    values: dict[str, Any] = {}
    if task["kind"] == "alarm":
        if re.search(r"\b(no|none|nothing|missing|absent)\b", text, re.IGNORECASE):
            values["answer"] = "absent"
        elif re.search(r"\b(yes|there is|present|got one|found)\b", text, re.IGNORECASE):
            values["answer"] = "present"
    else:
        hits = SIZE.findall(text)
        if len(hits) == 1:
            values["value_m"] = round(float(hits[0][0]) * TO_M[hits[0][1].lower()], 4)
    if not values:
        return False
    with chat.typing():
        cap = store.save(s.base.id, store.Meta(kind="reading", task=task["id"], scan=task["sid"], room=task.get("room"),
                                               opening=task.get("opening"), values=values))
        did = apply.handle(s, cap)
    visit_outcome(chat, st, t, s, task, did)
    return True


def visit_outcome(chat: Chat, st: State, t: dict, s, task: dict, did: dict) -> None:
    if did.get("problem"):
        chat.say(did["problem"])
        return
    o = did.get("outcome") or {}
    line = o.get("text") or f"Settled: {o.get('verdict', 'done')}."
    rest = site_tasks(s)
    if rest:
        chat.say(f"{line} ({len(rest)} to go.)")
        next_task(chat, st, s, rest[0])
    else:
        st.update(chat.space, visit=None)
        tail = f"\nFull view: {link(s.base.id)}" if link(s.base.id) else ""
        chat.say(f"{line}\nThat was the last check. Say \"report\" for the PDF.{tail}")


# ---- report ----

def report(chat: Chat, st: State, ws: str | None) -> None:
    if not ws:
        chat.say("There's nothing to report yet. Ask me about a building first.")
        return
    from ..api.report import _report
    from ..report import pdf
    with chat.typing():
        _, page = _report(ws, None, None)
        data = pdf.from_html(page)
    chat.file(data, "application/pdf", "cranley-report.pdf")
    chat.say("Here's the report, ready to forward. It lists what was measured, what fails, and what was not checked.")
