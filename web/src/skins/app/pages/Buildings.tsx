import { useBuildings, useWorkspace, userOp, type ShortlistItem, type Status } from '../../../core/index.ts'
import { DataTable, Empty, Icon, IconBtn, St, type Col } from '../design/ui.tsx'
import { int } from '../lib/format.ts'
import { go, goScan } from '../lib/place.ts'

const WORST: Record<Status, number> = { fail: 0, warn: 1, unknown: 2, pass: 3 }

/** The kept scans, with what has been found on each. */
export function Buildings() {
  const doc = useWorkspace((s) => s.doc)
  const all = useBuildings((s) => s.all)
  const of = (sid: string) => {
    const panels = doc.panels.filter((p) => p.sid === sid)
    const verdicts = panels.flatMap((p) => p.blocks.filter((b) => b.type === 'VerdictHeader')).map((b) => (b.type === 'VerdictHeader' ? b.status : 'unknown'))
    return { panels: panels.length, findings: doc.findings.filter((f) => f.anchor && 'sid' in f.anchor && f.anchor.sid === sid).length, worst: verdicts.sort((a, b) => WORST[a] - WORST[b])[0] as Status | undefined, b: all.find((x) => x.scans.some((y) => y.sid === sid)) }
  }
  const cols: Col<ShortlistItem>[] = [
    { id: 'name', label: 'Scan', fixed: true, sort: (s) => s.name, cell: (s) => <><span className="strong">{s.name}</span><span className="sub">{s.address.split(',')[0] || 'Address not recorded'}</span></> },
    { id: 'city', label: 'City', width: 130, sort: (s) => of(s.sid).b?.city ?? '', cell: (s) => <span className="dim">{of(s.sid).b?.city ?? '–'}</span> },
    { id: 'worst', label: 'Worst result', width: 140, sort: (s) => WORST[of(s.sid).worst ?? 'pass'], cell: (s) => { const w = of(s.sid).worst; return w ? <St status={w} /> : <span className="muted">no results</span> } },
    { id: 'results', label: 'Results', num: true, width: 80, sort: (s) => of(s.sid).panels, cell: (s) => int(of(s.sid).panels) },
    { id: 'findings', label: 'Findings', num: true, width: 84, sort: (s) => of(s.sid).findings, cell: (s) => int(of(s.sid).findings) },
    { id: 'note', label: 'Note', width: '24%', cell: (s) => <span className="dim" title={s.note}>{s.note ?? ''}</span> },
    { id: 'x', label: '', width: 56, fixed: true, cell: (s) => <IconBtn icon="close" label={`Stop keeping ${s.name}`} className="btn icon quiet sm" size={13} onClick={(e) => { e.stopPropagation(); userOp({ op: 'shortlist.remove', sid: s.sid }) }} /> },
  ]
  return (
    <div className="listpage">
      <div className="bar"><p className="grow dim">Scans kept in the open investigation, by you or by the agent. Removing one can be undone with Ctrl Z.</p><button className="btn" onClick={() => go('explore')}><Icon name="map" size={14} />Find more on the map</button></div>
      <DataTable label="Saved buildings" noun="scan" cols={cols} rows={doc.shortlist} rowKey={(s) => s.sid} onRow={(s) => goScan(s.sid)}
        empty={<Empty icon="keep" title="Nothing kept yet" action={<button className="btn solid" onClick={() => go('explore')}>Explore the map</button>}>Open a scan and press Keep (or K). The agent also keeps the scans it shortlists.</Empty>} />
    </div>
  )
}
