"""Workspaces in MongoDB Atlas: the people side of Threshold. Building facts live in Postgres (Tiger Data); nothing
here duplicates them.

Collections
  ops         the append-only log, one document per entry, unique (workspace, seq). A regular collection, not a time
              series: time series collections take no unique index (it is the optimistic lock here) and no change
              streams (live sync reads them), and the log is read by workspace and seq, never by time range.
  workspaces  the folded document per workspace (`doc`) and `seq`, the last entry it includes. Replaced only by a
              writer with a higher seq, so a slow writer cannot put an older document back.
  prefs       profile preferences, one document per (profile, key), written only when the stored edit is older:
              workspaces sharing a profile cannot overwrite each other's keys, across threads or processes.
  history     searchable items (briefs, findings, notes, removed tools, shortlisted scans): Atlas Search index
              `history` with facets on tool, status, city, kind, feedback.
  memories    one per workspace with a brief: the need and how it turned out. Vector Search index `memory`
              filtered on persona; Atlas embeds `text` itself (automated embedding, voyage-4) where the deployment
              offers it, else the store embeds locally into `vector` (embed.py).
  shortlist   shortlisted scans with a GeoJSON `location` and a 2dsphere index.
  shares      read-only share links; a TTL index on `expires` deletes them when they lapse.

Writes: the store inserts new log entries (several in one transaction), then replaces the snapshot if its seq is
higher, then upserts the derived items that changed (content hash `h`). A duplicate (workspace, seq) raises
Conflict; Session pulls the newer entries and retries.
"""
from __future__ import annotations

import datetime as dt
import os
import secrets
import threading
import time
from collections.abc import Iterator

from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.errors import BulkWriteError, DuplicateKeyError, OperationFailure
from pymongo.operations import DeleteMany, ReplaceOne, SearchIndexModel

from . import Conflict, derive

DUP = 11000
AUTO_MODEL = "voyage-4"
SEARCH_FIELDS = ["title", "text", "reason"]
FACETS = ["tool", "status", "city", "kind", "feedback"]

HISTORY_INDEX = {"mappings": {"dynamic": False, "fields": {
    **{f: {"type": "string", "analyzer": "lucene.english"} for f in SEARCH_FIELDS},
    "address": {"type": "string"},
    **{f: {"type": "token"} for f in [*FACETS, "profile", "workspace", "persona", "sid"]},
    "at": {"type": "number"}}}}
FILTERS = [{"type": "filter", "path": p} for p in ("persona", "profile", "workspace")]
RECALL_TTL = 60  # the free tier allowed about three query embeddings a minute (measured 2026-11-14)


class EmbedLimit(RuntimeError):
    """Atlas automated embedding refused the query for now."""


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


