# Threshold web

The shell (everything here except `src/scene/`), the city map and the workspace renderer.

```
cd ../server && uv sync && uv run uvicorn threshold.api.app:app --port 8787
pnpm install && pnpm dev            # proxies /api to 8787, or set THRESHOLD_API
pnpm test                           # reducer, filters and the fixture audit (node --test)
```

| Path | What |
|---|---|
| `/app` | The product: the App look. `/` and links without a look (`/map`, `/scan/<sid>`) open here |
| `/sheet`, `/a`, `/b`, `/c` | The front door in each earlier look: Sheet (the first shell), Overflight, Broadsheet, Maquette. The tab at the edge of the screen (or Alt+L) switches |
| `/<look>/map?city=hou&kind=apartment&drone=1&empty=1&rooms=3-8&b=<building id>` | City map, its filters and the selected building |
| `/<look>/scan/<sid>?f=<finding>&v=<mode>&demo=access` | One scan. `demo=access` replays the scripted audit on it |
| `/study/a`, `/study/b`, `/study/c` | The three design studies |

- `src/core/` is the product every look shares: workspace, agent link, data clients, URL, scene bridge. Its
  `README.md` is the contract a look is built against. Read it before adding UI.
- `src/skins/<look>/` is one look: its own tokens, type, layout, components and motion. `skins/registry.ts` maps URL
  prefixes to folders. `skins/sheet/design/README.md` holds the Sheet look's own rules.
- `src/scene/` is the shared 3D building view.
- `src/core/agent.ts` tries `POST /api/agent/turn` and falls back to the fixtures in `src/core/fixtures/`.
- `design-lab/` keeps the two direction studies (`sheet.html`, `instrument.html`).
