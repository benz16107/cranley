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


def is_local(u: str | None) -> bool:
    """True when the URL names a database on this machine (the Docker copy), false for the cloud service."""
    return bool(u) and (urlparse(u).hostname or "localhost") in ("localhost", "127.0.0.1", "::1")


@functools.cache
def _params(u: str) -> dict:
    p = urlparse(u)
    q = parse_qs(p.query)
    kw = {"user": unquote(p.username or "postgres"), "password": unquote(p.password or "") or None,
          "host": p.hostname or "localhost", "port": p.port or 5432, "database": (p.path or "/postgres")[1:] or "postgres",
          "application_name": "threshold"}
    mode = (q.get("sslmode") or ["prefer"])[0]
    if mode == "disable":
        kw["ssl_context"] = False
    elif mode in ("verify-ca", "verify-full"):
        kw["ssl_context"] = ssl.create_default_context()
        kw["ssl_context"].check_hostname = mode == "verify-full"
    else:  # require, prefer, allow: encrypt without verifying the certificate, as libpq does (Tiger Cloud: require)
        kw["ssl_context"] = True
    return kw


def connect() -> pg8000.native.Connection:
    u = url()
    if not u:
        raise LookupError("TIGER_DATABASE_URL is not set")
    con = pg8000.native.Connection(timeout=10, **_params(u))
    con.run("SET search_path = threshold, public")
    return con


def con() -> pg8000.native.Connection:
    """This thread's connection, opened on first use and reopened if it broke or the URL changed."""
    c = getattr(_local, "con", None)
    if c is not None and getattr(_local, "url", None) != url():
        c, _local.con = None, None
    if c is not None:
        try:
            c.run("SELECT 1")
            return c
        except Exception:  # noqa: BLE001 - a dropped connection; open a new one
            _local.con = None
    _local.con, _local.url = connect(), url()
    return _local.con


_up: dict[str, float] = {}  # url -> time until which a positive check is trusted (a cloud round trip is ~25 ms)


def available() -> bool:
    """A database is configured, answers, and has the schema. Trusted for 60 s once seen; cached as down for 30 s
    after a failure."""
    global _down_until
    u = url()
    if not u or time.time() < _down_until:
        return False
    if _up.get(u, 0) > time.time():
        return True
    try:
        ok = bool(con().run("SELECT to_regclass('threshold.scan') IS NOT NULL")[0][0])
    except Exception:  # noqa: BLE001 - any failure means fall back
        _down_until = time.time() + 30
        return False
    if ok:
        _up[u] = time.time() + 60
    return ok


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


TARGETS = {"cloud": "TIGER_DATABASE_URL", "test": "TIGER_TEST_DATABASE_URL"}


def drop_all(*, target: str) -> str:
    """Delete everything this project stored in the database `target` names ("cloud": TIGER_DATABASE_URL, the Tiger
    Cloud service; "test": TIGER_TEST_DATABASE_URL, the local test database): the schema with every table, view and
    index, the read-only role and the migration record. CoStar's terms require deleting derived data after the event.
    It opens its own connection to that target, so it can never drop a database other than the one named."""
    if target not in TARGETS:
        raise ValueError(f"target must be one of {', '.join(TARGETS)}")
    u = env().get(TARGETS[target])
    if not u:
        raise LookupError(f"{TARGETS[target]} is not set")
    c = pg8000.native.Connection(timeout=10, **_params(u))
    try:
        return _drop(c)
    finally:
        c.close()


def _drop(c: pg8000.native.Connection) -> str:
    for attempt in range(5):  # a TimescaleDB background job touching the catalog can race the drop; try again
        try:
            c.run("DROP SCHEMA IF EXISTS threshold CASCADE")
            break
        except pg8000.native.DatabaseError as e:
            if attempt == 4 or (e.args[0] or {}).get("C") not in ("XX000", "40P01", "55P03"):
                raise
            time.sleep(1 + attempt)
    c.run("DROP TABLE IF EXISTS public.threshold_migrations")
    c.run("DROP SCHEMA IF EXISTS ai CASCADE")  # the pgai vectorizer's catalog and queue (facts/vectorizer.py)
    if not c.run("SELECT 1 FROM pg_roles WHERE rolname = :r", r=READER):
        return "dropped the schema and the migration record"
    c.run(f"DROP OWNED BY {READER}")
    try:
        c.run(f"DROP ROLE {READER}")
        return f"dropped the schema, the migration record and role {READER}"
    except pg8000.native.DatabaseError:  # roles span the server; another database still grants this one rights
        c.run(f"ALTER ROLE {READER} NOLOGIN")
        return (f"dropped the schema and the migration record; role {READER} still has rights in another database "
                "on this server, so it was set to NOLOGIN (run drop_all there too)")
