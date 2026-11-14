import { useEffect, useMemo, useState } from 'react'
import { Dialog } from '@base-ui/react/dialog'
import { currentRoute, fetchCaptures, fetchPlan, runTool, runToolHere, search, useBuildings, useWorkspace, type Capture, type ScanPlan } from '../../../core/index.ts'
import { Icon, ToolKey } from '../design/ui.tsx'
import { clock } from '../lib/format.ts'
import { goScan } from '../lib/place.ts'
import { encode, problem } from '../lib/start.ts'
import { family, useTools, type Field, type ToolInfo } from '../lib/tools.ts'
import { useUi } from './store.ts'

/** Start a tool by hand. One that needs nothing but the scan in view runs at once (it asks in the agent panel if it
    must); any other opens the form, with the scan in view filled in. */
export function startTool(t: Pick<ToolInfo, 'id' | 'form'>, sid?: string | null, form = t.form) {
  if (sid && !form) runToolHere(t.id, sid)
  else useUi.setState({ start: { tool: t.id, sid: sid ?? null } })
}

type Values = Record<string, string | boolean>
const CAPTURE_KIND: Record<string, Capture['kind']> = { photo_measure: 'photo', walkthrough: 'video' }

function ScanPick({ sid, onPick, optional }: { sid: string | null; onPick: (sid: string | null) => void; optional: boolean }) {
  const all = useBuildings((s) => s.all), doc = useWorkspace((s) => s.doc)
  const [q, setQ] = useState('')
  const row = (id: string) => { for (const b of all) { const s = b.scans.find((x) => x.sid === id); if (s) return { sid: id, name: s.name, address: b.address.split(',')[0] } } return { sid: id, name: id, address: '' } }
  const list = useMemo(() => {
    if (q.trim().length >= 3) return search(all, q, 5).flatMap((b) => b.scans.slice(0, 3).map((s) => ({ sid: s.sid, name: s.name, address: b.address.split(',')[0] })))
    return [...new Set([...doc.shortlist.map((s) => s.sid), ...doc.runs.map((r) => r.sid).filter((x): x is string => !!x).reverse()])].slice(0, 5).map(row)
  }, [q, all, doc.shortlist, doc.runs]) // eslint-disable-line react-hooks/exhaustive-deps
  if (sid) {
    const r = row(sid)
    return <div className="fld"><span>Building</span><div className="scanpick"><Icon name="building" /><span className="grow trunc"><b>{r.name}</b>{r.address && r.address !== r.name && <span className="muted"> · {r.address}</span>}</span><button type="button" className="btn sm quiet" onClick={() => onPick(null)}>Change</button></div></div>
  }
  return (
    <div className="fld">
      <span>Building{optional && <small> · optional</small>}</span>
      <label className="inset"><Icon name="search" size={13} /><input className="field" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search by address or scan name" aria-label="Find a building to run on" /></label>
      {list.length > 0 ? <ul className="rows">{list.map((r) => <li key={r.sid}><button type="button" onClick={() => onPick(r.sid)}><Icon name="building" /><span className="grow"><span className="trunc">{r.name}</span>{r.address && r.address !== r.name && <span className="s">{r.address}</span>}</span></button></li>)}</ul>
        : <small>{q.trim().length >= 3 ? 'No address or scan name matches.' : 'Type three letters of an address. Scans this investigation has kept or measured are offered here.'}</small>}
    </div>
  )
}

