"""The Threshold MCP server: every registered tool, generated from its manifest, plus search, building facts,
workspaces and agent turns, two resources and three prompts.

Read-only unless built with `write=True` (`python -m threshold.mcp --write`): workspace ops, agent turns and tools
whose manifest says they write (room_labeller) are left out otherwise. Tools other threads add appear on their own,
because the list is read from the registry on every `tools/list`.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Annotated, Any

import anyio
from mcp.server.fastmcp import Context, FastMCP
from mcp.types import CallToolResult, TextContent, Tool as MCPTool, ToolAnnotations
from pydantic import Field

from ..tools import ToolError
from ..tools.types import Manifest, ToolResult
from . import core

INSTRUCTIONS = """Threshold measures scanned buildings in Houston and Los Angeles (Matterport scans, Vexcel aerials,
CoStar records). Find a scan with search_buildings, read building_facts, then run a tool on it (each tool's inputs
take a `scan` id). Every number in a result comes from a calculation; quote values from the structured result,
with their source and confidence, and say when a result's status is unknown because the scan cannot answer."""

WRITES = "WRITES: changes a saved workspace. "
RESULT_SCHEMA = ToolResult.model_json_schema(mode="serialization")


def reply(data: dict, text: str) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=text)], structuredContent=data)


def error(text: str) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=text)], isError=True)


def as_mcp(m: Manifest) -> MCPTool:
    ro = m.annotations.read_only
    desc = (WRITES if not ro else "") + m.model_description
    if m.examples:
        desc += "\nExamples: " + " | ".join(m.examples[:3])
    if m.requires:
        desc += "\nNeeds: " + ", ".join(r.layer + ("" if r.need == "required" else " (optional)") for r in m.requires)
    return MCPTool(name=m.id, title=m.title, description=desc, inputSchema=m.inputs, outputSchema=RESULT_SCHEMA,
                   annotations=ToolAnnotations(title=m.title, readOnlyHint=ro, destructiveHint=False,
                                               idempotentHint=ro, openWorldHint=False))


async def in_thread(ctx: Context, work: Callable[[Callable[[str], None]], Any]) -> Any:
    """Run blocking work in a worker thread; each line it reports reaches the client as a log message and progress."""
    n = 0

    def line(text: str) -> None:
        nonlocal n
        n += 1
        try:
            anyio.from_thread.run(ctx.info, text)
            anyio.from_thread.run(lambda: ctx.report_progress(n, None, text))
        except Exception:  # the client went away; the work carries on
            pass
    return await anyio.to_thread.run_sync(lambda: work(line))


class Threshold(FastMCP):
    def __init__(self, write: bool = False, **kw):
        kw.setdefault("log_level", "WARNING")  # not a line per request on the client's stderr
        super().__init__("threshold", instructions=INSTRUCTIONS, **kw)
        self.write = write

    def generated(self) -> dict:
        fixed = {t.name for t in self._tool_manager.list_tools()}
        return {k: t for k, t in core.tools(self.write).items() if k not in fixed}

    async def list_tools(self) -> list[MCPTool]:
        return await super().list_tools() + [as_mcp(t.manifest) for t in self.generated().values()]

    async def call_tool(self, name: str, arguments: dict[str, Any]):
        if name not in self.generated():
            return await super().call_tool(name, arguments)
        ctx = self.get_context()
        try:
            r = await in_thread(ctx, lambda line: core.run(name, arguments or {}, on_step=line))
        except ToolError as e:
            return error(str(e))
        return reply(r, core.summary(r))


