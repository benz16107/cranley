"""Search inside buildings by meaning: the vision model describes each room from its central panorama, a local
embedding model turns the description into a vector, and pgvectorscale's StreamingDiskANN index finds similar rooms.
The same query filters on measured facts (area, turning circle, city) and can mix in BM25 word matching
(pg_textsearch), so "a sunlit kitchen with an island, over 12 m2, in Houston" is one SQL statement.

The model describes; it never measures. Areas and widths in results come from the room table (geometry).
Model answers are cached on disk by threshold.vision.model.ask; embeddings run locally (fastembed, BAAI/bge-small).
"""
from __future__ import annotations

import functools
import hashlib
import time

from ..config import CACHE
from . import db
from .load import cached_plan

EMBED_MODEL = "BAAI/bge-small-en-v1.5"  # 384 dimensions, MIT licence, runs on the CPU
LABELS = ["Kitchen", "Living Room", "Bathroom", "Bedroom", "Dining Room", "Family Room", "Office", "Laundry",
          "Garage", "Patio", "Game Room", "Exercise Room"]
FACES = [1, 2, 3, 4]
PX = 512
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["description", "features", "light"],
          "properties": {
              "description": {"type": "string", "description": "Two or three plain sentences: what the room is used "
                              "for, its finishes, fixtures and furniture, and its light. No sizes or measurements."},
              "features": {"type": "array", "items": {"type": "string"},
                           "description": "Short noun phrases, e.g. 'kitchen island', 'walk-in shower', 'bay window'; at most twelve"},
              "light": {"type": "string", "enum": ["dark", "artificial", "some daylight", "bright daylight",
                                                   "direct sun"]}}}
PROMPT = ("The images are four horizontal views from one point inside a room, looking in four directions 90 degrees "
          "apart. Describe the room the camera stands in for someone searching for rooms like it: what it is used "
          "for, finishes (floor, counters, cabinets, walls), fixtures and notable features, furniture, and how it is "
          "lit. Do not estimate sizes, distances or counts of anything you cannot see clearly. The plan calls it "
          "'{label}'.")


@functools.cache
def _embedder():
    from fastembed import TextEmbedding
    return TextEmbedding(EMBED_MODEL, cache_dir=str(CACHE / "fastembed"))


def embed(texts: list[str]) -> list[list[float]]:
    return [v.tolist() for v in _embedder().embed(texts)]


