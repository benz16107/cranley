# External site plan (no build yet)

A one-page site in the style of Ben's earlier submissions (tesseraphoto.com had a hero, how it works, and one page
per sponsor track). Source of every word: `docs/story.md`.

## The constraint that shapes every visual

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
4. **Tools by persona.** A grid of the 34 personas grouped (getting around, safety, home life, business, research),
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

## Current screenshots that are NOT safe for public use

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
its API serves sponsor data. A domain is question 2 in `docs/story.md`.
