# Cranley (code name `threshold`)

Listings say "accessible", "two-car garage", "fits a king bed". Nobody measures before you commit. Cranley is one
place where an agent assembles the tools your need requires, from a city map down to a measured doorway, and checks
real buildings inside and out. Every number comes from a calculation, never from a model's text.

Built at HackPrinceton Fall 2026 (November 13 to 15) for CoStar's "Inside and Out: AI for the Built World" track, on
Matterport interior scans, Vexcel aerial imagery and CoStar records, plus your own iPhone scan for any building.

<!-- Screenshots go here. Use only images from our own scans, the made-up demo cafe, OpenStreetMap or our own
     diagrams (docs/site-plan.md lists what is safe). Never sponsor imagery. -->
| | |
|---|---|
| *Screenshot: the workspace after a wheelchair search* | *Screenshot: a phone scan converted to a plan* |
| *Screenshot: the agent's parallel lanes and an approval card* | *Screenshot: the PDF site report* |

## What it does

1. You say what you need, in plain words.
2. A composer picks tools from more than 75 and asks only for missing inputs (your chair's width, your truck).
3. An investigator agent plans, checks many buildings at once (one subagent each, shown live), and waits for your yes
   before expensive steps such as a fire simulation.
4. The workspace shows a ranked table, the route drawn through the 3D building, the failing door in red, the photo that
   shows it, and the source and reliability (high, medium, low) of every number.
5. You can change the building ("widen this door"), re-run the checks, and take a PDF report with you.

Tools cover step-free access, aging in place, furniture paths, stretcher routes, fire pre-plans with NIST CFAST smoke,
smoke-alarm census from photos, flood rehearsal with Hurricane Harvey water levels, record versus reality, office fit,
takeoff and bids, garage and driveway fit, pets and kids, docks, truck access, parking, roof facts, site scorecards
and market comps, sun and solar, wildfire space, Wi-Fi and camera coverage, quiet rooms, feng shui and more. The story
behind the product, per track, is in [`docs/story.md`](docs/story.md).

## Architecture

```
 web (React 19, Vite)                              server (Python 3.12, FastAPI)
 ┌───────────────────────────────────────┐         ┌────────────────────────────────────────┐
 │ /app   Home, Explore, Building,       │         │ agent/     composer + deepagents        │
 │        Investigations, Insights,      │◄──SSE───┤            investigator, workspace ops  │
 │        Tools, Settings                │         │ tools/     one folder per tool          │
 │ /m     phone companion (QR pairing)   │──ops───►│ geometry/  routes, clearance, rules,    │
 │ scene/ three.js: dollhouse, plan,     │         │            takeoff, georef, water       │
 │        panoramas, mesh, splats        │         │ vision/    panorama reader              │
 └───────────────────────────────────────┘         │ aerial/    site facts, elevation        │
 ios/   SwiftUI app: RoomPlan scan, LiDAR          │ sources/   Matterport, Vexcel, CoStar   │
        measure, barometer → POST /api/scans/user  │ world/     3D city, terrain, storms     │
                                                   │ splat/     interior splat training      │
                                                   │ report/    PDF site reports             │
                                                   │ whatif/    plan edits, cost, forks      │
                                                   └──────────┬───────────────┬─────────────┘
                                              MongoDB Atlas ◄─┘               └─► Tiger Cloud
                                    workspaces, op log, live sync,     building facts, history,
                                    search, memory, checkpoints        search by measurement, forks
```

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md): the five contracts (plan, data API, tool result, overlays, workspace).
- [`server/threshold/tools/README.md`](server/threshold/tools/README.md): how to write a tool.
- [`web/src/core/README.md`](web/src/core/README.md): the web core and how a look plugs in.

## Data and keys: bring your own

**No sponsor data is in this repository, and none may be added.** CoStar's hackathon terms limit the data to the event
and forbid it in public repos and demos. To run Cranley on the real layers you need your own access to the Matterport
Model API, Vexcel and the CoStar kit, under your own agreement with them.

