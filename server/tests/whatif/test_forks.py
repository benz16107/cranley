"""Fork scenarios: the Tiger API is mocked, the SQL runs on a database of its own made for this module in the local
test server (TIGER_TEST_DATABASE_URL), never on the cloud service."""
import secrets
from urllib.parse import urlparse, urlunparse

import httpx
import pg8000.native
import pytest

from tests.whatif.conftest import make_flat
from threshold.config import env
from threshold.facts import db, forks
from threshold.tools.measure_search import table as mt
from threshold.whatif import apply

TEST_URL = env().get("TIGER_TEST_DATABASE_URL")


@pytest.fixture(scope="module")
def own_db():
    if not TEST_URL:
        pytest.skip("TIGER_TEST_DATABASE_URL is not set")
    if not db.is_local(TEST_URL):
        pytest.fail("TIGER_TEST_DATABASE_URL must name a local database")
    name = f"threshold_whatif_{secrets.token_hex(3)}"
    try:
        admin = pg8000.native.Connection(**db._params(TEST_URL))
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"test database not reachable: {e}")
    admin.run(f"CREATE DATABASE {name}")  # a database of our own: the facts tests drop and rebuild theirs
    url = urlunparse(urlparse(TEST_URL)._replace(path=f"/{name}"))
    mp = pytest.MonkeyPatch()
    mp.setenv("TIGER_DATABASE_URL", url)
    mp.setattr(db, "_down_until", 0.0)
    try:
        db.migrate()
        c = db.con()
        flat = make_flat()
        m = mt.measure(flat)
        for sid, city in (("flat", "Los Angeles"), ("other", "Los Angeles"), ("hou", "Houston")):
            c.run("INSERT INTO scan (sid, name, kind, city, walls) VALUES (:s, 'x', 'apartment_unit', :c, true)",
                  s=sid, c=city)
            cols = [k for k in mt.FIELDS if m.get(k) is not None]
            vals = {k: int(m[k]) if mt.FIELDS[k][2] in ("count", "flag") else m[k] for k in cols}
            c.run(f"INSERT INTO measures (sid, {', '.join(cols)}) VALUES (:sid, {', '.join(':' + k for k in cols)})",
                  sid=sid, **vals)
        c.close()
        db._local.con = None
        yield url
    finally:
        mp.undo()
        admin.run("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = :n AND pid <> pg_backend_pid()", n=name)
        admin.run(f"DROP DATABASE IF EXISTS {name}")
        admin.close()


@pytest.fixture
def renovated():
    flat = make_flat()
    after, _ = apply(flat, [{"op": "widen_door", "opening": "LT", "width_m": 0.915},
                            {"op": "move_wall", "wall": "tc", "offset_m": 0.25, "grow": "T"}])
    return flat, after


def test_without_a_key_the_scenario_runs_in_a_schema_that_is_dropped(own_db, renovated, monkeypatch):
    monkeypatch.setenv("TIGER_DATABASE_URL", own_db)
    monkeypatch.setenv("TIGER_ACCESS_KEY", "")
    steps = []
    r = forks.city_scenario(*renovated, steps.append)
    assert r["available"], r
    assert r["mode"] == "schema" and r["homes"] == 2 and r["ready_now"] == 0  # the flat fails as it is
    assert r["base_ready"] is False and r["renovated_ready"] is True
    assert r["with_renovation"] == 1  # the renovated copy joins the ready homes
    assert r["after"] == 1  # widening doors alone does not give the other flat a turning circle
    c = forks._connect(own_db)
    left = c.run("SELECT count(*) FROM information_schema.schemata WHERE schema_name LIKE 'whatif_%'")[0][0]
    n = c.run("SELECT count(*) FROM threshold.measures")[0][0]
    c.close()
    assert left == 0 and n == 3  # nothing changed on the service itself


def _tiger(calls, ready_after=1):
    state = {"polls": 0}

    def handle(req: httpx.Request):
        calls.append((req.method, req.url.path))
        if req.method == "GET" and req.url.path.endswith("/services/svc"):
            return httpx.Response(200, json={"region_code": "us-east-1", "resources": [{"spec": {"cpu_millis": 500, "memory_gbs": 2}}]})
        if req.method == "POST":
            body = req.read()
            assert b'"fork_strategy":"NOW"' in body.replace(b" ", b"")
            return httpx.Response(202, json={"service_id": "fk1", "status": "QUEUED", "initial_password": "pw"})
        if req.method == "GET":
            state["polls"] += 1
            ok = state["polls"] >= ready_after
            return httpx.Response(200, json={"status": "READY" if ok else "CONFIGURING",
                                             "endpoint": {"host": "fk1.proj.tsdb.cloud.timescale.com", "port": 3}})
        return httpx.Response(202)
    return httpx.Client(base_url="https://api.test", transport=httpx.MockTransport(handle))


def test_with_a_key_the_scenario_runs_on_a_fork_that_is_deleted(own_db, renovated, monkeypatch):
    monkeypatch.setenv("TIGER_DATABASE_URL", own_db)
    monkeypatch.setenv("TIGER_ACCESS_KEY", "k")
    monkeypatch.setenv("TIGER_SECRET_KEY", "s")
    monkeypatch.setattr(forks, "ids", lambda url=None: ("proj", "svc"))
    calls, urls = [], []
    client = _tiger(calls, ready_after=2)

    def connect(url):
        urls.append(url)
        return forks._connect(own_db)  # the "fork" is our own throwaway database
    r = forks.city_scenario(*renovated, connect=connect,
                            forker=lambda step: forks.fork(step, client=client, sleep=lambda s: None))
    assert r["available"] and r["mode"] == "fork", r
    assert urls[0].startswith("postgresql://") or "@fk1.proj.tsdb.cloud.timescale.com:3" in urls[0]
    assert ("DELETE", "/projects/proj/services/fk1") in calls
    assert r["renovated_ready"] is True


def test_a_fork_that_never_starts_is_still_deleted(monkeypatch):
    monkeypatch.setattr(forks, "ids", lambda url=None: ("proj", "svc"))
    monkeypatch.setattr(forks, "READY_TIMEOUT_S", -1)
    calls = []
    with pytest.raises(forks.ForkError, match="not ready"):
        with forks.fork(client=_tiger(calls, ready_after=99), sleep=lambda s: None):
            pass
    assert calls[-1] == ("DELETE", "/projects/proj/services/fk1")


def test_ids_from_a_cloud_host():
    assert forks.ids("postgres://u:p@abcdefghij.klmnopqrst.tsdb.cloud.timescale.com:3/tsdb") == ("klmnopqrst", "abcdefghij")
    assert forks.ids("postgres://u:p@127.0.0.1:5544/x") is None
