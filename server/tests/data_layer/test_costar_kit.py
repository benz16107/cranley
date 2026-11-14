"""The CoStar kit adapter, on a tiny made-up kit: password-protected zips, the offset index, the join, the record."""
import json
import shutil
import subprocess
import zipfile

import pyzipper
import pytest
from fastapi.testclient import TestClient

from threshold.api.app import app
from threshold.sources import costar, index, upstream

PASSWORD = "s3cret"


def jl(*recs):
    return "".join(json.dumps(r) + "\n" for r in recs)


FILES = {
    "index.md": "# kit\n",
    "schemas/enums.json": json.dumps({"SprinklerType": {"0": "Unknown", "1": "Wet"}, "BuildingConstructionMaterialType": {"3": "ReinforcedConcrete"}}),
    "commercial-properties.csv": "PropertyId,MatterportModelId,Address,City,State\n100,unit0000001,100 Main St,Houston,TX\n"
                                 "100,gym00000001,100 Main St,Houston,TX\n200,wh000000001,9 Dock Rd,Los Angeles,CA\n300,,1 Empty St,Houston,TX\n",
    "residential-listings.csv": "ListingId,ResidentialListingId,MatterportModelId,Address,City,State\n"
                                "1001,2001,house0000001,5 Elm St,Houston,TX\n1002,2002,house0000001,5 Elm St,Houston,TX\n",
    "data/commercial-property.jsonl": jl(
        {"id": 100, "primaryAddress": {"city": "Houston"}, "grossBuildingAreaSquareFeet": 50000.0, "numStoriesAboveGrade": 3,
         "constructionEvents": [{"eventType": 2, "year": 1999}, {"eventType": 4, "year": 2010}], "parking": [{"totalSpaces": 10}, {"totalSpaces": 5}, {"parkingType": 3}],
         "parkingRatio": 1.5, "sprinklerType": 1, "hasSprinklers": True, "buildingConstructionMaterial": 3, "amenities": [1, 2],
         "contacts": [{"name": "A Broker"}], "notes": [{"text": "x"}], "attachments": [{"videoKey": "gym00000001"}],
         "propertyApartment": {"totalNumUnits": 20, "models": [
             {"id": 1, "numBeds": 2, "numBaths": 2, "minSquareFeet": 900, "maxSquareFeet": 900, "numUnits": 5,
              "attachments": [{"videoKey": "unit0000001"}], "units": [{"unitNumber": str(i)} for i in range(200)]},
             {"id": 2, "numBeds": 1, "numBaths": 1, "minSquareFeet": 600, "maxSquareFeet": 600, "numUnits": 15}]}},
        {"id": 200, "attachments": [{"videoKey": "wh000000001"}], "propertyIndustrial": {
            "numExternalLoadingDocks": 2, "numInternalLoadingDocks": 1, "driveInBays": {"numDriveInBays": 1},
            "structural": {"ceilingHeightFeet": 24.0, "ceilingHeightInches": 6.0, "elevators": [{"elevatorType": 1, "numElevators": 2, "elevatorState": 1}]}}},
        {"id": 300}),
    "data/commercial-listing-summary.jsonl": jl({"id": 900, "propertyId": 100, "listingStatus": 1, "notes": ["secret"], "forLeaseSummary": {"properties": [{"id": 200}]}}),
    "data/location-occupancy.jsonl": jl({"id": 5, "propertyId": 100, "tenantLocationId": 77, "fromDate": "2020-01-01"},
                                        {"id": 6, "propertyId": 100, "tenantLocationId": None, "fromDate": "2022-01-01"}),
    "data/company-detail.jsonl": jl({"id": 77, "name": "Acme Dental", "numEmployees": 4, "address": {"x": 1}}),
    "data/commercial-sale-comp.jsonl": jl({"id": 1, "soldDate": "2015-01-01", "soldForPrice": 5, "entities": [{"propertyId": 100}, {"propertyId": 200}]},
                                          {"id": 2, "soldDate": "2021-01-01", "soldForPrice": 9, "entities": [{"propertyId": 100}]}),
    "data/apartment-listing.jsonl": jl({"id": 50, "propertyId": 100, "yearBuilt": 1999, "minSquareFeet": 600, "maxSquareFeet": 900}),
    "data/residential-listings.jsonl": jl(
        {"id": 1001, "residentialListingId": 2001, "propertyId": 9001, "listDate": "2024-01-01", "property": {"bedsMax": 3, "bathsMax": 2, "sqftMax": 1500, "yearBuilt": 1950},
         "agents": [{"name": "x"}], "remarks": "r" * 2000},
        {"id": 1002, "residentialListingId": 2002, "propertyId": 9001, "listDate": "2026-01-01", "property": {"bedsMax": 3, "bathsMax": 2.5, "sqftMax": 1520, "yearBuilt": 1950},
         "resoValues": {"hasElevator": False, "hasAccessibilityFeatures": True, "structure": {"stories": 2}}}),
    "data/residential-listing-features.jsonl": jl({"id": 1002, "derivedValues": {"totalBedrooms": 3, "homeSquareFeet": 1520}}),
}

