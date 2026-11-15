# Cranley: the submission story

The living source for the Devpost page, the README, the site and the 2-minute pitch. Edit this file first; the
others are generated from it. Owner: the submission thread (`ws/submission`). Product name: Cranley (Ben, 2026-11-14); the code name `threshold` stays on packages,
folders, the CLI and the MCP server.

Name check (web search, 2026-11-14): no software, app or proptech product called Cranley. Several small UK property
companies carry the name (Cranley Gardens Property, Cranley Place Management, Cranley Property Company in Guernsey),
most named after Cranley Gardens and Cranley Place, streets in South Kensington, London. Domains not checked.

Public-text rule: this file goes into a public repo. It holds no sponsor data, no scan ids, no addresses, no
screenshots of sponsor imagery and no per-building counts. Devpost and the video may show the real product with
sponsor content on screen (CoStar organizer in #costar-group, 2026-11-14 5:42 pm: "Yes absolutely"); raw data files
never. The external website stays on the conservative plan until CoStar answers for it (`docs/site-plan.md`). Numbers about our own system (tests, timings, tool
counts) are fine. Dataset-derived numbers for the spoken pitch live outside the repo in
`$THRESHOLD_DATA_DIR/submission/pitch-numbers.md`.

---

## Questions for Ben

Answer these in the thread; the defaults below go in if there is no answer by about 6 am.

1. **Domain.** MLH has a GoDaddy Registry prize (needs a GoDaddy Registry TLD such as `.co`, `.us` or `.club`, not
   `.com`). Options: buy one for the external site (for example `cranley.co`, availability not checked), or skip.
   Default: skip; the site waits for CoStar's answer about websites anyway (see `docs/site-plan.md`).

2. **Tagline.** Candidates (Devpost allows 200 characters):
   - A. "Tell it what you need from a building. An agent builds the tools, measures the real thing inside and out, and shows its work."
   - B. "Listings say 'accessible' and 'two-car garage'. Cranley measures it: an agent that checks real buildings, inside and out, before you commit."
   - C. "One place where an agent assembles the tools your need requires, from the city map down to a measured doorway, and every number comes from a calculation."
   Default: **B** (problem first, names the product, says what it does).

3. **Main HackPrinceton track.** The form allows exactly one of Healthcare, Sustainability, Business/Enterprise,
   Entertainment/Media, Education, Science & Discovery. Default: **Business/Enterprise** (the product is a working
   tool for people who decide about buildings, which is what CoStar's customers do). Pick **Healthcare** instead if
   the pitch leads with the wheelchair and aging-in-place flow, or **Sustainability** if it leads with the Houston
   flood.

4. **LangChain is not on the Devpost prize list.** The handbook lists "Best use of deepagents" but Devpost's prizes do
   not include it, so there is no box to tick. Ask a LangChain rep or #qna on Discord how to enter. Default: name it in
   the description and tell the LangChain judge at the table.

5. **Peri needs a real business consulted during the event.** About 150 emails sent; the only human reply so far was a decline.
   The rule needs a business name, the person's name and role, and one piece of evidence. Cheapest path: walk into a
   cafe that opens early on Sunday (the outreach list has one opening 6:30 am a minute from the venue), show the field
   report flow, and get a quote and a photo. Default if nobody is consulted: **do not enter Peri** (an entry without
   the evidence is ineligible).

6. **Demo flow per track.** Proposed below under each track. Pick the lead flow for the 2-minute general pitch:
   wheelchair search (default), Houston flood, or fire pre-plan.

7. **Team and form fields** I cannot know: team members, Discord usernames, schools, rookie fraction. The Gemini
   project number field is required on the form: answer "N/A".

8. **Repo and licence.** Decided by the lead: the public repo is `benz16107/cranley`, built from a cleaned history
   (no scan ids on any tracked file), README saying sponsor data is not included and "All rights reserved; see the
   event terms". Its URL goes in the Devpost form's repository field once it exists.

---

## The problem

Every decision about a building is made blind. The listing says "two-car garage", "accessible", "fits a king bed",
"1,200 square feet". Nobody measures before you commit. You find out on moving day that the sofa does not turn the
corner, that the bathroom door is 71 cm and your chair needs 81, that the garage fits one truck and a bicycle.

The people who carry the cost are the ones with the least slack: a wheelchair user signing a lease, a family in
Houston deciding what to carry upstairs before a storm, a fire crew walking into a house they have never seen, a small
business signing for a space it has not checked against its own headcount.

The information exists. Laser scans of the interior, aerial photos sharp enough to count parking spaces, and market
records for the same address. But each layer sits in its own product, and every existing feature works inside one
listing at a time. Nobody joins them, and nobody asks your question across a whole city.

## What Cranley is

One place where an agent assembles the tools a person's need requires, from a world explorer down to a measured room.

You say what you need ("I use a wheelchair, find me a one-bedroom in Houston I can get into and use the bathroom").
The agent picks the tools, asks only what it must (your chair's width), runs them across many buildings at once, and
lays out a workspace: a ranked table, the route drawn through the 3D building, the door that fails in red, the photo
that proves it.

Every number comes from a calculation, never from a model's text. The model chooses, labels and explains. A door width
goes from the wall geometry to the result object to the screen. A grader checks the agent's closing message and
rejects any number it states.

## What makes it different

- **Inside, outside and the record, fused for one address.** Matterport interior scans (walls, doorways with real
  widths, rooms, panoramas), Vexcel aerial imagery (orthophotos, elevation, 165 ready-made property facts, a 3D city
  mesh) and CoStar records, joined in one scan frame. Tools check claims across layers: the record says one thing,
  the scan measures another, and the finding shows both with the evidence.
- **Your own building, anywhere.** The iPhone app scans a room with LiDAR (Apple RoomPlan) and converts it into the
  same plan format, so every geometry tool runs on a home or a shop that is in no dataset.
- **Photoreal 3D, built ourselves.** Matterport's mesh baked with its own panoramas, interior Gaussian splats we
  trained, the drone splat outside, all set inside the Vexcel 3D city with a cut-away. One continuous view from the
  street into the room.
- **Real physics, not illustrations.** Smoke runs through NIST's CFAST fire model on the measured rooms and doors.
  Floods use real water levels from Hurricane Harvey's USGS high-water marks against the floor height from aerial
  elevation and door sills.
- **What-if on a database fork.** "Widen this door, add a ramp": the renovate tool edits the plan, re-runs the checks,
  prices the work from a takeoff, and runs city-wide what-ifs on a zero-copy fork of the facts database that is deleted
  afterwards.
- **The building in its city.** One continuous view from the map down through the aerial and the 3D city into the
  scanned room, with 66 layers around it: flood zones, Harvey high-water marks, fire stations and hydrants, zoning,
  permits, transit, schools, live weather and earthquakes, each labelled with its source and the date it was fetched.
- **Search by what is measured inside.** "Houses in Los Angeles with three bedrooms on one floor and every door at
  least 81 cm" is one query over the facts database, not a filter on a listing.
- **Any agent can use it.** The same tool manifests feed the web app, the agent, an MCP server (stdio and streamable
  HTTP, read-only unless started with `--write`) and the `threshold` CLI. Claude Code can ask "will an F-150 fit in
  this garage" and answer from the tool's result.

## The ecosystem

| Part | What it does | State |
|---|---|---|
| Web app (`/app`) | Home, Explore (one view from the map to the room, 66 layers), Building (3D, plan, inside, drone; measured or photoreal; alone or on its site), Investigations, Insights, Tools, Settings | merged |
| Phone companion (`/m`) | Pairs by QR with a desktop workspace; GPS, camera, mic, barometer, tilt and typed measurements feed tools live | merged |
| iPhone LiDAR app | RoomPlan scan of your own space, LiDAR tape measure, barometer floor height, compass window facing, scan-to-report | merged; builds and runs in the simulator; not on a phone yet (Apple licence agreement) |
| PDF reports | Site report for any workspace: plan with numbered fixes, evidence, occupant load, smoke-alarm census, what was not checked | merged |
| MCP server and CLI | Every tool for Claude Code, Claude Desktop, Cursor or a LangChain agent; resources and prompts; `threshold` on the command line | merged |
| Shared databases | MongoDB Atlas for people's work, Tiger Cloud for building facts | merged |

## Honesty

- Every number carries its source: layer (Matterport, Vexcel, CoStar, drone, model), method (geometry, vision, lookup,
  simulation) and a reliability label (high, medium, low) with a note.
- When a scan cannot answer, the tool says so with an `unknown` verdict and the reason (no wall graph, no door data,
  unscanned space). Every plan carries a quality block the tools check first.
- Reports end with "what was not checked".
- The agent's closing message is graded: no numbers, no claim that a check was skipped unless the transcript shows it.
- Expensive or invasive steps (a smoke simulation, a vision read of every panorama, a plan edit) wait for the person's
  yes.

## The hardware story

The photoreal interiors were trained on a mini PC with an AMD Ryzen 9 7940HS and its integrated Radeon 780M graphics.
No NVIDIA card. We ran Brush (an open-source Gaussian splat trainer in Rust and WebGPU) through Vulkan at about 17
steps a second, 16 to 23 minutes per building, seeded from the scanned mesh, with virtual views rendered from that mesh
and a free-space carve to clear haze. The same machine runs the API, the CFAST fire model, Ollama for embeddings, and
the headless real-GPU Chrome that renders our screenshots.

---

## Tracks

### CoStar: Inside and Out, AI for the Built World (main target)

Judged 30% use of the data, 30% agentic depth, 25% usefulness, 15% demo and polish.

**Angle.** The track asks for something that makes CoStar say "we didn't know you could do that with our data". Every
CoStar product today answers questions inside one listing. Cranley answers a person's question across a whole city,
by measurement, with all three layers checking each other.

| Criterion | What serves it |
|---|---|
| Use of the data (30%) | All three layers in one frame: walls and doorways from Matterport, elevation, ortho, property facts and the 3D city from Vexcel, records from CoStar. Cross-layer tools: record versus reality (listed vs measured area, claims check), flood (Vexcel ground elevation + Matterport door sills), garage and driveway fit (interior garage + aerial driveway), site tools (docks, truck access, parking from the air), drone splat aligned to the scan. Search by measurement over every scan with a wall graph. |
| Agentic depth (30%) | A deepagents investigator that plans (todo list the person watches), fans out one subagent per building in parallel, asks before expensive steps, remembers what it learned per building, and resumes after a restart from a MongoDB checkpoint. The composer picks tools for the need from more than 75, asks only the missing inputs, and the workspace is a document the agent and the person edit with the same operations (with undo). |
| Usefulness (25%) | 50 personas, each a real user with a named need: wheelchair user, fire captain, Houston homeowner before a storm, truck dispatcher, office tenant, CoStar researcher, insurance underwriter, daycare operator, car owner. For the people who open CoStar every morning: a tenant rep's weighted site scorecard across candidates, market comps from CoStar records, industrial fit (clear height, docks, truck court), retail site screening, commute fit for a whole team, and a facility audit PDF. PDF report a person can hand to a landlord. |
| Demo and polish (15%) | Photoreal building on its site, flood rising in the street, smoke filling rooms, the agent's lanes working in parallel. A dense working tool, not a showcase. |

**Demo path (2 minutes).**
1. Home. Type "I use a wheelchair, 81 cm wide. Find a one-bedroom in Houston I can get into and use the bathroom."
2. The composer adds step-free route, door widths, turning space and bathroom clearance, asks nothing (width given).
3. The investigator's lanes run five buildings at once; the ranked table fills.
4. Open the top building: photoreal, on its site in the city. The route draws from the curb to the toilet; the one
   narrow door shows red with "Matterport geometry, high".
5. Record versus reality on the same building: the listed area against the measured one.
6. Twenty-second switch: Houston homeowner, Harvey water rising through the same photoreal house, the list of what
   to move first.
7. Close on the catalogue and the line "every number from a calculation".

### Amazon: Best Practical AI Innovation

Judged creativity, usefulness, technical implementation and user experience, 25% each.

**Angle.** AI someone would use every day: a person with a real need about a building gets an answer they can act on,
without learning a tool. And it works on their own home, not only on a dataset.

| Criterion | What serves it |
|---|---|
| Creativity | An agent that builds the interface per need instead of a chat box; physics and geometry instead of text answers. |
| Usefulness | The wheelchair, flood, fire, garage, pet and furniture tools answer questions people ask on forums every day. The iPhone scan makes it work on any building. |
| Technical | About 600 server tests and 90 web tests; every tool run on a 15-place demo set with a matrix of results (see Proof); FastAPI, deepagents, two cloud databases, our own 3D renderer and splat training. |
| User experience | The App look: one thing first on every screen, the rest folded; plain-word reliability chips; every panel resizable; guided first run; both themes; phone companion with live sync. |

**Adaptive intelligence** (a named focus area): the agent's memory per building and per person, "what I learned about
you" with undo per item, past investigations searchable by words and meaning.

**Demo path.** Phone: scan a room with the iPhone app (demo cafe in the simulator), name the business, pick
Accessibility, get the PDF in seconds. Desktop: the same workspace updates live. Then the wheelchair search above.

### Peri: Forward Deployed Challenge

Judged real-world need, usability (could the business adopt it immediately), execution.

**State: no business consulted yet.** See question 5. The entry is only eligible with a business name, the person's
name and role, and one piece of evidence.

**Angle if a business is consulted.** A small business in Princeton is not in CoStar's data. The iPhone app scans the
shop, and the same tools answer the questions a fire inspector or a wheelchair-using customer would ask: step-free
route from the door to the counter, door widths, occupant load from the measured floor area, exits, smoke alarms seen
in photos. The output is a PDF the owner keeps, with numbered fixes and what was not checked. They could use it the
same day.

**Demo path.** The owner's quote and photo first, then their problem in their words, then the scan-to-report flow on
their space (or the demo cafe if they declined a scan), then the report.

### LangChain: Best use of deepagents

Not on the Devpost prize list (question 4). Every feature below does a job in the product; the full table with what
was skipped and why is `$THRESHOLD_DATA_DIR/reports/sponsor-features.md`.

| Feature | Why it is a real use |
|---|---|
| `create_deep_agent` with declarative subagents | One building or one whole property per subagent, each with its own context, so ten buildings do not crowd one context window. |
| Parallel subagents, shown live | Buildings are independent, so they are checked at the same time; middleware reports each tool call and the panel shows one lane per subagent. |
| Planning (`write_todos`) | The plan is the person's progress view, not hidden state. |
| Virtual filesystem and CompositeBackend | Case notes per building in state; `/memories/` in the store; `/skills/` read-only from disk. |
| StoreBackend on MongoDB (long-term memory) | A second investigation of a building starts from what the last one learned. |
| Skills (SKILL.md) | Procedures for fire pre-plan, storm prep, step-free home and record check load only when the need matches. |
| Human-in-the-loop (`interrupt_on`, `when` predicate) | A smoke simulation, a vision read of every panorama, a plan edit or a city rollup waits for "Run it / Skip it / Always run it here". |
| MongoDB checkpointer, `Command(resume=…)` | A paused turn resumes in any server process, even after a restart. |
| Rubric grader middleware | Catches the closing message stating numbers or claiming checks did not run; a real turn made that mistake before this existed. |
| MCP tools via langchain-mcp-adapters | The read-only MongoDB MCP server's tools, behind a guard, answer counts over the person's own past work. |
| LangSmith traces, datasets and experiments | Every turn is one trace tagged by persona; the composer's briefs are a dataset, and each prompt change is an experiment scored per check. |

**Demo path.** A fire captain's brief over two houses: the todo list appears, two lanes run in parallel, both pause
on the CFAST approval card, "Run it" resumes from the checkpoint, the rubric verdict and the LangSmith trace close it.

### MLH: Best Use of Tiger Data

Tiger Cloud is the building facts database: what was measured, when, and how it changed.

| Feature | Why it is a real use |
|---|---|
| Hypertables for facts, flood simulations and the op log | Facts are measured again as tools improve; the history is time series by nature. |
| Columnstore compression | 234 MB to 58 MB on the cloud service. |
| Continuous aggregates, real-time, plus a hierarchical one | The Insights page reads daily rollups that include a fact measured a second ago, and a neighbourhood rollup built on them. |
| `percentile_agg` hyperfunction | Medians that roll up across days and areas. |
| PostGIS | Distance filters in search by measurement. |
| pgvector + pgvectorscale StreamingDiskANN with label filters, BM25 | Similar-room search filtered by room type inside the index, blended with words. |
| pgai vectorizer | Room descriptions embed themselves inside the database when they change (Ollama, nomic-embed-text). |
| TimescaleDB job | Rebuilds the room-search graphs hourly, because a graph grown row by row had recall@10 of 0.0. |
| Retention policy | The analytics copy of the op log deletes itself after the event, as CoStar's terms require. |
| Read-only role for the agent's SQL | The agent can ask its own questions of the facts and cannot write. |
| Database forks | City-wide what-if on a zero-copy fork, ready in about 31 s on the free plan, deleted after. |

**Demo path.** Search by measurement (one query, a ranked table), then renovate: widen a door, re-run city-wide on a
fork, compare Now and After, the fork deleted.

### MLH: Best Use of MongoDB Atlas

Atlas holds the people side: workspaces, their operation logs, live sync, memory and search over past work.

| Feature | Why it is a real use |
|---|---|
| Documents with a unique (workspace, seq) index | An optimistic lock: two writers cannot both append operation n. |
| Multi-document transactions | A person's operation and what it taught the agent land together. |
| Change streams | Live sync between server processes, browsers and the phone: a door width typed on the phone reaches the desktop in about a second. |
| `$jsonSchema` validation | The append-only log refuses a malformed entry. |
| TTL index | Read-only share links delete themselves. |
| Atlas Search (fuzzy, facets, highlights) | Search past investigations with counts by tool, status and city. |
| Vector Search with filters, automated embedding (voyage-4) | Recall similar past needs per persona, with no embedding key in the app. |
| Hybrid search with `$rankFusion` | "Could not roll a chair into the toilet" finds "No ADA clearance at the toilet". |
| Time series collection | Every phone reading (GPS, altitude, tilt, sound) as one measurement; the timeline groups by minute with `$dateTrunc`. |
| 2dsphere and `$geoNear` | Shortlisted buildings near a point. |
| LangGraph checkpointer and store | Paused agent turns and long-term memory next to the workspaces. |
| MongoDB MCP server (read-only, guarded) | The agent counts and groups over the person's own past work. |

**Demo path.** Pair the phone by QR, type a door width on the phone, watch it land on the desktop; Copy link opens a
read-only shared workspace; search past work for a phrase that is not in it word for word.

### HackPrinceton main track (one of six)

General judges score creativity, utility, charity and avidity. Charity is where the product is strongest: the
wheelchair user, the family before a storm, the fire crew. Track pick: question 3.

---

## Proof (numbers about our own system)

- Tool matrix: every tool run through the real API on a 15-place demo set (houses, apartments, offices, a warehouse,
  a scan with no wall graph, a phone scan, bare points with no scan). Before the polish pass: 230 ok, 18 errors, 29
  judged wrong. After: 266 ok, 62 honest "cannot answer here", 1 error (a bad input), 0 wrong.
- Tests on main: about 600 server tests and 90 web tests (exact counts at each merge in the Built list).
- Agent: a wheelchair turn composed 6 tools and ran 25 tool runs on 5 buildings in 3.7 minutes, ranked and shortlisted.
- Interior splats: four buildings, 16 to 23 minutes each on the integrated AMD GPU, 15 to 18 dB held-out PSNR.
- Photoreal view renders at 56 to 60 fps.
- Live sync: phone to desktop in about a second.
- Tiger: 234 MB to 58 MB compressed; a fork ready in 31 s; room descriptions embedded in-database at about nine a second.

## Built (synced to `main`)

Checked against `git log main` at `f3c29d1` (2026-11-14, 6:56 pm ET). Update at each merge.

**Merged**
- [x] Data layer: Matterport, Vexcel and CoStar sources, normalized plan format with quality flags (`ws/data`)
- [x] Geometry engines: routes, clearance, fit, rule packs, takeoff, georeference and sun, water (`ws/geometry`, `ws/walls`)
- [x] Perception: room labels and objects from panoramas, aerial site facts (`ws/perception`)
- [x] Agent: composer, deepagents investigator, workspace document and operations (`ws/agent`, `ws/agent2`)
- [x] 3D scene: dollhouse from the wall graph, plan, panorama, drone splat (`ws/scene`)
- [x] Flagship tools: flood, fire, access, office, truth (record vs reality), site (`tool/*`)
- [x] Tiger Cloud facts database (`ws/tiger`) and MongoDB Atlas store (`ws/mongo`)
- [x] Web core split into looks; the App look at `/app` is the default (`skin/app`, `polish/app`)
- [x] Phone companion `/m` with QR pairing and live sync (`ws/mobile`, `polish/phone`)
- [x] iPhone app: RoomPlan scan, LiDAR measure, barometer, scan-to-report (`ws/ios`, `ws/field`); simulator only
- [x] Polish: security review, tool matrix, UX audit (`polish/review`, `polish/tools`, `polish/app`)
- [x] Photoreal dollhouse, one world inside and out, x-ray, fly-in, flood in the street (`ws/views`)
- [x] Interior Gaussian splats trained on the AMD iGPU (`ws/splat`)
- [x] PDF site reports (`ws/field`)
- [x] Harvey flood, CFAST smoke in the dollhouse, agent camera tour (`ws/show`)
- [x] What-if renovations, cost, Now/After, Tiger forks (`ws/whatif`)
- [x] Sponsor depth: HITL approvals, Mongo checkpointer and store, skills, rubric, LangSmith, `$rankFusion`, time series, pgai (`ws/sponsors`)
- [x] Scene height fix for scans whose origin is upstairs (`fix/scene-z`, `fix/scene-z-tools`)
- [x] Garage and driveway fit with 58 vehicles (`ws/garage`)
- [x] Pets and kids: pet fit, nearby places from OpenStreetMap, home search by pet policy, fence, pool and yard (`ws/pets`)
- [x] Feng shui, room sizes, earthquake prep; personas for location scout, virtual stager, LA earthquake prep (`ws/fengshui`)
- [x] Brand is Cranley in the App look, the phone page, the PDF report and the iPhone display name; code identifiers stay `threshold`
- [x] Commercial: site scorecard, market comps, industrial fit, retail site, commute fit, facility audit; tenant rep, retail chain, office relocation and facility manager personas (`ws/commercial`)
- [x] Sun rooms, solar roof, wildfire space (`ws/sunfire`)
- [x] Wi-Fi coverage, camera coverage (isovists through the wall graph), quiet rooms (noise map plus walls and facade); remote worker, home security and light sleeper personas (`ws/signals`)
- [x] World explorer: one continuous view from the map to aerial to the 3D city to the scanned building, inspector beside it, sun and shadow slider (`ws/explorer`)
- [x] 66 map layers in eight groups (live, people, rules, hazards, getting around, services, imagery, coverage), most from free public sources, each served with its source and fetch date; area profile, zoning check, permit history, hazard profile and connectivity tools (`ws/datalayers`)
- [x] Real 3D models for vehicles and furniture, scaled to each tool's exact dimensions, drag to place with live clearance (`ws/models`)
- [x] App look motion polish: shorter exits, switch and copy feedback, staggered tool list (`ws/motion`)
- [x] MCP server (stdio and `/mcp`), `threshold` CLI, deep agent over MCP, `docs/MCP.md` (`ws/mcp`)

**Not merged yet (building tonight)**
- [ ] Offline demo copy and six demo flows (`ws/demo`)

**Not merged on purpose:** the Overflight look (`ws/design2`).

**Blocked:** iPhone app on a real phone (Apple Program License Agreement); Peri evidence (no business consulted; one emailed business declined).
