import { Suspense, useEffect, useMemo, useRef, useState } from 'react'
import {
  CITIES, Scene, SceneBoundary, ask, focusFinding, navigate, orthoImage, runToolHere, setQuery, useBuildingView, useMapModel, useRoute, useWorkspace,
  type Doc, type Overlay, type Panel, type SceneMode, type SceneProps, type ScanPlan,
} from '../../core/index.ts'
import { Desk, OpenQuestions, Plan } from './Desk.tsx'
import { Fig, Mark, reduced } from './parts.tsx'
import { Headline, Story, look, pictureOf } from './Story.tsx'
import { Contents, useCurrent, useStories } from './stories.tsx'
import { familyOf, headSize, num, plural, unitOf, word } from './words.ts'

/* One building. The story runs down the column; the building is figure 1 beside it, in any of its modes: the
   cut-open model, the plan, the 360° photograph inside, the drone capture, the aerial photograph. The figure opens to
   the whole screen and comes back, and while it is open the story's headline stays on it as its caption. */

const VIEW: Record<SceneMode, string> = { dollhouse: 'Model', plan: 'Plan', pano: 'Inside', splat: 'Drone' }
const CUT = 1.3 // metres above the floor: low enough to see into every room

/** The aerial photograph with what the site tools found drawn on it. */
function AirPlate({ plan, findings, current }: { plan: ScanPlan; findings: Doc['findings']; current?: string }) {
  const pics = findings.map((f) => ({ f, pic: pictureOf(f) })).filter((x) => x.pic?.kind === 'ortho')
  const src = pics.find((x) => x.f.id === current)?.pic?.src ?? pics[0]?.pic?.src ?? orthoImage(plan.geo!.lat, plan.geo!.lon, 90, 1024)
  const [ok, setOk] = useState<boolean | null>(null)
  useEffect(() => setOk(null), [src])
  const boxes = pics.filter((x) => x.pic!.src === src && x.pic!.box)
  return (
    <div className="airplate" style={{ zIndex: 5 }}>
      {ok === false ? <div className="state"><p>The aerial photograph did not load.</p></div>
        : <img src={src} alt={`Aerial photograph of ${plan.name}, north up`} data-ok={ok === true} onLoad={() => setOk(true)} onError={() => setOk(false)} />}
      {ok && (
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
          {boxes.map(({ f, pic }) => { const [x0, y0, x1, y1] = pic!.box!; return <rect key={f.id} className="airbox" aria-current={f.id === current || undefined} x={x0 * 100} y={y0 * 100} width={(x1 - x0) * 100} height={(y1 - y0) * 100} onClick={() => look(f)} /> })}
        </svg>
      )}
    </div>
  )
}

/** What the marks on figure 1 mean, read from the overlays that are on it. */
function legendOf(overlays: Overlay[]): string {
  const out: string[] = []
  for (const o of overlays) {
    if (o.kind === 'lens') out.push(`Shading: ${o.legend.title}, ${num(o.legend.min)} to ${num(o.legend.max)}${o.legend.unit ? ` ${unitOf(o.legend.unit)}` : ''}.`)
    else if (o.kind === 'water') out.push('Blue: the water, standing level.')
    else if (o.kind === 'box' && o.label) out.push(`Box: ${o.label}.`)
  }
  const routes = overlays.flatMap((o) => (o.kind === 'route' ? [o.label] : []))
  if (routes.length === 1 && routes[0]) out.push(`Pencil line: ${routes[0]}.`)
  else if (routes.length) out.push(`Pencil lines: ${routes.length} routes, each named where it ends.`)
  if (overlays.some((o) => o.kind === 'pins' || o.kind === 'rule')) out.push('Circle passes, triangle is close, square fails, dashed ring was not measured.')
  return [...new Set(out)].slice(0, 4).join(' ')
}

function Intro({ plan, sid }: { plan: ScanPlan | null; sid: string }) {
  const tools = useWorkspace((s) => s.doc.tools)
  const busy = useWorkspace((s) => s.doc.runs.findLast((r) => r.status === 'running'))
  if (!plan) return <><h1 className="head" data-size="m"><span className="reading">Reading the plan</span></h1><div className="writing"><i className="unset" /><i className="unset" /><i className="unset" /></div></>
  const doors = plan.openings.filter((o) => o.type === 'doorway').length
  return (
    <>
      <h1 className="head" data-size={headSize(plan.name)}>{plan.name}</h1>
      <p className="deck"><Mark>{word(plan.rooms.length)}</Mark> {plural(plan.rooms.length, 'room')} and {doors} {plural(doors, 'doorway')} on {plan.floors.length} {plural(plan.floors.length, 'floor')}, drawn from {plan.walls.length} {plural(plan.walls.length, 'wall')} in its scan. {busy ? <em>Writing: {busy.label}.</em> : 'Nothing has been written about it yet.'}</p>
      <section className="sec" aria-labelledby="write-h">
        <h2 id="write-h">Write about it</h2>
        {!tools.length && <p className="empty">No sections yet. Add one from the masthead, or say what you need in a sentence on the front page.</p>}
        <ul className="scans">
          {tools.map((t) => <li key={t.id}><span className="open"><b>{t.title}</b><span>{t.summary ?? t.reason}</span></span><button className="btn line" onClick={() => runToolHere(t.id, sid)}>Run</button></li>)}
        </ul>
      </section>
    </>
  )
}