function Control({ f, v, set, bad, plan, captures, toolId }: { f: Field; v: string | boolean | undefined; set: (v: string | boolean) => void; bad: string | null; plan: ScanPlan | null; captures: Capture[] | null; toolId: string }) {
  const id = `st-${f.id}`, s = typeof v === 'boolean' ? '' : v ?? ''
  const hint = bad ? <small role="alert" style={{ color: 'var(--fail)' }}>{bad}</small> : f.about && f.kind !== 'long' ? <small>{f.about}</small> : null
  if (f.kind === 'toggle') return <label className="fld check"><input type="checkbox" checked={v === true} onChange={(e) => set(e.target.checked)} /><span>{f.label}{f.about && <small>{f.about}</small>}</span></label>
  let control
  if (f.kind === 'choice') control = <select id={id} className="field" value={s} onChange={(e) => set(e.target.value)} aria-invalid={!!bad || undefined}>{!f.required && f.fallback == null && <option value="">Any</option>}{f.options!.map((o) => <option key={o} value={o}>{o.replace(/_/g, ' ')}</option>)}</select>
  else if (f.kind === 'room') control = <select id={id} className="field" value={s} onChange={(e) => set(e.target.value)} disabled={!plan} aria-invalid={!!bad || undefined}><option value="">{!plan ? 'Pick a building first' : f.required ? 'Choose a room' : 'Left to the tool'}</option>{plan?.rooms.map((r, i) => <option key={r.id} value={r.id}>{r.label ?? 'Room'} {i + 1}</option>)}</select>
  else if (f.kind === 'capture') {
    const kind = CAPTURE_KIND[toolId], list = (captures ?? []).filter((c) => c.file && (!kind || c.kind === kind))
    control = list.length ? <select id={id} className="field" value={s} onChange={(e) => set(e.target.value)} aria-invalid={!!bad || undefined}><option value="">{f.required ? `Choose a ${kind ?? 'capture'}` : 'None'}</option>{list.map((c) => <option key={c.id} value={c.id}>{c.kind}, {clock(c.at * 1000)}{c.note ? `, ${c.note.slice(0, 40)}` : ''}</option>)}</select>
      : <p className="note"><Icon name="camera" size={13} /><span>{captures == null ? 'Looking for what the phone has sent.' : `No ${kind ?? 'capture'} from a phone in this investigation yet. `}{captures != null && <button type="button" className="link" onClick={() => window.dispatchEvent(new Event('threshold:phone'))}>Pair a phone</button>}{captures != null && ' and take one on site; it is offered here when it arrives.'}</span></p>
  }
  else if (f.kind === 'long' || f.kind === 'criteria') control = <textarea id={id} className="field mono" rows={f.kind === 'criteria' ? 3 : 5} value={s} onChange={(e) => set(e.target.value)} spellCheck={false} aria-invalid={!!bad || undefined} />
  else control = (
    <span className="row">
      <input id={id} className="field" value={s} onChange={(e) => set(e.target.value)} inputMode={f.kind === 'number' || f.kind === 'reading' ? 'decimal' : undefined} aria-invalid={!!bad || undefined}
        placeholder={f.kind === 'point' ? '29.7604, -95.3698' : f.fallback != null ? String(f.fallback) : undefined} style={f.kind === 'number' || f.kind === 'reading' ? { width: 120 } : undefined} />
      {(f.unit || f.kind === 'reading') && <span className="muted">{f.unit ?? 'dBA'}</span>}
    </span>
  )
  return <div className="fld"><label htmlFor={id}>{f.kind === 'reading' ? 'Sound level' : f.kind === 'point' ? 'Latitude, longitude' : f.label}{f.required && <small> · needed</small>}</label>{control}{hint}{f.kind === 'long' && f.about && <details className="about"><summary>What it can read</summary><pre>{f.about}</pre></details>}</div>
}

