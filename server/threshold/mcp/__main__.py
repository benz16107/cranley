"""`python -m threshold.mcp [--write]` serves MCP over stdio. `--write` adds workspace ops and agent turns."""
import argparse
import logging
import sys

from .server import build

p = argparse.ArgumentParser(prog="threshold.mcp")
p.add_argument("--write", action="store_true", help="also expose tools that change workspaces (agent turns, ops)")
a = p.parse_args()
logging.basicConfig(stream=sys.stderr, level=logging.WARNING)  # stdout carries the protocol
build(write=a.write).run("stdio")