export function BuildingPage({ sid }: { sid: string }) {
  const v = useBuildingView(sid)
  const route = useRoute()
  const m = useMapModel()
  const { story, stories } = useStories()
  const doc = useWorkspace((s) => s.doc)
  const current = useCurrent()
  const plan = v.plan
  const open = route.q.get('b_o') === '1'
  const air = route.q.get('b_v') === 'air' && !!plan?.geo
  const [text, setText] = useState('')

  // Arriving: the model rises out of the page, walls growing from the floor to the cut.
  const setView = v.setView, mode = v.mode
  useEffect(() => {
    if (!plan) return
    if (mode !== 'dollhouse' || reduced()) { setView((x) => ({ ...x, cut: x.cut ?? CUT })); return }
    const t0 = performance.now()
    const id = setInterval(() => {
      const k = Math.min(1, (performance.now() - t0) / 900), e = 1 - (1 - k) ** 3
      setView((x) => ({ ...x, cut: 0.08 + (CUT - 0.08) * e }))
      if (k >= 1) clearInterval(id)
    }, 75)
    return () => clearInterval(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [plan?.sid])

  // A link that names a finding opens on it.
  const f = route.q.get('f')
  useEffect(() => {
    if (!f || doc.camera || air) return
    const hit = doc.findings.find((x) => x.id === f)
    if (hit?.anchor && 'sid' in hit.anchor && hit.anchor.sid === sid) focusFinding(hit)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [f, doc.findings.length, sid])

  const city = m.selected?.metro ? CITIES[m.selected.metro].name : plan?.city ?? ''
  const street = (plan?.address ?? m.selected?.address ?? '').split(',')[0]
  const toMap = () => navigate('/map', { b: route.q.get('b') ?? m.selected?.id, city: route.q.get('city') ?? m.selected?.metro ?? undefined })
  const setMode = (x: SceneMode) => { setQuery({ b_v: null }); v.setMode(x) }
  const photo = air || v.mode === 'pano' || v.mode === 'splat'
  const storyFindings = story ? doc.findings.filter((x) => x.run === story.run || x.tool === story.tool) : doc.findings
  // The figure illustrates the story being read: of everything the tools drew on this scan, it carries this story's
  // marks only (what is in map coordinates is the aerial plate's and the map's, as in core).
  const drawn = useMemo(() => (!story ? v.overlays : doc.overlays.filter((o) => o.tool === story.tool && (!o.sid || o.sid === sid)).map((o) => o.overlay)
    .map((o) => (o.kind === 'pins' ? { ...o, pins: o.pins.filter((p) => !('geo' in p.anchor)) } : o))
    .filter((o) => !(o.kind === 'route' && o.floor === 'geo') && !(o.kind === 'pins' && !o.pins.length))), [story?.tool, doc.overlays, v.overlays, sid]) // eslint-disable-line react-hooks/exhaustive-deps
  const marks = legendOf(drawn)
  const camFinding = doc.camera?.finding
  // The figure closes in on a finding only while its own story is on the page. The scene does not step back when a
  // focus is taken away, so a figure that had closed in is drawn again for the next story.
  const owner = camFinding ? doc.findings.find((x) => x.id === camFinding) : null
  const foreign = !!story && !!owner && owner.tool !== story.tool
  const sceneView: SceneProps['view'] = v.sceneProps?.view && foreign ? { ...v.sceneProps.view, focus: null } : v.sceneProps?.view
  const closedIn = useRef(false), lastStory = useRef(story?.id)
  const [redraw, setRedraw] = useState(0)
  if (sceneView?.focus) closedIn.current = true
  useEffect(() => {
    if (lastStory.current && story?.id !== lastStory.current && closedIn.current) { closedIn.current = false; setRedraw((n) => n + 1) }
    lastStory.current = story?.id
  }, [story?.id])
  const place = <><button className="back" onClick={toMap}>{city ? `${city} edition` : 'The map'}</button>{street && <span>{street}</span>}</>
  const keep = plan && <button className="link keep" aria-pressed={v.kept} onClick={v.toggleKeep}>{v.kept ? 'Kept' : 'Keep'}</button>

  // When the camera goes to a finding from another story on this page, the page turns to that story.
  const lastFinding = useRef<string | undefined>(undefined)
  useEffect(() => {
    if (!camFinding || camFinding === lastFinding.current) return
    const first = lastFinding.current === undefined
    lastFinding.current = camFinding
    if (first && route.q.get('b_s')) return // a link that names its story opens on that story
    const hit = doc.findings.find((x) => x.id === camFinding)
    const owner = hit && stories.find((p) => (hit.run && p.run === hit.run) || p.tool === hit.tool)
    if (owner && owner.id !== story?.id) setQuery({ b_s: owner.id })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [camFinding])
  const caption = !plan ? 'The building, once its plan has loaded.'
    : air ? `${plan.name} from the air, north up. Yellow boxes are what the section on the page found.`
    : v.mode === 'dollhouse' ? `${plan.name}, cut open${v.view.cut != null && v.view.cut < 50 ? ` at ${v.view.cut.toFixed(1)} m` : ''}. Drawn from ${plan.walls.length} ${plural(plan.walls.length, 'wall')} and ${plan.openings.filter((o) => o.type === 'doorway').length} doorways in its scan. ${marks}`
    : v.mode === 'plan' ? `The floor plan of ${plan.name}. ${marks}`
    : v.mode === 'pano' ? `Inside ${plan.name}, a 360° photograph from one of ${plan.panos.length} scan positions. Drag to look around; the rings on the floor are the next positions.`
    : `${plan.name} from the drone capture, drawn as Gaussian splats. Drag to turn it.`

  return (
    <div className="page" data-open={open || undefined} data-plate={photo ? 'photo' : 'paper'}>
      <div className="stage">
        {v.error && <div className="state" role="alert"><p>{v.error}</p><button className="btn" onClick={v.retry}>Try again</button></div>}
        {!plan && !v.error && <div className="state" aria-label="Loading the plan"><i className="unset" /><i className="unset" /></div>}
        {v.sceneProps && (
          <Suspense fallback={<div className="state"><i className="unset" /><i className="unset" /></div>}>
            <SceneBoundary key={`${v.sceneKey}:${redraw}`} fallback={<div className="state" role="alert"><p>The building view stopped on this scan.</p><button className="btn" onClick={v.retry}>Try again</button></div>}>
              <Scene {...v.sceneProps} view={sceneView} overlays={drawn as SceneProps['overlays']} className="bs-scene" />
            </SceneBoundary>
          </Suspense>
        )}
        {air && plan && <AirPlate plan={plan} findings={storyFindings} current={current} />}
      </div>

      <div className="col">
        <OpenQuestions />
        <Contents stories={stories} story={story} />
        {story ? <Story key={`${story.id}:${story.run}`} panel={story} place={place} end={keep} /> : <><p className="kicker cap">{place}{keep}</p><Intro plan={plan} sid={sid} /></>}
        <Plan />
        <Desk />
        <form className="phone-ask" onSubmit={(e) => { e.preventDefault(); if (text.trim()) { void ask(text.trim()); setText('') } }}>
          <input className="field" value={text} onChange={(e) => setText(e.target.value)} placeholder="Ask for a change" aria-label="Ask the agent for a change" autoComplete="off" /><button className="btn">Ask</button>
        </form>
      </div>

      <figure className="figbar">
        <Fig n={1}>{caption}</Fig>
        <div className="views" role="group" aria-label="What the figure shows">
          {v.modes.map((x) => <button key={x} aria-pressed={!air && v.mode === x} onClick={() => setMode(x)}>{VIEW[x]}</button>)}
          {plan?.geo && <button aria-pressed={air} onClick={() => setQuery({ b_v: air ? null : 'air' })}>Aerial</button>}
          {!air && (v.mode === 'dollhouse' || v.mode === 'plan') && plan?.has.openings && <button aria-pressed={!!v.view.measures} onClick={() => v.setView((x) => ({ ...x, measures: !x.measures }))}>Widths</button>}
          {!air && v.mode === 'pano' && plan?.has.defurnished && <button aria-pressed={v.view.wipe != null} onClick={() => v.setView((x) => ({ ...x, wipe: x.wipe == null ? 0.5 : null }))}>Empty rooms</button>}
          <button className="open" onClick={() => setQuery({ b_o: open ? null : '1' })}>{open ? 'Back to the page' : 'Open the figure'}</button>
        </div>
      </figure>

      {open && (
        <aside className="opencap" aria-label="What the figure shows">
          <p className="cap">{[street, story?.title].filter(Boolean).join(' · ')}</p>
          {story ? <Headline panel={story as Panel} family={familyOf(story.tool)} as="h2" brief /> : <h2 className="head">{plan?.name}</h2>}
          <div className="row" style={{ marginTop: '0.875rem' }}><button className="btn" onClick={() => setQuery({ b_o: null })}>Back to the page</button><span className="fig">or press Esc</span></div>
        </aside>
      )}
    </div>
  )
}
