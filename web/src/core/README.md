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
| `/app` | `skins/app/` | App, the default: `/` and links without a look open here. |

A small tab at the edge of the screen (in a shadow root, so your CSS cannot touch it) opens the same place in another
look. Alt+L steps to the next one. It sits at the bottom centre unless your `index.tsx` says otherwise:

```ts
export const switcher: SwitcherPlace = 'top-right'   // 'bottom' | 'top' | 'bottom-left' | 'bottom-right' | 'top-left' | 'top-right'
```

Leave 80 px of that edge clear of anything a person must click.

## Places: the URL is the state of the view

The first path segment is the look. The rest is the place, and it means the same in every look, which is how the
switcher lands on the same moment. Name places only; the look in the address bar is kept for you.

| Place | Means | Query |
|---|---|---|
| `/` | the front door | |
| `/map` | the city map | `city` (`hou`, `la`), `kind`, `drone`, `empty`, `rooms`, `b` (selected building id) |
| `/scan/<sid>` | one scan in the building view | `f` (focused finding id), `v` (scene mode), `p` (panorama position), `b`, `city` |
| `/shared/<token>` | a read-only link to someone's workspace | |

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
| `brief` | `{ text, limits?, scope? }`: what the person said; `limits` are plain sentences on what no tool here can do; `scope` is the scans the agent has narrowed the work to, once it has | the brief, and its limits |
| `questions` | `{ id, text, kind: 'choice' \| 'number' \| 'text', options?, unit?, answer?, hint? }` | a form; `answer == null` is open; offer `hint` |
| `tools` | `ToolRef { id, title, code?, summary?, reason, coverage?, by }` | the dock, with why each is here and who added it |
| `plan` | `PlanStep { id, label, status: 'pending' \| 'active' \| 'done' }` | the agent's plan, live |
| `runs` | `Run { id, tool, label, sid?, place?, step?, status: 'running' \| 'done' \| 'failed', ms?, at?, summary?, stale? }`; `sid` is the scan it is about | tool calls under their plan step (`step` is a `PlanStep.id`); a running run's `summary` is its latest progress line |
| `panels` | `Panel { id, tool, title, role?, scope?, sid?, run?, blocks }`; `role` is `'tool'` (also when missing), `'summary'` (the agent's closing note), `'ranking'` or `'note'` | one panel each, built from the twelve blocks |
| `findings` | `Finding { id, title, status, detail?, anchor, source, media? } & { tool, run? }` | evidence; `anchor` is where it is in the building or on the map |
| `overlays` | `{ id, tool, sid?, overlay }` | drawn in the scene (core does this) and on the map (you do this, from `useMapModel().geo`) |
| `prefs` | `Pref { key, label, value, unit?, from, by }`: `label` names the setting, `value` is its value, `from` is the sentence that says where it came from | "what I have learned", each with an undo |
| `shortlist` | `ShortlistItem { sid, name, address, note? }` | the kept scans |
| `camera` | `{ anchor, finding?, by }` | `finding` is the current one: mark it in every list that shows it |

**The twelve blocks** (`Block`, discriminated by `type`). Each carries its data; render every one.

| `type` | Data |
|---|---|
| `VerdictHeader` | `status`, `text` |
| `MetricRow` | `metrics: Metric[]` (at most 4): `label`, `value` (null is "not measured"), `unit`, `source` |
| `CheckList` | `checks: Check[]`, worst first: `rule`, `measured`, `threshold`, `unit`, `status`, `standard?`, `kind?`, `findings` (ids; clicking a check focuses the first with an anchor). `kind: 'claim'` means `threshold` is what a record or listing says, not a limit: set it as "record says / scan measures" |
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
focusFinding(finding, { stay: true })                             // the same, without leaving the place (below)
```

The store applies the op at once and core tells the server. You do not call the server.

## The agent

```ts
compose(sentence, needId?)   // the front door: a new brief. Tools and questions arrive in doc as the server composes;
                             // the promise resolves when composing has ended, for a caller that goes straight on
investigate()                // every question answered (or "use the defaults"): start the work
ask(text)                    // the one-line command bar, anywhere
runToolHere(toolId, sid)     // run one tool on the scan in view, from the dock. A slow tool does not block: see below
runTool(toolId, inputs?, sid?) // run a tool with inputs a person gave; no sid for a tool that takes none (a city rollup)
runAction(action, panel)     // a panel's follow-up, or { id: 'rerun' }
startOver()                  // forget the workspace; then navigate('/')
answerPref(q, answer)        // only for a question answered after the work began: userOp(answerPref(q, a))
NEEDS, TOOLS                 // the front door's starting points and their tools, for when no server answers
useToolCatalog(): CatalogTool[]     // every tool there is to add (the server's list, planned ones last)
useCatalog((s) => s.live)    // true: the agent server answers. false: scripted playback. null: not known yet
shareWorkspace(days?)        // { url, expires }: a read-only link to the open workspace. Rejects with a sentence when
                             // the server cannot make one (it needs the database store). Never copy the page address
                             // for someone else: it holds the workspace id, and whoever has the id can write
useCatalog((s) => s.shared)  // set on a read-only link: { state: 'loading' | 'ready' | 'gone', expires? }. null otherwise
```

**A read-only link** opens at `/shared/<token>` in any look. Core shows that workspace in `doc` and keeps it up to date;
it is never written. Every change a person tries (an op, a tool run, a new brief) is refused with a notice and the
server's document is put back, so a look need not guard each control. A look should say the page is read-only, offer
the way out (load its own front door again), and may hide what cannot work there. `doc.id` is `"shared"` on such a page.

```ts```

**Receiving agent operations.** You do not subscribe to a stream. Core reads the server's events and the document
changes; you re-render from `doc`. To animate an arrival, compare with the previous render (a tool that was not in
`doc.tools`, a run that turned `done`, a `camera` that changed). While a turn runs, `doc.plan` has an `active` step
and `doc.runs` has `running` entries whose `summary` changes as the tool reports progress.

**Slow tools.** Most tools answer in a second or two. A few take minutes (`smoke_clock` runs a fire simulation for 3
to 11 minutes the first time on a house). You do nothing different: the run is in `doc.runs` with `status: 'running'`
from the start, its `summary` is its latest progress line, and its panel, findings and overlays arrive when it ends,
also after a reload. Design the running state so that minutes of it look intended.

**The view follows the agent.** When the agent focuses a finding and `follow` is on, core navigates to its scan (or
to the map for a map anchor) and sets `?f`. You see a new route and a new `doc.camera`. How the move looks is yours.
The person's own focus does the same, unless you pass `{ stay: true }`: then `doc.camera` and `?f` change and the
place does not (a roof or dock finding looked at from its own scan's page). A link that carries `?f` opens on that
finding, and a link that carries `?v` keeps that mode, whatever camera the workspace comes back with.

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

## The world explorer

One view from the city down to a room: the map carries on into the aerial photo, Vexcel's 3D city mesh and then a
building's own scene. `skins/app/pages/Explore.tsx` and `skins/app/explore/` are the worked example.

```ts
mapStyle(palette, { base, closeUp })      // base: 'streets' | 'aerial' | 'terrain' | 'plain' (BASE_VIEWS has their labels);
                                          // closeUp: the zoom by which the aerial photo has faded in under any base
SLOT.data, SLOT.solid, SLOT.marks         // ids of empty layers in that style: insert data under the first, 3D under
                                          // the second, marks under the third, and the map's names stay on top
MAP_CREDIT[base], MAP_CREDIT.close        // who to credit for the ground, far out and close in

fetchLayers(city): MapLayer[]             // the data layers: title, group, source, confidence, note, the day our copy
                                          // was fetched. Print these; never write a source or a caveat yourself
layerCityUrl(id, city)                    // a 'city' layer's GeoJSON, as a map source's data
fetchLayerTile(id, z, x, y)               // one tile of a 'grid' layer at its own grid_z
fetchWeather(city), fetchSite(sid)

const Mesh = await loadCityMesh()         // the 3D city as a MapLibre custom layer (three.js comes with it, on demand)
const mesh = new Mesh(); map.addLayer(mesh, SLOT.solid)
mesh.want({ lat, lon }) / mesh.want({ sid }, ring)   // the tiles round a point, or exactly a scan's own
mesh.setShown(on), mesh.setSun({ azimuth, altitude } | null), mesh.sunlight(lon, lat, from, to, sunAt)

sunPosition(date, lat, lon), sunDay(date, lat, lon), zonedInstant(y, m, d, minutes, zone)
```

**Handing over between the map and the scene.** Both use the same lens (`SCENE_FOV`; set it with
`map.setVerticalFieldOfView`) and draw the same city mesh. `stand(plan, site, { w, h })` works out where the scene's
camera target is in the world and the ranges at which to swap (`enter`, `leave`); `cameraOf(stand, { bearing, pitch,
range })` gives the camera itself, which `map.calculateCameraOptionsFromCameraLngLatAltRotation` turns into a place
for the map. Give the scene `pose: { bearing, pitch, range: stand.enter }` and `env: 'aerial'`, wait for `onCamera`
to report it there and `onState` to report its surroundings in, and wait for `mesh.key === 'sid:<sid>'`: then the two
pictures agree and one can fade over the other. Mesh against mesh they were within 1 px on 2026-11-14.

## One building

```tsx
const v = useBuildingView(sid)            // sid from useRoute(). useBuildingView(sid, { tools: ['flood_rehearsal'] })
                                          // draws only those tools' overlays (the result on top); missing is all
v.plan, v.error, v.retry                  // the ScanPlan; a sentence when it did not load
v.modes, v.mode, v.setMode(m)             // 'dollhouse' | 'plan' | 'pano' | 'splat'; only the modes this scan has
v.view, v.setView                         // the whole scene view, for your own controls (below)
v.stepBack()                              // frame the whole building again, after a close-up on a finding
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
restyle them or hide them with CSS and drive the view yourself.

**Where the camera puts its subject.** All optional; leave them out and the scene behaves as it always has.

| Field | Modes | Meaning |
|---|---|---|
| `frame: { top?, right?, bottom?, left? }` | all | The free part of the picture, in CSS px in from each edge of the scene element. Outside it is your interface. Every fit and every focus lands in this rectangle, by shifting the projection: nothing tilts, and labels, pins and clicks follow. A change eases over 400 ms. Like MapLibre's `setPadding`. |
| `fov: number` | `pano` | Vertical field of view in degrees, 34 to 96; null is 76. Applied when it changes and when a panorama is entered; the person's zoom then stays until it changes again. |
| `look: { yaw_deg, pitch_deg }` | `pano` | Which way to look, in the scan frame as Contract 3 defines it (yaw counter-clockwise from +x, pitch up). Applied when it changes and on entering; a focused panorama anchor at that position wins. |
| `pose: { bearing?, pitch?, range? }` | `dollhouse`, `splat` | Where the outside camera stands, in the map's terms: `bearing` is the compass direction it looks toward (0 north, clockwise), `pitch` degrees from straight down (0 plan view, 90 horizon), `range` metres from the target or `'fit'` (the default). Pass `map.getBearing()` and `map.getPitch()` straight through. A change flies there in 1 s; the person's drag then stays. |
| `orbit: number` | `dollhouse`, `splat` | Degrees per second of slow turn about the target (positive is counter-clockwise seen from above). 0 stops it; leaving it out keeps the splat's own drift. A drag stops it until the value changes. |

Two callbacks, passed beside `sceneProps`:

```tsx
<Scene {...v.sceneProps}
  onCamera={(c: SceneCamera) => …}   // { mode, moving, bearing, pitch, range, fov, focus: { x, y, visible } | null }
  onState={(s: SceneState) => …} />  // { mode, loading, pano, hasEmpty, noWalls, splat: { status, progress, splats, total } }
```

`onCamera` is called whenever the camera changes by more than half a pixel or a tenth of a degree, and once when a
designed flight ends (`moving: false`). `focus` is where the focused finding is, in CSS px inside the scene element:
end a leader line there and it follows as the person looks around. `onState` is the scene's own loading state, for a
caption in your voice or a crossfade that starts when the first of the drone capture is in. Apply both straight to
the DOM (a ref), not to React state: they can fire every frame.

`bearing` needs the scan's compass rotation. It uses `plan.geo.yaw_deg` and, when the scan's footprint check passed,
that fit as well. `plan.quality.georef` tells you whether the check passed; when it is false (always, for a unit
inside a larger building) the bearing is the scan's own guess, good to a few degrees on houses. Without `plan.geo`,
0 is the scan's +y. The drone capture is not registered to the scan frame yet, so nothing in map coordinates is drawn
in `splat` mode.

**The scene's look is yours through CSS variables**, set on `.th-scene`, on a class you pass as `className`, or on
any ancestor rule for it. The defaults are in `src/scene/tokens.css` under `:where()`, so your rule wins.

| Variable | Used for |
|---|---|
| `--scene-stage` | behind the building |
| `--scene-paper` | wall faces, label chips, control backgrounds |
| `--scene-ink`, `--scene-ink-2`, `--scene-hairline` | cut faces of walls, linework, text |
| `--scene-grid` | the ground's 1 m and 5 m lines and the shade round the footprint; unset, it is `--scene-ink` |
| `--scene-accent` | selection, routes, the current position |
| `--scene-glass`, `--scene-water` | windows, the water overlay |
| `--scene-ramp-lo`, `--scene-ramp-hi` | the lens ramp, low to high |
| `--scene-pass`, `--scene-warn`, `--scene-fail`, `--scene-unknown`, `--scene-on-status`, `--scene-on-warn` | the status scale and the text on it |
| `--scene-font`, `--scene-mono`, `--scene-text-xs`, `--scene-text-sm`, `--scene-text-md` | type inside the scene |
| `--scene-radius`, `--scene-ease-out`, `--scene-ease-in-out` | corners and motion of its controls |

Colours the 3D renderer reads (stage, paper, ink, accent, glass, water, ramp, status) must be 6-digit hex, and they
are read when the scene mounts. A look with a light and a dark scheme remounts the scene on change (a different
`key`). The scene's own class names start with `th-`; do not rely on any other detail of its DOM, with one exception you
may use: the pin of the focused finding is `.th-pin[aria-current="true"]`.

**Pictures and records of a building**: `fetchPlan(sid)`, `panoFace(sid, pano, face)` (cube face 1 to 4 are the
sides), `panoEquirect(sid, pano)`, `floorplanImage(sid, floor)`, `orthoImage(lat, lon, size_m)`, `fetchRecord(sid)`
(the CoStar or listing record), `fetchDrone(sid)` and `droneImage(sid, name, width?)`, `fetchScans(filter)`. `anchorFloor(plan,
anchor)` tells you which floor an anchor is on. From the facts database: `fetchFactHistory(sid)` (every value recorded for
a scan) and `fetchFloodWet()`. `fetchCaptures(workspaceId)` lists what a paired phone sent. `photorealReady(sid)` says whether a scan's
photoreal colour is made already, without starting to make it.

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
