# External site plan

**Built and live (2026-11-14, 8 pm):** https://cranley.app, from `site/` (`ws/site`, Astro and Starlight, static,
Vercel). Track pages are generated from `docs/story.md`; docs from the tool manifests and the OpenAPI schema. Every
picture is a slot (`site/src/site/slots.ts`): safe files in `site/public/media/` are committed; real-product files go
in the git-ignored `site/public/media/real/` and are used only with `CRANLEY_REAL_VISUALS=1`, after CoStar confirms
websites. Production deploys (`site/scripts/deploy.sh --prod`) need Ben's yes; the rollback target is in that script.
The plan below is what the site was built from.

A one-page site in the style of Ben's earlier submissions (tesseraphoto.com had a hero, how it works, and one page
per sponsor track). Source of every word: `docs/story.md`.

## What may be shown where (updated 2026-11-14, 5:45 pm)

| Where | Real product with Matterport, Vexcel and CoStar content on screen | Raw data files | Source of the rule |
|---|---|---|---|
| Devpost page and gallery | **Yes** | No | CoStar organizer (tweidling) in #costar-group, 5:42 pm: "Yes absolutely" to showing screenshots of the app displaying scans, imagery and records |
| Demo video | **Yes** | No | same answer |
| In-person demo to judges | Yes | No | same answer |
| Public repo (`benz16107/cranley`) | No: no screenshots of sponsor content, no data | No | the terms; the README says sponsor data is not included and "All rights reserved; see the event terms" |
| External website (cranley.app) | **Ask CoStar first.** Until then, only safe slots (`CRANLEY_REAL_VISUALS` off) | No | the question did not cover a website |

Even where allowed, prefer frames without a private home's street address in large type; crop the address line when
it adds nothing. Gallery picks with captions: `$THRESHOLD_DATA_DIR/submission/gallery/CAPTIONS.md`.

## The constraint that shapes every website visual (until CoStar answers about the site)

