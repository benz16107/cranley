"""market_comps and the kit rows, with hand-made records (no sponsor data)."""
from threshold.tools import Site, ToolContext, run_tool
from threshold.tools.market_comps import kit


def lease(rate, basis=2, sf=10000, service=13, ltype=14, status=1, off=None):
    return {"id": 9, "listingType": ltype, "listingStatus": status, "forLeaseSummary": {
        "askingRateMeasurementType": 1, "spaces": [{"rateLow": rate, "rateHigh": rate, "rateBasis": basis, "squareFeetMax": sf,
                                                    "serviceType": service, "monetaryUnit": 1, "dateOffMarket": off}]}}


def prop(pid, lat, lon, rba, ptype=2, cls=2, year=1990):
    return {"id": pid, "propertyType": ptype, "buildingClass": cls, "rentableBuildingAreaSquareFeet": rba,
            "primaryAddress": {"streetNumber": str(pid), "streetName": "Test", "streetType": "St", "city": "Houston",
                               "latitude": lat, "longitude": lon},
            "constructionEvents": [{"eventType": 2, "year": year}],
            "propertyIndustrial": {"structural": {"ceilingHeightFeet": 24, "ceilingHeightInches": 6}, "numExternalLoadingDocks": 4}}


def test_rents_normalise_monthly_and_drop_zero_and_off_market():
    r = kit.rents([lease(1.0, basis=1), lease(0), lease(12, off="2026-01-01"), lease(9, status=3)])
    assert [x["rate"] for x in r] == [12.0]


def test_sales_keep_single_property_sales_with_price_per_ft2():
    comps = [{"id": 1, "soldForPrice": 1_000_000, "salePriceStatus": 3, "soldDate": "2020-05-01T00:00", "monetaryUnit": 1,
              "entities": [{"propertyId": 7, "assetType": 1, "totalSquarefeet": 20000}]},
             {"id": 2, "soldForPrice": 9_000_000, "salePriceStatus": 8, "soldDate": "2021-01-01", "monetaryUnit": 1,
              "entities": [{"propertyId": 7, "assetType": 1}, {"propertyId": 8, "assetType": 1}]}]
    s = kit.sales(7, comps, 25000)
    assert len(s) == 1 and s[0]["psf"] == 50.0 and s[0]["status"] == "confirmed"


def test_summary_reads_industrial_facts():
    row = kit.summarize(prop(1, 29.7, -95.4, 50000), [lease(10)], [])
    assert row["clear_ft"] == 24.5 and row["docks"] == 4 and row["class"] == "B" and kit.asking_rent(row)["rate"] == 10


def rows():
    out = {1: kit.summarize(prop(1, 29.70, -95.40, 50000), [lease(12)], [])}
    for i, (dlat, rate) in enumerate([(0.01, 8), (0.02, 10), (0.03, 9), (0.5, 20)], start=2):
        out[i] = kit.summarize(prop(i, 29.70 + dlat, -95.40, 60000), [lease(rate)], [])
    out[9] = kit.summarize(prop(9, 29.705, -95.40, 50000, ptype=5), [lease(30)], [])  # an office: not a comp
    out[10] = kit.summarize(prop(10, 29.705, -95.40, 900000), [lease(5)], [])           # too big
    return out


def test_comps_are_same_type_similar_size_and_near(monkeypatch):
    monkeypatch.setattr(kit, "rows", rows)
    monkeypatch.setattr(kit, "row", lambda pid: rows().get(pid))
    ctx = ToolContext(sites=lambda p: Site(p, 29.70, -95.40, "1 Test St", "Houston", 1, [], "test"))
    res = run_tool("market_comps", {"place": {"property_id": 1}}, ctx)
    m = {x.id: x.value for x in res.metrics}
    assert m["comps"] == 3 and m["median_rent"] == 9 and m["subject_rent"] == 12
    assert "c9/rent" not in m and "c10/rent" not in m and "c5/rent" not in m
    assert res.verdict.status == "warn" and "above" in res.verdict.text
    assert any(f.id.endswith(":limits") for f in res.findings)


def test_a_bare_point_needs_a_type(monkeypatch):
    monkeypatch.setattr(kit, "rows", rows)
    monkeypatch.setattr(kit, "row", lambda pid: None)
    ctx = ToolContext(sites=lambda p: Site(p, 29.70, -95.40, None, None, None, [], "point given"))
    res = run_tool("market_comps", {"place": {"geo": [-95.4, 29.7]}}, ctx)
    assert res.verdict.status == "unknown" and "which type" in res.verdict.text
    res = run_tool("market_comps", {"place": {"geo": [-95.4, 29.7]}, "property_type": "industrial", "size_sf": 55000}, ctx)
    assert {x.id: x.value for x in res.metrics}["comps"] == 4  # property 1 is a comp of a bare point
