"""The connection to the building facts database (Postgres with TimescaleDB, PostGIS, pgvector, pgvectorscale and
pg_textsearch). `TIGER_DATABASE_URL` in $THRESHOLD_DATA_DIR/.env names it, so moving to a Tiger Cloud service is
one variable. With no URL, or no database answering, `available()` is False and callers fall back."""
from __future__ import annotations

import functools
import pathlib
import ssl
import threading
import time
from contextlib import contextmanager
from urllib.parse import parse_qs, unquote, urlparse

import pg8000.native

from ..config import env

MIGRATIONS = pathlib.Path(__file__).parent / "migrations"
READER = "threshold_reader"
_local = threading.local()
_down_until = 0.0  # after a failed connect, do not try again for a while, so a missing database costs nothing


def url() -> str | None:
    return env().get("TIGER_DATABASE_URL")


@functools.cache
def _params(u: str) -> dict:
    p = urlparse(u)
    q = parse_qs(p.query)
    kw = {"user": unquote(p.username or "postgres"), "password": unquote(p.password or "") or None,
          "host": p.hostname or "localhost", "port": p.port or 5432, "database": (p.path or "/postgres")[1:] or "postgres",
          "application_name": "threshold"}
    if (q.get("sslmode") or ["disable"])[0] not in ("disable", "allow", "prefer"):  # Tiger Cloud uses sslmode=require
        kw["ssl_context"] = ssl.create_default_context()
    return kw


def connect() -> pg8000.native.Connection:
    u = url()
    if not u:
        raise LookupError("TIGER_DATABASE_URL is not set")
    con = pg8000.native.Connection(timeout=10, **_params(u))
    con.run("SET search_path = threshold, public")
    return con


def con() -> pg8000.native.Connection:
    """This thread's connection, opened on first use and reopened if it broke."""
    c = getattr(_local, "con", None)
    if c is not None:
        try:
            c.run("SELECT 1")
            return c
        except Exception:  # noqa: BLE001 - a dropped connection; open a new one
            _local.con = None
    _local.con = connect()
    return _local.con


def available() -> bool:
    """A database is configured, answers, and has the schema. Cached as down for 30 s after a failure."""
    global _down_until
    if not url() or time.time() < _down_until:
        return False
    try:
        return bool(con().run("SELECT to_regclass('threshold.scan') IS NOT NULL")[0][0])
    except Exception:  # noqa: BLE001 - any failure means fall back
        _down_until = time.time() + 30
        return False


def rows(sql: str, **params) -> list[dict]:
    c = con()
    out = c.run(sql, **params)
    cols = [d["name"] for d in c.columns or []]
    return [dict(zip(cols, r)) for r in out or []]


@contextmanager
def transaction():
    c = con()
    c.run("BEGIN")
    try:
        yield c
        c.run("COMMIT")
    except BaseException:
        c.run("ROLLBACK")
        raise


def migrate() -> list[str]:
    """Apply migrations/NNN_*.sql in order, each once. Returns the names applied now."""
    c = con()
    c.run("CREATE TABLE IF NOT EXISTS public.threshold_migrations (name text PRIMARY KEY, at timestamptz DEFAULT now())")
    done = {r[0] for r in c.run("SELECT name FROM public.threshold_migrations")}
    applied = []
    for f in sorted(MIGRATIONS.glob("*.sql")):
        if f.name in done:
            continue
        # one simple-query call runs the whole file; continuous aggregates cannot be created inside a transaction
        c.execute_simple(f.read_text())
        c.run("INSERT INTO public.threshold_migrations (name) VALUES (:n)", n=f.name)
        applied.append(f.name)
    c.run("SET search_path = threshold, public")
    return applied


def drop_all() -> None:
    """Delete everything this project stored: the schema with every table, view and index, the read-only role and
    the migration record. CoStar's terms require deleting derived data after the event."""
    c = con()
    c.run("DROP SCHEMA IF EXISTS threshold CASCADE")
    c.run("DROP TABLE IF EXISTS public.threshold_migrations")
    if c.run("SELECT 1 FROM pg_roles WHERE rolname = :r", r=READER):
        c.run(f"DROP OWNED BY {READER}")
        c.run(f"DROP ROLE {READER}")
