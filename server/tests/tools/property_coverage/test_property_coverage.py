from threshold.tools import Site, ToolContext, run_tool
from threshold.tools.places import default_site
from threshold.tools.types import Place


def site(place, record):
    return Site(place, 29.7, -95.4, "1 Test St", "Houston", None, ["h1"], "test",
                [{"sid": "h1", "name": "1 Test St", "kind": "house"}], record)


def test_a_place_with_no_record_is_not_applicable():
    res = run_tool("property_coverage", {"place": {"scan": "h1"}}, ToolContext(sites=lambda p: site(p, None)))
    assert res.verdict.status == "unknown" and "no CoStar property record" in res.verdict.text and not res.checks


def test_a_record_lists_shared_spaces():
    res = run_tool("property_coverage", {"place": {"scan": "h1"}}, ToolContext(sites=lambda p: site(p, {"id": 1})))
    assert res.verdict.status == "warn" and any(c.id.startswith("area.") for c in res.checks)


def test_a_phone_scan_resolves_without_a_location(monkeypatch):
    from threshold.sources import index
    monkeypatch.setattr(index, "rows", lambda: {})
    s = default_site(Place(scan="u_000000000000"))
    assert s.lat is None and s.sids == ["u_000000000000"]
