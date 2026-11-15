"""Persona presets, planned tools, and how a tool's inputs get filled from the workspace.

A preset is data in agent/personas/<id>.json: a tool list, default thresholds keyed by preference key (x-pref)
and a layout hint. Tools a preset names that are not built yet come from personas/planned_tools.json.
"""
from __future__ import annotations

import functools
import json
import pathlib
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from ..tools import Manifest, manifests
from .workspace import Workspace

HERE = pathlib.Path(__file__).parent / "personas"


class Layout(BaseModel):
    model_config = ConfigDict(extra="forbid")
    view: Literal["map", "scene", "plan", "pano"] = "scene"
    lead_tool: str | None = None


class Persona(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    title: str
    who: str
    tools: list[str]
    thresholds: dict[str, Any] = {}
    layout: Layout = Layout()


@functools.cache
def personas() -> dict[str, Persona]:
    return {p.id: p for p in (Persona.model_validate_json(f.read_text()) for f in sorted(HERE.glob("*.json"))
                              if f.name != "planned_tools.json")}


@functools.cache
def catalog() -> dict[str, Manifest]:
    """Every tool the composer may choose: the registered ones, then planned stubs."""
    real = {m.id: m for m in manifests()}
    planned = json.loads((HERE / "planned_tools.json").read_text())
    stubs = {k: Manifest(id=k, title=v["title"], summary=v["summary"], model_description=v["summary"], status="planned",
                         personas=[p.id for p in personas().values() if k in p.tools])
             for k, v in planned.items() if k not in real}
    return real | stubs


def resolve(m: Manifest, doc: Workspace, given: dict | None = None) -> tuple[dict, dict[str, str], list[tuple[str, dict]]]:
    """Fill a tool's inputs: what the caller gave, then the user's preferences, then intake answers, then the
    persona preset; the schema default applies after that. Returns (inputs, input -> pref key, missing required)."""
    given = given or {}
    preset = personas().get(doc.brief.persona or "")
    props, required = m.inputs.get("properties", {}), set(m.inputs.get("required", []))
    inputs, used, missing = {}, {}, []
    for name, schema in props.items():
        key = schema.get("x-pref")
        if name in given and given[name] is not None:
            inputs[name] = given[name]
            if key and key in doc.prefs and doc.prefs[key].value == given[name]:
                used[name] = key  # the caller repeated the person's own value: it is theirs, and says where it came from
        elif key and key in doc.prefs:
            inputs[name], used[name] = doc.prefs[key].value, key
        elif key and key in doc.brief.facts:
            inputs[name], used[name] = doc.brief.facts[key], key
        elif key and preset and key in preset.thresholds:
            inputs[name], used[name] = preset.thresholds[key], key
        elif name in required and "x-source" not in schema:
            missing.append((name, schema))
    return inputs, used, missing
