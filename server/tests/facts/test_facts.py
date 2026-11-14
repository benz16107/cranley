"""The facts database against a throwaway Postgres (TIGER_TEST_DATABASE_URL), with hand-made scans only.
Skipped when no test database is configured or reachable. The schema is dropped and rebuilt for the module."""
import json
import math
import random

import pg8000.native
import pytest

from tests.tools.conftest import make_home, no_walls
from threshold.config import env
from threshold.facts import ask, census, db, flood, record, search
from threshold.facts.load import FACT_COLS, copy
from threshold.tools.measure_search import table as mt

TEST_URL = env().get("TIGER_TEST_DATABASE_URL")
HOU = (29.7600, -95.3700)


def _point(lat, lon):
    return f"SRID=4326;POINT({lon} {lat})"


@pytest.fixture(autouse=True)
def test_database(monkeypatch):
    """Overrides the root conftest's blank URL with the test database for each test here."""
    if TEST_URL:
        monkeypatch.setenv("TIGER_DATABASE_URL", TEST_URL)


@pytest.fixture(scope="module")
def schema():
    if not TEST_URL:
        pytest.skip("TIGER_TEST_DATABASE_URL is not set")
    mp = pytest.MonkeyPatch()
    mp.setenv("TIGER_DATABASE_URL", TEST_URL)
    try:
        db.con()
    except Exception as e:  # noqa: BLE001
        mp.undo()
        pytest.skip(f"test database not reachable: {e}")
    db.drop_all(target="test")
    db.migrate()
    home, bare = make_home("hand_a"), no_walls("hand_b")
    m_a, m_b = mt.measure(home), mt.measure(bare)
    with db.transaction() as c:
        copy(c, "building", ["id", "address", "city", "zip", "property_type", "geom"],
             [["b1", "1 Made Up St", "Houston", "77001", "home", _point(*HOU)],
              ["b2", "2 Made Up St", "Houston", "77002", "apartment community", _point(29.80, -95.37)]])
        # hand_a 1 km from HOU, hand_b 4.4 km, hand_c in Los Angeles
        copy(c, "scan", ["sid", "building_id", "name", "kind", "city", "zip", "geom", "walls"],
             [["hand_a", "b1", "A", "house", "Houston", "77001", _point(HOU[0] + 0.009, HOU[1]), True],
              ["hand_b", "b2", "B", "apartment_unit", "Houston", "77002", _point(29.80, -95.37), False],
              ["hand_c", "b2", "C", "apartment_unit", "Los Angeles", "90001", _point(34.05, -118.25), True]])
        cols = ["sid"] + list(mt.FIELDS)
        rows = [["hand_a"] + [m_a[k] for k in mt.FIELDS], ["hand_b"] + [m_b[k] for k in mt.FIELDS],
                ["hand_c"] + [m_a[k] for k in mt.FIELDS]]
        copy(c, "measures", cols, [[int(v) if isinstance(v, float) and mt.FIELDS.get(k, ("", "", ""))[2] in ("count", "flag")
                                    else v for k, v in zip(cols, r)] for r in rows])
        copy(c, "room", ["sid", "room", "label", "area", "turn_diameter"],
             [["hand_a", "K", "Kitchen", 14.0, 1.6], ["hand_a", "T", "Bathroom", 6.0, 1.2],
              ["hand_c", "K", "Kitchen", 9.0, 1.7], ["hand_c", "L", "Living Room", 20.0, 3.0]])
    yield {"home": home, "measures": m_a}
    db.drop_all(target="test")
    mp.undo()


def test_search_matches_sqlite_and_adds_distance_and_rooms(schema, tmp_path):
    crit = [mt.parse("bath_route_door>=0.81"), mt.parse("bedrooms>=2")]
    pg = search.search(crit)
    rows = [({"sid": s, "name": s, "kind": k, "city": c, "lat": 0, "lon": 0, "walls": w, **m}, [])
            for s, k, c, w, m in (("hand_a", "house", "Houston", 1, schema["measures"]),
                                  ("hand_b", "apartment_unit", "Houston", 0, mt.measure(no_walls("hand_b"))),
                                  ("hand_c", "apartment_unit", "Los Angeles", 1, schema["measures"]))]
    f = tmp_path / "m.sqlite"
    mt.write(rows, {"scans": 3}, f)
    lite = mt.search(crit, path=f)
    assert (pg["pool"], pg["answerable"], pg["matches"]) == (lite["pool"], lite["answerable"], lite["matches"]) == (3, 2, 2)
    assert pg["rows"][0]["why"][0] == lite["rows"][0]["why"][0] == "Doors to the bathroom 0.90 m >= 0.81 m"
    near = search.search(crit, near=HOU, within_m=2000)
    assert [r["sid"] for r in near["rows"]] == ["hand_a"] and 950 < near["rows"][0]["distance_m"] < 1050
    kitchens = search.search([], rooms=[{"label": "kitchen", "where": [{"measure": "area", "op": ">=", "value": 12}]}])
    assert [r["sid"] for r in kitchens["rows"]] == ["hand_a"]
    with pytest.raises(ValueError):
        mt.search(crit, path=f, within_m=10)  # the SQLite fallback cannot measure distance


