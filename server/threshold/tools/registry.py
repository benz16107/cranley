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
from .types import Manifest, Place, ScanScope, ToolResult


class ToolError(Exception):
    """Unknown tool, a planned tool, bad inputs, or missing data. The message is safe to show a person."""


def field(default: Any = ..., *, ask: str | None = None, pref: str | None = None, source: str | None = None,
          unit: str | None = None, **kw) -> Any:
    """A tool input. `ask` becomes an intake question, `pref` names the saved preference that fills it,
    `source` fills it from the selection (e.g. "selection.scan"), `unit` is shown next to it."""
    extra = {k: v for k, v in {"x-ask": ask, "x-pref": pref, "x-source": source, "x-unit": unit}.items() if v}
    return Field(default, json_schema_extra=extra or None, **kw)


def default_plan(sid: str) -> dict:
    """A ScanPlan: the fixture copy if there is one (no network), else the data workstream's cached loader."""
    f = DATA / "fixtures" / "scanplan" / f"{sid}.json"
    if f.exists():
        return json.loads(f.read_text())
    from ..sources import matterport
    return matterport.plan(sid)


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
    result = t.handler(ctx or ToolContext(), parsed)
    result.tool = tool_id
    return ToolResult.model_validate(result.model_dump())  # re-check what the handler built


__all__ = ["Place", "ScanScope", "Site", "Tool", "ToolContext", "ToolError", "field", "load", "manifests", "run_tool", "tool"]
