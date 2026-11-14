"""Where workspaces live. Two stores with one interface (load, since, save, profile, merge_profile):

- FileStore (default): JSON files under $THRESHOLD_DATA_DIR/workspaces/.
- MongoStore: MongoDB Atlas, chosen with THRESHOLD_STORE=mongo; MONGODB_URI (and MONGODB_DB) in the data folder's
  .env say which deployment. It adds live sync (change streams), search over past work (Atlas Search), memory
  (Atlas Vector Search), shortlists near a point (2dsphere) and expiring share links (TTL).

`python -m threshold.store setup|migrate|status|drop_all` manages the database.
"""
from __future__ import annotations

import functools

from ..config import env
from .files import FileStore


class Conflict(RuntimeError):
    """Another writer appended to the workspace first; reload and try again."""


def use_mongo() -> bool:
    return env().get("THRESHOLD_STORE", "files").lower() == "mongo"


@functools.cache
def mongo(uri: str | None = None, db: str | None = None):
    from .mongo import MongoStore
    e = env()
    uri = uri or e.get("MONGODB_URI")
    if not uri:
        raise RuntimeError("THRESHOLD_STORE=mongo needs MONGODB_URI (environment or $THRESHOLD_DATA_DIR/.env)")
    return MongoStore(uri, db or e.get("MONGODB_DB", "threshold"))


MIN_SCORE = 0.82  # (1 + cos) / 2 with bge-small: related needs scored 0.85-0.88 on the 11 real workspaces, unrelated 0.75-0.79


def recall_lines(store, text: str | None, persona: str | None = None, exclude: str | None = None, k: int = 3) -> list[str]:
    """Similar past needs as prompt lines, for stores with memory; [] otherwise or when recall fails (memory must
    never stop a turn)."""
    if not text or not hasattr(store, "recall"):
        return []
    from .derive import lines
    try:
        return lines(store.recall(text, persona=persona, exclude=exclude, k=k, min_score=MIN_SCORE))
    except Exception:
        return []


__all__ = ["Conflict", "FileStore", "mongo", "recall_lines", "use_mongo"]
