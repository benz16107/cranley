import { useEffect, useMemo, useState } from 'react'
import { Command } from 'cmdk'
import { search, useBuildings, useToolCatalog, useWorkspace, userOp } from '../../../core/index.ts'
import { Icon, ToolKey, type IconName } from '../design/ui.tsx'
import { go, goInvestigation } from '../lib/place.ts'
import { openSeen, useSeen } from '../lib/pending.ts'
import { newInvestigation } from './Sidebar.tsx'
import { useTheme } from './theme.ts'
import { useUi } from './store.ts'

const PAGES: { page: Parameters<typeof go>[0]; label: string; icon: IconName; key: string }[] = [
  { page: 'home', label: 'Home', icon: 'home', key: 'G H' }, { page: 'explore', label: 'Explore the map', icon: 'map', key: 'G E' },
  { page: 'investigations', label: 'Investigations', icon: 'runs', key: 'G I' }, { page: 'buildings', label: 'Saved buildings', icon: 'keep', key: 'G B' },
  { page: 'insights', label: 'Insights', icon: 'chart', key: 'G N' }, { page: 'tools', label: 'Tools', icon: 'tool', key: 'G T' }, { page: 'settings', label: 'Settings', icon: 'gear', key: 'G S' },
]

/** Ctrl K: go anywhere, find a building, add a tool. It opens and closes without animation: it is used too often for one. */
export function CommandMenu() {
  const open = useUi((s) => s.menu), close = () => useUi.setState({ menu: false })
  const [q, setQ] = useState('')
  const all = useBuildings((s) => s.all)
  const doc = useWorkspace((s) => s.doc), undo = useWorkspace((s) => s.undo)
  const catalog = useToolCatalog()
  const seen = useSeen((s) => s.all)
  const setTheme = useTheme((s) => s.setTheme)
  useEffect(() => { if (open) setQ('') }, [open])
  const hits = useMemo(() => (q.length >= 3 ? search(all, q, 6) : []), [all, q])
  const run = (fn: () => void) => () => { fn(); close() }
  const tools = open === 'tools'
  return (
    <Command.Dialog open={!!open} onOpenChange={(o) => !o && close()} label="Command menu" className="cmd" shouldFilter>
      <Command.Input value={q} onValueChange={setQ} placeholder={tools ? 'Add a tool to this investigation' : 'Search buildings by address, tools, pages'} />
      <Command.List>
        <Command.Empty>Nothing matches “{q}”.</Command.Empty>
        {!tools && hits.length > 0 && (
          <Command.Group heading="Buildings">
            {hits.map((b) => (
              <Command.Item key={b.id} value={`${b.address} ${b.scans.map((s) => s.name).join(' ')}`} onSelect={run(() => go('explore', { city: b.metro ?? undefined, b: b.id }))}>
                <Icon name="building" /><span className="grow trunc">{b.address}</span><small>{b.count} {b.count === 1 ? 'scan' : 'scans'}</small>
              </Command.Item>
            ))}
          </Command.Group>
        )}
        {!tools && (
          <Command.Group heading="Go to">
            {PAGES.map((p) => <Command.Item key={p.page} value={`go ${p.label}`} onSelect={run(() => go(p.page))}><Icon name={p.icon} /><span className="grow">{p.label}</span><span className="kbd">{p.key}</span></Command.Item>)}
          </Command.Group>
        )}
        {!tools && (
          <Command.Group heading="Actions">
            <Command.Item value="new investigation start over brief" onSelect={run(newInvestigation)}><Icon name="plus" /><span className="grow">New investigation</span></Command.Item>
            <Command.Item value="agent panel plan runs" onSelect={run(() => useUi.getState().setRun(!useUi.getState().run))}><Icon name="runs" /><span className="grow">Show or hide the agent panel</span><span className="kbd">]</span></Command.Item>
            <Command.Item value="undo my last change" onSelect={run(undo)}><Icon name="undo" /><span className="grow">Undo my last change</span><span className="kbd">Ctrl Z</span></Command.Item>
            <Command.Item value="keyboard shortcuts help" onSelect={run(() => useUi.setState({ keys: true }))}><Icon name="help" /><span className="grow">Keyboard shortcuts</span><span className="kbd">?</span></Command.Item>
            <Command.Item value="appearance theme light" onSelect={run(() => setTheme('light'))}><Icon name="sun" /><span className="grow">Light appearance</span></Command.Item>
            <Command.Item value="appearance theme dark blueprint" onSelect={run(() => setTheme('dark'))}><Icon name="moon" /><span className="grow">Dark appearance</span></Command.Item>
            <Command.Item value="appearance theme system" onSelect={run(() => setTheme('system'))}><Icon name="monitor" /><span className="grow">Match the system appearance</span></Command.Item>
          </Command.Group>
        )}
        {!tools && Object.keys(seen).length > 0 && (
          <Command.Group heading="Investigations">
            {Object.values(seen).sort((a, b) => b.last - a.last).slice(0, 6).map((s) => (
              <Command.Item key={s.id} value={`investigation ${s.brief} ${s.id}`} onSelect={run(() => (s.id === doc.id ? goInvestigation(s.id) : openSeen(s.id)))}><Icon name="runs" /><span className="grow trunc">{s.brief || 'Untitled investigation'}</span><small>{s.id === doc.id ? 'open' : ''}</small></Command.Item>
            ))}
          </Command.Group>
        )}
        <Command.Group heading={tools ? 'Tools' : 'Add or remove a tool'}>
          {catalog.map((t) => {
            const on = doc.tools.some((x) => x.id === t.id)
            return (
              <Command.Item key={t.id} value={`tool ${t.title} ${t.summary}`} disabled={t.planned} onSelect={run(() => userOp(on ? { op: 'tool.disable', id: t.id } : { op: 'tool.enable', tool: { id: t.id, title: t.title, summary: t.summary, coverage: t.coverage, reason: 'You added it from the command menu.' } }))}>
                <ToolKey id={t.id} title={t.title} /><span className="grow"><span>{t.title}</span><small className="trunc">{t.summary}</small></span><span className="muted">{t.planned ? 'Planned' : on ? 'Remove' : 'Add'}</span>
              </Command.Item>
            )
          })}
        </Command.Group>
      </Command.List>
    </Command.Dialog>
  )
}
