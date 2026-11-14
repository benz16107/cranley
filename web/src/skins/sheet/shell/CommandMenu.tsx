import { useEffect, useMemo, useState } from 'react'
import { Command } from 'cmdk'
import { search, CITIES, type Building, type CityId } from '../../../core/buildings.ts'
import { TOOLS } from '../../../core/fixtures/catalog.ts'
import { useWorkspace, userOp } from '../../../core/store.ts'
import { useCatalog } from '../../../core/server.ts'
import { startOver } from '../../../core/agent.ts'
import { navigate } from '../../../core/router.ts'
import { ToolKey } from '../design/ui.tsx'

/** Ctrl K. Also where a tool is added by hand. It opens and closes without animation: it is used too often for one. */
export function CommandMenu({ open, onClose, all }: { open: false | 'all' | 'tools'; onClose: () => void; all: Building[] }) {
  const [q, setQ] = useState('')
  const tools = useWorkspace((s) => s.doc.tools), undo = useWorkspace((s) => s.undo)
  // the server's tools when it answers (planned ones last), else the fixture list
  const served = useCatalog((s) => s.tools)
  const catalog = useMemo(() => (served.length ? [...served].sort((a, b) => Number(a.status === 'planned') - Number(b.status === 'planned')).map((m) => ({ id: m.id, title: m.title, code: undefined, summary: m.status === 'planned' ? `Planned, not built yet. ${m.summary}` : m.summary })) : Object.values(TOOLS)), [served])
  useEffect(() => { if (open) setQ('') }, [open])
  const hits = useMemo(() => (q.length >= 3 ? search(all, q, 6) : []), [all, q])
  const run = (fn: () => void) => () => { fn(); onClose() }
  const setTheme = (t: string) => { if (t === 'system') { delete document.documentElement.dataset.theme; localStorage.removeItem('threshold.theme') } else { localStorage.setItem('threshold.theme', t) } window.location.reload() }
  return (
    <Command.Dialog open={!!open} onOpenChange={(o) => !o && onClose()} label="Command menu" className="cmd" shouldFilter>
      <Command.Input value={q} onValueChange={setQ} placeholder={open === 'tools' ? 'Add a tool' : 'Go to a place, add a tool, change the view'} />
      <Command.List>
        <Command.Empty>Nothing matches “{q}”.</Command.Empty>
        <Command.Group heading="Tools">
          {catalog.map((t) => {
            const on = tools.some((x) => x.id === t.id)
            return (
              <Command.Item key={t.id} value={`tool ${t.title} ${t.summary}`} onSelect={run(() => userOp(on ? { op: 'tool.disable', id: t.id } : { op: 'tool.enable', tool: { ...t, reason: 'You added it from the command menu.' } }))}>
                <ToolKey id={t.id} title={t.title} code={t.code} /><span className="grow">{t.title}<small>{t.summary}</small></span><span className="label">{on ? 'Remove' : 'Add'}</span>
              </Command.Item>
            )
          })}
        </Command.Group>
        {open !== 'tools' && (
          <>
            {hits.length > 0 && (
              <Command.Group heading="Buildings">
                {hits.map((b) => <Command.Item key={b.id} value={`${b.address} ${b.scans.map((s) => s.name).join(' ')}`} onSelect={run(() => navigate('/map', { city: b.metro ?? undefined, b: b.id }))}><span className="grow">{b.address}</span><span className="num muted">{b.count} {b.count === 1 ? 'scan' : 'scans'}</span></Command.Item>)}
              </Command.Group>
            )}
            <Command.Group heading="Go to">
              <Command.Item onSelect={run(() => navigate('/'))}>Front door</Command.Item>
              {(Object.keys(CITIES) as CityId[]).map((c) => <Command.Item key={c} onSelect={run(() => navigate('/map', { city: c }))}>{CITIES[c].name} map</Command.Item>)}
            </Command.Group>
            <Command.Group heading="Workspace">
              <Command.Item onSelect={run(undo)}>Undo my last change</Command.Item>
              <Command.Item onSelect={run(() => { startOver(); navigate('/') })}>Start over with a new brief</Command.Item>
            </Command.Group>
            <Command.Group heading="Colour scheme">
              {['light', 'dark', 'system'].map((t) => <Command.Item key={t} value={`scheme ${t}`} onSelect={() => setTheme(t)}>{t === 'system' ? 'Match the system' : t === 'light' ? 'Light: ink on paper' : 'Dark: blueprint'}</Command.Item>)}
            </Command.Group>
          </>
        )}
      </Command.List>
    </Command.Dialog>
  )
}
