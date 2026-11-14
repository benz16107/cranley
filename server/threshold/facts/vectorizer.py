"""Room descriptions embedded inside the database by Tiger's pgai vectorizer.

`room_text.description` is written by the vision build and rewritten when a room is described again. A pgai
vectorizer watches that column: its trigger queues every changed row, and the vectorizer worker
(`pgai vectorizer worker`, a user service on linuxbox) embeds the queued rows with Ollama's nomic-embed-text and writes
the vector to `room_text.description_embedding`. Nothing in the app embeds or re-indexes by hand any more, and a
description and its vector cannot drift apart. Queries are embedded with the same model (`embed_query`).

`python -m threshold.facts vectorize` installs pgai's catalog (schema `ai`), creates the vectorizer if missing and
reports its queue. Safe on live data: it adds one nullable column, one trigger and the `ai` schema.
"""
from __future__ import annotations

import json
import urllib.request

from ..config import env
from . import db

NAME = "room_text_vectorizer"
MODEL = "nomic-embed-text"
DIMS = 768
COLUMN = "description_embedding"


def ollama() -> str:
    return env().get("OLLAMA_HOST_URL", "http://127.0.0.1:11434")


def install() -> dict:
    """pgai's catalog, the vectorizer, and the job that keeps its DiskANN graph sound. Idempotent."""
    _install_catalog()
    c = db.con()
    c.run("SET search_path = threshold, public")
    vid = c.run("SELECT id FROM ai.vectorizer WHERE name = :n", n=NAME)
    has_col = c.run("SELECT 1 FROM information_schema.columns WHERE table_schema = 'threshold' "
                    "AND table_name = 'room_text' AND column_name = :c", c=COLUMN)
    if vid and not has_col:  # the schema was dropped and rebuilt under it (drop_all, tests): register it again
        c.run("SELECT ai.drop_vectorizer(:i, drop_all => true)", i=vid[0][0])
        vid = []
    if not vid:
        # nomic-embed-text wants a task prefix: documents are stored as search_document, queries asked as search_query
        c.run(f"""SELECT ai.create_vectorizer('threshold.room_text'::regclass, name => '{NAME}',
                    loading => ai.loading_column('description'),
                    embedding => ai.embedding_ollama('{MODEL}', {DIMS}, base_url => '{ollama()}'),
                    chunking => ai.chunking_none(),
                    formatting => ai.formatting_python_template('search_document: $chunk'),
                    destination => ai.destination_column('{COLUMN}'),
                    indexing => ai.indexing_none())""")  # our own DiskANN index below, rebuilt by a job
    c.run(f"CREATE INDEX IF NOT EXISTS room_text_description_embedding ON threshold.room_text "
          f"USING diskann ({COLUMN} vector_cosine_ops, labels)")
    return status()


def _install_catalog() -> None:
    """pgai's catalog (schema `ai`). Tiger Cloud sets `ai.external_functions_executor_url` for its managed workers,
    and then `pgai.install` insists on the `ai` extension, which the PG18 service does not offer; our worker is
    self-hosted and needs no ping, so the catalog SQL is run directly."""
    import pgai
    try:
        pgai.install(db.url())
        return
    except Exception as e:  # noqa: BLE001
        if "ai.control" not in str(e):
            raise
    import psycopg
    import importlib
    pi = importlib.import_module("pgai._install.install")  # shortcut: private helpers of pgai 0.12; re-check on upgrade
    with psycopg.connect(db.url(), autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(pi._get_vector_extension_schema_sql())
        schema = cur.fetchone()[0]
        try:
            conn.execute(pi._get_sql(schema))
        except psycopg.errors.DuplicateObject as e:  # already installed at this version
            if not pi.verify_error_library_already_installed(e):
                raise


def status() -> dict:
    rows = db.rows("SELECT ai.vectorizer_queue_pending(id) AS pending FROM ai.vectorizer WHERE name = :n", n=NAME)
    done = db.rows(f"SELECT count({COLUMN}) AS n, count(*) AS of FROM room_text")[0]
    return {"vectorizer": NAME, "model": MODEL, "pending": rows[0]["pending"] if rows else None,
            "embedded": done["n"], "rooms": done["of"]}


def ready() -> bool:
    """The column holds a vector for every described room: search may use it without losing rooms. While the worker
    is behind (or stopped), search keeps the app's own embeddings."""
    try:
        r = db.rows(f"SELECT count(*) AS n, count({COLUMN}) AS v FROM room_text")[0]
        return r["n"] > 0 and r["v"] == r["n"]
    except Exception:  # noqa: BLE001 - no column yet (vectorizer not installed): use the app-side embeddings
        return False


def embed_query(text: str) -> list[float]:
    body = json.dumps({"model": MODEL, "input": f"search_query: {text}"}).encode()
    req = urllib.request.Request(f"{ollama()}/api/embed", body, {"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)["embeddings"][0]
