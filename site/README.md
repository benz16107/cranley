# Cranley site

The public site and docs: a home page, sponsor track pages, privacy and terms, and docs under `/docs`. Astro and
Starlight, static output, no server.

```sh
pnpm install
pnpm generate          # writes the generated docs and src/generated/site.json from the code (needs ../server set up)
pnpm dev               # http://localhost:5381
pnpm build && pnpm check
```

## What is generated

`scripts/generate.py` runs in the server's Python environment and writes, from the code:

| Page | From |
|---|---|
| `/docs/tools/*`, one page per tool | each tool's manifest, plus a real run on a made-up test scan |
| `/docs/reference/api/*` | FastAPI's OpenAPI schema (`server/threshold/api/app.py`) |
| `/docs/reference/result-format/` | `server/threshold/tools/types.py` |
| `/docs/reference/personas/` | `server/threshold/agent/personas/` |
| `/docs/reference/layers/` | `server/threshold/layers/catalog.py` |
| `/docs/mcp/` | `docs/MCP.md` |
| `/docs/sponsor-integrations/`, `/tracks/*` | the tracks in `docs/story.md` |
| the home page's drawing and counts | `src/generated/site.json` |

It runs with an empty data folder and the network switched off, so nothing it writes can hold sponsor data. Run it
again after a tool, a route, a persona or `docs/story.md` changes, and commit the result. Do not edit the generated
files by hand.

## Pictures are slots

Every picture and clip is a slot (`src/site/slots.ts`). To fill one, add a file named after the slot:

- `public/media/<slot>.webp` (or png, jpg, mp4, webm): a safe visual. Made-up test scans, our own drawings,
  OpenStreetMap. Committed.
- `public/media/real/<slot>.*`: the real product with sponsor content on screen. This folder is git-ignored and is
  used only when the site is built with `CRANLEY_REAL_VISUALS=1`, after CoStar has confirmed the website.

Build flags: `PUBLIC_SLOT_LABELS=off` hides the notes that name each slot (and any slot with nothing in it),
`PUBLIC_INDEX=1` lets search engines in.

## Rules

- No sponsor data, scan ids or private-home addresses in this folder. `pnpm check` looks for the obvious ones.
- No copyleft dependencies. `sharp` (libvips, LGPL) is left out in `pnpm-workspace.yaml`; pictures are sized when they
  are copied in (`generate.py --media <shots folder>`).
- The tokens are the App look's (`../web/src/skins/app/design/tokens.css`). `src/styles/site.css` adds reading sizes only.
