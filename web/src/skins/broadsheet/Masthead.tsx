import { useEffect, useMemo, useRef, useState } from 'react'
import { readStory } from './stories.tsx'
import { Command } from 'cmdk'
import { Popover } from '@base-ui/react/popover'
import {
  CITIES, ask, navigate, runToolHere, search, startOver, useMapModel, useRoute, useToolCatalog, useWorkspace, userOp,
  type Building, type CityId, type Panel,
} from '../../core/index.ts'

/* The masthead. The tools are the sections of the paper: a section the agent or the person added is a word in the
   strip, and a section that has a story about the building in view is set in ink. One line to ask for a change. */

const today = new Date().toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })

export type Menu = false | 'all' | 'tools'

export function Masthead({ story, stories, onMenu }: { story: Panel | null; stories: Panel[]; onMenu: (m: Menu) => void }) {
  const route = useRoute()
  const { filters, selected } = useMapModel()
  const tools = useWorkspace((s) => s.doc.tools), shortlist = useWorkspace((s) => s.doc.shortlist)
  const canUndo = useWorkspace((s) => s.undoStack.length > 0), undo = useWorkspace((s) => s.undo)
  const [text, setText] = useState('')
  // a section that was not here at the last render has just been added: its rule is drawn under it once
  const seen = useRef<Set<string> | null>(null)
  const fresh = seen.current ? tools.filter((t) => !seen.current!.has(t.id)).map((t) => t.id) : []
  useEffect(() => { seen.current = new Set(tools.map((t) => t.id)) }, [tools])
  const city: CityId | null = route.path === '/map' ? filters.city : selected?.metro ?? null
  return (
    <header className="mast">
      <a className="sr" href="#page">Skip to the page</a>
      <div className="mast-top">
        <button className="mast-name" onClick={() => navigate('/')} aria-label="Threshold, front page">Threshold</button>
        <span className="mast-date cap">{today}</span>
        <div className="edition" role="group" aria-label="City edition">
          {(Object.keys(CITIES) as CityId[]).map((id) => <button key={id} aria-pressed={city === id} onClick={() => navigate('/map', { city: id, b: null }, { keep: true })} aria-label={`${CITIES[id].name} edition`}><span className="long">{CITIES[id].name}</span><span className="short" aria-hidden="true">{id === 'hou' ? 'Houston' : 'L.A.'}</span></button>)}
        </div>
        <button className="mast-do" onClick={() => onMenu('all')} aria-label="Open the index: places, sections and commands"><span>Index</span><kbd>Ctrl K</kbd></button>
      </div>
      <div className="mast-strip">
        <nav className="sections" aria-label="Sections">
          <div className="scroller">
          {tools.length === 0 && <span className="section">No sections yet</span>}
          {tools.map((t) => {
            const has = stories.find((p) => p.tool === t.id)
            return (
              <Popover.Root key={t.id}>
                <Popover.Trigger className={fresh.includes(t.id) ? 'section new' : 'section'} data-story={has ? '' : undefined} aria-current={story?.tool === t.id || undefined} aria-label={`${t.title}. Why this section is here.`}>{t.title}</Popover.Trigger>
                <Popover.Portal><Popover.Positioner side="bottom" align="start" sideOffset={10}><Popover.Popup className="slip">
                  <span className="cap">Why this section is here</span>
                  <Popover.Title render={<h3 />}>{t.title}</Popover.Title>
                  <p>{t.reason || 'You added it.'}</p>
                  {t.summary && <p>{t.summary}</p>}
                  <dl><dt>Works on</dt><dd>{t.coverage ?? 'Not stated'}</dd><dt>Added by</dt><dd>{t.by === 'agent' ? 'The agent, from your brief' : 'You'}</dd></dl>
                  <div className="row">
                    {has && has.id !== story?.id && <Popover.Close className="btn" onClick={() => (has.sid && has.sid !== route.sid ? navigate(`/scan/${has.sid}`, { b_s: has.id }, { keep: true }) : readStory(has.id))}>Read it</Popover.Close>}
                    {route.sid && <Popover.Close className={has ? 'btn line' : 'btn'} onClick={() => runToolHere(t.id, route.sid!)}>{has ? 'Run again here' : 'Run on this scan'}</Popover.Close>}
                    <Popover.Close className="link" onClick={() => userOp({ op: 'tool.disable', id: t.id })}>Remove</Popover.Close>
                  </div>
                </Popover.Popup></Popover.Positioner></Popover.Portal>
              </Popover.Root>
            )
          })}
          </div>
          <button className="section add" onClick={() => onMenu('tools')}>+ Add<span className="long"> a section</span></button>
        </nav>
        <form className="askline" onSubmit={(e) => { e.preventDefault(); if (text.trim()) { void ask(text.trim()); setText('') } }}>
          <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Ask for a change" aria-label="Ask the agent for a change" autoComplete="off" />
          {canUndo && <button type="button" className="section" style={{ color: 'var(--ink)' }} onClick={undo} title="Undo your last change (Ctrl Z)">Undo</button>}
          <Popover.Root>
            <Popover.Trigger className="section" style={{ color: 'var(--ink)' }} aria-label={`Kept, ${shortlist.length}`}>Kept {shortlist.length}</Popover.Trigger>
            <Popover.Portal><Popover.Positioner side="bottom" align="end" sideOffset={10}><Popover.Popup className="slip">
              <Popover.Title render={<h3 />}>Kept</Popover.Title>
              {shortlist.length === 0 && <p>Nothing kept yet. Use Keep beside a scan to put it here.</p>}
              <ul className="keptlist">
                {shortlist.map((s) => (
                  <li key={s.sid}>
                    <Popover.Close render={<button />} onClick={() => navigate(`/scan/${s.sid}`, {}, { keep: true })}><b>{s.name}</b><span>{s.address.split(',')[0]}</span></Popover.Close>
                    <button className="link" aria-label={`Remove ${s.name} from the kept list`} onClick={() => userOp({ op: 'shortlist.remove', sid: s.sid })}>Remove</button>
                  </li>
                ))}
              </ul>
            </Popover.Popup></Popover.Positioner></Popover.Portal>
          </Popover.Root>
        </form>
      </div>
    </header>
  )
}

