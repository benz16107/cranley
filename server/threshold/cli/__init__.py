"""`threshold`: the tools, search and the agent from a terminal. Human-readable by default, `--json` for scripts.

    threshold tools
    threshold run garage_fit --scan <scan-id> --input vehicle=ford_f150
    threshold search "greenwood" --city Houston --kind house
    threshold search --where garage_width>=6 --kind house
    threshold building <scan-id>
    threshold ask "will an F-150 fit in this garage" --scan <scan-id>
"""
from __future__ import annotations

import argparse
import json
import sys

from ..mcp import core
from ..tools import ToolError


def _value(v: str):
    """`--input k=v`: JSON when it parses (numbers, true, lists), else the string."""
    try:
        return json.loads(v)
    except json.JSONDecodeError:
        return v


def _say(line: str) -> None:
    print(line, file=sys.stderr, flush=True)


def cmd_tools(a) -> object:
    ts = core.tools(write=True)
    if a.json:
        return [t.manifest.model_dump(mode="json", include={"id", "title", "summary", "annotations"}) for t in ts.values()]
    width = max(map(len, ts))
    return "\n".join(f"{k:<{width}}  {'' if t.manifest.annotations.read_only else '[writes] '}{t.manifest.title}: "
                     f"{t.manifest.summary}" for k, t in sorted(ts.items()))


def cmd_run(a) -> object:
    inputs = {}
    for kv in a.input:
        k, sep, v = kv.partition("=")
        if not sep:
            raise ToolError(f"--input wants key=value, got {kv!r}")
        inputs[k] = _value(v)
    if a.scan:
        inputs["scan"] = a.scan
    r = core.run(a.tool, inputs, on_step=None if a.json else lambda s: _say(f"  {s}"))
    return r if a.json else core.summary(r)


def cmd_search(a) -> object:
    out = core.search(a.query, a.address, a.city, a.kind, a.where, a.limit)
    if a.json:
        return out
    rows = out["scans"]
    head = f"{out.get('total', out.get('matches'))} matches"
    return "\n".join([head] + [f"{r['sid']}  {r.get('kind', ''):<14} {r.get('address') or r.get('name') or ''}"
                               + (f"  ({'; '.join(r['why'])})" if r.get("why") else "") for r in rows])


def cmd_building(a) -> object:
    b = core.building(a.scan)
    if a.json:
        return b
    s, p = b["scan"], b["plan"]
    lines = [f"{s['sid']}  {s['name']}", f"  {s['address'] or ''} ({s['kind']}, {s['city'] or ''})"]
    if "rooms" in p:
        q = p["quality"]
        lines += [f"  floors {len(p['floors'])}, rooms {p['rooms']['count']}, area {p['rooms']['total_area_m2']} m2, "
                  f"doorways {p['openings']['doorways']} (narrowest {p['openings']['narrowest_doorway_m']} m), "
                  f"windows {p['openings']['windows']}, panoramas {p['panos']}",
                  "  has: " + ", ".join(k for k in ("walls", "polygons", "openings", "labels", "georef") if q.get(k)),
                  "  rooms: " + ", ".join(f"{k} {v}" for k, v in p["rooms"]["by_label"].items())]
    else:
        lines.append(f"  plan: {p.get('error')}")
    if b["record_claims"]:
        lines.append("  record says: " + ", ".join(f"{k} {c['value']}{' ' + c['unit'] if c.get('unit') else ''}"
                                                   for k, c in b["record_claims"].items()))
    return "\n".join(lines)


def cmd_ask(a) -> object:
    out = core.ask(a.brief, a.workspace, a.scan, on_line=None if a.json else _say)
    return out if a.json else core.ask_text(out)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="threshold", description="Threshold's building tools from a terminal")
    sub = p.add_subparsers(dest="cmd", required=True)
    j = argparse.ArgumentParser(add_help=False)
    j.add_argument("--json", action="store_true", help="print JSON instead of text")
    sub.add_parser("tools", parents=[j], help="list the tools").set_defaults(fn=cmd_tools)
    r = sub.add_parser("run", parents=[j], help="run one tool")
    r.add_argument("tool")
    r.add_argument("--scan")
    r.add_argument("--input", "-i", action="append", default=[], metavar="KEY=VALUE")
    r.set_defaults(fn=cmd_run)
    s = sub.add_parser("search", parents=[j], help="find scans")
    s.add_argument("query", nargs="?")
    s.add_argument("--address")
    s.add_argument("--city")
    s.add_argument("--kind")
    s.add_argument("--where", action="append", metavar="MEASURE>=VALUE", help="e.g. garage_width>=6; repeatable")
    s.add_argument("--limit", type=int, default=10)
    s.set_defaults(fn=cmd_search)
    b = sub.add_parser("building", parents=[j], help="one scan's facts")
    b.add_argument("scan")
    b.set_defaults(fn=cmd_building)
    k = sub.add_parser("ask", parents=[j], help="run the agent on a brief (writes a workspace)")
    k.add_argument("brief")
    k.add_argument("--workspace")
    k.add_argument("--scan", action="append", help="scope to a scan; repeatable")
    k.set_defaults(fn=cmd_ask)
    return p


def main(argv: list[str] | None = None) -> int:
    a = parser().parse_args(argv)
    try:
        out = a.fn(a)
    except (ToolError, ValueError, LookupError) as e:
        _say(f"threshold: {e}")
        return 1
    print(json.dumps(out, indent=1, default=str) if a.json else out)
    return 0