ROWS = {  # models_index.csv rows as the code sees them
    "unit0000001": {"costar_property_id": "100", "homes_listing_id": ""},
    "gym00000001": {"costar_property_id": "", "homes_listing_id": ""},
    "wh000000001": {"costar_property_id": "999", "homes_listing_id": ""},     # the index disagrees with the CSV; the CSV wins
    "house0000001": {"costar_property_id": "", "homes_listing_id": "2001"},   # the index agrees (it holds the ResidentialListingId)
    "idxonly00001": {"costar_property_id": "200", "homes_listing_id": ""},    # not in the CSV: the index column is the fallback
    "idxhome00001": {"costar_property_id": "", "homes_listing_id": "2002"},
    "nothing00001": {"costar_property_id": "", "homes_listing_id": ""},
}


def write_kit(root):
    for name, text in FILES.items():
        f = root / name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text)


def aes_zip(src, dest, password=PASSWORD):
    with pyzipper.AESZipFile(dest, "w", compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES) as z:
        z.setpassword(password.encode())
        for name in FILES:
            z.write(src / name, name)


@pytest.fixture
def kit(tmp_path, monkeypatch):
    """A configured kit, unpacked. Returns the folder."""
    d = tmp_path / "kit"
    write_kit(d)
    return configure(tmp_path, monkeypatch, dir_=d)


def configure(tmp_path, monkeypatch, dir_=None, zip_=None, password=PASSWORD):
    for k in ("COSTAR_KIT_DIR", "COSTAR_KIT_ZIP", "COSTAR_KIT_URL", "COSTAR_ZIP_PASSWORD"):
        monkeypatch.setenv(k, "")  # os.environ wins over the real data folder's .env
    monkeypatch.setenv("COSTAR_KIT_DIR", str(dir_ or tmp_path / "unpacked"))
    if zip_:
        monkeypatch.setenv("COSTAR_KIT_ZIP", str(zip_))
    monkeypatch.setenv("COSTAR_ZIP_PASSWORD", password)
    for m in (costar, upstream):
        monkeypatch.setattr(m, "CACHE", tmp_path / "cache")
    blank = {k: "" for k in ("name", "segment", "kind", "address", "city", "lat", "lon", "splat", "defurnished", "drone_photos", "pano_count",
                             "room_count", "floor_count", "created", "ai_summary")}
    monkeypatch.setattr(index, "rows", lambda: {sid: {**blank, "sid": sid, **r} for sid, r in ROWS.items()})
    costar.joins.cache_clear()
    costar._enums.cache_clear()
    return dir_ or tmp_path / "unpacked"


# --- finding the kit ---
def test_not_configured_says_what_to_set(tmp_path, monkeypatch):
    configure(tmp_path, monkeypatch)
    with pytest.raises(costar.NotConfigured, match="COSTAR_KIT_DIR.*COSTAR_KIT_ZIP.*COSTAR_KIT_URL"):
        costar.record("unit0000001")


def test_route_is_404_with_the_message_when_not_configured(tmp_path, monkeypatch):
    configure(tmp_path, monkeypatch)
    r = TestClient(app).get("/api/scan/unit0000001/record")
    assert r.status_code == 404 and "not configured" in r.json()["detail"]