/** The index (Ctrl K): add or remove a section, go to a place, undo, start over. It opens without animation: it is
    used too often for one. */
export function Index({ open, onClose, all }: { open: Menu; onClose: () => void; all: Building[] }) {
  const [q, setQ] = useState('')
  const tools = useWorkspace((s) => s.doc.tools), undo = useWorkspace((s) => s.undo)
  const catalog = useToolCatalog()
  useEffect(() => { if (open) setQ('') }, [open])
  const hits = useMemo(() => (q.length >= 3 ? search(all, q, 6) : []), [all, q])
  const run = (fn: () => void) => () => { fn(); onClose() }
  return (
    <Command.Dialog open={!!open} onOpenChange={(o) => !o && onClose()} label="Index" shouldFilter>
      <Command.Input value={q} onValueChange={setQ} placeholder={open === 'tools' ? 'Add a section' : 'Go to a place, add a section, undo'} />
      <Command.List>
        <Command.Empty>Nothing matches “{q}”.</Command.Empty>
        <Command.Group heading="Sections">
          {catalog.map((t) => {
            const on = tools.some((x) => x.id === t.id)
            return (
              <Command.Item key={t.id} value={`section ${t.title} ${t.summary}`} onSelect={run(() => userOp(on ? { op: 'tool.disable', id: t.id } : { op: 'tool.enable', tool: { id: t.id, title: t.title, code: t.code, summary: t.summary, coverage: t.coverage, reason: 'You added it from the index.' } }))}>
                <span className="grow">{t.title}{t.summary && <small>{t.summary}</small>}</span><span className="cap">{t.planned ? 'Planned · ' : ''}{on ? 'Remove' : 'Add'}</span>
              </Command.Item>
            )
          })}
        </Command.Group>
        {open !== 'tools' && (
          <>
            {hits.length > 0 && (
              <Command.Group heading="Buildings">
                {hits.map((b) => <Command.Item key={b.id} value={`${b.address} ${b.scans.map((s) => s.name).join(' ')}`} onSelect={run(() => navigate('/map', { city: b.metro ?? undefined, b: b.id }))}><span className="grow">{b.address}</span><span className="cap">{b.count} {b.count === 1 ? 'scan' : 'scans'}</span></Command.Item>)}
              </Command.Group>
            )}
            <Command.Group heading="Go to">
              <Command.Item onSelect={run(() => navigate('/'))}>Front page</Command.Item>
              {(Object.keys(CITIES) as CityId[]).map((c) => <Command.Item key={c} onSelect={run(() => navigate('/map', { city: c }))}>{CITIES[c].name} edition</Command.Item>)}
            </Command.Group>
            <Command.Group heading="Workspace">
              <Command.Item onSelect={run(undo)}>Undo my last change</Command.Item>
              <Command.Item onSelect={run(() => { startOver(); navigate('/') })}>Start over with a new brief</Command.Item>
            </Command.Group>
          </>
        )}
      </Command.List>
    </Command.Dialog>
  )
}
