import { useEffect, useRef, useState } from 'react'
import { Dialog } from '@base-ui/react/dialog'
import { Tooltip } from '@base-ui/react/tooltip'
import { Drawer } from 'vaul'
import { currentRoute, setQuery, useWorkspace } from '../../../core/index.ts'
import { Icon } from '../design/ui.tsx'
import { Edge, Fill, Pane, Split } from '../design/split.tsx'
import { FirstRun } from './FirstRun.tsx'
import { go, usePlace } from '../lib/place.ts'
import '../lib/pending.ts' // keeps the index of investigations seen in this browser
import { useBuildings } from '../../../core/index.ts'
import { Building } from '../pages/Building.tsx'
import { Buildings } from '../pages/Buildings.tsx'
import { Explore } from '../pages/Explore.tsx'
import { Home } from '../pages/Home.tsx'
import { Insights } from '../pages/Insights.tsx'
import { Investigation, Investigations } from '../pages/Investigations.tsx'
import { Settings } from '../pages/Settings.tsx'
import { Tools } from '../pages/Tools.tsx'
import { CommandMenu } from './CommandMenu.tsx'
import { PanelDrawer, RunPanel } from './RunPanel.tsx'
import { LiveLink } from './AgentLive.tsx'
import { Knows } from './Knows.tsx'
import { StartTool } from './StartTool.tsx'
import { PAGE_KEYS, Sidebar } from './Sidebar.tsx'
import { Topbar } from './Topbar.tsx'
import { useScheme } from './theme.ts'
import { useIsPhone, useUi } from './store.ts'

export const SHORTCUTS: [keys: string, what: string][] = [
  ['Ctrl K', 'Search and commands'], ['/', 'Search'], [']', 'Show or hide the agent panel'], ['Ctrl B', 'Show or hide the sidebar'], ['[', 'Narrow or widen the sidebar'],
  ['G then H', 'Home'], ['G then E', 'Explore'], ['G then I', 'Investigations'], ['G then B', 'Saved buildings'], ['G then N', 'Insights'], ['G then T', 'Tools'], ['G then S', 'Settings'],
  ['C', 'On Home: write a new brief'], ['1 2 3 4', 'On a building: 3D, plan, inside, drone'], ['K', 'On a building: keep or stop keeping it'], ['Ctrl Z', 'Undo my last change'], ['Esc', 'Close what is open, or clear the selected building'], ['?', 'This list'],
]
const typing = (e: KeyboardEvent) => { const t = e.target as HTMLElement; return /^(input|textarea|select)$/i.test(t.tagName) || t.isContentEditable }

