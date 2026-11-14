"""What-if scenarios that change data run on a throwaway copy of the facts database, never on the service itself.

First choice: a zero-copy fork of the Tiger Cloud service (copy-on-write on the free plan, ready in 30 to 90 s),
made through Tiger's REST API and deleted when the scenario ends. It needs a project API key, TIGER_ACCESS_KEY and
TIGER_SECRET_KEY in $THRESHOLD_DATA_DIR/.env; the project and service ids come from TIGER_DATABASE_URL's host
(<service>.<project>.tsdb.cloud.timescale.com). The free plan allows two free services, so one fork at a time.

Fallback, with no API key or when the fork cannot be made: a schema per scenario (`whatif_<hex>`) on the service,
holding copies of the two tables the scenario changes, dropped at the end.

`city_scenario(plan, after)` adds the renovated home as a row, then asks the city-wide question: how many homes of
this kind in this city have a wheelchair-ready bathroom now, and how many would if the doors on the way were
widened to 36 in.
"""
from __future__ import annotations

import base64
import secrets
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from urllib.parse import quote, urlparse, urlunparse

import httpx

from ..config import env
from . import db

API = "https://console.cloud.tigerdata.com/public/api/v1"
READY_TIMEOUT_S = 300
POLL_S = 5
DOOR_M, TURN_M, WIDENED_M = 0.815, 1.525, 0.865  # ADA door clear, ADA turning circle, a 36 in door's clear width
Step = Callable[[str], None]


class ForkError(RuntimeError):
    """The fork could not be made or reached. The message never contains a credential."""


def ids(url: str | None = None) -> tuple[str, str] | None:
    """(project id, service id) from a Tiger Cloud host name, else None (a local database)."""
    host = urlparse(url or db.url() or "").hostname or ""
    parts = host.split(".")
    return (parts[1], parts[0]) if len(parts) == 6 and host.endswith(".tsdb.cloud.timescale.com") else None


def configured() -> bool:
    e = env()
    return bool(e.get("TIGER_ACCESS_KEY") and e.get("TIGER_SECRET_KEY") and ids())


def _client() -> httpx.Client:
    e = env()
    token = base64.b64encode(f"{e['TIGER_ACCESS_KEY']}:{e['TIGER_SECRET_KEY']}".encode()).decode()
    return httpx.Client(base_url=API, timeout=30, headers={"Authorization": f"Basic {token}"})


def _check(r: httpx.Response, what: str) -> dict:
    if r.status_code >= 400:
        try:
            msg = r.json().get("message") or r.json().get("error") or ""
        except ValueError:
            msg = ""
        raise ForkError(f"Tiger API refused to {what} (HTTP {r.status_code}) {str(msg)[:200]}".strip())
    return r.json() if r.content else {}


def _fork_url(parent: str, host: str, port: int, password: str) -> str:
    p = urlparse(parent)
    netloc = f"{quote(p.username or 'tsdbadmin', safe='')}:{quote(password, safe='')}@{host}:{port}"
    return urlunparse(p._replace(netloc=netloc))


@contextmanager
def fork(step: Step = lambda s: None, client: httpx.Client | None = None, sleep=time.sleep) -> Iterator[dict]:
    """A fork of the facts service: yields {url, service_id, name, seconds}, deletes the fork afterwards whatever
    happens. Raises ForkError when it cannot be made."""
    project, service = ids() or (None, None)
    if not project:
        raise ForkError("TIGER_DATABASE_URL is not a Tiger Cloud service")
    c = client or _client()
    base = f"/projects/{project}/services/{service}"
    parent = _check(c.get(base), "read the service")
    spec = (parent.get("resources") or [{}])[0].get("spec") or {}
    name = f"threshold-whatif-{secrets.token_hex(3)}"
    t0 = time.time()
    body = {"name": name, "region_code": parent.get("region_code"), "fork_strategy": "NOW",
            "cpu_millis": spec.get("cpu_millis"), "memory_gbs": spec.get("memory_gbs")}
    # a free service reports no resource spec; its fork is free too and takes none
    made = _check(c.post(f"{base}/forkService", json={k: v for k, v in body.items() if v is not None}),
                  "fork the service")
    fid, password = made["service_id"], made.get("initial_password")
    step(f"Forked the facts database as {name}; waiting for it to start")
    try:
        info = made
        while (info.get("status") or "").upper() != "READY" or not (info.get("endpoint") or {}).get("host"):
            if time.time() - t0 > READY_TIMEOUT_S:
                raise ForkError(f"the fork was not ready after {READY_TIMEOUT_S} s")
            sleep(POLL_S)
            info = _check(c.get(f"/projects/{project}/services/{fid}"), "read the fork")
        if not password:
            raise ForkError("the fork came back without a password")
        ep = info["endpoint"]
        secs = round(time.time() - t0, 1)
        step(f"Fork ready after {secs} s")
        yield {"url": _fork_url(db.url(), ep["host"], ep["port"], password), "service_id": fid, "name": name,
               "seconds": secs}
    finally:
        try:
            _check(c.delete(f"/projects/{project}/services/{fid}"), "delete the fork")
            step(f"Deleted the fork {name}")
        except (ForkError, httpx.HTTPError) as e:  # say so: a forgotten fork holds one of the two free services
            step(f"Could not delete the fork {name} ({e}); delete it in the Tiger console")


def _connect(url: str):
    import pg8000.native
    c = pg8000.native.Connection(timeout=30, **db._params(url))
    c.run("SET search_path = threshold, public")
    return c


def _rows(c, sql: str, **params) -> list[dict]:
    out = c.run(sql, **params)
    cols = [d["name"] for d in c.columns or []]
    return [dict(zip(cols, r)) for r in out or []]


