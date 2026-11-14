"""Capture files and records. One folder per workspace: captures/<workspace>/<id>.json and <id>.<ext>."""
from __future__ import annotations

import json
import secrets
import time
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..config import DATA

ROOT = DATA / "captures"
Kind = Literal["photo", "video", "audio", "reading"]
# What a file must start with, by kind. The browser's content type is not trusted: the bytes decide.
LIMIT_MB = {"photo": 15, "video": 150, "audio": 20}
META_LIMIT = 64_000  # bytes of JSON; a reading is a few hundred


class Rejected(ValueError):
    """The upload is too big, the wrong type, or its record does not validate. Safe to show the person."""


class Fix(BaseModel):
    """A GPS fix as the browser gives it. Altitude and its accuracy are missing on many phones indoors."""
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    accuracy_m: float | None = Field(None, ge=0)
    altitude_m: float | None = None
    altitude_accuracy_m: float | None = Field(None, ge=0)
    samples: int = Field(1, ge=1, description="Fixes averaged into this one")


class Meta(BaseModel):
    """What the phone sends with a capture. Everything but `kind` is optional: a sensor may be missing or refused."""
    model_config = ConfigDict(extra="forbid")
    kind: Kind
    task: str | None = Field(None, description="Id of the phone task this answers")
    tool: str | None = Field(None, description="Phone tool this feeds, when it is not a task")
    scan: str | None = None
    room: str | None = None
    opening: str | None = None
    finding: str | None = None
    note: str | None = Field(None, max_length=2000)
    taken: float | None = Field(None, description="Unix seconds on the phone's clock")
    fix: Fix | None = None
    heading_deg: float | None = Field(None, ge=0, lt=360, description="Compass heading of the phone's top edge")
    heading_accuracy_deg: float | None = Field(None, ge=0)
    tilt: dict[str, float] | None = Field(None, description="pitch_deg, roll_deg of the phone when it was taken")
    values: dict[str, Any] = Field(default={}, description="The reading itself, or inputs for the tool")
    device: str | None = Field(None, max_length=300)


def sniff(data: bytes) -> tuple[Kind, str, str] | None:
    """(kind, mime, extension) from the first bytes, or None for anything this does not accept."""
    h = data[:16]
    if h[:3] == b"\xff\xd8\xff":
        return "photo", "image/jpeg", "jpg"
    if h[:8] == b"\x89PNG\r\n\x1a\n":
        return "photo", "image/png", "png"
    if h[:4] == b"RIFF" and h[8:12] == b"WEBP":
        return "photo", "image/webp", "webp"
    if h[4:8] == b"ftyp":
        brand = h[8:12]
        if brand in (b"heic", b"heix", b"mif1", b"hevc"):
            return None  # HEIC: Pillow here cannot read it, so the apps send JPEG
        if brand in (b"M4A ", b"M4B "):
            return "audio", "audio/mp4", "m4a"
        return "video", "video/quicktime" if brand == b"qt  " else "video/mp4", "mov" if brand == b"qt  " else "mp4"
    if h[:4] == b"\x1a\x45\xdf\xa3":
        return "video", "video/webm", "webm"  # also audio-only webm; the declared kind settles it below
    if h[:4] == b"OggS":
        return "audio", "audio/ogg", "ogg"
    if h[:4] == b"RIFF" and h[8:12] == b"WAVE":
        return "audio", "audio/wav", "wav"
    if h[:3] == b"ID3" or h[:2] in (b"\xff\xfb", b"\xff\xf3"):
        return "audio", "audio/mpeg", "mp3"
    return None


def check(meta: Meta, data: bytes | None) -> tuple[str, str] | None:
    """(mime, extension) of an accepted file; None for a reading. Raises Rejected."""
    if meta.kind == "reading":
        if data:
            raise Rejected("A reading carries no file.")
        return None
    if not data:
        raise Rejected(f"That {meta.kind} capture arrived without its file. Record it again.")
    found = sniff(data)
    if found is None:
        raise Rejected("That file is not a photo, video or audio clip this accepts.")
    kind, mime, ext = found
    if kind == "video" and meta.kind == "audio" and ext in ("webm", "mp4"):  # audio-only recordings share containers
        kind, mime = "audio", "audio/" + ext
    if kind != meta.kind:
        raise Rejected(f"The file is {kind}, not {meta.kind}.")
    if len(data) > LIMIT_MB[kind] * 1_000_000:
        raise Rejected(f"That {kind} is over {LIMIT_MB[kind]} MB.")
    return mime, ext


def _safe(part: str) -> str:
    if not part or not all(c.isalnum() or c in "_-" for c in part):
        raise LookupError("no such capture")
    return part


def save(workspace: str, meta: Meta, data: bytes | None = None, root=None) -> dict:
    """Check and write one capture. Returns its record."""
    found = check(meta, data)
    cid = "cap_" + secrets.token_hex(8)
    d = (root or ROOT) / _safe(workspace)
    d.mkdir(parents=True, exist_ok=True)
    rec = {"id": cid, "workspace": workspace, "at": time.time(), **meta.model_dump(exclude_none=True),
           "file": None, "mime": None, "bytes": 0, "result": None}
    if found:
        mime, ext = found
        (d / f"{cid}.{ext}").write_bytes(data)
        rec.update(file=f"{cid}.{ext}", mime=mime, bytes=len(data))
    _write(d / f"{cid}.json", rec)
    return rec


def _write(f, rec: dict) -> None:
    """Whole or not at all: the phone polls listing() while a capture is saved."""
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(rec))
    tmp.replace(f)


def _record(cid: str, root=None):
    # shortcut: finds the workspace folder by a glob over all of them; index by id once there are thousands
    return next((root or ROOT).glob(f"*/{_safe(cid)}.json"), None)


def get(cid: str, root=None) -> dict:
    f = _record(cid, root)
    if f is None:
        raise LookupError(f"no capture {cid}")
    return json.loads(f.read_text())


def path(cid: str, root=None):
    """The capture's file on disk, or None for a reading."""
    f = _record(cid, root)
    rec = json.loads(f.read_text()) if f else None
    if rec is None:
        raise LookupError(f"no capture {cid}")
    return f.parent / rec["file"] if rec["file"] else None


def read(cid: str, root=None) -> bytes:
    p = path(cid, root)
    if p is None:
        raise LookupError(f"capture {cid} has no file")
    return p.read_bytes()


def image(cid: str, px: int = 1600, root=None) -> bytes:
    """A photo capture as an upright JPEG, `px` on its long side: the pixel space the vision reader's points are in."""
    import io

    from PIL import Image, ImageOps
    im = ImageOps.exif_transpose(Image.open(io.BytesIO(read(cid, root)))).convert("RGB")
    s = px / max(im.size)
    if s < 1:
        im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=88)
    return buf.getvalue()


def update(cid: str, root=None, **fields) -> dict:
    f = _record(cid, root)
    if f is None:
        raise LookupError(f"no capture {cid}")
    rec = {**json.loads(f.read_text()), **fields}
    _write(f, rec)
    return rec


def listing(workspace: str, root=None) -> list[dict]:
    """A workspace's captures, oldest first."""
    d = (root or ROOT) / _safe(workspace)
    return sorted((json.loads(f.read_text()) for f in d.glob("cap_*.json")), key=lambda r: r["at"]) if d.exists() else []


def public(rec: dict) -> dict:
    """The record without the workspace id: a phone holding a pairing token must not learn it."""
    return {k: v for k, v in rec.items() if k != "workspace"}
