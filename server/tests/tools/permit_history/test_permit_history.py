"""permit_history: permits at the address told from those nearby, counted by year and type; code cases matched on the
street. No network."""
from tests.datalayers.conftest import by_url, fake_site, offline, row  # noqa: F401
from threshold.layers import lookup
from threshold.tools import run_tool
from threshold.tools.permit_history import street_parts

PERMITS = [
    {"permit_nbr": "1", "primary_address": "123 N MAIN ST", "permit_type": "Bldg-Alter/Repair", "issue_date": "2024-03-01T00:00:00",
     "lat": "34.05", "lon": "-118.25", "valuation": "5000"},
    {"permit_nbr": "2", "primary_address": "131 N MAIN ST", "permit_type": "Bldg-New", "issue_date": "2025-06-01T00:00:00",
     "lat": "34.0505", "lon": "-118.2505"},
]


def test_street_parts():
    assert street_parts("123 N MAIN ST, LOS ANGELES, CA") == {"stno": "123", "predir": "N", "stname": "MAIN"}
    assert street_parts("Somewhere") is None


def test_la_permits_and_cases(offline):  # noqa: F811
    def socrata(domain, ds, params, ttl_s=0):
        if ds == "pi9x-tg5x":
            return PERMITS
        if ds == "u82d-eh7z":
            return [{"apno": "9", "stno": "123", "predir": "N", "stname": "MAIN", "aptype": "GENERAL", "adddttm": "2023-01-01"}]
        return []
    offline.setattr(lookup, "socrata", socrata)
    r = run_tool("permit_history", {"place": {"geo": [-118.25, 34.05]}}, fake_site(-118.25, 34.05, "123 N Main St, Los Angeles"))
    m = {x.id: x.value for x in r.metrics}
    assert m["permits_here"] == 1 and m["permits_near"] == 2 and m["cases_here"] == 1 and m["new_buildings_near"] == 1
    assert m["year.2024"] == 1 and m["year.2025"] == 1
    assert r.verdict.status == "warn"  # an open case


def test_houston_reads_311(offline):  # noqa: F811
    offline.setattr(lookup, "arcgis_at", by_url({"HOUSTON311": [row(CASE_NUMBER="1", CASE_TYPE="Nuisance On Property", STATUS="Open"),
                                                                row(CASE_NUMBER="2", CASE_TYPE="Traffic Signals", STATUS="Open")]}))
    r = run_tool("permit_history", {"place": {"geo": [-95.37, 29.76]}}, fake_site(-95.37, 29.76))
    m = {x.id: x.value for x in r.metrics}
    assert m == {"requests_near": 2, "code_requests_near": 1} and r.verdict.status == "unknown"
