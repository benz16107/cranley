"""Write docs/contracts/workspace.schema.json and docs/contracts/workspace.ts from the Pydantic models.

    cd server && uv run python -m threshold.agent.export

The TypeScript comes from the schema through json-schema-to-typescript (npx, MIT); nothing is added to the repo's
dependencies. Run it after any change to workspace.py or tools/types.py and commit both files."""
from __future__ import annotations

import json
import pathlib
import subprocess

from pydantic import BaseModel

from ..tools.types import Manifest, ToolResult
from .workspace import Block, LogEntry, Op, Workspace

OUT = pathlib.Path(__file__).resolve().parents[3] / "docs" / "contracts"


class WorkspaceContract(BaseModel):
    """Contract 5. `workspace` is the document, `op` one of the sixteen operations, `log_entry` what the SSE
    stream and the op log carry, `block` one panel block, plus Contract 3 (`tool_result`) and the tool manifest."""
    workspace: Workspace
    op: Op
    log_entry: LogEntry
    block: Block
    tool_result: ToolResult
    manifest: Manifest


def tidy(node):
    """Drop per-property titles (they become junk type aliases in TypeScript) and make discriminators required."""
    if isinstance(node, dict):
        for name, prop in (node.get("properties") or {}).items():
            prop.pop("title", None)
            if name in ("op", "type", "kind", "schema") and "const" in prop and name not in node.setdefault("required", []):
                node["required"].append(name)
        for v in node.values():
            tidy(v)
    elif isinstance(node, list):
        for v in node:
            tidy(v)
    return node


def schema_text() -> str:
    schema = tidy(WorkspaceContract.model_json_schema(by_alias=True))
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = "threshold/workspace/1"
    return json.dumps(schema, indent=2, ensure_ascii=False) + "\n"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "workspace.schema.json"
    path.write_text(schema_text())
    ts = subprocess.run(["npx", "--yes", "json-schema-to-typescript@15.0.4", "--input", str(path),
                         "--unreachableDefinitions", "--additionalProperties", "false",
                         "--bannerComment", "/* Generated from workspace.schema.json by "
                         "server/threshold/agent/export.py. Do not edit. */"],
                        capture_output=True, text=True, check=True).stdout
    (OUT / "workspace.ts").write_text(ts)
    print(f"wrote {path} and workspace.ts ({len(ts.splitlines())} lines)")


if __name__ == "__main__":
    main()
