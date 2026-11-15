"""The Photon 2.0 API (https://api.photon.codes/v1), only the calls Cranley makes. Keys come from the data folder's .env
(PHOTON_API_KEY, PHOTON_PROJECT_ID) and are never logged."""
from __future__ import annotations

import json
import secrets
from typing import Any

import httpx

from ..config import env

BASE = "https://api.photon.codes/v1"


class PhotonError(RuntimeError):
    def __init__(self, status: int, code: str, title: str):
        super().__init__(f"Photon {status} {code}: {title}")
        self.status, self.code = status, code


def _cfg() -> tuple[str, str]:
    e = env()
    if not e.get("PHOTON_API_KEY") or not e.get("PHOTON_PROJECT_ID"):
        raise RuntimeError("PHOTON_API_KEY and PHOTON_PROJECT_ID are not set in $THRESHOLD_DATA_DIR/.env")
    return e["PHOTON_API_KEY"], e["PHOTON_PROJECT_ID"]


def enabled() -> bool:
    e = env()
    return bool(e.get("PHOTON_API_KEY") and e.get("PHOTON_PROJECT_ID"))


def call(method: str, path: str, body: Any = None, *, idem: str | bool = False, raw: bytes | None = None,
         content_type: str | None = None, timeout: float = 30) -> Any:
    """One request under /projects/{project}. `idem` True sends a fresh Idempotency-Key, a string sends that key."""
    key, project = _cfg()
    h = {"Authorization": f"Bearer {key}"}
    if idem:
        h["Idempotency-Key"] = idem if isinstance(idem, str) else secrets.token_hex(16)
    if raw is not None:
        h["Content-Type"] = content_type or "application/octet-stream"
    r = httpx.request(method, f"{BASE}/projects/{project}{path}", headers=h, timeout=timeout,
                      content=raw if raw is not None else None, json=body if raw is None and body is not None else None)
    if r.status_code >= 400:
        try:
            p = r.json()
        except ValueError:
            p = {}
        raise PhotonError(r.status_code, p.get("code", "HTTP"), p.get("title") or p.get("detail") or r.text[:200])
    ct = r.headers.get("content-type", "")
    return r.json() if "json" in ct else r.content


def multipart(data: bytes, content_type: str, filename: str) -> tuple[bytes, str]:
    """POST /attachments takes multipart/related: a JSON part with the size, then the bytes."""
    b = "cranley" + secrets.token_hex(8)
    meta = json.dumps({"contentType": content_type, "sizeBytes": len(data), "filename": filename})
    body = (f"--{b}\r\nContent-Type: application/json\r\n\r\n{meta}\r\n--{b}\r\nContent-Type: {content_type}\r\n\r\n").encode() \
        + data + f"\r\n--{b}--\r\n".encode()
    return body, f"multipart/related; boundary={b}"


def upload(data: bytes, content_type: str, filename: str) -> str:
    body, ct = multipart(data, content_type, filename)
    return call("POST", "/attachments", raw=body, content_type=ct, idem=True, timeout=120)["id"]


def download(attachment_id: str) -> tuple[str, bytes]:
    meta = call("GET", f"/attachments/{attachment_id}")
    return meta.get("contentType", ""), call("GET", f"/attachments/{attachment_id}/content", timeout=120)


def send(space: str, sender: str, content: dict, parent: str | None = None, idem: str | bool = True, **extra) -> str:
    """POST /messages; the new message's id. `extra` passes channel options (email, telegram)."""
    body = {"spaceId": space, "senderId": sender, "content": content, **extra}
    if parent:
        body["parentMessageId"] = parent
    return call("POST", "/messages", body, idem=idem).get("id", "")


def text(space: str, sender: str, words: str, parent: str | None = None, idem: str | bool = True) -> str:
    return send(space, sender, {"type": "text", "format": "plain", "text": words}, parent, idem)


def attachment(space: str, sender: str, data: bytes, content_type: str, filename: str, parent: str | None = None,
               caption: str | None = None) -> str:
    content: dict = {"type": "attachment", "attachmentId": upload(data, content_type, filename)}
    if caption:
        content["metadata"] = {"caption": caption}
    return send(space, sender, content, parent)


def voice(space: str, sender: str, m4a: bytes) -> str:
    """A native voice message (iMessage plays it in the bubble). Photon refuses voice as a reply."""
    return send(space, sender, {"type": "voice", "attachmentId": upload(m4a, "audio/mp4", "cranley.m4a")})


def background(space: str, sender: str, png: bytes) -> str:
    """Set the chat's background (iMessage) to an image."""
    att = upload(png, "image/png", "building.png")
    return send(space, sender, {"type": "space.background.update", "background": {"type": "image", "attachmentId": att}})


def typing(space: str, sender: str, on: bool = True) -> None:
    call("POST", f"/spaces/{space}/typing", {"senderId": sender, "typing": on})


def user(platform: str, handle: str) -> dict:
    """Create or get a User by handle."""
    return call("POST", "/users", {"platform": platform, "handle": handle}, idem=True)


def space(platform: str, participants: list[str]) -> dict:
    """Create or get a direct Space between users."""
    return call("POST", "/spaces", {"platform": platform, "participantIds": participants}, idem=True)
