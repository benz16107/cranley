# Cranley site

The public site and docs: a short home page, the long version at `/how/`, sponsor track pages, privacy and terms, and docs under `/docs`. Astro and
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
| `/about/` | `docs/devpost/about.md`, word for word from its first section on |
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

Every captured screenshot on the site is in dark mode (Ben's rule, 2026-11-15): the proof pictures, phone screens and
any app screen. The share card `public/og.png` follows it: it is the home page's hero shot in dark at 1200 x 630, with
the header links, the buttons and the drawing's legend hidden. Drawings and charts follow the site's own theme and are exempt. A light screenshot does not go in.

The pictures of what people sent us (`src/site/proof.ts`, shown by `Proof.astro`) are not slots. They are copied in by
hand after a read for names, usernames, addresses and scan data; the header of `proof.ts` says which of them carry
blurs added for this site. The interview on the Peri page is YouTube's player, the one thing the site loads from
another company; `pnpm check` allows that address on that page only, and the privacy page names it.

One thing on the site is never in git: the recorded phone call on the Photon page, because it is about a real home
(repo rule 1). `scripts/deploy.sh` copies its audio and its timeline from `$THRESHOLD_DATA_DIR/site-private/` into two
ignored paths (`public/media/real/` and `src/site/call.local.json`) before each build, and says whether it found them.
A checkout without that folder builds the Photon page without the call. The folder's README says what was checked.

Build flags: `PUBLIC_SLOT_LABELS=off` hides the notes that name each slot (and any slot with nothing in it),
`PUBLIC_INDEX=1` lets search engines in.

## Deploying

The site is live at https://cranley.app (Vercel project `cranley`, deployed from benmac, where the Vercel login is).

```sh
scripts/deploy.sh           # a preview behind a Vercel login, slot notes on
scripts/deploy.sh --prod    # production. Needs Ben's yes. Builds with PUBLIC_SLOT_LABELS=off PUBLIC_INDEX=1
```

The rollback target and the DNS records are in the header of `scripts/deploy.sh`.

## Rules

- No sponsor data, scan ids or private-home addresses in this folder. `pnpm check` looks for the obvious ones.
- No copyleft dependencies. `sharp` (libvips, LGPL) is left out in `pnpm-workspace.yaml`; pictures are sized when they
  are copied in (`generate.py --media <shots folder>`).
- The tokens are the App look's (`../web/src/skins/app/design/tokens.css`). `src/styles/site.css` adds reading sizes only.
