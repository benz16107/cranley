# Threshold web

The shell (everything here except `src/scene/`), the city map and the workspace renderer.

```
cd ../server && uv sync && uv run uvicorn threshold.api.app:app --port 8787
pnpm install && pnpm dev            # proxies /api to 8787, or set THRESHOLD_API
pnpm test                           # reducer, filters and the fixture audit (node --test)
```

| Path | What |
|---|---|
| `/` | Front door: say who you are, or pick a starting point |
| `/map?city=hou&kind=apartment&drone=1&empty=1&rooms=3-8&b=<lon,lat>` | City map, its filters and the selected address |
| `/scan/<sid>?f=<finding>&demo=access` | One scan. `demo=access` replays the scripted audit on it |

- `src/design/` holds the tokens and the rules (`README.md`). Read it before adding UI.
- `src/workspace/types.ts` is the one file of shared types, to be swapped for `docs/contracts/workspace.ts`.
- `src/workspace/agent.ts` tries `POST /api/agent/turn` and falls back to the fixtures in `src/fixtures/`.
- `design-lab/` keeps the two direction studies (`sheet.html`, `instrument.html`).