def test_measure_search_tool_runs_on_postgres(schema):
    from threshold.tools import run_tool
    r = run_tool("measure_search", {"criteria": [{"measure": "bath_route_door", "op": ">=", "value": 0.81}],
                                    "near": list(HOU), "within_km": 2})
    assert r.scope.sid == "hand_a" and r.checks[0].rule.endswith("1.0 km away")


def test_tool_results_become_facts_and_rollups_see_them_at_once(schema):
    result = {"scope": {"sid": "hand_a"},
              "metrics": [{"id": "rooms_ok", "label": "Rooms OK", "value": 3, "unit": "", "source":
                           {"layer": "matterport", "method": "geometry", "confidence": "high"}}],
              "checks": [{"id": "turn.T1abc2345678", "rule": "Turn in T", "measured": 1.2, "threshold": 1.525,
                          "unit": "m", "status": "fail", "standard": "ADA 304.3", "findings": ["f1"]},
                         {"id": "smoke_alarms", "rule": "Smoke alarms seen", "measured": 2, "threshold": None,
                          "unit": "", "status": "pass", "findings": []}],
              "findings": [{"id": "f1", "anchor": {"sid": "hand_a", "room": "T"}, "source":
                            {"layer": "matterport", "method": "geometry", "confidence": "medium"}}],
              "overlays": [{"kind": "lens", "values": {"K": 4.5, "T": 0.0}, "ramp": "sequential",
                            "legend": {"title": "Sun hours", "unit": "h", "min": 0, "max": 5}}]}
    rows = record.fact_rows("risk_sheet", result)
    fields = sorted(r[FACT_COLS.index("field")] for r in rows)
    assert fields == ["risk_sheet.check.smoke_alarms", "risk_sheet.check.turn", "risk_sheet.lens.sun_hours",
                      "risk_sheet.lens.sun_hours", "risk_sheet.rooms_ok"]
    turn = next(r for r in rows if r[FACT_COLS.index("field")] == "risk_sheet.check.turn")
    assert turn[FACT_COLS.index("room")] == "T" and turn[FACT_COLS.index("record_path")] == "ADA 304.3"
    assert record.fact_rows("x", {"scope": {"sids": ["a", "b"]}, "metrics": result["metrics"]}) == []
    record.record_result("risk_sheet", result)
    record.record_result("risk_sheet", {**result, "scope": {"sid": "not_in_the_database"}})
    record.flush()
    got = db.rows("SELECT field, room, city, kind, property_type FROM fact WHERE tool = 'risk_sheet' ORDER BY field, room")
    assert len(got) == 5 and {g["city"] for g in got} == {"Houston"} and got[0]["property_type"] == "home"
    # the continuous aggregate is real time: the census sees the fact without a refresh
    res = census.preset("smoke_alarms", min_scans=1)
    assert res["rows"] == [{"grp": "b1", "scans": 1, "share": 1.0, "mean": 2.0, "median": 2.0}]
    # a later observation replaces the earlier one in the census, and both stay in the history
    later = {**result, "checks": [{**result["checks"][1], "measured": 0}]}
    record.record_result("risk_sheet", later)
    record.flush()
    assert census.preset("smoke_alarms", min_scans=1)["rows"][0]["share"] == 0.0
    assert len(census.history("hand_a", "risk_sheet.check.smoke_alarms")) == 2


def test_op_log_rows(schema):
    entry = {"seq": 3, "at": 1_763_000_000.0, "op": {"op": "run.finish", "by": "agent", "id": "r1",
                                                     "result": {"tool": "daylight"}}, "undo": None, "cause": None}
    row = record.op_row("ws1", entry)
    assert row[1:6] == ["ws1", 3, "run.finish", "agent", "daylight"]
    record.record_op("ws1", entry)
    record.flush()
    assert db.rows("SELECT ops FROM ops_hourly WHERE op = 'run.finish'")[0]["ops"] == 1


