"""The MCP server and CLI: tools generated from the registry, write gating, text summaries from result fields."""
import asyncio

from mcp.shared.memory import create_connected_server_and_client_session as connect

from threshold.cli import _value, main
from threshold.mcp import core
from threshold.mcp.server import build
from threshold.tools import load

RESULT = {"tool": "garage_fit", "scope": {"sid": "x"}, "verdict": {"status": "warn", "text": "Tight."},
          "metrics": [{"id": "w", "label": "Inside width", "value": 5.5, "unit": "m",
                       "source": {"layer": "matterport", "method": "geometry", "confidence": "medium"}},
                      {"id": "h", "label": "Door height", "value": None, "unit": "m",
                       "source": {"layer": "matterport", "method": "geometry", "confidence": "low"}}],
          "checks": [{"id": "c", "rule": "Door room", "measured": 0.7, "threshold": 0.9, "unit": "m", "status": "fail"}],
          "findings": [{"id": "f", "title": "Too tight", "status": "fail"}], "assumptions": []}


def _tools(write: bool) -> dict:
    async def go():
        async with connect(build(write=write)._mcp_server) as c:
            return {t.name: t for t in (await c.list_tools()).tools}
    return asyncio.run(go())


def test_every_ready_read_only_tool_is_listed_and_writes_are_gated():
    ro, rw = _tools(False), _tools(True)
    reg = {k: t.manifest for k, t in load().items() if t.manifest.status == "ready"}
    assert {k for k, m in reg.items() if m.annotations.read_only} <= set(ro)
    assert set(reg) <= set(rw)
    assert not [n for n, t in ro.items() if not t.annotations.readOnlyHint]
    assert {"agent_turn", "workspace_ops", "workspace_create"} <= set(rw) - set(ro)
    assert rw["garage_fit"].inputSchema == reg["garage_fit"].inputs
    assert rw["agent_turn"].description.startswith("WRITES")


def test_summary_comes_from_result_fields():
    s = core.summary(RESULT)
    assert s.splitlines()[0] == "garage_fit: WARN. Tight."
    assert "Inside width: 5.5 m  [medium]" in s and "Door height: not measured" in s
    assert "fail: Door room (measured 0.7, limit 0.9 m)" in s and "fail: Too tight" in s


def test_plan_summary_has_counts_not_geometry():
    plan = {"sid": "x", "rooms": [{"id": "r1", "label": "Garage", "area": 30.0, "polygon": [[0, 0]]},
                                  {"id": "r2", "label": None, "area": 10.04}],
            "openings": [{"type": "doorway", "width": 0.81}, {"type": "doorway", "width": 0.7}, {"type": "window"}],
            "floors": [{"id": "f0", "label": "1", "elevation": 0}], "panos": [{}, {}]}
    p = core.plan_summary(plan)
    assert p["rooms"]["by_label"] == {"Garage": 1, "unlabelled": 1} and p["rooms"]["total_area_m2"] == 40.0
    assert p["openings"] == {"doorways": 2, "windows": 1, "narrowest_doorway_m": 0.7} and p["panos"] == 2
    assert "polygon" not in str(p)


def test_cli_values_and_errors(capsys):
    assert _value("1.5") == 1.5 and _value("ford_f150") == "ford_f150" and _value("[1,2]") == [1, 2]
    assert main(["run", "no_such_tool"]) == 1
    assert "Unknown tool" in capsys.readouterr().err
    assert main(["tools", "--json"]) == 0
