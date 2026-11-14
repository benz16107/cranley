"""Rate limit and retry, the disk cache, name checks, the splat's Range handling, and the scan index."""
import csv
import threading
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from threshold.api import data as api
from threshold.api.app import app
from threshold.sources import hackathon, index, upstream


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setattr(upstream, "CACHE", tmp_path / "cache")
    monkeypatch.setattr(upstream.time, "sleep", lambda s: None)  # no real backoff or rate waiting
    return tmp_path / "cache"


def client_with(monkeypatch, handler):
    monkeypatch.setattr(upstream, "_client", httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True))


def test_retries_429_and_5xx_then_succeeds(cache, monkeypatch):
    seen = []

    def handler(req):
        seen.append(1)
        return httpx.Response([429, 503, 200][len(seen) - 1], headers={"retry-after": "0"}, text="ok")

    client_with(monkeypatch, handler)
    assert upstream.send("GET", "https://x.test/a").text == "ok" and len(seen) == 3


def test_gives_up_after_the_retries_and_raises(cache, monkeypatch):
    client_with(monkeypatch, lambda req: httpx.Response(500))
    with pytest.raises(httpx.HTTPStatusError):
        upstream.send("GET", "https://x.test/a", retries=2)


def test_a_404_is_not_retried(cache, monkeypatch):
    n = []
    client_with(monkeypatch, lambda req: (n.append(1), httpx.Response(404))[1])
    with pytest.raises(httpx.HTTPStatusError):
        upstream.send("GET", "https://x.test/a")
    assert len(n) == 1