def test_aes_password_protected_zip_is_unpacked(tmp_path, monkeypatch):
    src = tmp_path / "src"
    write_kit(src)
    aes_zip(src, tmp_path / "kit.zip")
    d = configure(tmp_path, monkeypatch, zip_=tmp_path / "kit.zip")
    assert costar.ensure_kit() == d and (d / "data" / "company-detail.jsonl").exists()
    assert costar.get("company-detail", 77)["name"] == "Acme Dental"


@pytest.mark.skipif(not shutil.which("zip"), reason="needs the zip command to make a ZipCrypto archive")
def test_zipcrypto_password_protected_zip_is_unpacked(tmp_path, monkeypatch):
    src = tmp_path / "src"
    write_kit(src)
    subprocess.run(["zip", "-q", "-r", "-P", PASSWORD, str(tmp_path / "kit.zip"), "."], cwd=src, check=True)
    assert all(i.flag_bits & 1 for i in zipfile.ZipFile(tmp_path / "kit.zip").infolist() if not i.is_dir())  # really encrypted
    configure(tmp_path, monkeypatch, zip_=tmp_path / "kit.zip")
    assert costar.get("commercial-property", 200)["id"] == 200


def test_wrong_password_is_reported(tmp_path, monkeypatch):
    src = tmp_path / "src"
    write_kit(src)
    aes_zip(src, tmp_path / "kit.zip")
    configure(tmp_path, monkeypatch, zip_=tmp_path / "kit.zip", password="nope")
    with pytest.raises(costar.NotConfigured, match="rejected COSTAR_ZIP_PASSWORD"):
        costar.ensure_kit()


# --- lookups ---
def test_lookups_by_id_and_by_property(kit):
    assert costar.get("commercial-property", 100)["numStoriesAboveGrade"] == 3 and costar.get("commercial-property", 12345) is None
    assert [t["id"] for t in costar.by_property("location-occupancy", 100)] == [5, 6]
    assert [s["id"] for s in costar.by_property("commercial-sale-comp", 200)] == [1]      # indexed under every entity
    assert [x["id"] for x in costar.by_property("commercial-listing-summary", 200)] == [900]  # and under forLeaseSummary.properties
    assert [x["id"] for x in costar.by_resident_listing_id(2002)] == [1002]


def test_the_index_is_rebuilt_when_a_data_file_changes(kit):
    assert costar.get("company-detail", 78) is None
    with open(kit / "data" / "company-detail.jsonl", "a") as f:
        f.write(json.dumps({"id": 78, "name": "New Co"}) + "\n")
    assert costar.get("company-detail", 78)["name"] == "New Co"


# --- the join ---
def test_the_csv_wins_over_the_index(kit):
    assert costar.resolve("wh000000001")["property_ids"] == [200] and costar.resolve("wh000000001")["index_property_id"] == 999
    assert costar.property_id_of("gym00000001") == 100
    r = costar.resolve("idxonly00001")
    assert r["source"] == "models_index" and r["property_ids"] == [200]
    assert costar.resolve("idxhome00001")["listing_ids"] == [1002]
    assert costar.resolve("nothing00001")["source"] is None


def test_agreement_counts(kit):
    a = costar.agreement()
    assert a["property"]["both_agree"] == 1 and a["property"]["both_disagree"] == 1 and a["property"]["both_disagree_id_not_in_kit"] == 1
    assert a["property"]["csv_only"] == 1 and a["property"]["index_only"] == 1
    assert a["listing"]["both_agree"] == 1 and a["listing"]["index_only"] == 1


def test_scans_of_property(kit):
    assert costar.scans_of_property(100) == ["unit0000001", "gym00000001"]
    assert costar.scans_of_property(200) == ["wh000000001", "idxonly00001"]
    assert costar.scans_of_property(7) == []