function Form({ t, from, close }: { t: ToolInfo; from: string | null; close: () => void }) {
  const [sid, setSid] = useState(from)
  const [vals, setVals] = useState<Values>(() => Object.fromEntries(t.fields.map((f) => [f.id, f.kind === 'toggle' ? f.fallback === true : String(f.start ?? f.fallback ?? (f.kind === 'choice' && f.required ? f.options![0] : ''))])))
  const [tried, setTried] = useState(false)
  const [plan, setPlan] = useState<ScanPlan | null>(null)
  const [captures, setCaptures] = useState<Capture[] | null>(null)
  const ws = useWorkspace((s) => s.doc.id)
  const wantsRoom = t.fields.some((f) => f.kind === 'room'), wantsCapture = t.fields.some((f) => f.kind === 'capture')
  useEffect(() => { setPlan(null); if (sid && wantsRoom) { let on = true; fetchPlan(sid).then((p) => on && setPlan(p), () => {}); return () => { on = false } } }, [sid, wantsRoom])
  useEffect(() => { if (wantsCapture) fetchCaptures(ws).then(setCaptures, () => setCaptures([])) }, [ws, wantsCapture])
  const bad = (f: Field) => problem(f, vals[f.id])
  const noScan = t.needsScan && !sid
  const ok = !noScan && t.fields.every((f) => !bad(f))
  const first = t.fields.filter((f) => f.first), more = t.fields.filter((f) => !f.first)
  const aside = t.onScan && t.family === 'database' // a search across the city: a building only narrows it, so it sits with the other settings
  const control = (f: Field) => <Control key={f.id} f={f} v={vals[f.id]} set={(v) => setVals((x) => ({ ...x, [f.id]: v }))} bad={tried ? bad(f) : null} plan={plan} captures={captures} toolId={t.id} />

  async function run() {
    setTried(true)
    if (!ok) return
    const inputs: Record<string, unknown> = {}
    for (const f of t.fields) { const v = encode(f, vals[f.id]); if (v !== undefined) inputs[f.id] = v }
    const before = new Set(useWorkspace.getState().doc.runs.map((r) => r.id))
    close()
    // a result on a building shows on that building; one with no building shows in the agent panel, then opens
    if (sid && t.onScan) { if (currentRoute().sid !== sid) goScan(sid) } else useUi.getState().setRun(true)
    await runTool(t.id, inputs, t.onScan ? sid : null)
    if (sid && t.onScan) return
    const made = useWorkspace.getState().doc.panels.findLast((p) => p.tool === t.id && !!p.run && !before.has(p.run))
    if (made) useUi.setState({ panel: made.id })
  }
  return (
    <form className="startform" onSubmit={(e) => { e.preventDefault(); void run() }}>
      <header>
        <ToolKey id={t.id} title={t.title} />
        <Dialog.Title render={<h2 className="trunc" />}>Run {t.title}<span className="muted"> · {family(t.id).label}</span></Dialog.Title>
        <Dialog.Close render={<button type="button" className="btn icon quiet" aria-label="Close" />}><Icon name="close" /></Dialog.Close>
      </header>
      <div className="body stack">
        <p className="dim">{t.summary}</p>
        {t.onScan && !aside && <ScanPick sid={sid} onPick={setSid} optional={!t.needsScan} />}
        {tried && noScan && <small role="alert" style={{ color: 'var(--fail)' }}>Pick a building to run it on.</small>}
        {first.map(control)}
        {(more.length > 0 || aside) && <details className="more"><summary><Icon name="right" size={11} />More settings<span className="count">{more.length + (aside ? 1 : 0)}</span></summary><div className="stack">{aside && <ScanPick sid={sid} onPick={setSid} optional />}{more.map(control)}</div></details>}
      </div>
      <footer>
        <span className="grow muted small">{t.slow ? 'Slow: seconds to minutes. It keeps running if you leave.' : 'Fast: a second or two.'}</span>
        <Dialog.Close render={<button type="button" className="btn quiet" />}>Cancel</Dialog.Close>
        <button className="btn solid"><Icon name="play" size={12} />Run</button>
      </footer>
    </form>
  )
}

/** The form that starts any tool by hand: a building when it needs one, what it must be told, the rest folded. */
export function StartTool() {
  const start = useUi((s) => s.start)
  const t = useTools().find((x) => x.id === start?.tool)
  const close = () => useUi.setState({ start: null })
  return (
    <Dialog.Root open={!!start && !!t} onOpenChange={(o) => !o && close()}>
      <Dialog.Portal>
        <Dialog.Backdrop className="backdrop" />
        {/* the first thing to fill in takes the focus, not the close button */}
        <Dialog.Popup className="dialog" initialFocus={() => document.querySelector<HTMLElement>('.startform .body :is(input, select, textarea)')}>{t && start && <Form key={`${t.id}:${start.sid ?? ''}`} t={t} from={start.sid} close={close} />}</Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
