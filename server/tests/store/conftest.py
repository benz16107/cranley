"""MongoDB store tests run against MONGODB_URI (the local Atlas deployment) in a throwaway database, dropped after.
They skip when no database answers. Scan places are made up; no sponsor data."""
import uuid

import pytest

from threshold.config import env

PLACES = {  # sid -> made-up place (two near each other, one across town)
    "t1": {"address": "1 Test St", "city": "Houston", "lat": 29.7600, "lon": -95.3700},
    "t2": {"address": "2 Test St", "city": "Houston", "lat": 29.7700, "lon": -95.3800},
    "t3": {"address": "3 Test St", "city": "Los Angeles", "lat": 34.0500, "lon": -118.2500},
}


@pytest.fixture(scope="session")
def mongo_store():
    pytest.importorskip("pymongo")
    uri = env().get("MONGODB_URI")
    if not uri:
        pytest.skip("MONGODB_URI is not set")
    from pymongo import MongoClient
    from pymongo.errors import PyMongoError
    try:
        MongoClient(uri, serverSelectionTimeoutMS=2000).admin.command("ping")
    except PyMongoError:
        pytest.skip("no MongoDB answers at MONGODB_URI")
    from threshold.store.mongo import MongoStore
    s = MongoStore(uri, f"threshold_test_{uuid.uuid4().hex[:8]}", where=PLACES.get)
    yield s
    s.client.drop_database(s.db.name)


@pytest.fixture
def ms(mongo_store):
    for c in ("ops", "workspaces", "prefs", "history", "memories", "shortlist", "shares"):
        mongo_store.db[c].delete_many({})
    mongo_store._seen.clear()
    return mongo_store