def test_read_only_sql_refuses_writes_at_every_layer(schema):
    r = ask.run("SELECT kind, count(*) AS n FROM scan GROUP BY kind ORDER BY kind")
    assert r["columns"] == ["kind", "n"] and r["rows"] == [["apartment_unit", 2], ["house", 1]]
    for bad in ("DELETE FROM scan", "SELECT 1; DELETE FROM scan", "WITH x AS (DELETE FROM scan RETURNING *) SELECT 1",
                "SELECT set_config('role', 'postgres', false)", "SELECT * FROM pg_authid"):
        with pytest.raises(ValueError):
            ask.run(bad)
    # below the statement check, the role itself cannot write or become the owner
    c = ask._reader["con"]
    for sql in ("SELECT set_config('role', 'postgres', false)", "INSERT INTO meta VALUES ('x', '1')"):
        with pytest.raises(pg8000.native.DatabaseError):
            c.run(sql)
        c.run("ROLLBACK")
    assert db.rows("SELECT count(*) AS n FROM scan")[0]["n"] == 3


def test_flood_runs_store_depth_series(schema):
    from datetime import UTC, datetime

    from tests.geometry.conftest import _plan
    plan = {**_plan(), "sid": "hand_a"}  # the water engine's test plan: room C sits behind a 0.2 m sill
    rows = flood.simulate(plan, datetime(2026, 11, 14, tzinfo=UTC))
    levels = sorted({r[5] for r in rows})
    assert levels[0] == 0.0 and math.isclose(levels[-1], 2.0) and len(levels) == 41
    with db.transaction() as c:
        copy(c, "flood_run", ["run", "sid", "started"], [[rows[0][1], "hand_a", "2026-11-14T00:00:00+00:00"]])
        copy(c, "flood_depth", ["ts", "run", "sid", "room", "label", "level_m", "depth_m", "wet_area_m2"], rows)
    wet = {float(r["level_m"]): r for r in flood.wet_at([0.1, 0.5])}
    assert wet[0.1]["houses"] == 1 and (wet[0.1]["rooms_wet"], wet[0.5]["rooms_wet"], wet[0.5]["rooms"]) == (2, 3, 4)
    c = {float(r["level_m"]): float(r["depth_m"]) for r in db.rows(
        "SELECT level_m, depth_m FROM flood_depth WHERE room = 'C' AND level_m IN (0.1, 0.5)")}
    assert c[0.1] == 0 and c[0.5] == pytest.approx(0.5)


def test_similar_rooms_uses_diskann_with_label_filter(schema):
    from threshold.facts import rooms
    rnd = random.Random(1)
    base = [rnd.gauss(0, 1) for _ in range(384)]
    vecs = {("hand_a", "K"): base, ("hand_c", "K"): [x + rnd.gauss(0, 0.3) for x in base],
            ("hand_c", "L"): [x + rnd.gauss(0, 0.1) for x in base], ("hand_a", "T"): [rnd.gauss(0, 1) for _ in range(384)]}
    with db.transaction() as c:
        c.run("INSERT INTO room_type VALUES (1, 'Kitchen'), (2, 'Living Room'), (3, 'Bathroom')")
        for (sid, room), v in vecs.items():
            lab = {"K": 1, "L": 2, "T": 3}[room]
            c.run("INSERT INTO room_text (sid, room, pano, description, features, embedding, labels) VALUES "
                  "(:s, :r, 'p', :d, ARRAY['island'], CAST(:v AS vector), ARRAY[CAST(:l AS smallint)])",
                  s=sid, r=room, d=f"A sunny room {room} with an island", v=rooms.vec(v), l=lab)
    res = rooms.similar(like=("hand_a", "K"), label="Kitchen")
    assert [(r["sid"], r["room"]) for r in res["rows"]] == [("hand_c", "K")]  # the closer Living Room is filtered out
    res = rooms.similar(like=("hand_a", "K"), min_area=15, words=0.5)
    assert [(r["sid"], r["room"]) for r in res["rows"]] == [("hand_c", "L")] and res["rows"][0]["bm25"] is not None
    plan = db.rows("EXPLAIN (FORMAT JSON) SELECT sid FROM room_text ORDER BY embedding <=> "
                   "(SELECT embedding FROM room_text LIMIT 1) LIMIT 2")[0]
    assert "room_text_embedding" in json.dumps(plan)


def test_drop_all_leaves_nothing(schema):
    db.drop_all(target="test")
    assert db.rows("SELECT to_regclass('threshold.fact') IS NULL AS gone")[0]["gone"]
    assert not db.rows("SELECT 1 FROM pg_roles WHERE rolname = 'threshold_reader' AND rolcanlogin")
    db.migrate()  # the module fixture drops again at the end
