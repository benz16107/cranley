"""The vision model: structured answers about images, cached on disk, a few calls at a time.

The endpoint is a shared subscription, so every answer is cached under `$THRESHOLD_DATA_DIR/cache/vision/`
keyed by the caller's key (scan, panorama, question), the prompt, the schema, the images and the model.
Answers come back as JSON matching a schema (`output_config.format`), never as prose to parse. The current
Opus rejects forced tool choice, which is why this uses the output format instead of a forced tool.
"""
from __future__ import annotations

import base64
import functools
import hashlib
import io
import json
import threading

import anthropic
from PIL import Image

from ..config import CACHE, env

CONCURRENCY = 3
_slots = threading.BoundedSemaphore(CONCURRENCY)
SYSTEM = ("You read photographs of buildings for a property inspection tool. Answer only from what is visible. "
          "When something is not visible or you are unsure, say so through the confidence field instead of guessing. "
          "Never state measurements; describe and label.")


class ModelError(RuntimeError):
    pass


@functools.cache
def _client() -> anthropic.Anthropic:
    e = env()
    return anthropic.Anthropic(base_url=e.get("ANTHROPIC_BASE_URL"), api_key=e["ANTHROPIC_API_KEY"], max_retries=3)


def model_name() -> str:
    return env().get("THRESHOLD_MODEL", "claude-opus-5-5")


def jpeg(data: bytes, px: int) -> bytes:
    """Re-encode an image at `px` pixels on its long side, so box coordinates are in a known pixel space."""
    im = Image.open(io.BytesIO(data)).convert("RGB")
    s = px / max(im.size)
    if abs(s - 1) > 1e-3:
        im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=88)
    return buf.getvalue()


def ask(images: list[bytes], prompt: str, schema: dict, *, key: str, effort: str = "medium") -> dict:
    """One structured answer about `images` (already sized by the caller). `key` names the question for the
    cache, e.g. "label_room/<sid>/<pano>"."""
    model = model_name()
    h = hashlib.sha256()
    for part in (model, key, prompt, json.dumps(schema, sort_keys=True), effort, *[hashlib.sha256(i).hexdigest() for i in images]):
        h.update(part.encode() if isinstance(part, str) else part)
    f = CACHE / "vision" / model / key.replace("/", "_")[:120] / f"{h.hexdigest()[:20]}.json"
    if f.exists():
        return json.loads(f.read_text())
    content = [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                            "data": base64.standard_b64encode(i).decode()}} for i in images]
    content.append({"type": "text", "text": prompt})
    with _slots:
        r = _client().messages.create(
            model=model, max_tokens=16000, system=SYSTEM,
            output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
            messages=[{"role": "user", "content": content}])
    if r.stop_reason != "end_turn":
        raise ModelError(f"vision model stopped with {r.stop_reason}")
    out = json.loads(next(b.text for b in r.content if b.type == "text"))
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(out))
    return out


BOX = {"type": "object", "additionalProperties": False, "required": ["x0", "y0", "x1", "y1"],
       "properties": {k: {"type": "integer"} for k in ("x0", "y0", "x1", "y1")}}
CONFIDENCE = {"type": "string", "enum": ["high", "medium", "low"]}
