---
title: Getting started
description: Run the Cranley server and web app, with your own CoStar, Matterport and Vexcel access or with no keys at all.
---

Cranley is a Python server and a React web app. You can run both on one machine.

## What you need

- Python 3.12 or newer through [uv](https://docs.astral.sh/uv/)
- Node 22 or newer and [pnpm](https://pnpm.io/)
- A folder outside the repository for keys and data
- For the agent: a key for any Anthropic-compatible endpoint

## The data folder

Keys and data never go in the repository. They live in a folder you choose, named by `THRESHOLD_DATA_DIR`.

```sh
export THRESHOLD_DATA_DIR=~/cranley-data
mkdir -p $THRESHOLD_DATA_DIR
cp .env.example $THRESHOLD_DATA_DIR/.env
```

Fill in what you have. Everything is optional.

| Variable | For |
|---|---|
| `MATTERPORT_API_KEY`, `MATTERPORT_API_TOKEN`, `MATTERPORT_SDK_KEY` | Interior scans |
| `VEXCEL_API_KEY` | Aerial imagery, elevation, property facts, the 3D city |
| `COSTAR_KIT_URL`, `COSTAR_ZIP_PASSWORD` | CoStar records |
| `ANTHROPIC_BASE_URL`, `ANTHROPIC_API_KEY`, `THRESHOLD_MODEL` | The agent and the reader of panoramas |
| `THRESHOLD_STORE=mongo`, `MONGODB_URI`, `MONGODB_DB` | Workspaces on MongoDB Atlas. Without it, workspaces are files in the data folder |
| `TIGER_DATABASE_URL`, and `TIGER_ACCESS_KEY`, `TIGER_SECRET_KEY` for forks | Building facts on Tiger Cloud |
| `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT`, `LANGSMITH_TRACING` | Traces and experiments |
| `OLLAMA_HOST_URL` | Embeddings inside the database through pgai |
| `CFAST`, `BRUSH_BIN` | Paths to the CFAST fire model and the Brush splat trainer, if installed |

## Bring your own keys

No sponsor data is in the repository, and none may be added. CoStar's hackathon terms limit the data to the event. To run Cranley on the real layers you need your own access to the Matterport Model API, to Vexcel and to CoStar's data, under your own agreement with each.

## Run the server

```sh
cd server
uv sync
uv run uvicorn threshold.api.app:app --port 8787
uv run pytest
```

Unit tests use small hand-made plans. Tests that need real data skip when it is missing.

## Run the web app

```sh
cd web
pnpm install
pnpm dev
```

Open `http://localhost:5173/app`. The dev server proxies `/api` to port 8787. Set `THRESHOLD_API` to point it somewhere else.

## Try it with no keys

A scan from an iPhone becomes the same plan format as a sponsor scan, so every geometry tool runs on it. The repository can write two made-up test scans, a home and a small cafe. No real place was scanned for either.

```sh
cd server
uv run python -m threshold.roomplan.demo /tmp/home.json
python3 -c 'import json; print(json.dumps({"export": json.load(open("/tmp/home.json")), "name": "Test home"}))' \
  | curl -s -X POST http://127.0.0.1:8787/api/scans/user -H 'content-type: application/json' -d @-
```

The reply starts with the new scan's id, `u_` and twelve characters. Use it with any tool:

```sh
uv run threshold run door_widths --scan <scan-id> -i min_width_m=0.813
```

The test home's bathroom door is 0.71 m wide, so this check fails. That result is the drawing on the [home page](/).

We checked these steps on a server started with an empty data folder: the upload returned an id, and both `threshold run` and `POST /api/tools/door_widths/run` returned the result.

## Next

- Add the [MCP server](/docs/mcp/) to Claude Code.
- Pair a [phone](/docs/phone/) with a workspace.
- Read how a [tool](/docs/concepts/tools/) is written.
