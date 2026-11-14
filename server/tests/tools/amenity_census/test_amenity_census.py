from threshold.tools import ToolContext, run_tool
from threshold.tools import amenity_census as ac
from threshold.tools.room_labeller import facts


def test_claims_from_titles_and_captions():
    assert ac.claimed("Fitness Center Featuring Cardio") == {"fitness center"}
    assert ac.claimed("Pool + Clubroom") == {"pool", "lounge or clubroom"}
    assert ac.claimed("Package Services") == {"mail or package room"}
    assert ac.claimed("2BR, 2BA - 1,052SF") == set()


def test_seen_against_claimed(monkeypatch):
    names = {"g": "Fitness Center", "p": "Pool", "u": "2BR, 1BA"}
    monkeypatch.setattr(ac.costar, "scans_of_property", lambda pid: list(names))
    monkeypatch.setattr(ac.costar, "joins", lambda: {"property_address": {7: "1 Test St"}})
    monkeypatch.setattr(ac.costar, "get", lambda ds, pid: {"attachments": [{"caption": "Dog Park"}], "amenities": [1, 2]})
    monkeypatch.setattr(facts, "scan_name", names.get)
    monkeypatch.setattr(facts, "scan_kind", lambda s: "apartment_unit" if s == "u" else "amenity")
    seen = {"g": [{"amenity": "fitness center", "sid": "g", "room": "r", "label": "gym", "confidence": "high",
                   "reason": "Treadmills.", "evidence": {"sid": "g", "pano": "x", "face": 1}, "counts": {"treadmill": 3}}],
            "p": [{"amenity": "lounge or clubroom", "sid": "p", "room": "r", "label": "lounge or clubroom", "confidence": "medium",
                   "reason": "Sofas.", "evidence": None, "counts": {}}]}
    monkeypatch.setattr(ac, "read_scan", lambda ctx, s, count: seen.get(s, []))
    looked = []
    monkeypatch.setattr(ac, "look_for", lambda ctx, s, am: looked.append((s, am)))  # the Pool tour shows no pool
    res = run_tool("amenity_census", {"property": 7}, ToolContext())
    st = {c.id: c.status for c in res.checks}
    assert st == {"claim.fitness_center": "pass", "claim.pool": "warn", "claim.dog_park_or_pet_spa": "unknown"}
    m = {x.id: x.value for x in res.metrics}
    assert m["count.treadmill"] == 3 and m["confirmed"] == 1
    assert "Not in the listing: lounge or clubroom" in res.verdict.text
    assert looked == [("p", "pool")]  # only a read tour titled for a missing amenity is searched