def test_slots_are_spaced_across_threads(monkeypatch):
    monkeypatch.setenv("THRESHOLD_RPS", "4")
    upstream._next_slot = 0.0
    slept = []
    monkeypatch.setattr(upstream.time, "sleep", slept.append)
    ts = [threading.Thread(target=upstream._wait_for_slot) for _ in range(4)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert len(slept) == 3 and abs(sorted(slept)[-1] - 0.75) < 0.1      # 4 callers at 4 per second: 0, 0.25, 0.5, 0.75 s


def test_cached_calls_make_once_and_survive_concurrency(cache):
    calls = []

    def make():
        calls.append(1)
        time.sleep(0)
        return b"bytes"

    p = cache / "a" / "b.bin"
    out = []
    ts = [threading.Thread(target=lambda: out.append(upstream.cached(p, make))) for _ in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert out == [b"bytes"] * 8 and len(calls) == 1 and p.read_bytes() == b"bytes"
    assert not list(p.parent.glob("*.tmp"))


@pytest.mark.parametrize("value,kind", [("../etc", "sid"), ("a/b", "id"), ("x" * 40, "sid"), ("..", "file"), ("a b", "id"), ("", "id"), ("abc", "sid")])
def test_names_that_reach_the_file_system_are_refused(value, kind):
    with pytest.raises(LookupError):
        upstream.check(value, kind)


def test_plain_names_pass():
    assert upstream.check("Abc123Xyz09", "sid") and upstream.check("1ab-2_c", "id") and upstream.check("DJI_0001_D.JPG", "file")


# --- Range ---
@pytest.mark.parametrize("header,want", [(None, None), ("bytes=0-99", (0, 99)), ("bytes=100-", (100, 999)), ("bytes=-50", (950, 999)),
                                         ("bytes=900-5000", (900, 999)), ("bytes=0-1,5-6", None), ("items=0-5", None), ("bytes=-", None)])
def test_byte_range_parsing(header, want):
    assert api._byte_range(header, 1000) == want


@pytest.mark.parametrize("header", ["bytes=1000-", "bytes=500-100", "bytes=5000-6000"])
def test_unsatisfiable_ranges(header):
    with pytest.raises(ValueError):
        api._byte_range(header, 1000)


def test_splat_route_serves_ranges_from_the_cache(cache, monkeypatch):
    body = bytes(range(256)) * 40
    (cache / "splat").mkdir(parents=True)
    (cache / "splat" / "AAAAAAAAAAA.ply").write_bytes(body)
    monkeypatch.setattr(hackathon, "splat_size", lambda sid: len(body))
    monkeypatch.setattr(hackathon, "_downloads", {})
    c = TestClient(app)
    r = c.get("/api/scan/AAAAAAAAAAA/splat", headers={"Range": "bytes=10-19"})
    assert r.status_code == 206 and r.content == body[10:20] and r.headers["content-range"] == f"bytes 10-19/{len(body)}"
    assert r.headers["accept-ranges"] == "bytes" and "content-encoding" not in r.headers
    assert c.get("/api/scan/AAAAAAAAAAA/splat").content == body
    assert c.get("/api/scan/AAAAAAAAAAA/splat", headers={"Range": "bytes=-5"}).content == body[-5:]
    assert c.head("/api/scan/AAAAAAAAAAA/splat").headers["content-length"] == str(len(body))
    r = c.get("/api/scan/AAAAAAAAAAA/splat", headers={"Range": "bytes=99999-"})
    assert r.status_code == 416 and r.headers["content-range"] == f"bytes */{len(body)}"


def test_splat_bytes_waits_for_a_download_in_progress(cache, monkeypatch):
    sid, total = "BBBBBBBBBBB", 3000
    (cache / "splat").mkdir(parents=True)
    part = cache / "splat" / f"{sid}.ply.part"
    part.write_bytes(b"a" * 1000)
    dl = hackathon._Download(total, got=1000)
    monkeypatch.setattr(hackathon, "_downloads", {sid: dl})
    monkeypatch.setattr(hackathon, "_ensure_splat", lambda s: dl)
    monkeypatch.setattr(hackathon.time, "sleep", lambda s: None)

    def finish():  # runs when the reader first has to wait
        with open(part, "ab") as f:
            f.write(b"b" * 2000)
        dl.got = total
        dl.done.set()

    real_sleep = []
    monkeypatch.setattr(hackathon.time, "sleep", lambda s: (real_sleep.append(s), finish() if len(real_sleep) == 1 else None)[1])
    got = b"".join(hackathon.splat_bytes(sid, 500, 1499))
    assert got == b"a" * 500 + b"b" * 500 and real_sleep                    # it had to wait for bytes 1000 to 1499


def test_splat_bytes_stops_when_the_download_failed(cache, monkeypatch):
    sid = "CCCCCCCCCCC"
    (cache / "splat").mkdir(parents=True)
    (cache / "splat" / f"{sid}.ply.part").write_bytes(b"a" * 100)
    dl = hackathon._Download(1000, got=100, error="boom")
    monkeypatch.setattr(hackathon, "_ensure_splat", lambda s: dl)
    assert b"".join(hackathon.splat_bytes(sid, 0, 999)) == b"a" * 100


# --- the scan index ---
@pytest.fixture
def small_index(tmp_path, monkeypatch):
    head = ["sid", "name", "segment", "lat", "lon", "latlon_source", "address", "city", "state", "postal_code", "internal_id",
            "costar_property_id", "homes_listing_id", "splat", "drone_photos", "pano_count", "room_count", "floor_count", "created",
            "defurnished", "ai_summary"]
    rows = [
        ["house0000001", "<address>", "residential", "29.6", "-95.1", "model", "<address>, Houston, TX, 77059, US", "Houston", "TX", "77059", "Homes-1", "", "111", "yes", "9", "100", "30", "2", "2026-11-09", "yes", "no"],
        ["unit0000001", "2BR, 2BA - 900SF", "commercial", "29.7", "-95.2", "model", "100 Main St, Houston, TX, 77001, US", "Houston", "TX", "77001", "Apartments-5", "5", "", "no", "", "20", "8", "1", "2026-11-09", "yes", "yes"],
        ["unit0000002", "1BR, 1BA - 700SF", "commercial", "29.7001", "-95.2001", "model", "100 Main Street Unit 4, Houston, TX, 77001, US", "Houston", "TX", "77001", "Apartments-5", "5", "", "no", "", "15", "6", "1", "2026-11-09", "yes", "yes"],
        ["gym00000001", "Fitness Center", "commercial", "29.7", "-95.2", "model", "US", "Houston", "TX", "", "Apartments-5", "", "", "no", "", "9", "2", "1", "2026-11-09", "yes", "no"],
        ["wh000000001", "Warehouse", "commercial", "34.0", "-118.2", "model", "9 Dock Rd, Los Angeles, CA, 90001, US", "Los Angeles", "CA", "90001", "", "", "", "no", "", "12", "3", "1", "2026-11-09", "no", "no"],
        ["nowhere0001", "Lobby", "commercial", "", "", "", "", "", "", "", "", "", "", "no", "", "3", "1", "1", "2026-11-09", "no", "no"],
    ]
    f = tmp_path / "models_index.csv"
    with open(f, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(head)
        w.writerows(rows)
    monkeypatch.setattr(index, "DATA", tmp_path)
    index.rows.cache_clear()
    yield
    index.rows.cache_clear()


def test_kind_guesses(small_index):
    assert {r["sid"]: r["kind"] for r in index.rows().values()} == {
        "house0000001": "house", "unit0000001": "apartment_unit", "unit0000002": "apartment_unit", "gym00000001": "amenity",
        "wh000000001": "warehouse", "nowhere0001": "amenity"}


def test_search_filters(small_index):
    assert index.search(splat=True)[1][0]["sid"] == "house0000001"
    assert index.search(kind="apartment_unit")[0] == 2
    assert index.search(city="los angeles")[1][0]["sid"] == "wh000000001"
    assert index.search(rooms_min=25)[0] == 1 and index.search(floors_min=2)[0] == 1
    assert index.search(defurnished=False)[0] == 2
    total, rows = index.search(q="bellwick houston")
    assert total == 1 and rows[0]["panos"] == 100 and rows[0]["drone_photos"] == 9 and rows[0]["lat"] == 29.6
    assert index.search(q="unit0000002")[1][0]["sid"] == "unit0000002"
    assert index.search(address="main st")[0] == 2 and index.search(q="nothing like this")[0] == 0
    assert index.search(limit=2, offset=4)[1] and len(index.search(limit=2)[1]) == 2 and index.search(limit=2)[0] == 6


def test_buildings_group_by_property_then_address_then_spot(small_index):
    b = {x["id"]: x for x in index.buildings()}
    assert sorted(len(x["scans"]) for x in b.values()) == [1, 1, 3]                  # nowhere0001 has no coordinates: not mapped; the gym joins the building at its spot
    assert {s["sid"] for s in b["p5"]["scans"]} == {"unit0000001", "unit0000002", "gym00000001"} and b["p5"]["property_id"] == 5
    assert b["p5"]["address"].startswith("100 Main")                               # a street address, not "US"
    regrouped = {x["id"] for x in index.buildings(lambda sid: 77 if sid.startswith("unit") else None)}
    assert "p77" in regrouped and "p5" not in regrouped


def test_scans_route(small_index):
    c = TestClient(app)
    d = c.get("/api/scans", params={"kind": "apartment_unit", "limit": 1}).json()
    assert d["total"] == 2 and len(d["scans"]) == 1
    assert c.get("/api/scans", params={"kind": "bogus"}).status_code == 422
    assert c.get("/api/scan/..%2Fetc/plan").status_code == 404
    assert c.get("/api/scan/short/plan").status_code == 404
