"""The Photon bridge without the network: signatures, answer parsing, rule 5 in replies, and routing with a fake API."""
from __future__ import annotations

import base64
import hashlib
import hmac
import time
from types import SimpleNamespace

import pytest

from threshold.photon import router, words
from threshold.photon.state import State
from threshold.photon.webhook import verify

SECRET = "whsec_" + base64.b64encode(b"k" * 32).decode()


def sign(body: bytes, mid="evt_1", ts=None):
    ts = str(int(ts or time.time()))
    sig = base64.b64encode(hmac.new(b"k" * 32, f"{mid}.{ts}.".encode() + body, hashlib.sha256).digest()).decode()
    return mid, ts, f"v1,{sig}"


def test_signature_accepts_good_and_rejects_tampered_or_stale():
    body = b'{"type":"message.received"}'
    mid, ts, sig = sign(body)
    assert verify(SECRET, mid, ts, body, sig)
    assert verify(SECRET, mid, ts, body, "v1,bogus " + sig)  # rotation: any matching signature
    assert not verify(SECRET, mid, ts, body + b" ", sig)
    assert not verify(SECRET, "evt_2", ts, body, sig)
    old = sign(body, ts=time.time() - 3600)
    assert not verify(SECRET, *old[:2], body, old[2])
    assert not verify(SECRET, mid, "nope", body, sig)


SIZE_Q = {"id": "q_chair", "text": "How wide is your wheelchair?", "input": {"type": "number", "x-unit": "m", "minimum": 0.3, "maximum": 1.5}}


def test_parse_sizes_from_the_persons_words():
    assert words.parse_answer(SIZE_Q, "it's 70 cm") == 0.7
    assert words.parse_answer(SIZE_Q, "28 in") == pytest.approx(0.711, abs=0.001)
    with pytest.raises(words.Unclear):
        words.parse_answer(SIZE_Q, "70")          # no unit: never guessed
    with pytest.raises(words.Unclear):
        words.parse_answer(SIZE_Q, "70 cm or 80 cm")
    with pytest.raises(words.Unclear):
        words.parse_answer(SIZE_Q, "5 m")         # outside what the tool accepts


def test_parse_approvals_and_prefilled_answers():
    from threshold.agent.investigator import ALWAYS, RUN, SKIP
    q = {"id": "approve:t", "text": "Smoke simulation?", "input": {"type": "string", "enum": [RUN, SKIP, ALWAYS], "x-approval": {"tool": "smoke_clock"}}}
    assert words.parse_answer(q, "yes please") == RUN
    assert words.parse_answer(q, "no") == SKIP
    assert words.parse_answer(q, "always") == ALWAYS
    pre = {**SIZE_Q, "answer": 0.76}
    assert words.parse_answer(pre, "yep") == 0.76
    assert words.parse_answer(pre, "actually 80 cm") == 0.8


def test_model_note_never_carries_a_number():
    assert words.model_note("The bathroom door is the problem.") == "The bathroom door is the problem."
    assert words.model_note("The door is 71 cm wide.") is None


def test_answer_lines_come_from_the_result():
    run = {"tool": "door_widths", "sid": None, "status": "done", "result": {
        "verdict": {"status": "fail", "text": "2 of 9 doorways are narrower than 0.81 m."},
        "metrics": [{"label": "Narrowest", "value": 0.71, "unit": "m", "source": {"confidence": "high"}}],
        "checks": [{"rule": "Bathroom door", "measured": 0.71, "threshold": 0.81, "unit": "m", "status": "fail"}]}}
    text = words.done_text([run], "Ask the landlord about 42.", None)
    assert "No. 2 of 9 doorways are narrower than 0.81 m." in text
    assert "0.71 m (28 in)" in text and "needs 0.81 m (32 in)" in text
    assert "42" not in text  # the model's note had a number, so it was dropped


class FakeAPI:
    def __init__(self):
        self.sent, self.n = [], 0

    def _id(self):
        self.n += 1
        return f"pho_msg_out{self.n}"

    def text(self, space, sender, words_, parent=None, idem=True):
        self.sent.append(("text", words_, parent))
        return self._id()

    def attachment(self, space, sender, data, ct, name, parent=None, caption=None):
        self.sent.append(("attachment", name, parent))
        return self._id()

    def typing(self, *a, **k):
        pass

    def background(self, *a, **k):
        self.sent.append(("background",))

    def voice(self, *a, **k):
        self.sent.append(("voice",))


def event(text, mid="pho_msg_in1", parent=None, kind="user"):
    return {"type": "message.received", "data": {"object": {
        "id": mid, "platform": "imessage", "parentMessageId": parent, "space": {"id": "pho_spc_1"},
        "sentBy": {"id": "pho_usr_p", "handle": "+15550001111", "kind": kind}, "receivedBy": {"id": "pho_usr_agent"},
        "content": {"type": "text", "format": "plain", "text": text}}}}


def test_help_dedupe_and_own_messages(tmp_path):
    st, api = State(tmp_path / "s.json"), FakeAPI()
    router.handle(event("hi"), st, api)
    router.handle(event("hi"), st, api)                       # Photon delivered it twice
    router.handle(event("hi", "pho_msg_in2", kind="agent"), st, api)  # our own message echoed back
    assert [s[0] for s in api.sent] == ["text"]
    assert api.sent[0][1].startswith("I'm Cranley") and api.sent[0][2] == "pho_msg_in1"  # a native reply
    assert st.thread("pho_spc_1")["handle"] == "+15550001111"


def test_a_reply_goes_back_to_that_answers_workspace(tmp_path, monkeypatch):
    st, api = State(tmp_path / "s.json"), FakeAPI()
    st.remember("pho_spc_1", "pho_msg_old", "ws_old")
    st.update("pho_spc_1", workspace="ws_new")
    seen = {}

    def fake_session(ws):
        seen["ws"] = ws
        return SimpleNamespace(base=SimpleNamespace(id=ws), doc=SimpleNamespace(questions=[], runs=[]), plans=None)
    monkeypatch.setattr(router, "session", fake_session)
    monkeypatch.setattr("threshold.mcp.core.ask", lambda brief, workspace_id=None: {"status": "done", "runs": [], "note": None})
    router.handle(event("what about a 76 cm chair?", "pho_msg_in3", parent="pho_msg_old"), st, api)
    assert seen["ws"] == "ws_old"
    assert st.thread("pho_spc_1")["workspace"] == "ws_old"
    assert api.sent[-1][0] == "text" and "couldn't run a check" in api.sent[-1][1]


def test_a_failure_tells_the_person(tmp_path, monkeypatch):
    st, api = State(tmp_path / "s.json"), FakeAPI()
    monkeypatch.setattr(router, "route", lambda *a: (_ for _ in ()).throw(RuntimeError("boom")))
    router.handle(event("anything", "pho_msg_in4"), st, api)
    assert "Something broke" in api.sent[-1][1]