@contextmanager
def scenario(step: Step = lambda s: None, connect=_connect, forker=fork) -> Iterator[tuple[object, str, dict]]:
    """A connection to a throwaway copy and the schema to use in it: a fork when an API key is configured and the
    fork works, else a fresh schema on the service with copies of `scan` and `measures`. Yields (con, schema, how)."""
    if configured():
        yielded = False
        try:
            with forker(step) as f:
                try:
                    c = connect(f["url"])
                except Exception as e:  # noqa: BLE001 - READY before it takes connections: fall back like any fork failure
                    raise ForkError(f"the fork did not accept a connection ({type(e).__name__})") from None
                try:
                    yielded = True
                    yield c, "threshold", {"mode": "fork", "service": f["name"], "seconds": f["seconds"]}
                finally:
                    c.close()
                return
        except ForkError as e:
            if yielded:
                raise
            step(f"No fork ({e}); using a scenario schema instead")
    if not db.url():
        raise ForkError("no facts database is configured (TIGER_DATABASE_URL)")
    schema = f"whatif_{secrets.token_hex(4)}"
    c = connect(db.url())
    try:
        c.run(f"CREATE SCHEMA {schema}")
        c.run(f"CREATE TABLE {schema}.scan AS SELECT sid, kind, city, walls FROM threshold.scan")  # only what is read
        c.run(f"CREATE TABLE {schema}.measures AS SELECT * FROM threshold.measures")
        step(f"Copied scan and measures into the scenario schema {schema}")
        yield c, schema, {"mode": "schema", "service": schema, "seconds": None}
    finally:
        try:
            c.run(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
            step(f"Dropped the scenario schema {schema}")
        finally:
            c.close()


READY = f"m.bath_route_door >= {DOOR_M} AND m.bath_turn >= {TURN_M} AND m.step_free_bath = 1"


def _count(c, s: str, city: str | None, kind: str | None) -> dict:
    sql = (f"SELECT count(*) AS homes, count(*) FILTER (WHERE {READY}) AS ready FROM {s}.measures m "
           f"JOIN {s}.scan c USING (sid) WHERE c.walls AND m.bathrooms >= 1 AND c.city IS NOT DISTINCT FROM CAST(:city AS text) "
           f"AND c.kind IS NOT DISTINCT FROM CAST(:kind AS text)")
    return {**_rows(c, sql, city=city, kind=kind)[0], "sql": sql}


def city_scenario(plan: dict, after: dict, step: Step = lambda s: None, **kw) -> dict:
    """The renovated home as a row, and the city-wide count before and after widening doors, on a throwaway copy."""
    from ..tools.measure_search import table as mt
    base, sid = (after.get("whatif") or {}).get("base") or plan["sid"], after["sid"]
    measured = mt.measure(after)
    t0 = time.time()
    try:
        with scenario(step, **kw) as (c, s, how):
            row = _rows(c, f"SELECT city, kind FROM {s}.scan WHERE sid = :sid", sid=base)
            city, kind = (row[0]["city"], row[0]["kind"]) if row else (plan.get("city"), None)
            before = _count(c, s, city, kind)
            if row:
                c.run(f"INSERT INTO {s}.scan (sid, kind, city, walls) SELECT :w, kind, city, walls FROM {s}.scan "
                      f"WHERE sid = :b", w=sid, b=base)
                cols = [k for k in mt.FIELDS if k in measured and measured[k] is not None]
                whole = {k: int(v) if mt.FIELDS[k][2] in ("count", "flag") and isinstance(v, float) else v
                         for k, v in measured.items() if k in cols}
                c.run(f"INSERT INTO {s}.measures (sid, {', '.join(cols)}) VALUES (:sid, "
                      + ", ".join(f":{k}" for k in cols) + ")", sid=sid, **whole)
                step(f"Added the renovated home {sid} as a row beside {base}")
            mine = _rows(c, f"SELECT sid, ({READY}) AS ready FROM {s}.measures m WHERE sid IN (:b, :w)", b=base, w=sid)
            upd = (f"UPDATE {s}.measures SET bath_route_door = {WIDENED_M} WHERE bath_route_door < {DOOR_M} "
                   f"AND step_free_bath = 1 AND sid IN (SELECT sid FROM {s}.scan WHERE city IS NOT DISTINCT FROM CAST(:city AS text))")
            joined = _count(c, s, city, kind)
            c.run(upd, city=city)
            widened = _count(c, s, city, kind)
            step(f"{before['ready']} of {before['homes']} homes ready now; {widened['ready']} with the doors widened")
    except Exception as e:  # noqa: BLE001 - any database failure: the renovation still stands
        return {"available": False, "reason": f"The city-wide scenario did not run: {type(e).__name__}: {e}"[:300]}
    ready = {r["sid"]: bool(r["ready"]) for r in mine}
    return {"available": True, **how, "city": city, "kind": kind, "homes": before["homes"],
            "ready_now": before["ready"], "with_renovation": joined["ready"], "after": widened["ready"], "base_ready": ready.get(base),
            "renovated_ready": ready.get(sid), "ms": round(1000 * (time.time() - t0)),
            "label": f"{kind or 'homes'} in {city or 'this city'} with a wheelchair-ready bathroom if the doors on "
                     "the way were widened to 36 in",
            "note": f"Measures table on a {'zero-copy fork of the Tiger Cloud service' if how['mode'] == 'fork' else 'scenario schema copy'}"
                    f", deleted after. Ready: doors on the route {DOOR_M} m clear, a {TURN_M} m circle, no step. "
                    "Widening every narrow door on the route is an upper bound for one door.",
            "sql": [before["sql"], upd]}
