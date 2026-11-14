import { useEffect, useMemo, useState } from 'react'
import { Command } from 'cmdk'
import { Popover } from '@base-ui/react/popover'
import { CITIES, navigate, runToolHere, search, startOver, useMapModel, useToolCatalog, useWorkspace, userOp, type CityId, type Panel } from '../../core/index.ts'
import { PanelSheet } from './blocks.tsx'
import { block, type useSheet } from './state.ts'
import { Glyph, Icon } from './ui.tsx'

/* Tools are sheets laid over the model. The stack sits at the far edge of the table: a tab for each tool that is
   out (why it is here, run it on this scan, put it away), then the result sheets for this place, the one on top
   open. The sheet on top is also the lens on the model (Model.tsx). */

const open = (p: Panel) => (p.sid ? navigate(`/scan/${p.sid}`, { c_p: p.id, c_fold: null }, { keep: true }) : navigate('/map', { c_p: p.id, c_fold: null }, { keep: true }))

export function Sheets({ sid, sheet, onAdd }: { sid: string | null; sheet: ReturnType<typeof useSheet>; onAdd: () => void }) {
  const doc = useWorkspace((s) => s.doc)
  const { here, active, pick, folded, fold } = sheet
  const elsewhere = doc.panels.filter((p) => !here.includes(p))
  const drawing = doc.runs.filter((r) => r.status === 'running' && !doc.panels.some((p) => p.run === r.id)).slice(-2)
  const title = (tool: string) => doc.tools.find((t) => t.id === tool)?.title
  return (
    <aside className="mq-sheets" data-folded={folded || undefined} aria-label="Tools and their results">
      <ul className="mq-tools" aria-label="Tools laid out">
        {doc.tools.map((t) => (
          <li key={t.id}>
            <Popover.Root>
              <Popover.Trigger className="mq-tool" data-on={active?.tool === t.id || undefined} aria-label={`${t.title}. Why this is here.`}>{t.title}</Popover.Trigger>
              <Popover.Portal><Popover.Positioner className="mq-popper" side="left" align="start" sideOffset={10}><Popover.Popup className="mq-pop">
                <Popover.Title render={<h3 />}>{t.title}</Popover.Title>
                <span className="mq-caps">Why this is here</span>
                <p>{t.reason || 'You added it.'}</p>
                {t.summary && <p className="mq-dim">{t.summary}</p>}
                <dl><dt>Works on</dt><dd>{t.coverage ?? 'Not stated'}</dd><dt>Laid out by</dt><dd>{t.by === 'agent' ? 'The agent, from your brief' : 'You'}</dd></dl>
                <div className="mq-row">
                  {sid ? <Popover.Close className="mq-btn is-tape is-sm" onClick={() => runToolHere(t.id, sid)}>Run on this scan</Popover.Close> : <span className="mq-dim">Open a building to run it.</span>}
                  <Popover.Close className="mq-btn is-quiet is-sm" onClick={() => userOp({ op: 'tool.disable', id: t.id })}>Put it away</Popover.Close>
                </div>
              </Popover.Popup></Popover.Positioner></Popover.Portal>
            </Popover.Root>
          </li>
        ))}
        <li><button className="mq-tool is-add" onClick={onAdd}><Icon name="plus" size={12} />{doc.tools.length ? 'Lay another tool' : 'Lay a tool on the table'}</button></li>
      </ul>

      {drawing.map((r) => (
        <div key={r.id} className="mq-sheet mq-paper is-drawing" role="status">
          <span className="mq-caps">{title(r.tool) ?? 'Working'}</span>
          <b>{title(r.tool) && r.label.startsWith(title(r.tool)!) ? r.label.slice(title(r.tool)!.length).replace(/^[\s·:,]+/, '') || r.label : r.label}</b>
          <p>{r.summary ?? 'Measuring. The sheet is laid here when it is done.'}</p>
        </div>
      ))}

      {active && (
        <div className="mq-sheet mq-paper">
          <div className="mq-sheet-top">
            {here.length > 1 ? (
              <div className="mq-tabs" role="tablist" aria-label="Sheets for this place">
                {here.map((p, i) => <button key={p.id} role="tab" aria-selected={p.id === active.id} title={p.title} onClick={() => pick(p.id)}><span className="mq-num">{i + 1}</span>{p.id === active.id && <span className="t">{doc.tools.find((t) => t.id === p.tool)?.title ?? p.title}</span>}</button>)}
              </div>
            ) : <span className="mq-caps">{doc.tools.find((t) => t.id === active.tool)?.title ?? 'Result'}</span>}
            <button className="mq-x" aria-expanded={!folded} aria-label={folded ? 'Unfold the sheet' : 'Fold the sheet away'} onClick={() => fold(!folded)}><Icon name="down" size={14} /></button>
          </div>
          {!folded && <div className="mq-sheet-body" key={active.id}><PanelSheet panel={active} /></div>}
        </div>
      )}

      {elsewhere.length > 0 && (
        <Popover.Root>
          <Popover.Trigger className="mq-else"><span className="mq-num">{elsewhere.length}</span> {elsewhere.length === 1 ? 'sheet' : 'sheets'} on other {sid ? 'places' : 'buildings'}</Popover.Trigger>
          <Popover.Portal><Popover.Positioner className="mq-popper" side="left" align="end" sideOffset={10}><Popover.Popup className="mq-pop mq-index">
            <span className="mq-caps">Every sheet</span>
            <ul>
              {elsewhere.map((p) => { const v = block(p, 'VerdictHeader'); return (
                <li key={p.id}><Popover.Close className="open" onClick={() => open(p)}>{v ? <Glyph status={v.status} size={10} /> : <i />}<span><b>{p.title}</b><small>{p.scope ?? (p.sid ? 'One scan' : 'Several places')}</small></span></Popover.Close></li>
              ) })}
            </ul>
          </Popover.Popup></Popover.Positioner></Popover.Portal>
        </Popover.Root>
      )}
    </aside>
  )
}

