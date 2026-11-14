import pytest


@pytest.fixture(autouse=True)
def no_facts_database(monkeypatch):
    """Tests never reach the configured facts database (it may be the Tiger Cloud service with the event's data).
    tests/facts points at TIGER_TEST_DATABASE_URL itself."""
    from threshold.facts import db
    monkeypatch.setenv("TIGER_DATABASE_URL", "")
    monkeypatch.setattr(db, "_down_until", 0.0)
