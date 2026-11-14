"""Tool registry: `@tool(...)` registers a handler and its manifest; `run_tool` validates inputs and runs it.

Tools live one per package in `threshold/tools/<id>/`; `load()` imports them all. See tools/README.md.
"""
from __future__ import annotations

import importlib
import inspect
import json
import pathlib
import pkgutil
from collections.abc import Callable
from dataclasses import dataclass
from dataclasses import field as dc_field
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from ..config import DATA
from .places import Site, default_site
from .types import Manifest, Place, PropertyScope, ScanScope, ScansScope, ToolResult, Verdict


class ToolError(Exception):
    """Unknown tool, a planned tool, bad inputs, or missing data. The message is safe to show a person."""


class NotApplicable(ToolError):
    """The tool cannot answer for this building (a house is not an apartment community, a phone scan has no
    listing). `run_tool` turns it into an "unknown" result whose verdict is the message, not an error."""


def field(default: Any = ..., *, ask: str | None = None, pref: str | None = None, source: str | None = None,
          unit: str | None = None, **kw) -> Any:
    """A tool input. `ask` becomes an intake question, `pref` names the saved preference that fills it,
    `source` fills it from the selection (e.g. "selection.scan"), `unit` is shown next to it."""
    extra = {k: v for k, v in {"x-ask": ask, "x-pref": pref, "x-source": source, "x-unit": unit}.items() if v}
    return Field(default, json_schema_extra=extra or None, **kw)


def default_plan(sid: str) -> dict:
    """A ScanPlan from the data workstream's cached loader (current normalizer, with `quality`). The fixture copy,
    which an older normalizer wrote, is the fallback when the loader cannot reach the scan. Room labels from the
    label overlay (room_labeller: vision labels and people's corrections) are applied either way."""
    from ..sources import matterport
    from .room_labeller import store
    f = DATA / "fixtures" / "scanplan" / f"{sid}.json"
    try:
        return store.apply(matterport.plan(sid))
    except Exception:
        if f.exists():
            return store.apply(json.loads(f.read_text()))
        raise


@dataclass
class ToolContext:
    """What a handler gets besides its inputs."""
    plans: Callable[[str], dict] = default_plan
    on_step: Callable[[str], None] | None = None
    steps: list[str] = dc_field(default_factory=list)
    sites: Callable[[Place], Site] = default_site

    def plan(self, sid: str) -> dict:
        try:
            return self.plans(sid)
        except LookupError as e:
            raise ToolError(f"No scan {sid}: {e}") from None

    def site(self, place: Place | dict) -> Site:
        """Coordinates, address, CoStar property and scans of a place (scan, property, address or point)."""
        place = place if isinstance(place, Place) else Place.model_validate(place)
        try:
            return self.sites(place)
        except LookupError as e:
            raise ToolError(str(e).strip("'\"")) from None

    def step(self, text: str) -> None:
        """Report one progress step. It reaches the workspace as it happens (`run.progress`) and shows in the
        run's StepLog."""
        self.steps.append(text)
        if self.on_step:
            self.on_step(text)


@dataclass
class Tool:
    manifest: Manifest
    inputs: type[BaseModel]
    handler: Callable[[ToolContext, BaseModel], ToolResult]


REGISTRY: dict[str, Tool] = {}


def tool(**manifest: Any) -> Callable:
    """Register `run(ctx, inputs: Inputs) -> ToolResult`. Keyword arguments are Manifest fields; `inputs`
    comes from the type hint on the handler's second parameter."""
    def wrap(fn: Callable) -> Callable:
        hint = list(inspect.signature(fn, eval_str=True).parameters.values())[1].annotation
        m = Manifest(**manifest, inputs=hint.model_json_schema())
        if m.id in REGISTRY and REGISTRY[m.id].handler is not fn:
            raise ValueError(f"tool id {m.id} registered twice")
        REGISTRY[m.id] = Tool(m, hint, fn)
        return fn
    return wrap


def load() -> dict[str, Tool]:
    """Import every tool package once."""
    for m in pkgutil.iter_modules([str(pathlib.Path(__file__).parent)]):
        if m.ispkg:
            importlib.import_module(f"{__package__}.{m.name}")
    return REGISTRY


def manifests() -> list[Manifest]:
    return [t.manifest for t in load().values()]


def run_tool(tool_id: str, inputs: dict, ctx: ToolContext | None = None) -> ToolResult:
    t = load().get(tool_id)
    if not t:
        raise ToolError(f"Unknown tool {tool_id}")
    try:
        parsed = t.inputs.model_validate(inputs)
    except ValidationError as e:
        raise ToolError(f"Bad inputs for {tool_id}: " + "; ".join(
            f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors())) from None
    try:
        result = t.handler(ctx or ToolContext(), parsed)
    except NotApplicable as e:
        result = ToolResult(scope=_scope(parsed.model_dump()), verdict=Verdict(status="unknown", text=str(e)))
    result.tool = tool_id
    result = ToolResult.model_validate(result.model_dump())  # re-check what the handler built
    from ..facts.record import record_result  # facts history (Tiger Data); a no-op without a database
    record_result(tool_id, result)
    return result


def _scope(inputs: dict):
    place = inputs.get("place") or {}
    sid = inputs.get("scan") or place.get("scan")
    pid = inputs.get("property_id") or inputs.get("property") or place.get("property_id")
    return ScanScope(sid=sid) if sid else PropertyScope(property_id=pid) if pid else ScansScope(sids=inputs.get("scans") or [])


__all__ = ["NotApplicable", "Place", "ScanScope", "Site", "Tool", "ToolContext", "ToolError", "field", "load", "manifests", "run_tool", "tool"]