def build(write: bool = False, **kw) -> Threshold:
    s = Threshold(write, **kw)
    RO = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
    RW = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)

    @s.tool(annotations=RO, description="Find scanned buildings by words (name, address, ids), city and kind, or by "
            "what is measured inside them with `where` comparisons such as bath_route_door>=0.81 or garage_width>=6 "
            "(read threshold://measures for every measure). At most 25 rows.")
    def search_buildings(query: str | None = None, address: str | None = None, city: str | None = None,
                         kind: Annotated[str | None, Field(description="house, apartment_unit, amenity, office, warehouse, retail or other")] = None,
                         where: list[str] | None = None, limit: Annotated[int, Field(ge=1, le=25)] = 10) -> CallToolResult:
        try:
            out = core.search(query, address, city, kind, where, limit)
        except (ToolError, ValueError) as e:
            return error(str(e))
        rows = out["scans"]
        head = f"{out.get('total', out.get('matches'))} matches" + (f", showing {len(rows)}" if rows else "")
        return reply(out, "\n".join([head] + [f"  {r['sid']}  {r.get('kind', '')}  {r.get('name') or ''}  "
                                              f"{r.get('address') or ''}, {r.get('city') or ''}"
                                              + (f"  ({'; '.join(r['why'])})" if r.get("why") else "") for r in rows]))

    @s.tool(annotations=RO, description="One scan's facts: its index row, a plan summary (floors, rooms by label and "
            "area, doorway and window counts, the narrowest doorway, which data is missing) and the listing record's "
            "checkable claims. No geometry or images.")
    def building_facts(scan: str) -> CallToolResult:
        try:
            b = core.building(scan)
        except ToolError as e:
            return error(str(e))
        return reply(b, json.dumps(b, indent=1))

    @s.tool(annotations=RO, description="Read a workspace: its brief, enabled tools, runs with their verdicts, "
            "open questions, shortlist and preferences.")
    def workspace_read(workspace: str) -> CallToolResult:
        try:
            w = core.workspace(workspace)
        except Exception as e:
            return error(f"No workspace {workspace}: {e}")
        return reply(w, json.dumps(w, indent=1))

    @s.tool(annotations=RO, description="Findings in a workspace (newest runs' findings, superseded ones hidden), "
            "optionally only one status (pass, warn, fail, unknown) or one tool. At most 50.")
    def list_findings(workspace: str, status: str | None = None, tool: str | None = None,
                      limit: Annotated[int, Field(ge=1, le=50)] = 50) -> CallToolResult:
        try:
            out = core.findings(workspace, status, tool, limit)
        except Exception as e:
            return error(f"No workspace {workspace}: {e}")
        return reply(out, f"{out['total']} findings\n" + "\n".join(
            f"  {f['status']}: {f['title']} ({f['tool']})" for f in out["findings"]))

    if write:
        @s.tool(annotations=RW, description=WRITES + "Create an empty workspace for a profile; returns its id.")
        def workspace_create(profile: str = "default") -> CallToolResult:
            w = core.workspace_create(profile)
            return reply(w, f"Created workspace {w['id']}")

        @s.tool(annotations=RW, description=WRITES + "Apply user ops to a workspace in the workspace vocabulary "
                "(brief.set, question.answer, tool.enable, tool.disable, pref.set, shortlist.add, shortlist.remove, "
                "finding.add with feedback, ...). Schema: docs/contracts/workspace.schema.json.")
        def workspace_ops(workspace: str, ops: list[dict[str, Any]]) -> CallToolResult:
            try:
                out = core.apply_ops(workspace, ops)
            except Exception as e:
                return error(getattr(e, "detail", None) or str(e))
            return reply(out, f"Applied {out['applied']} ops to {workspace}")

        @s.tool(annotations=RW, description=WRITES + "Run Threshold's own agent on a brief (\"will an F-150 fit in "
                "this garage\"). It composes a workspace, asks intake questions or runs tools, and streams progress. "
                "Give `workspace` to continue one, `scans` to scope it. Slow: tens of seconds to minutes.")
        async def agent_turn(brief: str, ctx: Context, workspace: str | None = None,
                             scans: list[str] | None = None) -> CallToolResult:
            try:
                out = await in_thread(ctx, lambda line: core.ask(brief, workspace, scans, on_line=line))
            except Exception as e:
                from ..api.agent import public_error
                return error(public_error(e))
            return reply(out, core.ask_text(out))

    @s.resource("threshold://scan/{sid}/summary", name="plan_summary", mime_type="application/json",
                description="A scan's plan summary: floors, rooms, openings, data quality. No geometry.")
    def plan_resource(sid: str) -> str:
        from ..tools.registry import default_plan
        return json.dumps(core.plan_summary(default_plan(sid)))

    @s.resource("threshold://workspace/{id}", name="workspace", mime_type="application/json",
                description="A workspace: brief, runs with verdicts, questions, shortlist.")
    def workspace_resource(id: str) -> str:
        return json.dumps(core.workspace(id))

    @s.resource("threshold://measures", name="measures", mime_type="application/json",
                description="Measures search_buildings can filter on with `where`, with labels and units.")
    def measures_resource() -> str:
        from ..tools.measure_search import table
        return json.dumps({k: {"label": v[0], "unit": v[1], "description": v[3]} for k, v in table.FIELDS.items()})

    @s.prompt(description="Can a wheelchair user live in this scan? Doors, step-free route, turning space, bathroom.")
    def wheelchair_check(scan: str) -> str:
        return (f"Check scan {scan} for a wheelchair user. Read building_facts first and say if the plan lacks walls "
                "or openings. Then run door_widths, step_free_route, turning_space and bathroom_clearance on it. "
                "Inputs such as min_width_m are the person's limits: use the numbers they gave, else ask them. "
                "Report each verdict with the measured values from the results and their confidence, list what "
                "fails and what must be measured on site. Do not state a number that is not in a result.")

    @s.prompt(description="A fire pre-plan for a building: entrances, egress routes, hazards.")
    def fire_preplan(scan: str) -> str:
        return (f"Make a fire pre-plan for scan {scan}: run fire_preplan, then egress_routes. Summarise entrances, "
                "the longest egress route and its narrowest point, and anything a crew should know, quoting values "
                "only from the results.")

    @s.prompt(description="Will a vehicle fit in this garage, with its doors open?")
    def garage_check(scan: str, vehicle: str = "ford_f150") -> str:
        return (f"Will a {vehicle} fit in the garage of scan {scan}? Run garage_fit with scan={scan} and "
                f"vehicle={vehicle}. Answer yes, no or tight with the clearances from the result, the assumptions it "
                "used and their confidence.")
    return s
