"""Voice in and out with ElevenLabs (ELEVENLABS_API_KEY in the data folder's .env): a voice note becomes text, an
answer becomes an M4A that iMessage plays as a native voice message. ffmpeg converts the audio."""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import httpx

from ..config import env

API = "https://api.elevenlabs.io/v1"
VOICE = "jqcCZkN6Knx8BJ5TBdYR"  # "Zara", a warm conversational voice from the account's library


def _key() -> str:
    k = env().get("ELEVENLABS_API_KEY")
    if not k:
        raise RuntimeError("ELEVENLABS_API_KEY is not set")
    return k


def transcribe(audio: bytes, content_type: str = "audio/mp4", filename: str = "note.m4a") -> str:
    r = httpx.post(f"{API}/speech-to-text", headers={"xi-api-key": _key()}, timeout=120,
                   data={"model_id": "scribe_v1"}, files={"file": (filename, audio, content_type)})
    r.raise_for_status()
    return (r.json().get("text") or "").strip()


def speak(text: str, voice: str = VOICE) -> bytes:
    """MP3 from ElevenLabs, as M4A (AAC) for iMessage."""
    r = httpx.post(f"{API}/text-to-speech/{voice}", params={"output_format": "mp3_44100_128"}, timeout=120,
                   headers={"xi-api-key": _key()}, json={"text": text, "model_id": "eleven_turbo_v2_5"})
    r.raise_for_status()
    return to_m4a(r.content, "mp3")


def to_m4a(data: bytes, ext: str) -> bytes:
    with tempfile.TemporaryDirectory(prefix="cranley-voice-") as d:
        src, out = Path(d) / f"in.{ext}", Path(d) / "out.m4a"
        src.write_bytes(data)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(src), "-c:a", "aac", "-b:a", "96k", str(out)],
                       check=True, timeout=60)
        return out.read_bytes()