class MongoStore:
    def __init__(self, uri: str, db: str = "threshold", where: derive.Where = derive.scan_place):
        from . import is_local
        self.client = MongoClient(uri, appname="threshold", tz_aware=True, serverSelectionTimeoutMS=5000)
        self.db = self.client[db]
        self.target = f"{'local' if is_local(uri) else 'atlas'}:{db}"  # names the deployment without its address
        for name in ("ops", "workspaces", "prefs", "history", "memories", "shortlist", "shares"):
            setattr(self, name, self.db[name])
        self.where = where
        self._seen: dict[tuple[str, str], dict[str, str]] = {}  # (collection, workspace) -> {_id: content hash}
        self._lock = threading.Lock()
        self.vector_mode = "local"
        self._recalled: dict[tuple, tuple[float, list[dict]]] = {}  # shortcut: per process and unbounded; fine for one event
        self.setup()

    # ---- setup ----

    def setup(self) -> None:
        have = set(self.db.list_collection_names())
        for name in ("ops", "workspaces", "prefs", "history", "memories", "shortlist", "shares"):
            if name not in have:
                self.db.create_collection(name)  # search indexes need the collection to exist
        self.ops.create_index([("workspace", ASCENDING), ("seq", ASCENDING)], unique=True, name="workspace_seq")
        self.workspaces.create_index([("profile", ASCENDING), ("updated", DESCENDING)], name="profile_updated")
        self.prefs.create_index("profile", name="profile")
        for c in (self.history, self.memories, self.shortlist):
            c.create_index("workspace", name="workspace")
        self.shortlist.create_index([("location", "2dsphere")], name="location")
        self.shortlist.create_index("profile", name="profile")
        self.shares.create_index("expires", expireAfterSeconds=0, name="expires")
        self.shares.create_index("workspace", name="workspace")
        if not self._index("history", self.history):
            self.history.create_search_index(SearchIndexModel(HISTORY_INDEX, name="history"))
        mem = self._index("memory", self.memories)
        if mem:
            fields = (mem.get("latestDefinition") or mem.get("definition") or {}).get("fields", [])
            self.vector_mode = "auto" if any(f["type"] == "autoEmbed" for f in fields) else "local"
            return
        if os.environ.get("THRESHOLD_EMBED") != "local":
            try:  # Atlas embeds the text with Voyage, at write and at query: no embedding key, no client model
                self.memories.create_search_index(SearchIndexModel(
                    {"fields": [{"type": "autoEmbed", "path": "text", "model": AUTO_MODEL, "modality": "text"}, *FILTERS]},
                    name="memory", type="vectorSearch"))
                self.vector_mode = "auto"
                return
            except OperationFailure:
                pass  # a local deployment without a Voyage key: embed here instead
        from .embed import DIMS
        self.memories.create_search_index(SearchIndexModel(
            {"fields": [{"type": "vector", "path": "vector", "numDimensions": DIMS, "similarity": "cosine"}, *FILTERS]},
            name="memory", type="vectorSearch"))
        self.vector_mode = "local"

    @staticmethod
    def _index(name: str, coll) -> dict | None:
        return next((i for i in coll.list_search_indexes(name)), None)

    def wait_ready(self, timeout: float = 120) -> bool:
        """Until both search indexes answer queries."""
        end = time.time() + timeout
        while time.time() < end:
            idx = [self._index("history", self.history), self._index("memory", self.memories)]
            if all(i and (i.get("queryable") or i.get("status") == "READY") for i in idx):
                return True
            time.sleep(1)
        return False

    # ---- the store interface (see store/__init__.py) ----

    def load(self, id: str) -> dict:
        w = self.workspaces.find_one({"_id": id}, {"doc": 0})
        if not w:
            raise LookupError(f"no workspace {id}")
        return {"id": id, "profile": w["profile"], "created": w["created"], "log": self.since(id, 0)}

    def since(self, id: str, seq: int) -> list[dict]:
        return list(self.ops.find({"workspace": id, "seq": {"$gt": seq}}, {"_id": 0, "workspace": 0}).sort("seq", 1))

    def save(self, meta: dict, log: list, new_from: int, doc) -> None:
        id, new = meta["id"], log[new_from:]
        if new:
            rows = [{**e.model_dump(mode="json", by_alias=True), "workspace": id} for e in new]
            try:
                if len(rows) == 1:
                    self.ops.insert_one(rows[0])
                else:  # a user op and what it taught land together or not at all
                    with self.client.start_session() as s:
                        s.with_transaction(lambda s: self.ops.insert_many(rows, session=s))
            except DuplicateKeyError:
                raise Conflict(f"workspace {id}: seq {rows[0]['seq']} is taken") from None
            except BulkWriteError as e:
                if any(w.get("code") == DUP for w in e.details.get("writeErrors", [])):
                    raise Conflict(f"workspace {id}: seq {rows[0]['seq']} is taken") from None
                raise
            if all(e.op is not None and e.op.op == "run.progress" for e in new):
                return  # progress lines change nothing searchable; the run's finish rewrites the snapshot
        d = doc.model_dump(mode="json", by_alias=True)
        snap = {"_id": id, "profile": meta["profile"], "created": meta["created"], "updated": d["updated"],
                "seq": len(log), "doc": d}
        try:
            self.workspaces.replace_one({"_id": id, "seq": {"$lt": len(log)}}, snap, upsert=True)
        except DuplicateKeyError:
            return  # a newer snapshot is there, and its writer derives from it
        self.derive(d)

    def profile(self, profile: str) -> list[dict]:
        return [{k: v for k, v in p.items() if k not in ("_id", "profile")} for p in self.prefs.find({"profile": profile})]

    def merge_profile(self, profile: str, changes: dict[str, tuple[float, dict | None]]) -> None:
        reqs = [ReplaceOne({"_id": {"profile": profile, "key": key}, "at": {"$lte": at}},
                           {**(p or {"key": key, "value": None}), "key": key, "at": at, "profile": profile}, upsert=True)
                for key, (at, p) in changes.items()]
        if not reqs:
            return
        try:
            self.prefs.bulk_write(reqs, ordered=False)
        except BulkWriteError as e:  # a duplicate _id means a later edit is stored: it wins
            if any(w.get("code") != DUP for w in e.details.get("writeErrors", [])):
                raise

    # ---- derived collections ----

    def derive(self, d: dict) -> None:
        ws = d["id"]
        self._sync(self.history, ws, derive.history(d, self.where))
        self._sync(self.shortlist, ws, derive.shortlist(d, self.where))
        m = derive.memory(d)
        self._sync(self.memories, ws, [m] if m else [], vectors=self.vector_mode == "local")

    def _sync(self, coll, ws: str, docs: list[dict], vectors: bool = False) -> None:
        """Write the items whose content changed and delete the ones that went away."""
        with self._lock:
            key = (coll.name, ws)
            # shortcut: the hash cache is per process; another process's writes to the same workspace are seen on restart
            seen = self._seen.get(key)
            if seen is None:
                seen = {x["_id"]: x.get("h") for x in coll.find({"workspace": ws}, {"h": 1})}
            want, reqs = {}, []
            for x in docs:
                h = derive.digest({k: v for k, v in x.items() if k != "at"})
                want[x["_id"]] = h
                if seen.get(x["_id"]) != h:
                    if vectors:
                        from .embed import embed
                        x["vector"] = list(embed(x["text"]))
                    reqs.append(ReplaceOne({"_id": x["_id"]}, {**x, "h": h}, upsert=True))
            gone = [i for i in seen if i not in want]
            if gone:
                reqs.append(DeleteMany({"_id": {"$in": gone}}))
            if reqs:
                coll.bulk_write(reqs, ordered=False)
            self._seen[key] = want

    # ---- live sync ----

    def watch(self, id: str, after: int = 0, wait: float = 1.0) -> Iterator[dict | None]:
        """Entries after `after`, then each new one as any writer inserts it (a change stream on `ops`). Yields None
        when `wait` seconds pass without one, so the caller can send a keep-alive and notice a closed client."""
        match = [{"$match": {"operationType": "insert", "fullDocument.workspace": id}}]
        with self.ops.watch(match, max_await_time_ms=int(wait * 1000)) as stream:  # opened before the backfill: no gap
            last = after
            for e in self.since(id, after):
                last = e["seq"]
                yield e
            while stream.alive:
                ch = stream.try_next()
                if ch is None:
                    yield None
                    continue
                e = ch["fullDocument"]
                if e["seq"] <= last:
                    continue  # already sent in the backfill
                last = e["seq"]
                e.pop("_id", None)
                e.pop("workspace", None)
                yield e

    # ---- share links ----

    def share(self, workspace: str, days: float = 7) -> dict:
        now = _now()
        row = {"_id": secrets.token_urlsafe(16), "workspace": workspace, "mode": "read", "created": now,
               "expires": now + dt.timedelta(days=days)}
        self.shares.insert_one(row)
        return self._share_out(row)

    def shared(self, token: str) -> dict | None:
        # the TTL monitor deletes lapsed links about once a minute; the time check covers the gap
        row = self.shares.find_one({"_id": token, "expires": {"$gt": _now()}})
        return self._share_out(row) if row else None

    def unshare(self, token: str) -> bool:
        return self.shares.delete_one({"_id": token}).deleted_count == 1

    @staticmethod
    def _share_out(row: dict) -> dict:
        return {"token": row["_id"], "workspace": row["workspace"], "mode": row["mode"],
                "expires": row["expires"].isoformat()}

    # ---- search, memory, places ----

    def search(self, text: str | None = None, limit: int = 10, **filters) -> dict:
        """Full-text search over past work (Atlas Search), with facet counts. Filters (exact): profile, workspace,
        tool, status, city, kind, feedback, sid, persona."""
        must = [{"text": {"query": text, "path": SEARCH_FIELDS, "fuzzy": {"maxEdits": 1}}}] if text else \
            [{"exists": {"path": "kind"}}]
        flt = [{"equals": {"path": k, "value": v}} for k, v in filters.items() if v not in (None, "")]
        stage = {"index": "history", "facet": {"operator": {"compound": {"must": must, "filter": flt}},
                                               "facets": {f: {"type": "string", "path": f, "numBuckets": 12} for f in FACETS}}}
        if text:
            stage["highlight"] = {"path": SEARCH_FIELDS}
        out = list(self.history.aggregate([
            {"$search": stage},
            {"$limit": max(1, min(limit, 50))},
            {"$project": {"_id": 0, "h": 0, "profile": 0, "score": {"$meta": "searchScore"},
                          **({"highlights": {"$meta": "searchHighlights"}} if text else {})}},
            {"$facet": {"hits": [], "meta": [{"$replaceWith": "$$SEARCH_META"}, {"$limit": 1}]}}]))[0]
        meta = (out["meta"] or [{}])[0]
        facets = {f: {b["_id"]: b["count"] for b in v["buckets"]} for f, v in (meta.get("facet") or {}).items()}
        return {"total": (meta.get("count") or {}).get("lowerBound", len(out["hits"])), "hits": out["hits"],
                "facets": facets}

    def recall(self, text: str, persona: str | None = None, exclude: str | None = None, k: int = 3,
               min_score: float = 0.0) -> list[dict]:
        """Past needs most like `text` (Atlas Vector Search), optionally only one persona's, best first. Answers are
        kept for RECALL_TTL seconds: with automated embedding each query is one Voyage call, and the free tier
        refuses a burst of them ("Embedding provider rate limit exceeded", raised as EmbedLimit)."""
        key = (text, persona, exclude, k, min_score)
        hit = self._recalled.get(key) if self.vector_mode == "auto" else None  # local embedding has no quota
        if hit and time.time() - hit[0] < RECALL_TTL:
            return hit[1]
        try:
            rows = self._recall(text, persona, exclude, k, min_score)
        except OperationFailure as e:
            if "rate limit" in str(e).lower():
                raise EmbedLimit("Atlas embedding is rate limited; try again in a minute") from None
            raise
        self._recalled[key] = (time.time(), rows)
        return rows

    def _recall(self, text, persona, exclude, k, min_score) -> list[dict]:
        flt = {k_: v for k_, v in (("persona", persona), ("workspace", {"$ne": exclude} if exclude else None)) if v}
        vs = {"index": "memory", "numCandidates": max(50, k * 20), "limit": k}
        if self.vector_mode == "auto":
            vs |= {"path": "text", "query": {"text": text}}
        else:
            from .embed import embed
            vs |= {"path": "vector", "queryVector": list(embed(text))}
        if flt:
            vs["filter"] = flt
        rows = self.memories.aggregate([{"$vectorSearch": vs},
                                        {"$project": {"_id": 0, "vector": 0, "h": 0, "score": {"$meta": "vectorSearchScore"}}}])
        return [r for r in rows if r["score"] >= min_score]

    def shortlist_near(self, lon: float | None = None, lat: float | None = None, km: float | None = None,
                       **filters) -> list[dict]:
        """Shortlisted scans for a profile, workspace or list of workspaces, nearest first when a point is given."""
        q = {k: ({"$in": v} if isinstance(v, list) else v) for k, v in filters.items() if v not in (None, "", [])}
        if lon is None or lat is None:
            return list(self.shortlist.find(q, {"_id": 0, "h": 0}))
        near = {"near": {"type": "Point", "coordinates": [lon, lat]}, "distanceField": "distance_m", "spherical": True,
                "key": "location", "query": q}
        if km is not None:
            near["maxDistance"] = km * 1000
        return list(self.shortlist.aggregate([{"$geoNear": near}, {"$project": {"_id": 0, "h": 0}}]))

    # ---- housekeeping ----

    def status(self) -> dict:
        return {"target": self.target, "vector_mode": self.vector_mode,
                "counts": {c: self.db[c].estimated_document_count() for c in sorted(self.db.list_collection_names())},
                "search_indexes": {n: (self._index(n, c) or {}).get("status")
                                   for n, c in (("history", self.history), ("memory", self.memories))}}

    def drop_all(self) -> dict:
        """Delete every workspace, log entry, preference, memory, shortlist and share link (CoStar's terms: derived
        data goes after the event). Returns what was there."""
        counts = self.status()["counts"]
        self.client.drop_database(self.db.name)
        self._seen.clear()
        return counts

