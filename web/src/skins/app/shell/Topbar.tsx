import { Fragment, type ReactNode } from 'react'
import { useBuildings, useCatalog, useWorkspace } from '../../../core/index.ts'
import { Icon, IconBtn } from '../design/ui.tsx'
import { go, usePlace } from '../lib/place.ts'
import { leaveShared, useSeen } from '../lib/pending.ts'
import { useIsPhone, useUi } from './store.ts'
import { DemoMenu } from '../demo/DemoMenu.tsx'
import { isApproval, useStopped } from './AgentLive.tsx'

type Crumb = { label: string; to?: () => void }
const TITLE = { home: 'Home', explore: 'Explore', investigations: 'Investigations', buildings: 'Buildings', insights: 'Insights', tools: 'Tools', settings: 'Settings' } as const

function useCrumbs(): Crumb[] {
  const { page, id, sid } = usePlace()
  const all = useBuildings((s) => s.all)
  const doc = useWorkspace((s) => s.doc), seen = useSeen((s) => s.all)
  if (page === 'building') {
    const b = all.find((x) => x.scans.some((s) => s.sid === sid)), scan = b?.scans.find((s) => s.sid === sid)
    return [{ label: 'Explore', to: () => go('explore', { city: b?.metro ?? undefined }) }, ...(b && b.address.split(',')[0] !== scan?.name ? [{ label: b.address.split(',')[0], to: () => go('explore', { city: b.metro ?? undefined, b: b.id }) }] : []), { label: scan?.name ?? 'Scan' }] // a house's scan is named by its address: say it once
  }
  if (page === 'investigation') return [{ label: 'Investigations', to: () => go('investigations') }, { label: (id === doc.id ? doc.brief?.text : seen[id ?? '']?.brief) || 'Untitled investigation' }]
  return [{ label: TITLE[page] }]
}

export function Topbar({ actions }: { actions?: ReactNode }) {
  const crumbs = useCrumbs()
  const phone = useIsPhone()
  const run = useUi((s) => s.run), setRun = useUi((s) => s.setRun)
  const doc = useWorkspace((s) => s.doc)
  const shared = useCatalog((s) => s.shared?.state === 'ready')
  const running = doc.runs.filter((r) => r.status === 'running').length, open = doc.questions.filter((q) => q.answer == null).length
  const stopped = useStopped()
  const approving = doc.questions.some((q) => q.answer == null && isApproval(q)) // paused for the person: a dot, not a spinner
  const working = !stopped && !approving && (running > 0 || doc.plan.some((s) => s.status === 'active'))
  return (
    <header className="top">
      {phone && <IconBtn icon="menu" label="Open the navigation" onClick={() => useUi.setState({ nav: true })} />}
      <nav className="crumbs" aria-label="Where you are">
        {crumbs.map((c, i) => (
          <Fragment key={i}>
            {i > 0 && <Icon name="right" size={11} />}
            {c.to ? <button type="button" onClick={c.to}>{c.label}</button> : <h1 className="trunc">{c.label}</h1>}
          </Fragment>
        ))}
      </nav>
      {actions}
      {/* a read-only link says so on every page, with the way out */}
      {shared && <span className="readonly"><Icon name="eye" size={13} /><span>Read-only link</span><button type="button" className="btn sm" onClick={leaveShared}>Leave</button></span>}
      <DemoMenu />
      <button type="button" className="find" onClick={() => useUi.setState({ menu: 'all' })} aria-label="Search buildings, tools and pages">
        <Icon name="search" size={14} /><span className="grow">Search buildings, tools, pages</span><span className="kbd">Ctrl K</span>
      </button>
      <button type="button" className="btn agentbtn" aria-pressed={run} onClick={() => setRun(!run)} aria-label={`Agent panel${working ? ', working' : open ? `, ${open} to answer` : ''}`} title="Agent panel ( ] )">
        {working ? <i className="ring" /> : <Icon name="runs" size={15} />}
        <span>Agent</span>
        {working ? <span className="count">{running || ''}</span> : open > 0 && <span className="dot" aria-hidden="true" />}
      </button>
    </header>
  )
}
