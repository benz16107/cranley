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


__all__ = ["Conflict", "FileStore", "mongo", "use_mongo"]
