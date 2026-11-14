"""Capture files and pairing tokens: type and size checks, what a phone may learn, tokens that expire."""
import pytest

from threshold.capture import pair, store

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 64
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"0" * 64
WEBM = b"\x1a\x45\xdf\xa3" + b"0" * 64


@pytest.fixture(autouse=True)
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "ROOT", tmp_path / "captures")
    return tmp_path / "captures"


def test_a_photo_is_saved_and_read_back(root):
    rec = store.save("ws_a", store.Meta(kind="photo", scan="home", room="R", note="ceiling"), JPEG)
    assert rec["mime"] == "image/jpeg" and rec["bytes"] == len(JPEG) and store.read(rec["id"]) == JPEG
    assert store.get(rec["id"])["room"] == "R" and [c["id"] for c in store.listing("ws_a")] == [rec["id"]]
    assert "workspace" not in store.public(rec)                      # a paired phone never learns the workspace id
    assert store.listing("ws_b") == []
    assert store.update(rec["id"], result={"status": "pass"})["result"] == {"status": "pass"}


def test_the_bytes_decide_the_type_not_the_label():
    with pytest.raises(store.Rejected, match="is video, not photo"):
        store.save("ws_a", store.Meta(kind="photo"), MP4)
    with pytest.raises(store.Rejected, match="not a photo, video or audio"):
        store.save("ws_a", store.Meta(kind="photo"), b"#!/bin/sh\nrm -rf /\n" + b"0" * 40)
    with pytest.raises(store.Rejected, match="needs its file"):
        store.save("ws_a", store.Meta(kind="video"), None)
    with pytest.raises(store.Rejected, match="carries no file"):
        store.save("ws_a", store.Meta(kind="reading"), JPEG)
    assert store.save("ws_a", store.Meta(kind="audio"), WEBM)["mime"] == "audio/webm"   # audio-only webm from a browser
    assert store.save("ws_a", store.Meta(kind="reading", values={"reading_deg": 4.1}))["file"] is None


def test_size_limits(monkeypatch):
    monkeypatch.setitem(store.LIMIT_MB, "photo", 0.00001)
    with pytest.raises(store.Rejected, match="over"):
        store.save("ws_a", store.Meta(kind="photo"), JPEG)


def test_ids_cannot_walk_the_disk():
    for bad in ("../x", "a/b", "", "cap_..", "ws_a/cap_1"):
        with pytest.raises(LookupError):
            store.get(bad)
    with pytest.raises(LookupError):
        store.save("../etc", store.Meta(kind="reading"))


def test_a_fix_must_be_on_earth():
    with pytest.raises(ValueError):
        store.Meta(kind="reading", fix={"lat": 123.0, "lon": 0})
    with pytest.raises(ValueError):
        store.Meta(kind="reading", nonsense=1)


def test_pairing_tokens_expire_and_cannot_be_forged():
    t = pair.issue("ws_abc", hours=1, now=1000.0)
    assert pair.check(t["token"], now=1000.0 + 3599) == "ws_abc" and t["expires"] == 4600
    assert "ws_abc" not in t["token"]                                 # the id is not readable in the link
    with pytest.raises(LookupError, match="expired"):
        pair.check(t["token"], now=1000.0 + 3601)
    tok, other = t["token"], pair.issue("ws_other", hours=1, now=1000.0)["token"]
    flipped = tok[:20] + ("A" if tok[20] != "A" else "B") + tok[21:]
    for forged in (other[:16] + tok[16:], flipped, tok[:-2], "garbage", "", "a.b"):
        with pytest.raises(LookupError):
            pair.check(forged, now=1000.0)


def test_the_workspace_id_cannot_be_decoded_from_a_token():
    import base64
    tok = pair.issue("ws_secret1", hours=1)["token"]
    raw = base64.urlsafe_b64decode(tok + "=" * (-len(tok) % 4))
    assert b"ws_secret1" not in raw and b"secret1" not in raw
    assert pair.issue("ws_secret1", hours=1)["token"] != tok             # a fresh nonce each time
