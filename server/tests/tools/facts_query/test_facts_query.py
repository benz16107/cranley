from threshold.facts import ask, db
from threshold.tools import run_tool


def test_a_single_answer_is_the_verdict(monkeypatch):
    monkeypatch.setattr(db, "available", lambda: True)
    monkeypatch.setattr(ask, "run", lambda sql: {"role": "ro", "ms": 1, "sql": sql, "columns": ["houses"], "rows": [[620]],
                                                 "row_count": 1, "truncated": False})
    r = run_tool("facts_query", {"question": "How many Houston houses?", "sql": "SELECT 620"})
    assert r.verdict.text == "How many Houston houses: 620." and r.metrics[0].value == 620
