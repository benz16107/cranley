"""The MongoDB MCP server as the agent's window on its own history, read only.

One `mongodb-mcp-server` process per server process, started on first use, listening on localhost over streamable
HTTP, in read-only mode with the Atlas admin tools and connection switching disabled. The agent gets three of its
tools (`find`, `count`, `aggregate`) through langchain-mcp-adapters, wrapped so that every call:

- names this deployment's database and one of four collections (history, memories, shortlist, sensors);
- is scoped to the person: `profile` for past work, this workspace for phone readings, added as a filter or a
  leading `$match` that the model cannot drop;
- refuses stages that read another collection or write (`$lookup`, `$unionWith`, `$out`, `$merge`, ...).

What it answers that the fixed `search_history` tool cannot: counts and groupings over the person's past work
("which tools did I switch off most", "how many Houston units did I reject for the bathroom door")."""
from __future__ import annotations

import asyncio
import atexit
import functools
import json
import os
import shutil
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request

VERSION = "3.3.0"
TOOLS = ("find", "count", "aggregate")
SCOPE = {"history": "profile", "memories": "profile", "shortlist": "profile", "sensors": "meta.workspace"}
BANNED = ("$lookup", "$unionWith", "$graphLookup", "$out", "$merge", "$documents", "$search", "$searchMeta",
          "$vectorSearch", "$rankFusion", "$scoreFusion", "$currentOp", "$listSessions", "$collStats", "$indexStats",
          "$planCacheStats", "$listSearchIndexes", "$changeStream", "$function", "$accumulator", "$where")
HIDDEN = {"h": 0, "vector": 0}
_lock = threading.Lock()
_down_until = 0.0


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@functools.cache
def _server(uri: str) -> str:
    """Start the MCP server once; return its URL. The connection string goes in its environment, never a log."""
    npx = shutil.which("npx")
    if not npx:
        raise RuntimeError("npx is not installed")
    port = _free_port()
    env = {**os.environ, "MDB_MCP_CONNECTION_STRING": uri, "MDB_MCP_READ_ONLY": "true",
           "MDB_MCP_DISABLED_TOOLS": "atlas,connect,create,update,delete", "MDB_MCP_TELEMETRY": "disabled",
           "MDB_MCP_TRANSPORT": "http", "MDB_MCP_HTTP_HOST": "127.0.0.1", "MDB_MCP_HTTP_PORT": str(port)}
    proc = subprocess.Popen([npx, "-y", f"mongodb-mcp-server@{VERSION}"], env=env, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, start_new_session=True)
    atexit.register(proc.terminate)
    url = f"http://127.0.0.1:{port}/mcp"
    end = time.time() + 60  # the first start downloads the package
    while time.time() < end:
        if proc.poll() is not None:
            raise RuntimeError("mongodb-mcp-server exited")
        try:
            urllib.request.urlopen(url, timeout=1)
            return url
        except urllib.error.HTTPError:  # it answers (a bare GET is refused): up
            return url
        except OSError:
            time.sleep(0.5)
    proc.terminate()
    raise RuntimeError("mongodb-mcp-server did not start")


@functools.cache
def _mcp_tools(url: str) -> dict:
    from langchain_mcp_adapters.client import MultiServerMCPClient
    client = MultiServerMCPClient({"mongodb": {"transport": "streamable_http", "url": url}})
    return {t.name: t for t in asyncio.run(client.get_tools()) if t.name in TOOLS}


def guard(tool: str, args: dict, db: str, profile: str, workspace: str) -> dict:
    """The call as sent to the server: database fixed, collection allowed, scope added. ValueError otherwise."""
    coll = args.get("collection")
    if coll not in SCOPE:
        raise ValueError(f"collection must be one of {', '.join(SCOPE)}")
    bad = next((b for b in BANNED if f'"{b}"' in json.dumps(args)), None)
    if bad:  # $where, $function and stages that read other collections, in a filter as much as in a pipeline
        raise ValueError(f"{bad} is not allowed here")
    scope = {SCOPE[coll]: profile if SCOPE[coll] == "profile" else workspace}
    out = {"connectionId": "preconfigured", "database": db, "collection": coll}  # the server's own connection
    if tool == "aggregate":
        pipeline = args.get("pipeline") or []
        out["pipeline"] = [{"$match": scope}, *pipeline, {"$project": HIDDEN}, {"$limit": 50}]
    else:
        key = "filter" if tool == "find" else "query"
        out[key] = {"$and": [args.get(key) or {}, scope]}
        if tool == "find":
            proj = {k: v for k, v in (args.get("projection") or {}).items() if k not in HIDDEN}
            out["projection"] = proj if any(proj.values()) else {**proj, **HIDDEN}
            out["limit"] = min(int(args.get("limit") or 20), 50)
            if args.get("sort"):
                out["sort"] = args["sort"]
    return out


def tools(store, profile: str, workspace: str) -> list:
    """LangChain tools for this person, or [] when the workspaces are not in MongoDB or the server cannot start."""
    if not getattr(store, "uri", None):
        return []
    from langchain_core.tools import StructuredTool
    from pydantic import Field, create_model
    global _down_until
    if time.time() < _down_until:
        return []
    try:
        with _lock:
            remote = _mcp_tools(_server(store.uri))
    except Exception:  # noqa: BLE001 - the agent works without it; do not try again for a while
        _down_until = time.time() + 300
        return []
    db = store.db.name

    def make(name: str):
        def call(**kw):
            try:
                args = guard(name, kw, db, profile, workspace)
            except ValueError as e:
                return f"refused: {e}"
            try:
                res = asyncio.run(remote[name].ainvoke(args))
            except Exception as e:  # noqa: BLE001 - a bad stage or a dead server: tell the model, keep the turn
                return f"error: {type(e).__name__}: {str(e)[:300]}"
            return res if isinstance(res, str) else json.dumps(res, default=str)[:12000]
        return call

    coll = (str, Field(description="history (briefs, findings, notes, removed tools, shortlists: kind, tool, status, "
                                   "title, text, reason, feedback, city, sid, at), memories (past needs: need, persona, "
                                   "summary, rejected), shortlist (sid, note, location), sensors (phone readings: at, "
                                   "meta.tool, meta.scan, accuracy_m, altitude_m, heading_deg, values)"))
    schemas = {
        "find": create_model("mongo_find_args", collection=coll, filter=(dict, Field({}, description="MongoDB filter")),
                             projection=(dict, Field({})), sort=(dict, Field({})), limit=(int, Field(20))),
        "count": create_model("mongo_count_args", collection=coll, query=(dict, Field({}, description="MongoDB filter"))),
        "aggregate": create_model("mongo_aggregate_args", collection=coll,
                                  pipeline=(list, Field(description="Aggregation stages ($match, $group, $sort, ...)")))}
    help_ = ("Read only, through the MongoDB MCP server, and only this person's own records. Use it for counts and "
             "groupings over their past work that search_history cannot give. Never quote numbers from it to the person.")
    return [StructuredTool.from_function(func=make(n), name=f"mongo_{n}", args_schema=schemas[n],
                                         description=f"{remote[n].description}. {help_}") for n in TOOLS if n in remote]