CoStar's hackathon terms say no CoStar, Matterport or Vexcel data in a public demo or repo, the data is usable only
until Sunday 4:00 pm ET and must then be deleted with every derivative, and section 4.2 assigns project IP to CoStar.
So **every public visual comes from data that is not theirs**, unless CoStar confirms otherwise in writing (Ben has
been asked to post the question in #costar-group). Not theirs:

- an iPhone RoomPlan scan of a space we scanned ourselves (with the owner's permission), or the made-up test home and
  test cafe in `server/threshold/roomplan/demo.py`;
- OpenStreetMap (attribute "© OpenStreetMap contributors") and other public layers with open licences (USGS,
  FEMA flood maps, city open data), checked one by one;
- our own diagrams and UI with no sponsor content on screen.

A derivative counts too: a photoreal mesh, a splat, a route drawn on a scan, a table of results, a count per building,
a screenshot of the map with scan markers, even a blurred one. When in doubt, leave it out.

## Pages (one page with anchors; per-track anchors can become pages later)

1. **Hero.** Name, tagline, one line on who it is for, the real product in motion: a 10-second loop of the App look
   running on the test home (composer, agent lanes, ranked result, route drawn, door in red). Links: Devpost, code,
   video.
2. **The problem.** "Two-car garage", "accessible", "fits a king". Three short cases in words (wheelchair, flood, fire
   crew). No stock photos.
3. **How it works.** Four steps with one visual each: say the need; the agent composes the tools; it checks buildings
   in parallel and asks before expensive steps; you see the evidence and take the report. Then the rule: every number
   from a calculation, with a diagram of a number's path (geometry to result object to screen, model off to the side).
4. **Tools by persona.** A grid of the 50 personas grouped (getting around, safety, home life, business, research),
   each with its tools named. Text only, or icons drawn for us.
5. **The ecosystem.** Web app, phone companion, iPhone LiDAR app, PDF report, MCP server and CLI, the two databases.
   One diagram.
6. **Honesty.** Reliability labels, "cannot answer here", "what we did not check", the rubric grader.
7. **Built on an AMD mini PC.** Splats trained on an integrated GPU; the numbers from story.md. Visual: a photo of
   the mini PC and a training-loss chart (our own numbers, not the scene).
8. **Tracks.** Anchors for CoStar, Amazon, LangChain deepagents, Tiger Data, MongoDB Atlas (and Peri if entered): the
   angle, what serves each criterion, the proof. Text plus product screens from safe data.
9. **Team.** Names, schools, links.
10. **Footer.** Terms and privacy pages (needed once any form collects a name or email; the plan has no form, so a
    short privacy note is enough), data credits, the line "no CoStar, Matterport or Vexcel data appears on this site".

Design: follow the App look's tokens (the product is a tool, not a showcase), walk `design-tells.md` before shipping,
and keep one moving element per page (the hero loop).

## Visuals and where each comes from

| # | Visual | Section | Source | Safe? | To make |
|---|---|---|---|---|---|
| 1 | Hero loop: composer, agent lanes, ranked table, route, red door | Hero | App look on the made-up test home (`u_` scan from `roomplan/demo.py`), server with sponsor sources switched off | yes, if no sponsor panel or map marker appears | record with Playwright on a server started with no sponsor keys |
| 2 | iPhone scan to plan | How it works, Ecosystem | `shots/ios/01-home.png`, `02-scan-plan.png`, `03-scan-tools.png` (sample home) | yes (checked: sample home only) | reuse |
| 3 | Field report flow on the phone | Ecosystem, Peri | `shots/field/sim/01-06` (test cafe) | yes (checked `05-report.png`: "Test Cafe (made up)") | reuse |
| 4 | PDF report pages | Ecosystem, Honesty | `shots/field/test-cafe-*.pdf` | yes | export pages as images |
| 5 | Phone companion screens: level, sound, window compass | Ecosystem | `shots/mobile/iphone-21..24`, `iphone-13..15` | probably; check each for an address or scan name before use | review one by one |
| 6 | Number's-path diagram | How it works, Honesty | our own drawing | yes | draw |
| 7 | Ecosystem diagram | Ecosystem | our own drawing | yes | draw |
| 8 | Map of a neighbourhood with public layers | How it works | OpenStreetMap plus open layers, a place we pick, no scan markers | yes, with attribution | render from the explorer with the scan layer off |
| 9 | 3D of a scanned space | Hero alt, How it works | a real iPhone scan of a space we own or have permission for (needs the app on a phone; blocked on Apple's licence agreement) | yes once made | scan |
| 10 | Mini PC photo and training-loss chart | Hardware | a photo of the machine; loss numbers from our own training logs | yes (chart shows numbers only) | photograph; chart |
| 11 | Agent lanes and approval card | LangChain | re-shoot on the test home and test cafe | yes after re-shoot | re-shoot |
| 12 | LangSmith trace | LangChain | re-shoot a trace of a test-home turn | yes after re-shoot | re-shoot |
| 13 | Insights and search by measurement | Tiger | needs a public stand-in dataset (several test scans) or text only | not yet | decide: text only by default |
| 14 | Phone-to-desktop live sync | MongoDB | re-shoot on the test home | yes after re-shoot | re-shoot |
| 15 | Claude Code calling the tools over MCP | Ecosystem | re-record on the test home | yes after re-record | re-record |

## Re-shoot list for the website (after the build merges)

This list is for the external website only. Devpost and the video can use the real product; their retakes (for
the Cranley brand) are listed in `$THRESHOLD_DATA_DIR/submission/gallery/CAPTIONS.md`.

Three safe sources, and what each can and cannot show:

- **T (test scans):** the made-up home and cafe from `server/threshold/roomplan/demo.py`, uploaded through
  `POST /api/scans/user` (ids `u_` plus 12 hex). They have walls, doors, windows, rooms and objects, but no
  panoramas, no mesh, no splat and no location. So: the measured dollhouse, the plan, routes, clearances, checks,
  reports. Never photoreal, never "on its site".
- **R (a real RoomPlan scan we made):** a space we own or have written permission to scan, captured on an iPhone
  (blocked until the app installs on a phone). Same limits as T, but real-looking proportions and furniture.
- **O (OSM and open layers only):** the map or explorer with the scan coverage layer, aerial imagery and the 3D city
  switched off. Streets, buildings from OpenStreetMap, open hazard and transit layers, with attribution.

Rules for every shot: start a workspace scoped to the `u_` scan only (`/place` or `brief.set`), so the composer
cannot pull in a city-wide tool that lists real buildings; hide the sidebar footer's scanned-address count; check the
frame for an address, a scan id other than the `u_` one, a CoStar field or an aerial tile before keeping it. Save to
`$THRESHOLD_DATA_DIR/shots/public/` so safe shots never mix with the rest.

| # | Shot | Source | Setup and what must be on screen | Replaces |
|---|---|---|---|---|
| 1 | Hero loop, 10 s: type the need, composer adds tools, agent lane runs, verdict, route draws, failing door turns red | T (home) | Brief "I use a wheelchair, 81 cm wide. Can I get from the front door to the bathroom?" scoped to the test home (its bathroom door is 0.71 m, so it fails). Measured 3D, cut open. Record at 1440 px, light theme | `app/`, `home/`, `firstrun/` |
| 2 | Home page with the composer and persona list, no recents | T | Fresh browser profile; empty Recent and Saved; footer count hidden or cropped | `home/after-*` |
| 3 | Agent panel: plan todos, two parallel lanes, an approval card | T (home and cafe) | Brief over both test scans that asks for a smoke clock on each, so both lanes pause on the CFAST approval. Crop to the agent panel | `sponsors/approval-card*.png`, `live-subagents.png` |
| 4 | LangSmith trace of the same turn | T | Trace from shot 3's turn; crop out the project's other runs, which carry real addresses | `sponsors/langsmith-trace.png` |
| 5 | Phone-to-desktop live sync | T (home) | Desktop workspace on the test home and `/m` paired beside it; type a door width on the phone, the Door widths panel updates. Split-screen recording | `mobile/desktop-0*.png` |
| 6 | Copy link opens a read-only shared workspace | T | Share the shot-1 workspace; open it in a second browser | none yet |
| 7 | Renovate: widen the bathroom door, Now and After | T (home) | Renovate tool on the 0.71 m door; the check flips to pass; cost line from the takeoff | `whatif/` |
| 8 | PDF reports, three pages each | T (cafe) | Accessibility, fire pre-plan and fit-out reports exported as images from `shots/field/test-cafe-*.pdf` | reuse |
| 9 | iPhone app: scan, plan, tools, measure, floor height | T now, R later | `shots/ios/` and `shots/field/sim/` are already safe; re-take on a real phone with an R scan once the app installs | reuse, then R |
| 10 | Fire pre-plan and egress on the cafe | T (cafe) | fire_preplan and egress_routes on the cafe: exits, longest walk, narrowest point, plan with the route | `tools/`, `show/` |
| 11 | Furniture or garage fit with 3D models | T (home) | furniture_fit for a sofa through the front door and hallway; the box or model overlay in the measured 3D. Garage fit needs a garage: add one to the made-up home only if the demo script gets it | `garage/`, `models/` |
| 12 | Feng shui or pet fit plan overlay | T (home) | Bagua grid or pet hazards drawn on the test home's plan | `fengshui/`, `pets/` |
| 13 | Claude Code calling a tool over MCP | T | Re-record the asciinema take with `door_widths` or `garage_fit` on the `u_` id; no real scan id in the prompt or the answer | `mcp/claude-code-f150*` |
| 14 | Neighbourhood map with open layers | O | Explorer on a Princeton or neutral street, scan layer off, satellite and 3D city off; FEMA flood or transit layer on; OSM attribution visible | `explorer/`, `datalayers/` |
| 15 | Nearby places (parks, vets, schools) | O | `nearby` around a bare point with no scan; map only | `pets/houston-*` |
| 16 | 3D of a real space | R | A scan we made, measured 3D cut open, one route and one clearance drawn | none yet |
| 17 | Hardware: mini PC photo and splat training-loss chart | own photo, own log numbers | Photograph the machine; chart loss or steps per second from the Brush logs, no rendered scene | `splat/` |

Cannot be shown publicly without CoStar's written yes, whatever the setup: photoreal interiors, interior or drone
splats, the Vexcel 3D city or aerial tiles, Harvey water in a real house, record versus reality, search by measurement
or city census results, Insights charts over real facts. Devpost, the video and the in-person demo may show all of
this (CoStar, 5:42 pm); the website may not until CoStar says so.

## Current screenshots that are NOT safe for the website or the repo

(They are fine for Devpost and the video since CoStar's 5:42 pm answer, apart from the "Threshold" brand on every
App-look shot taken before the rename.)

Everything under `$THRESHOLD_DATA_DIR/shots/` except the folders marked safe above. In particular:

- `sponsors/approval-card.png`, `approval-card-2.png`, `live-subagents.png`, `langsmith-trace.png`: real addresses and
  scan ids on screen (checked `approval-card.png`).
- `app/`, `polish-app/`, `home/`, `firstrun/`, `ux-audit/`, `review/`, `review-app/`, `integration/`, `skins/`,
  `design2/`, `shell/`: the product on real scans, real addresses, aerial thumbnails, scan counts.
- `views/`, `splat/`, `show/`, `scene/`, `walls/`, `geometry/`: photoreal meshes, splats, dollhouses, routes and
  floods on Matterport scans and the Vexcel city.
- `perception/`, `tools/`, `garage/`, `pets/`, `signals/`, `fengshui/`, `sunfire/`, `commercial/`, `whatif/`,
  `models/`: tool results on real scans (file names alone carry street names and scan ids).
- `explorer/`, `datalayers/`: maps with scan coverage or Vexcel imagery; some public-layer shots may be reusable after
  a check that no scan marker or aerial tile shows.
- `mcp/claude-code-f150*`: an MCP answer about real garages.
- `phone-qa/`, `mobile/` (the desktop screens and anything naming a building): check one by one.
- Any video recorded so far (the show recordings) uses real scans.

## Hosting

Static site (Astro or plain HTML) on Vercel or GitHub Pages; no server, no form. The live app itself is never public:
its API serves sponsor data. The domain is cranley.app.
