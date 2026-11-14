import { useMemo, useState } from 'react'
import { Dialog } from '@base-ui/react/dialog'
import { useWorkspace, userOp } from '../../../core/index.ts'
import { DataTable, Empty, Icon, Seg, ToolKey, type Col } from '../design/ui.tsx'
import { go } from '../lib/place.ts'
import { FAMILIES, family, useTools, type Family, type ToolInfo } from '../lib/tools.ts'

const DRAWS: Record<string, string> = { lens: 'room tint', rule: 'room and wall marks', pins: 'pins', route: 'route', water: 'water level', box: 'boxes' }

function Detail({ t, on, onClose }: { t: ToolInfo | null; on: boolean; onClose: () => void }) {
  return (
    <Dialog.Root open={!!t} onOpenChange={(o) => !o && onClose()}>
      <Dialog.Portal>
        <Dialog.Backdrop className="backdrop" />
        <Dialog.Popup className="drawer">
          {t && (
            <>
              <header><ToolKey id={t.id} title={t.title} /><Dialog.Title render={<h2 className="trunc" />}><b>{t.title}</b><span className="muted"> · {family(t.id).label}</span></Dialog.Title><Dialog.Close render={<button className="btn icon quiet" aria-label="Close" />}><Icon name="close" /></Dialog.Close></header>
              <div className="body tooldetail">
                <p>{t.summary}</p>
                <div className="row wrap">
                  <button className="btn solid" disabled={t.planned} onClick={() => userOp(on ? { op: 'tool.disable', id: t.id } : { op: 'tool.enable', tool: { id: t.id, title: t.title, summary: t.summary, reason: 'You added it from the tool catalogue.' } })}>{on ? 'Remove from this investigation' : 'Add to this investigation'}</button>
                  {t.onScan && <button className="btn" onClick={() => { onClose(); go('explore') }}>Pick a building to run it on</button>}
                </div>
                {!t.onScan && <p className="note"><Icon name="info" size={13} /><span>This tool works across the city, not on one building, so it cannot be started from a building page. The agent uses it when it is in the investigation.</span></p>}
                {t.planned && <p className="note"><Icon name="info" size={13} /><span>Planned, not built yet.</span></p>}
                <section><h3>Reads</h3>{t.needs.length ? <ul className="needs">{t.needs.map((n) => <li key={n.layer}><span className="grow">{n.label}</span><span className="muted">{n.required ? 'required' : 'used when there'}</span></li>)}</ul> : <p className="muted">Nothing listed.</p>}</section>
                {t.asks.length > 0 && <section><h3>Asks you first</h3><ul className="asks">{t.asks.map((a) => <li key={a}>{a}</li>)}</ul></section>}
                {t.inputs.length > 0 && (
                  <section><h3>Settings</h3>
                    <table className="tbl mini"><tbody>{t.inputs.map((i) => <tr key={i.id}><td className="wrap"><b>{i.label}</b><span className="sub" style={{ whiteSpace: 'normal' }}>{i.about}</span></td><td className="r" style={{ width: 110 }}>{i.fallback != null ? <><span className="num">{i.fallback}</span>{i.unit && <span className="muted"> {i.unit}</span>}</> : <span className="muted">none</span>}</td></tr>)}</tbody></table>
                  </section>
                )}
                <section><h3>Shows</h3><p className="dim">{[t.draws.length ? `On the building: ${t.draws.map((d) => DRAWS[d] ?? d).join(', ')}` : 'Nothing drawn on the building', `${t.blocks.length} kinds of result block`, t.slow ? 'slow: seconds to minutes' : 'fast'].join('. ')}.</p></section>
                {t.examples.length > 0 && <section><h3>Questions it answers</h3><ul className="asks">{t.examples.map((e) => <li key={e}>{e}</li>)}</ul></section>}
              </div>
            </>
          )}
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

/** The catalogue: every tool, what it reads, what it asks, what it shows. */
export function Tools() {
  const tools = useTools()
  const mine = useWorkspace((s) => s.doc.tools)
  const [fam, setFam] = useState<'all' | 'mine' | Family>('all'), [text, setText] = useState(''), [open, setOpen] = useState<string | null>(null)
  const has = (id: string) => mine.some((m) => m.id === id)
  const rows = useMemo(() => tools.filter((t) => (fam === 'all' || (fam === 'mine' ? has(t.id) : t.family === fam)) && (!text.trim() || `${t.title} ${t.summary}`.toLowerCase().includes(text.trim().toLowerCase()))), [tools, fam, text, mine]) // eslint-disable-line react-hooks/exhaustive-deps
  const cols: Col<ToolInfo>[] = [
    { id: 'tool', label: 'Tool', fixed: true, width: '22%', sort: (t) => t.title, cell: (t) => <span className="row"><ToolKey id={t.id} title={t.title} /><span className="strong trunc">{t.title}</span>{t.planned && <span className="chip">Planned</span>}</span> },
    { id: 'family', label: 'Family', width: 156, sort: (t) => t.family, cell: (t) => <span className="dim">{family(t.id).label}</span> },
    { id: 'does', label: 'What it does', cell: (t) => <span className="dim" title={t.summary}>{t.summary}</span> },
    { id: 'needs', label: 'Needs', width: '17%', cell: (t) => <span className="dim" title={t.needs.map((n) => `${n.label}${n.required ? '' : ' (when there)'}`).join(', ')}>{[...new Set(t.needs.filter((n) => n.required).map((n) => n.label))].join(', ') || <span className="muted">nothing required</span>}</span> },
    { id: 'asks', label: 'Asks', num: true, width: 60, sort: (t) => t.asks.length, cell: (t) => (t.asks.length ? t.asks.length : <span className="muted">–</span>) },
    { id: 'speed', label: 'Speed', width: 70, sort: (t) => (t.slow ? 1 : 0), cell: (t) => <span className="dim">{t.slow ? 'Slow' : 'Fast'}</span> },
    { id: 'x', label: '', width: 104, fixed: true, cell: (t) => <button className="btn sm" disabled={t.planned} aria-pressed={has(t.id)} onClick={(e) => { e.stopPropagation(); userOp(has(t.id) ? { op: 'tool.disable', id: t.id } : { op: 'tool.enable', tool: { id: t.id, title: t.title, summary: t.summary, reason: 'You added it from the tool catalogue.' } }) }}>{has(t.id) ? <><Icon name="check" size={12} />Added</> : 'Add'}</button> },
  ]
  const sel = tools.find((t) => t.id === open) ?? null
  return (
    <div className="listpage">
      <div className="bar">
        <label className="inset"><Icon name="search" size={13} /><input className="field" value={text} onChange={(e) => setText(e.target.value)} placeholder="Filter tools" aria-label="Filter tools by name or what they do" /></label>
        <Seg label="Family" value={fam} onChange={setFam} options={[{ id: 'all', label: `All ${tools.length}` }, { id: 'mine', label: `In this investigation ${mine.length}` }, ...FAMILIES.filter((f) => tools.some((t) => t.family === f.id)).map((f) => ({ id: f.id, label: f.label, icon: f.icon }))]} />
      </div>
      <DataTable label="Tools" noun="tool" cols={cols} rows={rows} rowKey={(t) => t.id} onRow={(t) => setOpen(t.id)} loading={!tools.length} sortBy={{ col: 'family', dir: 1 }}
        empty={<Empty icon="tool" title="No tool matches" action={<button className="btn" onClick={() => { setText(''); setFam('all') }}>Clear the filter</button>} />} />
      <Detail t={sel} on={!!sel && has(sel.id)} onClose={() => setOpen(null)} />
    </div>
  )
}
