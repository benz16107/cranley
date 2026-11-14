import { lazy, Suspense, useEffect, useMemo, useRef, useState, type ComponentType } from 'react'
import { Drawer } from 'vaul'
import { CityMap, useMap } from '../map/CityMap.tsx'
import { AddressSearch, BuildingCard, Callout, FilterBar, HoverTip, Neatline, TitleBlock } from '../map/MapFurniture.tsx'
import { CITIES, matches, readFilters, useBuildings, type CityId } from '../map/buildings.ts'
import { Icon, Mark } from '../design/ui.tsx'
import { navigate, setQuery, useRoute } from '../lib/router.ts'
import { fetchPlan } from '../lib/api.ts'
import { useWorkspace, userOp } from '../workspace/store.ts'
import type { Anchor, BuildingSceneProps, ScanPlan, SceneView } from '../workspace/types.ts'
import { PanelView, focusAnchor, focusFinding } from '../workspace/blocks.tsx'
import { replayDemo } from '../workspace/agent.ts'
import { BriefCard, Dock, LearnedCard, PlanCard } from './Case.tsx'
import { anchorFloor, LensLegend, PlanDrawing } from './PlanDrawing.tsx'
import { CommandMenu } from './CommandMenu.tsx'
import { FrontDoor } from '../door/FrontDoor.tsx'
import { useScheme, useTheme } from './theme.ts'

/* The scene workstream's <BuildingScene plan overlays view onPick /> is picked up from web/src/scene/ as soon as it
   exists. Until then the plan drawing stands in, behind the same props. The shell never reaches into three.js. */
const sceneModule = Object.values(import.meta.glob<{ BuildingScene?: ComponentType<BuildingSceneProps>; default?: ComponentType<BuildingSceneProps> }>('../scene/{index,BuildingScene}.{ts,tsx}'))[0]
const RealScene = sceneModule ? lazy(() => sceneModule().then((m) => ({ default: (m.BuildingScene ?? m.default)! }))) : null

const SNAPS = ['112px', 0.55, 0.94]

function useIsPhone() {
  const [phone, setPhone] = useState(() => window.matchMedia('(max-width: 760px)').matches)
  useEffect(() => { const m = window.matchMedia('(max-width: 760px)'); const on = () => setPhone(m.matches); m.addEventListener('change', on); return () => m.removeEventListener('change', on) }, [])
  return phone
}

function CitySwitch({ city }: { city: CityId }) {
  return (
    <div className="cities" role="group" aria-label="City">
      {(Object.keys(CITIES) as CityId[]).map((id) => (
        <button key={id} aria-pressed={city === id} onClick={() => navigate('/map', { city: id, b: null }, { keep: true })}>
          <b>{CITIES[id].name}</b><span className="num">{CITIES[id].coord}</span>
        </button>
      ))}
      <i className="under" style={{ translate: city === 'la' ? '100% 0' : '0 0' }} aria-hidden="true" />
    </div>
  )
}