function Shortcuts() {
  const open = useUi((s) => s.keys)
  return (
    <Dialog.Root open={open} onOpenChange={(o) => useUi.setState({ keys: o })}>
      <Dialog.Portal>
        <Dialog.Backdrop className="backdrop" />
        <Dialog.Popup className="dialog">
          <header><Dialog.Title render={<h2 />}>Keyboard shortcuts</Dialog.Title><Dialog.Close render={<button className="btn icon quiet" aria-label="Close" />}><Icon name="close" /></Dialog.Close></header>
          <div className="body"><dl className="keys">{SHORTCUTS.map(([k, w]) => <div key={k}><dt>{k.split(' ').map((x, i) => (x === 'then' ? <span key={i} className="muted">then</span> : <span key={i} className="kbd">{x}</span>))}</dt><dd>{w}</dd></div>)}</dl></div>
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

export function Shell() {
  const place = usePlace()
  const scheme = useScheme()
  const phone = useIsPhone()
  const { run, rail, hidden, sliding, nav, setRun } = useUi()
  const undo = useWorkspace((s) => s.undo)
  useEffect(() => { document.documentElement.dataset.scheme = scheme }, [scheme])
  const load = useBuildings((s) => s.load)
  useEffect(load, [load]) // every page names buildings: the breadcrumb, the search, the saved list

  // The run panel opens by itself when the agent starts working or needs an answer. Closing it is the person's.
  const busy = useWorkspace((s) => s.doc.plan.some((p) => p.status === 'active') || ((s.doc.plan.length > 0 || s.doc.runs.length > 0 || !s.doc.brief) && s.doc.questions.some((q) => q.answer == null)))
  const was = useRef(busy)
  // Not when the busy document is the one this page load opened (a reload, another investigation opened, a read-only
  // link): that is not the agent starting, and on a phone the sheet would cover every page as it opens. A workspace
  // made after the page loaded is never that one. Not on a phone during the guided first run either: there the page
  // is what is being shown.
  const docId = useWorkspace((s) => s.doc.id), lastId = useRef(docId)
  const [atLoad] = useState(() => { try { return localStorage.getItem('threshold.workspace') } catch { return null } })
  useEffect(() => {
    const swapped = docId !== lastId.current && (docId === atLoad || docId === 'shared')
    lastId.current = docId
    if (busy && !was.current && !swapped && !(phone && useUi.getState().first)) setRun(true)
    was.current = busy
  }, [busy, docId, atLoad, setRun, phone])

  useEffect(() => {
    let g = 0
    const key = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey, k = e.key.toLowerCase(), ui = useUi.getState()
      if (mod && k === 'k') { e.preventDefault(); useUi.setState({ menu: ui.menu ? false : 'all' }); return }
      if (mod && k === 'b' && !e.shiftKey && !e.altKey) { e.preventDefault(); ui.toggleSide(); return } // from the keyboard: no slide
      if (mod && k === 'z' && !typing(e)) { e.preventDefault(); undo(); return }
      if (mod || e.altKey || typing(e) || ui.menu) return
      if (e.key === 'Escape' && !e.defaultPrevented && !document.querySelector('[data-open], [role="dialog"], [role="menu"]') && currentRoute().path === '/map' && currentRoute().q.has('b')) { setQuery({ b: null }, false); return }
      if (performance.now() - g < 900 && PAGE_KEYS[k]) { e.preventDefault(); g = 0; go(PAGE_KEYS[k]); return }
      if (k === 'g') { g = performance.now(); return }
      if (e.key === '/') { e.preventDefault(); useUi.setState({ menu: 'all' }) }
      else if (e.key === ']') ui.setRun(!ui.run)
      else if (e.key === '[') { if (ui.hidden) ui.setHidden(false); else ui.setRail(!ui.rail) } // hidden: the key brings it back as it was
      else if (e.key === '?') useUi.setState({ keys: true })
    }
    window.addEventListener('keydown', key)
    return () => window.removeEventListener('keydown', key)
  }, [undo])

  const sidepane = sliding ? `sidepane ${sliding}` : 'sidepane'
  const page =
    place.page === 'home' ? <Home /> : place.page === 'explore' || (place.page === 'building' && place.sid && !phone) ? <Explore sid={place.page === 'building' ? place.sid : null} />
    : place.page === 'building' && place.sid ? <Building sid={place.sid} key={place.sid} />
    : place.page === 'investigations' ? <Investigations /> : place.page === 'investigation' ? <Investigation id={place.id!} /> : place.page === 'buildings' ? <Buildings />
    : place.page === 'insights' ? <Insights /> : place.page === 'tools' ? <Tools /> : <Settings />

  return (
    <Tooltip.Provider delay={450} closeDelay={0}>
      <div className="app" data-page={place.page} data-rail={rail || undefined} data-side={(hidden && !phone) || undefined} data-run={(run && !phone) || undefined}>
        <a className="skip" href="#main">Skip to the page</a>
        {/* Sidebar, page and agent panel resize by the edges between them. The sidebar has three states: full, a fixed
            52 px of icons, and hidden. Dragging the full one's edge past half its smallest width hides it. */}
        <Split className="frame" off={phone}>
          {!phone && !hidden && (rail ? <Pane key="rail" id="rail" size={52} fixed className={sidepane}><Sidebar /></Pane>
            : <Pane key="side" id="side" size={224} min={184} max={400} className={sidepane} onCollapse={() => { if (!useUi.getState().sliding) useUi.getState().setHidden(true) }}><Sidebar /></Pane>)}
          {!phone && !hidden && !rail && <Edge key="side-edge" of="side" label="Resize the sidebar, or drag it shut" />}
          <Fill key="work" id="work" min={360} className="workpane">
            <FirstRun />
            <Topbar />
            <main className="main" id="main" tabIndex={-1}>{page}</main>
          </Fill>
          {run && !phone && <Edge key="run-edge" of="run" label="Resize the agent panel" />}
          {run && !phone && <Pane key="run" id="run" size={window.innerWidth <= 1700 ? 344 : 372} min={300} max={720}><RunPanel onClose={() => setRun(false)} /></Pane>}
        </Split>

        {phone && (
          <Drawer.Root open={nav} onOpenChange={(o) => useUi.setState({ nav: o })} direction="left">
            <Drawer.Portal><Drawer.Overlay className="backdrop" /><Drawer.Content className="navdrawer" aria-describedby={undefined}><Drawer.Title className="sr">Navigation</Drawer.Title><Sidebar onPick={() => useUi.setState({ nav: false })} /></Drawer.Content></Drawer.Portal>
          </Drawer.Root>
        )}
        {phone && (
          <Drawer.Root open={run} onOpenChange={setRun}>
            <Drawer.Portal><Drawer.Overlay className="backdrop" /><Drawer.Content className="rundrawer" aria-describedby={undefined}><Drawer.Handle className="grip" /><Drawer.Title className="sr">Agent</Drawer.Title><RunPanel onClose={() => setRun(false)} /></Drawer.Content></Drawer.Portal>
          </Drawer.Root>
        )}
        <LiveLink />
        <CommandMenu />
        <Shortcuts />
        <PanelDrawer />
        <Knows />
        <StartTool />
      </div>
    </Tooltip.Provider>
  )
}
