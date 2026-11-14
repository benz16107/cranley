import pytest


@pytest.fixture(autouse=True)
def no_facts_database(monkeypatch):
    """Tests never reach the configured databases (the Tiger Cloud service and the Atlas cluster hold the event's
    data). tests/facts points at TIGER_TEST_DATABASE_URL itself; tests/store at MONGODB_TEST_URI."""
    from threshold.facts import db
    monkeypatch.setenv("TIGER_DATABASE_URL", "")
    # the same for workspaces: files, never the Atlas cluster, even if the shell says THRESHOLD_STORE=mongo.
    # tests/store builds its own store on MONGODB_TEST_URI (local only) and hands it to the routes itself.
    monkeypatch.setenv("THRESHOLD_STORE", "files")
    monkeypatch.setenv("MONGODB_URI", "")
    monkeypatch.setattr(db, "_down_until", 0.0)