function ScanStage({ sid, frame }: { sid: string; frame: React.RefObject<HTMLDivElement | null> }) {
  const [plan, setPlan] = useState<ScanPlan | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [floor, setFloor] = useState<string | undefined>()
  const [tries, setTries] = useState(0)
  const doc = useWorkspace((s) => s.doc)
  const { q } = useRoute()
  useEffect(() => {
    let on = true
    setPlan(null); setError(null); setFloor(undefined)
    fetchPlan(sid).then((p) => on && setPlan(p), (e: Error) => on && setError(e.message))
    return () => { on = false }
  }, [sid, tries])
  useEffect(() => { if (q.get('demo') === 'access') replayDemo(sid) }, [sid, q])

  const overlays = useMemo(() => doc.overlays.filter((o) => !o.sid || o.sid === sid).map((o) => o.overlay), [doc.overlays, sid])
  const cam = doc.camera && 'sid' in doc.camera.anchor && doc.camera.anchor.sid === sid && !('point' in doc.camera.anchor) ? doc.camera : null
  const kept = doc.shortlist.some((s) => s.sid === sid)
  const onPick = (anchor: Anchor) => {
    const f = doc.findings.find((x) => x.anchor && JSON.stringify(x.anchor) === JSON.stringify(anchor))
    if (f) focusFinding(f); else focusAnchor(anchor)
  }
  const floors = plan ? [...plan.floors].sort((a, b) => a.sequence - b.sequence) : []
  // A finding on another floor brings that floor up. On any other floor there is nothing of it to point at.
  const camFloor = plan && cam ? anchorFloor(plan, cam.anchor) : null
  useEffect(() => { if (camFloor) setFloor(camFloor) }, [camFloor, cam])
  const shownFloor = floor ?? floors[0]?.id
  const here = cam && (!camFloor || camFloor === shownFloor) ? cam : null
  const view: SceneView = { mode: 'plan', floor: shownFloor, focus: here?.anchor, agentAt: here?.by === 'agent' ? here.anchor : null }
  return (
    <div className="scan" ref={frame}>
      <header className="pane scanhead">
        <button className="btn quiet sm" onClick={() => navigate('/map', { b: q.get('b'), city: q.get('city') })}><Icon name="left" size={14} /> Map</button>
        <div className="ttl">
          <h2>{plan?.name ?? (error ? 'Scan not available' : 'Loading the plan')}</h2>
          {plan && <p className="muted">{[plan.address.split(',')[0], plan.city, `${plan.rooms.length} rooms`, `${plan.openings.filter((o) => o.type === 'doorway').length} doorways`].filter(Boolean).join(' · ')}</p>}
        </div>
        {floors.length > 1 && (
          <div className="floors" role="group" aria-label="Floor">
            {floors.map((f) => <button key={f.id} className="chip" aria-pressed={(floor ?? floors[0].id) === f.id} onClick={() => setFloor(f.id)}>{f.label || `Floor ${f.sequence + 1}`}</button>)}
          </div>
        )}
        {plan && (
          <button className="btn sm" aria-pressed={kept} onClick={() => userOp(kept ? { op: 'shortlist.remove', sid } : { op: 'shortlist.add', item: { sid, name: plan.name, address: plan.address } })}>
            <Icon name="keep" size={14} /> {kept ? 'Kept' : 'Keep'}
          </button>
        )}
      </header>
      <div className="scene">
        {error && <div className="state"><p>{error}</p><button className="btn" onClick={() => setTries(tries + 1)}>Try again</button></div>}
        {!plan && !error && <div className="state skeleton" aria-label="Loading the plan" />}
        {plan && (
          <Suspense fallback={<div className="state skeleton" />}>
            {RealScene ? <RealScene plan={plan} overlays={overlays} onPick={onPick} view={view} /> : <PlanDrawing plan={plan} overlays={overlays} onPick={onPick} view={view} selected={here?.anchor} />}
          </Suspense>
        )}
      </div>
      {plan && !RealScene && <p className="scenenote label">Plan drawing from the wall outline. The 3D view takes this place.</p>}
      {plan && <LensLegend overlays={overlays} />}
    </div>
  )
}

