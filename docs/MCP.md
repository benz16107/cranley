# Threshold over MCP, and the `threshold` command

Threshold's tools work from any MCP client (Claude Code, Claude Desktop, Cursor, a LangChain agent) and from a
terminal. The server reads the same registry as the web app, so a tool added under `server/threshold/tools/`
shows up in both without further changes.

It runs on your machine with your data folder (`$THRESHOLD_DATA_DIR`, default
`~/Code/hackathons/hackprinceton26-data`) and keys (`$THRESHOLD_DATA_DIR/.env`). Results are for the
person running it: lists stop at 25 rows, findings at 50, and no tool returns panorama or floor plan images.

## What it exposes

| Kind | Name | Writes |
|---|---|---|
| Tools | every built tool in the registry (53 read-only today, e.g. `garage_fit`, `door_widths`, `fire_preplan`), inputs taken from its manifest | no |
| Tools | `search_buildings`, `building_facts`, `workspace_read`, `list_findings` | no |
| Tools, with `--write` only | `agent_turn`, `workspace_create`, `workspace_ops`, `room_labeller` | yes, marked `WRITES` and `readOnlyHint: false` |
| Resources | `threshold://scan/{sid}/summary`, `threshold://workspace/{id}`, `threshold://measures` | |
| Prompts | `wheelchair_check`, `fire_preplan`, `garage_check` | |

A tool returns the ToolResult (Contract 3) as structured content, plus a few lines of text built from the
result's own fields: the verdict, the metrics with their confidence, failing checks, findings and assumptions.

## Claude Code

```sh
claude mcp add threshold -- uv run --directory ~/Code/hackathons/hackprinceton26/server python -m threshold.mcp
# with agent turns and workspace writes:
claude mcp add threshold-write -- uv run --directory ~/Code/hackathons/hackprinceton26/server python -m threshold.mcp --write
```

Then ask: "Will an F-150 fit in the garage of scan <scan-id>?" Claude calls `garage_fit` and answers from
its result.

When the API is running, the same read-only server is at `http://127.0.0.1:<port>/mcp` over streamable HTTP:

```sh
claude mcp add --transport http threshold-http http://127.0.0.1:8787/mcp
```

The HTTP endpoint answers only requests addressed to `localhost` or `127.0.0.1` (MCP's DNS-rebinding guard), so
it is not reachable through the tailnet or a funnel. From another machine, run the stdio server over ssh as below.

## Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or
`%APPDATA%\Claude\claude_desktop_config.json` (Windows) and restart Claude Desktop.

On the machine that has the repo and the data folder:

```json
{
  "mcpServers": {
    "threshold": {
      "command": "uv",
      "args": ["run", "--directory", "~/Code/hackathons/hackprinceton26/server", "python", "-m", "threshold.mcp"]
    }
  }
}
```

From a laptop, with the server on linuxbox:

```json
{
  "mcpServers": {
    "threshold": {
      "command": "ssh",
      "args": ["linuxbox", "cd ~/Code/hackathons/hackprinceton26/server && uv run python -m threshold.mcp"]
    }
  }
}
```

## Cursor

`.cursor/mcp.json` in a project, or `~/.cursor/mcp.json` for every project:

```json
{
  "mcpServers": {
    "threshold": {
      "command": "uv",
      "args": ["run", "--directory", "~/Code/hackathons/hackprinceton26/server", "python", "-m", "threshold.mcp"]
    }
  }
}
```

## A LangChain deep agent

`server/examples/mcp_deepagent.py` loads the tools with `langchain-mcp-adapters` and hands them to
`create_deep_agent`:

```sh
cd server && uv run python examples/mcp_deepagent.py "will an F-150 fit in the garage of scan <scan-id>"
```

## The `threshold` command

`uv sync` in `server/` installs it. Run it as `uv run threshold ...`, or activate `server/.venv`.
`uv run python -m threshold.cli` does the same.

```sh
threshold tools                                         # every tool, [writes] marks the ones that write
threshold run garage_fit --scan <scan-id> -i vehicle=ford_f150
threshold run door_widths --scan <scan-id> -i min_width_m=0.81
threshold search greenwood --city Houston
threshold search --where 'garage_width>=6' --kind house --limit 5
threshold building <scan-id>                          # index row, plan summary, listing claims
threshold ask "will an F-150 fit in this garage" --scan <scan-id>   # agent turn; progress on stderr
```

`--json` prints the full result instead of text. `-i key=value` reads the value as JSON when it parses
(numbers, `true`, lists) and as a string otherwise. `threshold ask` writes a workspace, the same kind the web
app opens.

## Testing

```sh
cd server && uv run pytest tests/mcp
npx @modelcontextprotocol/inspector --cli uv run --directory server python -m threshold.mcp --method tools/list
```
