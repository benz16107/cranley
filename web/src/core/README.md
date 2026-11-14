# core: what every look shares

The web app is one product wearing several looks. `src/core/` is the product: the workspace, the agent link, the
data clients, the URL, and the bridge to the 3D scene. A look ("skin") is one folder under `src/skins/` that draws
it. This file is the contract between the two.

```
src/core/      the product, no visual decisions. Imports nothing from skins or from a UI library.
src/scene/     <BuildingScene>: dollhouse, plan, panorama, drone splat. Shared by every look.
src/skins/     registry.ts, then one folder per look: sheet/ overflight/ broadsheet/ maquette/
src/studies/   the three design studies (/study/a, /study/b, /study/c). Reference only.
```

## Rules

1. **A skin imports the product from `src/core/index.ts` and from nowhere else.** Not from another file in core, not
   from `src/scene/`, not from another skin, not from `src/studies/`. Everything in `index.ts` is listed below.
2. **A skin never edits `core`, `scene`, another skin, `registry.ts` or `main.tsx`.** When you need something that
   is not here (a field on the scene view, a new op, a helper), write it in your report under "Needed from core". The
   integrator adds it for everyone. Do not copy core code into your skin to change it.
3. **A skin owns everything it draws**: tokens, type, layout, components, motion, its own map styling. Copy an idea
   from `skins/sheet/` or `studies/` if you want it; do not import it.
4. **Numbers are never retyped or recomputed.** Print the value in the block, metric, check or overlay you were
   given. Formatting (digits, unit conversion for display) is yours; arithmetic that changes a result is not.