export function Shell() {
  const route = useRoute()
  const { all, state, load } = useBuildings()
  useEffect(load, [load])
  const { theme, cycle } = useTheme()
  const scheme = useScheme(theme)
  const phone = useIsPhone()
  const frame = useRef<HTMLDivElement>(null)
  const [menu, setMenu] = useState<false | 'all' | 'tools'>(false)
  const [caseOpen, setCaseOpen] = useState(false)

  const doc = useWorkspace((s) => s.doc), follow = useWorkspace((s) => s.follow), undo = useWorkspace((s) => s.undo)
  const filters = useMemo(() => readFilters(route.q), [route.q])
  const shown = useMemo(() => all.filter((b) => matches(b, filters)), [all, filters])
  const selected = useMemo(() => all.find((b) => b.id === route.q.get('b')) ?? (route.sid ? all.find((b) => b.scans.some((x) => x.sid === route.sid)) : undefined) ?? null, [all, route.q, route.sid])
  const marks = useMemo(() => {
    const sids = new Set([...doc.panels.map((p) => p.sid), ...doc.shortlist.map((s) => s.sid)])
    return all.filter((b) => b.scans.some((s) => sids.has(s.sid)))
  }, [all, doc.panels, doc.shortlist])
  const view = route.path === '/scan' ? 'scan' : route.path === '/map' ? 'map' : 'door'
  const hasRail = view !== 'door' && (doc.panels.length > 0 || doc.runs.some((r) => r.status === 'running'))

  // Where the camera is told to look, the view goes: the agent's moves only while "follow" is on.
  const cam = doc.camera
  useEffect(() => {
    if (!cam || (cam.by === 'agent' && !follow)) return
    const a = cam.anchor
    if ('geo' in a) {
      const near = all.find((b) => Math.abs(b.lon - a.geo[0]) < 1e-5 && Math.abs(b.lat - a.geo[1]) < 1e-5)
      navigate('/map', { b: near?.id, city: near?.metro ?? undefined }, { keep: true })
    } else if (route.sid !== a.sid) navigate(`/scan/${a.sid}`, { f: cam.finding }, { keep: true })
    else setQuery({ f: cam.finding })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cam])

  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey
      if (mod && e.key.toLowerCase() === 'k') { e.preventDefault(); setMenu((m) => (m ? false : 'all')) }
      if (mod && e.key.toLowerCase() === 'z' && !/input|textarea/i.test((e.target as HTMLElement).tagName)) { e.preventDefault(); undo() }
      if (e.key === 'Escape' && !e.defaultPrevented && !document.querySelector('[data-open], [cmdk-root]') && new URLSearchParams(window.location.search).has('b') && window.location.pathname === '/map') setQuery({ b: null }, false)
    }
    window.addEventListener('keydown', key)
    return () => window.removeEventListener('keydown', key)
  }, [undo])

  // The phone sheet rises to half height when there is something new to read in it.
  const [snap, setSnap] = useState<number | string | null>(SNAPS[0])
  useEffect(() => { if (selected || doc.panels.length) setSnap(SNAPS[1]) }, [selected, doc.panels.length])

  const map = useMap((s) => s.map)
  const caseBody = <><BriefCard /><PlanCard /><LearnedCard /></>
  const rail = doc.panels.map((p, i) => <PanelView key={p.id} panel={p} index={i} />)

  return (
    <div className="app" data-view={view} data-rail={hasRail} data-case={caseOpen}>
      <a className="skip" href="#stage">Skip to the map</a>
      <header className="bar">
        <button className="mark" onClick={() => navigate('/')} aria-label="Threshold, front door"><Mark /><span>THRESHOLD</span></button>
        {view !== 'door' && <button className="btn sm casebtn" aria-expanded={caseOpen} onClick={() => setCaseOpen(!caseOpen)}>Brief and plan</button>}
        <CitySwitch city={filters.city} />
        <AddressSearch all={all} />
        <button className="btn quiet sm menubtn" onClick={() => setMenu('all')} aria-label="Open the command menu"><span className="kbd">Ctrl K</span></button>
        <button className="btn icon quiet" onClick={cycle} aria-label={`Colour scheme: ${theme}. Change it.`} title={`Scheme: ${theme}`}><Icon name={scheme === 'dark' ? 'moon' : 'sun'} /></button>
      </header>

      <main className="stage" id="stage" tabIndex={-1}>
        <div className="mapwrap" data-inset={view === 'scan'}>
          <CityMap buildings={shown} selected={selected} marks={marks} city={filters.city} scheme={scheme} inset={view === 'scan'} frame={frame} onSelect={(b) => setQuery({ b: b?.id }, false)} />
          {view === 'scan' && <button className="keyplan" onClick={() => navigate('/map', { b: route.q.get('b'), city: route.q.get('city') })}><span className="label">Key plan</span><span className="sr">Back to the map</span></button>}
        </div>
        {state === 'error' && <div className="pane mapstate" role="alert"><p>The building list did not load. Is the data server running?</p><button className="btn" onClick={load}>Try again</button></div>}
        {state === 'loading' && view !== 'scan' && <div className="pane mapstate"><span className="skeleton" /><p className="muted">Loading the scanned buildings</p></div>}

        {view === 'scan' && route.sid ? <ScanStage sid={route.sid} frame={frame} /> : (
          <div className="free">
            <Neatline frame={frame} />
            {view === 'map' && <FilterBar filters={filters} all={all} selected={map ? selected : null} />}
            {view === 'map' && <HoverTip frame={frame} />}
            {view === 'map' && selected && !phone && <Callout b={selected} frame={frame} onClose={() => setQuery({ b: null }, false)} />}
            {view === 'map' && <TitleBlock buildings={shown} city={filters.city} frame={frame} />}
          </div>
        )}
      </main>

      {view !== 'door' && !phone && <aside className="pane case scroll" aria-label="Brief, plan and what has been learned">{caseBody}</aside>}
      {hasRail && !phone && <aside className="rail scroll" aria-label="Workspace panels">{rail}{!doc.panels.length && <div className="pane panel-loading skeleton" />}</aside>}
      {!phone && <Dock onAddTool={() => setMenu('tools')} />}

      {phone && view !== 'door' && (
        <Drawer.Root open modal={false} dismissible={false} snapPoints={SNAPS} activeSnapPoint={snap} setActiveSnapPoint={setSnap}>
          <Drawer.Portal>
            <Drawer.Content className="sheet" aria-label="Workspace">
              <Drawer.Handle className="grip" />
              <Drawer.Title className="sr">Workspace</Drawer.Title>
              <div className="sheetbody scroll">
                {selected && view === 'map' && <BuildingCard b={selected} onClose={() => setQuery({ b: null }, false)} />}
                {rail}
                {caseBody}
                <Dock onAddTool={() => setMenu('tools')} />
              </div>
            </Drawer.Content>
          </Drawer.Portal>
        </Drawer.Root>
      )}

      {view === 'door' && <FrontDoor count={state === 'ready' ? all.length : null} />}
      <CommandMenu open={menu} onClose={() => setMenu(false)} all={all} />
    </div>
  )
}