def vec(v: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"


def _cached_faces(sid: str) -> set[str]:
    d = CACHE / "pano" / sid / "furnished" / "2k"
    if not d.is_dir():
        return set()
    names = {f.name for f in d.iterdir()}
    return {n.split("_")[0] for n in names if all(f"{n.split('_')[0]}_{k}.jpg" in names for k in FACES)}


def choose(limit: int) -> list[tuple[str, str, str]]:
    """(sid, room, label) to describe: rooms of the common types, spread over both cities and many scans, the ones
    whose panorama is already on disk first (spares the shared Matterport key). Deterministic."""
    rs = db.rows("SELECT r.sid, r.room, r.label, s.city FROM room r JOIN scan s USING (sid) "
                 "WHERE s.walls AND r.label = ANY(CAST(:labels AS text[])) AND r.area > 2 "
                 "AND NOT EXISTS (SELECT 1 FROM room_text t WHERE t.sid = r.sid AND t.room = r.room) ORDER BY r.sid, r.room",
                 labels=LABELS)
    cached = {s: _cached_faces(s) for s in {r["sid"] for r in rs}}
    rs.sort(key=lambda r: (not cached[r["sid"]], hashlib.sha1(f"{r['sid']}{r['room']}".encode()).hexdigest()))
    picked, per_scan = [], {}
    for r in rs:  # at most two rooms per scan, so the index spans many homes
        if per_scan.get(r["sid"], 0) >= 2:
            continue
        per_scan[r["sid"]] = per_scan.get(r["sid"], 0) + 1
        picked.append((r["sid"], r["room"], r["label"]))
        if len(picked) >= limit:
            break
    return picked


def describe(sid: str, room: str, label: str) -> dict | None:
    from ..sources import matterport as mp
    from ..vision.model import ask, jpeg, model_name
    from ..vision.reader import room_panos
    plan = cached_plan(sid)
    r = next((x for x in plan["rooms"] if x["id"] == room), None)
    ps = room_panos(plan, r) if r else []
    if not ps:
        return None
    pano = ps[0]["id"]
    imgs = [jpeg(mp.pano_face(sid, pano, f, "2k"), PX) for f in FACES]
    a = ask(imgs, PROMPT.format(label=label), SCHEMA, key=f"describe_room/{sid}/{pano}", effort="low")
    return {"sid": sid, "room": room, "pano": pano, "label": label, "model": model_name(), **a}


def build(limit: int = 300, workers: int = 3) -> dict:
    """Describe and embed up to `limit` more rooms. Safe to re-run: rooms already described are skipped, and model
    answers come from the disk cache."""
    from concurrent.futures import ThreadPoolExecutor
    t0 = time.time()
    todo = choose(limit)
    errors = []

    def one(t):
        try:
            return describe(*t)
        except Exception as e:  # noqa: BLE001 - a panorama that will not load skips its room
            errors.append(f"{t[0]}/{t[1]}: {type(e).__name__}: {str(e)[:120]}")
            return None

    with ThreadPoolExecutor(workers) as ex:
        out = [d for d in ex.map(one, todo) if d]
    t_model = time.time() - t0
    types = {r["label"]: r["id"] for r in db.rows("SELECT id, label FROM room_type")}
    with db.transaction() as c:
        for lab in sorted({d["label"] for d in out} - set(types)):
            nid = max(types.values(), default=0) + 1
            c.run("INSERT INTO room_type VALUES (:i, :l)", i=nid, l=lab)
            types[lab] = nid
    vs = embed([text(d) for d in out])
    with db.transaction() as c:
        for d, v in zip(out, vs):
            c.run("INSERT INTO room_text (sid, room, pano, description, features, model, embed_model, embedding, labels) "
                  "VALUES (:s, :r, :p, :d, CAST(:f AS text[]), :m, :e, CAST(:v AS vector), CAST(:l AS smallint[])) "
                  "ON CONFLICT (sid, room) DO UPDATE SET description = EXCLUDED.description, features = EXCLUDED.features, "
                  "embedding = EXCLUDED.embedding, labels = EXCLUDED.labels, at = now()",
                  s=d["sid"], r=d["room"], p=d["pano"], d=d["description"] + f" Light: {d['light']}.",
                  f=d["features"], m=d["model"], e=EMBED_MODEL, v=vec(v), l=[types[d["label"]]])
    if out:  # a DiskANN graph grown row by row from an empty table had recall@10 of 0.0 on 299 rooms; rebuilt, 1.0
        db.con().run("REINDEX INDEX room_text_embedding")
    n = db.rows("SELECT count(*) AS n FROM room_text")[0]["n"]
    return {"asked": len(todo), "described": len(out), "errors": errors[:10], "rooms_indexed": n,
            "model_s": round(t_model, 1), "total_s": round(time.time() - t0, 1)}


def text(d: dict) -> str:
    return f"{d['label']}. {d['description']} Light: {d['light']}. Features: {', '.join(d['features'])}."


def similar(query: str | None = None, *, like: tuple[str, str] | None = None, label: str | None = None,
            city: str | None = None, kind: str | None = None, min_area: float | None = None,
            min_turn: float | None = None, words: float = 0.0, limit: int = 10) -> dict:
    """Rooms most like a text query or like an existing room (sid, room), filtered on measured facts.
    `words` (0 to 1) blends in BM25 word matching on the descriptions (pg_textsearch). Returns rows and the SQL."""
    if not query and not like:
        raise ValueError("give a query or a room to match")
    args: dict = {"lim": limit}
    if like:
        r = db.rows("SELECT embedding::text AS v, description FROM room_text WHERE sid = :s AND room = :r",
                    s=like[0], r=like[1])
        if not r:
            raise LookupError(f"room {like[1]} in {like[0]} has not been described yet")
        args["q"] = r[0]["v"]
        query = query or r[0]["description"]
    else:
        args["q"] = vec(embed([query])[0])
    where = ["t.embedding IS NOT NULL"]
    if label:
        where.append("t.labels && ARRAY[(SELECT id FROM room_type WHERE label ILIKE :label)]::smallint[]")
        args["label"] = label
    if like:
        where.append("NOT (t.sid = :ls AND t.room = :lr)")
        args["ls"], args["lr"] = like
    for col, val, op in (("s.city", city, "ILIKE"), ("s.kind", kind, "="), ("r.area", min_area, ">="),
                         ("r.turn_diameter", min_turn, ">=")):
        if val is not None:
            k = col.split(".")[1]
            where.append(f"{col} {op} :{k}")
            args[k] = f"%{val}%" if op == "ILIKE" else val
    # nearest neighbours from the DiskANN index (filtered by room type inside the index), then re-rank with BM25
    cand = max(limit * 4, 40)
    args["cand"] = cand
    bm25 = ("ts_bm" if words > 0 else None)
    sql = ("WITH near AS (SELECT t.sid, t.room, t.description, t.features, t.embedding <=> CAST(:q AS vector) AS dist "
           "FROM room_text t JOIN room r USING (sid, room) JOIN scan s USING (sid) "
           f"WHERE {' AND '.join(where)} ORDER BY t.embedding <=> CAST(:q AS vector) LIMIT :cand) "
           "SELECT n.sid, n.room, r.label, r.area, r.turn_diameter, r.widest_door, r.windows, s.city, s.kind, s.name, "
           "n.description, n.features, round((1 - n.dist)::numeric, 3) AS similarity"
           + (", round((-(n.description <@> to_bm25query(:words_q, 'threshold.room_text_bm25')))::numeric, 3) AS bm25"
              if bm25 else ", NULL AS bm25") +
           " FROM near n JOIN room r USING (sid, room) JOIN scan s USING (sid)")
    if bm25:
        args["words_q"] = query
    t0 = time.perf_counter()
    rows = db.rows(sql, **args)
    if bm25 and rows:  # blend: rank by cosine similarity plus `words` times the normalised BM25 score
        top = max((float(r["bm25"] or 0) for r in rows), default=0) or 1.0
        for r in rows:
            r["score"] = round(float(r["similarity"]) + words * float(r["bm25"] or 0) / top, 3)
    else:
        for r in rows:
            r["score"] = float(r["similarity"])
    rows.sort(key=lambda r: -r["score"])
    return {"query": query, "rows": rows[:limit], "sql": sql, "ms": round((time.perf_counter() - t0) * 1000, 1),
            "indexed": db.rows("SELECT count(*) AS n FROM room_text")[0]["n"]}