5. **No fetch to `/api` from a skin.** Use the clients below. If one is missing, rule 2.
6. **No scan ids, addresses or sponsor images in the repo** (the project's `CLAUDE.md`). Screenshots go to
   `$THRESHOLD_DATA_DIR/shots/<your workstream>/`.
7. Your CSS may style `body`, `:root` and plain element names. Only one look's code and CSS are ever on the page
   (each is loaded on its own, and changing look reloads the page).

## How a look is mounted

`skins/registry.ts` maps a URL prefix to a folder. Your folder's `index.tsx` exports one component, `Root`, and
imports your CSS. `main.tsx` reads the first path segment, loads that one skin and renders `<Root />`.

| Prefix | Folder | Look |
|---|---|---|
| `/sheet` | `skins/sheet/` | Sheet, the first shell. A complete example of everything below. |
| `/a` | `skins/overflight/` | A, Overflight |
| `/b` | `skins/broadsheet/` | B, Broadsheet |
| `/c` | `skins/maquette/` | C, Maquette |

A small tab at the bottom edge (in a shadow root, so your CSS cannot touch it) opens the same place in another look.
Alt+L steps to the next one. Leave the bottom centre 80 px of the screen clear of anything a person must click.

## Places: the URL is the state of the view

The first path segment is the look. The rest is the place, and it means the same in every look, which is how the
switcher lands on the same moment. Name places only; the look in the address bar is kept for you.

| Place | Means | Query |
|---|---|---|
| `/` | the front door | |
| `/map` | the city map | `city` (`hou`, `la`), `kind`, `drone`, `empty`, `rooms`, `b` (selected building id) |
| `/scan/<sid>` | one scan in the building view | `f` (focused finding id), `v` (scene mode), `p` (panorama position), `b`, `city` |

```ts
useRoute(): { path: '/' | '/map' | '/scan'; sid: string | null; q: URLSearchParams }   // re-renders on change
currentRoute()                                   // the same, outside React
navigate(place, params?, { replace?, keep? })    // keep: keep the current query and add params to it
setQuery(params, replace = true)                 // change query on the current place; null removes a key
```

You may add query keys of your own for view state you want in a link; prefix them with your look (`a_`).
`LOOKS` and `LookId` name the four looks.

## The workspace: the one document you render

```ts
const doc = useWorkspace((s) => s.doc)           // Doc; select the slice you need
const follow = useWorkspace((s) => s.follow)     // does the view go where the agent looks
useWorkspace.getState().setFollow(on) / .undo() / .undoStack
userOp(op)                                       // the person changes the workspace
```

`Doc` (types in `index.ts`): everything on screen comes from here.

| Field | What it is | Must be shown as |
|---|---|---|
| `brief` | `{ text, limits? }`: what the person said; `limits` are plain sentences on what no tool here can do | the brief, and its limits |
| `questions` | `{ id, text, kind: 'choice' \| 'number' \| 'text', options?, unit?, answer?, hint? }` | a form; `answer == null` is open; offer `hint` |
| `tools` | `ToolRef { id, title, code?, summary?, reason, coverage?, by }` | the dock, with why each is here and who added it |
| `plan` | `PlanStep { id, label, status: 'pending' \| 'active' \| 'done' }` | the agent's plan, live |
| `runs` | `Run { id, tool, label, step?, status: 'running' \| 'done' \| 'failed', ms?, summary?, stale? }` | tool calls under their plan step (`step` is a `PlanStep.id`); a running run's `summary` is its latest progress line |
| `panels` | `Panel { id, tool, title, scope?, sid?, run?, blocks }` | one panel each, built from the twelve blocks |
| `findings` | `Finding { id, title, status, detail?, anchor, source, media? } & { tool, run? }` | evidence; `anchor` is where it is in the building or on the map |
| `overlays` | `{ id, tool, sid?, overlay }` | drawn in the scene (core does this) and on the map (you do this, from `useMapModel().geo`) |
| `prefs` | `Pref { key, label, value, from, by }` | "what I have learned", each with an undo |
| `shortlist` | `ShortlistItem { sid, name, address, note? }` | the kept scans |
| `camera` | `{ anchor, finding?, by }` | `finding` is the current one: mark it in every list that shows it |

**The twelve blocks** (`Block`, discriminated by `type`). Each carries its data; render every one.

| `type` | Data |
|---|---|
| `VerdictHeader` | `status`, `text` |
| `MetricRow` | `metrics: Metric[]` (at most 4): `label`, `value` (null is "not measured"), `unit`, `source` |
| `CheckList` | `checks: Check[]`, worst first: `rule`, `measured`, `threshold`, `unit`, `status`, `standard?`, `findings` (ids; clicking a check focuses the first with an anchor) |
| `EvidenceStrip` | `findings: string[]` (ids into `doc.findings`); a finding's panorama picture is `panoFace(...)` of its `media` ref, `"<sid>/<pano>/<face>"` |
| `RankedTable` | `columns` (`id`, `label`, `unit?`, `better`), `rows` (`label`, `status?`, `anchor?`, `values`) **in rank order: keep it until the person sorts** |
| `MiniChart` | `title`, `unit`, `bars` (`label`, `value`, `status?`), `mark?`, `source` |
| `FloorPlanMini` | `sid`: a small plan of that scan with this panel's overlays; opens the scan |
| `Controls` | `controls`: `id`, `label`, `kind: 'slider' \| 'toggle' \| 'select'`, `value`, `min`, `max`, `step`, `unit`, `options`. A change is `userOp({ op: 'pref.set', key: control.id, label, value, unit, from })`; core runs the tool again |
| `AssumptionChips` | `assumptions`: `id`, `label`, `value`, `unit?`, `editable`. An edit is the same `pref.set` with `key: assumption.id` |
| `StepLog` | `steps`: `label`, `detail?`, `ms?` |
| `Note` | `text` |
| `ActionBar` | `actions`: `id`, `label`; a click is `runAction(action, panel)` |

Every `Metric`, `Finding`, `RankedTable` and `MiniChart` has a `Source { layer, method, confidence, note? }`. Showing
where a number came from and how sure it is is part of the product, in every look.

A panel whose run has `stale: true` says so and offers `runAction({ id: 'rerun', label: 'Run again' }, panel)`.

**The six overlay kinds** (`Overlay`, by `kind`): `lens` (a value per room with a legend), `rule` (rooms, walls or
openings shown solid, dim, hidden, highlighted, or in a status colour), `pins`, `route` (with `chokes`), `water`,
`box`. In the building they are drawn by the scene; you style them through the scene's CSS variables. Two forms are
in map coordinates and are yours to draw on the map: a `route` whose `floor` is `"geo"` and pins whose anchor is
`{ geo: [lon, lat] }`. `useMapModel().geo` hands you both.

**What the person can do** (`userOp`, all by the same vocabulary the agent uses):

```ts
userOp({ op: 'question.answer', id, answer })
userOp({ op: 'tool.enable', tool: { id, title, code?, summary?, coverage?, reason } })   // from useToolCatalog()
userOp({ op: 'tool.disable', id })
userOp({ op: 'pref.set', key, label?, value, unit?, from? })      // value: null forgets it (the undo in "learned")
userOp({ op: 'shortlist.add', item: { sid, name, address } }) / ({ op: 'shortlist.remove', sid })
focusFinding(finding) / focusAnchor(anchor)                       // look at this: camera.focus
```

The store applies the op at once and core tells the server. You do not call the server.

## The agent

```ts
compose(sentence, needId?)   // the front door: a new brief. Tools and questions arrive in doc as the server composes
investigate()                // every question answered (or "use the defaults"): start the work
ask(text)                    // the one-line command bar, anywhere
runToolHere(toolId, sid)     // run one tool on the scan in view, from the dock
runAction(action, panel)     // a panel's follow-up, or { id: 'rerun' }
startOver()                  // forget the workspace; then navigate('/')
answerPref(q, answer)        // only for a question answered after the work began: userOp(answerPref(q, a))
NEEDS, TOOLS                 // the front door's starting points and their tools, for when no server answers
useToolCatalog(): CatalogTool[]     // every tool there is to add (the server's list, planned ones last)
useCatalog((s) => s.live)    // true: the agent server answers. false: scripted playback. null: not known yet
```

**Receiving agent operations.** You do not subscribe to a stream. Core reads the server's events and the document
changes; you re-render from `doc`. To animate an arrival, compare with the previous render (a tool that was not in
`doc.tools`, a run that turned `done`, a `camera` that changed). While a turn runs, `doc.plan` has an `active` step
and `doc.runs` has `running` entries whose `summary` changes as the tool reports progress.

**The view follows the agent.** When the agent focuses a finding and `follow` is on, core navigates to its scan (or
to the map for a map anchor) and sets `?f`. You see a new route and a new `doc.camera`. How the move looks is yours.

**Notices.** What core has to say outside the workspace (the server did not answer, a tool needs an answer first)
arrives through `onNotice((n: Notice) => …)`: `{ kind: 'info' | 'error', title, description? }`. Register once in
your root, in an effect, and return its result to stop listening. Show it your way: a toast, a subtitle, a margin note.

With no server at all the front door still composes from `NEEDS` (scripted), and `/scan/<sid>?demo=access` replays a
scripted audit on any scan. Both go through the same `doc`, so they need nothing from you.

## The city map

```ts
const m = useMapModel()
m.all, m.state, m.reload      // every Building; 'loading' | 'ready' | 'error'
m.filters, m.shown            // the URL's filters; the buildings that pass them, in the current city
m.selected, m.select(b|null)  // the building in ?b, or the one the open scan belongs to
m.marks                       // buildings the workspace has a panel or shortlist entry for: where the agent has been
m.geo                         // GeoMarks { paths: [lon, lat][][], pins: { lon, lat, status, label }[] }
m.look                        // [lon, lat] the camera was told to look at, or null: go there, about zoom 18
```

`Building { id, lon, lat, address, city, metro, scans: Scan[], count, splat, defurnished, kinds, rooms }`,
`Scan { sid, name, rooms, panos, kind }`. `CITIES` has each city's centre and zoom, `KINDS` the filter's kinds,
`search(all, text)` finds buildings by address or scan name, `readFilters` and `matches` are what `m.shown` uses.
Filters are query keys: `setQuery({ kind: 'home,office' })`, `setQuery({ drone: '1' })`, `navigate('/map', { city: 'la' })`.

The map itself is yours: `MapLibre` and `Marker` are MapLibre GL 6 with its worker already set up (import them from
core, not from `maplibre-gl`), and `mapStyle(palette: MapPalette)` builds a keyless vector basemap in your colours.
deck.gl is installed (`@deck.gl/maplibre`, `deck.gl`). `skins/sheet/map/CityMap.tsx` is a worked example; pitch,
light points and extruded blocks are your own layers.

To show "the agent at work" on the map: `m.marks` for where it has been, `doc.runs` (each `label` ends with the
scan's name) and `doc.plan` for what it is doing, `m.look` and `m.geo` for what it points at.
Measurement search for the map: `searchMeasures(['floors==1', 'bath_route_door>=0.81'], { city: 'Houston' })` returns
rows with `lat`, `lon`, `why` and `values`; `fetchMeasureFields()` lists what can be searched.

## One building

```tsx
const v = useBuildingView(sid)            // sid from useRoute()
v.plan, v.error, v.retry                  // the ScanPlan; a sentence when it did not load
v.modes, v.mode, v.setMode(m)             // 'dollhouse' | 'plan' | 'pano' | 'splat'; only the modes this scan has
v.view, v.setView                         // the whole scene view, for your own controls (below)
v.kept, v.toggleKeep                      // the shortlist
v.overlays                                // this scan's overlays, for a plan drawing of your own

{v.sceneProps && (
  <Suspense fallback={…}>
    <SceneBoundary key={v.sceneKey} fallback={<YourFault onRetry={v.retry} />}>
      <Scene {...v.sceneProps} className="my-scene" />
    </SceneBoundary>
  </Suspense>
)}
```

That is the whole bridge. Core feeds the scene its overlays, moves it when a finding is focused (the floor comes up;
a panorama anchor means "stand there and look that way"), turns a click on a room, opening, wall or pin into
`focusFinding`, and keeps the mode and panorama position in `?v` and `?p`. Give the scene a sized parent
(`position: relative` with a height); it fills it.

**Every scene mode must be reachable**: `dollhouse` (walls, cut-away, floors pulled apart), `plan`, `pano` (walk,
furnished and empty wipe where `plan.has.defurnished`), `splat` (only where `plan.has.splat`).

**The scene view** (`SceneView`), through `v.setView((x) => ({ ...x, … }))`: `floor` (show this floor; null is all),
`pano` (position id), `cut` (metres above the floor; null is whole walls), `explode` (0 to 1), `wipe` (0 to 1 or null),
`measures` (opening widths on). The scene draws its own controls for cut, floors and wipe (marked `data-scene-ui`);
restyle them or hide them with CSS and drive the view yourself. There is no field of view, camera pose or frame
offset yet: if your direction needs one, ask (rule 2).

**The scene's look is yours through CSS variables**, set on `.th-scene`, on a class you pass as `className`, or on
any ancestor rule for it. The defaults are in `src/scene/tokens.css` under `:where()`, so your rule wins.

| Variable | Used for |
|---|---|
| `--scene-stage` | behind the building |
| `--scene-paper` | wall faces, label chips, control backgrounds |
| `--scene-ink`, `--scene-ink-2`, `--scene-hairline` | cut faces of walls, linework, text |
| `--scene-accent` | selection, routes, the current position |
| `--scene-glass`, `--scene-water` | windows, the water overlay |
| `--scene-ramp-lo`, `--scene-ramp-hi` | the lens ramp, low to high |
| `--scene-pass`, `--scene-warn`, `--scene-fail`, `--scene-unknown`, `--scene-on-status`, `--scene-on-warn` | the status scale and the text on it |
| `--scene-font`, `--scene-mono`, `--scene-text-xs`, `--scene-text-sm`, `--scene-text-md` | type inside the scene |
| `--scene-radius`, `--scene-ease-out`, `--scene-ease-in-out` | corners and motion of its controls |

Colours the 3D renderer reads (stage, paper, ink, accent, glass, water, ramp, status) must be 6-digit hex, and they
are read when the scene mounts. A look with a light and a dark scheme remounts the scene on change (a different
`key`). The scene's own class names start with `th-`; do not rely on any other detail of its DOM.

**Pictures and records of a building**: `fetchPlan(sid)`, `panoFace(sid, pano, face)` (cube face 1 to 4 are the
sides), `panoEquirect(sid, pano)`, `floorplanImage(sid, floor)`, `orthoImage(lat, lon, size_m)`, `fetchRecord(sid)`
(the CoStar or listing record), `fetchDrone(sid)` and `droneImage(sid, name)`, `fetchScans(filter)`. `anchorFloor(plan,
anchor)` tells you which floor an anchor is on.

## Minimum to be a complete skin

A look is complete when a person can do all of this in it, on real data, with the server running:

- [ ] **Front door.** Type a sentence or pick a starting point; tools arrive with their reasons; questions are asked
      and answered (all three kinds, with the hint offered); "start" and "use the defaults"; start over.
- [ ] **City map with the agent at work.** Both cities and the switch between them; filters; address search; a
      selected building and its scans; where the agent has been; the plan and its live runs; a map point the agent
      looks at; map-coordinate paths and pins.
- [ ] **Building view with every scene mode.** 3D with cut and floors, plan, panorama with the wipe, drone splat;
      loading and failure states; keep and un-keep.
- [ ] **Every panel block.** All twelve, with sources and confidence, the stale state and "run again".
- [ ] **Every overlay kind.** lens (with its legend), rule, pins, route, water, box, restyled for your look.
- [ ] **Tool dock.** The enabled tools, why each is here, remove, add any tool from the catalog (planned ones marked),
      run on this scan, the command line (`ask`), undo.
- [ ] **Plan.** Steps with status, runs under their step with progress, the follow switch.
- [ ] **Questions.** Open ones wherever the person is, including one a tool asks after a dock run (it arrives in
      `doc.questions` with a notice, and may arrive when `doc.brief` is still null).
- [ ] **Shortlist.** Keep from the building view, list, open, remove.
- [ ] **What I have learned.** Every `doc.prefs` item with where it came from and an undo.
- [ ] **A focused finding.** Clicking a check, an evidence item or a pin focuses it; the current one is marked
      everywhere it appears; a reload on a link with `?f` shows it.
- [ ] **Notices** shown in your manner.
- [ ] **Light or dark as your direction decides**, including the scene's variables. One scheme is enough.
- [ ] **Phone width** (390 px): every item above reachable, nothing clipped, 16 px side gutters, no sideways scroll.
- [ ] Keyboard reach and visible focus on everything clickable; `prefers-reduced-motion` respected.
- [ ] `pnpm build`, `pnpm test` and `pnpm lint` clean for your folder; the other looks still work.

Check yourself against `/sheet` at the same place: flip with the tab at the bottom (or Alt+L) and confirm nothing the
sheet shows is missing from yours.

## Report

End with: what works, with screenshot paths; what does not; **"Needed from core"** (each item: what, why, and what
you did meanwhile); what you did not check.