# --- the record ---
def test_commercial_record_is_trimmed_and_joined(kit):
    r = costar.record("unit0000001")
    assert r["scope"] == "floor_plan" and r["unit_match"]["model"]["id"] == 1 and "units" not in r["unit_match"]["model"]
    assert "contacts" not in r["property"] and "notes" not in r["property"] and "attachments" not in r["property"]
    assert r["tenancies"]["count"] == 2 and r["tenancies"]["items"][0].get("tenant") is None  # newest first; a null tenant is trimmed away
    assert r["tenancies"]["items"][1]["tenant"]["name"] == "Acme Dental"
    assert [s["id"] for s in r["sale_comps"]["items"]] == [2, 1] and r["apartment_listing"]["yearBuilt"] == 1999
    assert [x["id"] for x in r["listings"]] == [900] and "notes" not in r["listings"][0]


def test_claims_carry_their_source_paths(kit):
    c = costar.record("unit0000001")["claims"]
    assert c["gross_area"] == {"value": 50000.0, "unit": "ft2", "path": "grossBuildingAreaSquareFeet"}
    assert c["year_built"]["value"] == 1999 and c["year_renovated"]["value"] == 2010 and "eventType" in c["year_built"]["path"]
    assert c["parking_spaces"]["value"] == 15 and c["stories"]["value"] == 3 and c["parking_ratio"]["value"] == 1.5
    assert c["construction_material"]["value"] == "ReinforcedConcrete" and c["sprinkler_type"]["value"] == "Wet"
    assert (c["unit_beds"]["value"], c["unit_baths"]["value"], c["unit_area_min"]["value"]) == (2, 2, 900)
    assert c["unit_beds"]["path"] == "propertyApartment.models[].numBeds" and len(c["unit_mix"]["value"]) == 2
    w = costar.record("wh000000001")["claims"]
    assert w["ceiling_height"]["value"] == 24.5 and w["dock_doors"]["value"] == 3 and w["passenger_elevators"]["value"] == 2
    assert w["drive_in_bays"]["value"] == 1


def test_residential_record_shows_the_latest_listing(kit):
    r = costar.record("house0000001")
    assert r["match"]["listing_ids"] == [1001, 1002] and r["residential_listing"]["id"] == 1002
    assert r["other_listings_of_this_home"] == [1001] and r["residential_features"]["id"] == 1002
    c = r["claims"]
    assert c["beds"]["value"] == 3 and c["baths"]["value"] == 2.5 and c["living_area"]["value"] == 1520
    assert c["has_accessibility_features"]["value"] is True and c["stories"]["path"].endswith("resoValues.structure.stories")


def test_long_text_and_lists_are_cut_and_full_restores_them(kit):
    r = costar.record("house0000001")
    assert r["trimmed"] == {} or "remarks" not in r["trimmed"]          # the latest listing has no long remarks
    d = json.loads((kit / "data" / "residential-listings.jsonl").read_text().splitlines()[0])
    assert len(d["remarks"]) == 2000 and len(costar._trim(d, "", cut := {})["remarks"]) == costar.MAX_TEXT and cut == {"remarks": 2000}
    big = {"items": list(range(100))}
    cut = {}
    assert len(costar._trim(big, "", cut)["items"]) == costar.MAX_LIST and cut == {"items[]": 100}
    assert len(costar.record("unit0000001", full=True)["property"]["propertyApartment"]["models"][0]["units"]) == 200


def test_scan_not_in_the_kit(kit):
    with pytest.raises(LookupError, match="no CoStar record"):
        costar.record("nothing00001")


def test_property_scans_route(kit):
    c = TestClient(app)
    d = c.get("/api/property/100/scans").json()
    assert d["property_id"] == 100 and d["address"] == "100 Main St, Houston, TX" and d["count"] == 2
    assert c.get("/api/property/7/scans").status_code == 404


def test_scope_is_the_unit_when_the_scan_is_attached_to_a_unit():
    p = {"propertyApartment": {"models": [{"id": 1, "attachments": [], "units": [{"unitNumber": "4B", "attachments": [{"videoKey": "abc"}]}]}]}}
    got = costar._scan_scope(p, "abc")
    assert got["scope"] == "unit" and got["unit"]["unitNumber"] == "4B" and got["model"]["id"] == 1
    assert costar._scan_scope(p, "zzz")["scope"] == "unknown"