/** Ctrl K: every tool there is to lay out (planned ones marked), places, and the workspace. It opens and closes
    without motion; it is used too often for any. */
export function Catalog({ mode, onClose }: { mode: false | 'all' | 'tools'; onClose: () => void }) {
  const [q, setQ] = useState('')
  const tools = useWorkspace((s) => s.doc.tools), undo = useWorkspace((s) => s.undo)
  const catalog = useToolCatalog(), { all } = useMapModel()
  useEffect(() => { if (mode) setQ('') }, [mode])
  const hits = useMemo(() => (q.length >= 3 ? search(all, q, 6) : []), [all, q])
  const run = (fn: () => void) => () => { fn(); onClose() }
  return (
    <Command.Dialog open={!!mode} onOpenChange={(o) => !o && onClose()} label="Tools and places" className="mq-cmd">
      <Command.Input value={q} onValueChange={setQ} placeholder={mode === 'tools' ? 'Lay a tool on the table' : 'A tool, an address, a place'} />
      <Command.List>
        <Command.Empty>Nothing matches “{q}”.</Command.Empty>
        <Command.Group heading="Tools">
          {catalog.map((t) => {
            const on = tools.some((x) => x.id === t.id)
            return (
              <Command.Item key={t.id} value={`tool ${t.title} ${t.summary ?? ''}`} onSelect={run(() => userOp(on ? { op: 'tool.disable', id: t.id } : { op: 'tool.enable', tool: { id: t.id, title: t.title, code: t.code, summary: t.summary, coverage: t.coverage, reason: 'You laid it out.' } }))}>
                <span className="grow">{t.title}<small>{t.summary}</small></span>
                <span className="mq-caps">{t.planned ? 'Planned' : on ? 'Put away' : 'Lay out'}</span>
              </Command.Item>
            )
          })}
        </Command.Group>
        {mode !== 'tools' && (
          <>
            {hits.length > 0 && (
              <Command.Group heading="Buildings">
                {hits.map((b) => <Command.Item key={b.id} value={`${b.address} ${b.scans.map((s) => s.name).join(' ')}`} onSelect={run(() => navigate('/map', { city: b.metro ?? undefined, b: b.id }))}><span className="grow">{b.address}</span><span className="mq-num mq-dim">{b.count} {b.count === 1 ? 'scan' : 'scans'}</span></Command.Item>)}
              </Command.Group>
            )}
            <Command.Group heading="Go to">
              <Command.Item onSelect={run(() => navigate('/'))}>The front door</Command.Item>
              {(Object.keys(CITIES) as CityId[]).map((c) => <Command.Item key={c} onSelect={run(() => navigate('/map', { city: c }))}>The {CITIES[c].name} table</Command.Item>)}
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
