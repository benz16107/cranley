import { Suspense, useEffect, useRef, useState } from 'react'
import { Drawer } from 'vaul'
import { CityMap, useMap } from '../map/CityMap.tsx'
import { AddressSearch, BuildingCard, Callout, FilterBar, HoverTip, Neatline, TitleBlock } from '../map/MapFurniture.tsx'
import { Icon, Mark } from '../design/ui.tsx'
import { CITIES, Scene, SceneBoundary, currentRoute, navigate, setQuery, useBuildingView, useMapModel, useRoute, useWorkspace, type CityId, type SceneMode } from '../../../core/index.ts'
import { PanelView } from '../blocks/blocks.tsx'
import { BriefCard, Dock, LearnedCard, PlanCard } from './Case.tsx'
import { CommandMenu } from './CommandMenu.tsx'
import { FrontDoor } from '../door/FrontDoor.tsx'
import { useScheme, useTheme } from './theme.ts'

/* The building view is the shared <Scene>, driven through core's useBuildingView. The shell never reaches into three.js. */
const MODES: Record<SceneMode, string> = { dollhouse: '3D', plan: 'Plan', pano: 'Inside', splat: 'Drone' }

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
  const { plan, error, retry, modes, mode, setMode, sceneProps, sceneKey, kept, toggleKeep } = useBuildingView(sid)
  const { q } = useRoute()
  return (
    <div className="scan" ref={frame}>
      <header className="pane scanhead">
        <button className="btn quiet sm" onClick={() => navigate('/map', { b: q.get('b'), city: q.get('city') })}><Icon name="left" size={14} /> Map</button>
        <div className="ttl">
          <h2>{plan?.name ?? (error ? 'Scan not available' : 'Loading the plan')}</h2>
          {plan && <p className="muted">{[(plan.address ?? '').split(',')[0], plan.city, `${plan.rooms.length} rooms`, `${plan.openings.filter((o) => o.type === 'doorway').length} doorways`].filter(Boolean).join(' · ')}</p>}
        </div>
        {plan && (
          <div className="floors" role="group" aria-label="View">
            {modes.map((m) => <button key={m} className="chip" aria-pressed={mode === m} onClick={() => setMode(m)}>{MODES[m]}</button>)}
          </div>
        )}
        {plan && (
          <button className="btn sm" aria-pressed={kept} onClick={toggleKeep}>
            <Icon name="keep" size={14} /> {kept ? 'Kept' : 'Keep'}
          </button>
        )}
      </header>
      <div className="scene">
        {error && <div className="state"><p>{error}</p><button className="btn" onClick={retry}>Try again</button></div>}
        {!plan && !error && <div className="state skeleton" aria-label="Loading the plan" />}
        {sceneProps && (
          <Suspense fallback={<div className="state skeleton" />}>
            {/* keyed by scan: the scene builds its model for one plan, so a new scan gets a new scene */}
            <SceneBoundary key={sceneKey} fallback={<div className="state"><p>The building view stopped on this scan.</p><button className="btn" onClick={retry}>Try again</button></div>}>
              <Scene {...sceneProps} />
            </SceneBoundary>
          </Suspense>
        )}
      </div>
    </div>
  )
}

export function Shell() {
  const route = useRoute()
  const { all, state, reload: load, filters, shown, selected, select, marks, geo, look } = useMapModel()
  const { theme, cycle } = useTheme()
  const scheme = useScheme(theme)
  const phone = useIsPhone()
  const frame = useRef<HTMLDivElement>(null)
  const [menu, setMenu] = useState<false | 'all' | 'tools'>(false)
  const [caseOpen, setCaseOpen] = useState(false)

  const doc = useWorkspace((s) => s.doc), undo = useWorkspace((s) => s.undo)
  const view = route.path === '/scan' ? 'scan' : route.path === '/map' ? 'map' : 'door'
  const hasRail = view !== 'door' && (doc.panels.length > 0 || doc.runs.some((r) => r.status === 'running'))

  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey
      if (mod && e.key.toLowerCase() === 'k') { e.preventDefault(); setMenu((m) => (m ? false : 'all')) }
      if (mod && e.key.toLowerCase() === 'z' && !/input|textarea/i.test((e.target as HTMLElement).tagName)) { e.preventDefault(); undo() }
      if (e.key === 'Escape' && !e.defaultPrevented && !document.querySelector('[data-open], [cmdk-root]') && currentRoute().q.has('b') && currentRoute().path === '/map') setQuery({ b: null }, false)
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
          <CityMap buildings={shown} selected={selected} marks={marks} geo={geo} look={look} city={filters.city} scheme={scheme} inset={view === 'scan'} frame={frame} onSelect={select} />
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
