"""Local text embeddings, used only when the deployment cannot embed for us (Atlas automated embedding needs an
Atlas cluster, or a Voyage key on the local preview image). fastembed runs BAAI/bge-small-en-v1.5 (MIT, 384
dimensions) on the CPU: no key, no network after the first model download into $THRESHOLD_DATA_DIR/cache/fastembed."""
from __future__ import annotations

import functools

from ..config import CACHE

MODEL = "BAAI/bge-small-en-v1.5"
DIMS = 384


@functools.cache
def _model():
    from fastembed import TextEmbedding
    return TextEmbedding(MODEL, cache_dir=str(CACHE / "fastembed"))


@functools.lru_cache(maxsize=512)
def embed(text: str) -> tuple[float, ...]:
    return tuple(float(x) for x in next(iter(_model().embed([text]))))