Keys and data live outside the repo in a data folder, `$THRESHOLD_DATA_DIR` (default
`../hackprinceton26-data`, beside the checkout). Copy [`.env.example`](.env.example) to `$THRESHOLD_DATA_DIR/.env` and
fill in what you have:

| Variable | For |
|---|---|
| `MATTERPORT_API_KEY`, `MATTERPORT_API_TOKEN`, `MATTERPORT_SDK_KEY` | interior scans |
| `VEXCEL_API_KEY` | aerial imagery, elevation, property facts, 3D city |
| `COSTAR_KIT_URL`, `COSTAR_ZIP_PASSWORD` | CoStar records |
| `ANTHROPIC_BASE_URL`, `ANTHROPIC_API_KEY`, `THRESHOLD_MODEL` | the agent and the vision reader (any Anthropic-compatible endpoint) |
| `THRESHOLD_STORE=mongo`, `MONGODB_URI`, `MONGODB_DB` | workspaces on MongoDB Atlas (default: files in the data folder) |
| `TIGER_DATABASE_URL` (and `TIGER_ACCESS_KEY`, `TIGER_SECRET_KEY` for forks) | building facts on Tiger Cloud |
| `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT`, `LANGSMITH_TRACING` | traces and experiments |
| `OLLAMA_HOST_URL` | in-database embeddings through pgai |
| `CFAST`, `BRUSH_BIN` | paths to the CFAST fire model and the Brush splat trainer, if installed |

Without sponsor keys, the iPhone scan path still works: a RoomPlan export becomes a plan and every geometry tool runs on
it. `server/threshold/roomplan/demo.py` writes two made-up test scans (a home and a small cafe) to try it.

## Run it

Server (Python 3.12 through [uv](https://docs.astral.sh/uv/)):

```sh
cd server
uv sync
uv run uvicorn threshold.api.app:app --port 8787
uv run pytest                 # unit tests use hand-made plans; tests that need real data skip without it
```

Web (pnpm):

```sh
cd web
pnpm install
pnpm dev                      # http://localhost:5173/app, proxies /api to 8787 (THRESHOLD_API overrides)
pnpm test && pnpm build
```

Phone companion: open `/m` on a phone over HTTPS (camera, motion and location need a secure origin) and pair with the
QR code on the desktop's Phone tab.

iPhone app: `ios/Threshold` is an XcodeGen project (display name Cranley) (`xcodegen` then open in Xcode 27). It has a demo mode with the
test scans. `ios/scripts/install.sh` covers USB and TestFlight installs.

MCP server and CLI: every tool is also an MCP tool (read-only by default; agent turns and workspace writes only with
`--write`), plus building search, facts, workspace resources and prompts. Add it to Claude Code with

```sh
claude mcp add threshold -- uv run --directory <repo>/server python -m threshold.mcp
```

or, with the API running, `claude mcp add --transport http threshold-http http://127.0.0.1:8787/mcp` (localhost only).
The `threshold` command (`threshold tools`, `run`, `search`, `building`, `ask`) wraps the same registry. Claude Desktop,
Cursor and a LangChain deep agent over MCP are in [`docs/MCP.md`](docs/MCP.md).

Demo flows: six scripted walkthroughs, one per sponsor track, live in `web/src/skins/app/demo/flows/` (how they run,
record and replay offline: [`web/src/skins/app/demo/README.md`](web/src/skins/app/demo/README.md)).

## Credits

All code here was written during the event. We built on: FastAPI, Pydantic, Shapely, NumPy, LangChain deepagents,
LangGraph, LangSmith, langchain-mcp-adapters, the MongoDB MCP server, pymongo, pg8000, pgai, fastembed, Ollama, React,
Vite, three.js, React Three Fiber, drei, Spark, MapLibre GL, deck.gl, Base UI, cmdk, Sonner, Vaul, NumberFlow,
react-resizable-panels, zustand, Brush (Apache-2.0, run as an external binary), NIST CFAST (public domain, run as an
external binary), Apple RoomPlan and ARKit, OpenStreetMap (ODbL) and USGS high-water marks.

## Licence

All rights reserved; see the event terms (CoStar's hackathon terms, section 4.2, assign project IP to CoStar).
