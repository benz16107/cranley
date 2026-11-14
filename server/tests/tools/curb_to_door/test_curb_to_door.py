from threshold.tools import ToolContext, run_tool
from tests.tools.conftest import make_home


def test_without_geocoordinates_it_says_so(ctx):
    assert run_tool("curb_to_door", {"scan": "home", "read_panoramas": False}, ctx).verdict.status == "unknown"


def test_distance_from_detections(monkeypatch):
    import threshold.tools.curb_to_door as c
    p = make_home("geo")
    p["geo"] = {"lat": 29.7, "lon": -95.4, "yaw_deg": 0.0, "translation": {"x": 0, "y": 0}}
    fake = {"counts": {"car": 1}, "source": None, "detections": [
        {"label": "car", "confidence": 0.9, "anchor": {"geo": [-95.4, 29.7 + 20 / 110574]}, "image": "ortho"}]}
    monkeypatch.setattr(c.aerial_detect, "detect", lambda *a, **k: fake)
    monkeypatch.setattr(c.site, "elevation_profile", lambda a, b, n: {"points": [{"ground_m": 10.0}, {"ground_m": 10.4}]})
    monkeypatch.setattr(c, "index_rows", lambda: {"geo": {"kind": "apartment_unit"}})
    r = run_tool("curb_to_door", {"scan": "geo", "read_panoramas": False}, ToolContext(plans=lambda s: p))
    m = {x.id: x.value for x in r.metrics}
    assert abs(m["parking_m"] - 20) < 0.5 and m["rise_m"] == 0.4
    assert "Low confidence" in r.verdict.text
