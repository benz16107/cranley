"""The guard around the MongoDB MCP server's tools: database fixed, collections allowed, the person's scope forced."""
import pytest

from threshold.agent.mongo_mcp import guard


def test_find_and_count_are_scoped_to_the_profile():
    out = guard("find", {"collection": "history", "filter": {"kind": "finding"}, "limit": 500}, "threshold", "pat", "ws_1")
    assert out["database"] == "threshold" and out["filter"] == {"$and": [{"kind": "finding"}, {"profile": "pat"}]}
    assert out["limit"] == 50 and out["projection"] == {"h": 0, "vector": 0}
    assert guard("find", {"collection": "history", "projection": {"title": 1, "vector": 1}}, "d", "p", "w")["projection"] == {"title": 1}
    assert guard("count", {"collection": "sensors", "query": {}}, "d", "pat", "ws_1")["query"]["$and"][1] == {"meta.workspace": "ws_1"}


def test_aggregate_starts_with_the_scope_and_refuses_other_collections():
    out = guard("aggregate", {"collection": "history", "pipeline": [{"$group": {"_id": "$tool", "n": {"$sum": 1}}}]},
                "threshold", "pat", "ws_1")
    assert out["pipeline"][0] == {"$match": {"profile": "pat"}} and out["pipeline"][-1] == {"$limit": 50}
    for bad in ({"$lookup": {"from": "workspaces"}}, {"$unionWith": "ops"}, {"$merge": {"into": "x"}},
                {"$match": {"$where": "1"}}):
        with pytest.raises(ValueError):
            guard("aggregate", {"collection": "history", "pipeline": [bad]}, "d", "p", "w")
    with pytest.raises(ValueError):
        guard("find", {"collection": "ops"}, "d", "p", "w")  # the log holds every workspace id
