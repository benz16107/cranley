import { useRef, useState, type ReactNode } from 'react'
import { ICONS } from '../skins/app/design/icons.ts'
import { StatusGlyph } from '../skins/sheet/design/ui.tsx'
import { captureFile, captureFrame, usePhone, type Check, type Finding, type Outcome, type Points, type Result, type Room, type Status, type Task } from './api.ts'
import type { Sense } from './sensors.ts'

/* Shared pieces of the phone app. Colours, type and status glyphs are the Sheet look's; the structure is an iPhone
   app's (grouped lists, a large title, one action bar in reach of the thumb). */

/** An icon from the App look's set (Phosphor), so the phone and the desktop draw the same marks. */
export function Ico({ name, size = 22 }: { name: keyof typeof ICONS; size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 256 256" fill="currentColor" aria-hidden="true"><path d={ICONS[name]} /></svg>
}
const Chevron = () => <svg className="m-chev" width="8" height="14" viewBox="0 0 8 14" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m1 1 6 6-6 6" /></svg>
/** A short buzz where the phone can give one (Android). iPhone Safari has no vibration: the card and the toast carry it there. */
export function buzz(kind: 'ok' | 'error' = 'ok') { try { navigator.vibrate?.(kind === 'ok' ? 12 : [30, 50, 30]) } catch { /* not allowed before a tap */ } }

export const TOOL_TITLE: Record<string, string> = { field_check: 'Field check', photo_measure: 'Photo measure', slope_check: 'Slope check', noise_level: 'Noise level', where_am_i: 'Where am I',
  window_check: 'Window check', floor_height: 'Floor height', walkthrough: 'Walk-through', door_widths: 'Door widths', step_free_route: 'Step-free route', bathroom_clearance: 'Bathroom clearance',
  life_safety_census: 'Smoke alarm census', flood_rehearsal: 'Flood rehearsal', daylight: 'Daylight', roof_facts: 'Roof facts', truck_access: 'Truck access', parking_count: 'Parking count', risk_sheet: 'Risk sheet' }
export const toolTitle = (id: string) => TOOL_TITLE[id] ?? id.replaceAll('_', ' ')
const SAID = { confirmed: 'Confirms the scan', contradicted: 'Contradicts the scan', measured: 'First measurement' } as const

/** A tool's own number in the tool's own unit: results are not converted, because a metre there may be a door or a GPS fix. */
export function val(v: number | null | undefined, unit: string): string {
  if (v == null) return 'not measured'
  const text = Number.isInteger(v) ? String(v) : Math.abs(v) >= 100 ? v.toFixed(0) : Math.abs(v) >= 10 ? v.toFixed(1) : v.toFixed(2)
  return unit ? `${text} ${unit}` : text
}
/** A task's length (a door, a step, a floor height) in the person's unit; anything else as it is. */
export function num(v: number | null | undefined, unit: string): string {
  if (v == null) return 'not measured'
  if (unit === 'm') { // a length: in the person's unit
    if (usePhone.getState().unit === 'in') { const i = v / 0.0254; return `${i.toFixed(i < 2 ? 2 : 1)} in` }
    return v < 3 ? `${(v * 100).toFixed(1)} cm` : `${v.toFixed(2)} m`
  }
  return val(v, unit)
}

/** A capture screen: back at the top, a large title, content, then the one action in reach of the thumb. */
export function Page({ title, sub, onBack, children, actions }: { title: string; sub?: string | null; onBack: () => void; children: ReactNode; actions?: ReactNode }) {
  return (
    <div className="m-page">
      <header className="m-top">
        <button className="m-back" onClick={onBack} aria-label="Back">
          <svg width="11" height="19" viewBox="0 0 11 19" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M9.5 1.5 1.5 9.5l8 8" /></svg><span aria-hidden="true">Back</span>
        </button>
      </header>
      <main className="m-body">
        <div className="m-title"><h1>{title}</h1>{sub && <p>{sub}</p>}</div>
        {children}
      </main>
      {actions && <footer className="m-actions">{actions}</footer>}
    </div>
  )
}

/** A titled group of rows or controls, as an iPhone settings list groups them. */
export function Group({ title, count, foot, pad, children }: { title?: ReactNode; count?: number; foot?: ReactNode; pad?: boolean; children: ReactNode }) {
  return (
    <section className="m-group">
      {title && <h2 className="m-group-h">{title}{count != null && <> · <span className="num">{count}</span></>}</h2>}
      <div className="m-list" data-pad={pad || undefined}>{children}</div>
      {foot && <p className="m-hint">{foot}</p>}
    </section>
  )
}

export function Seg<T extends string>({ label, options, value, onChange }: { label: string; options: readonly (readonly [T, string])[]; value: T; onChange: (v: T) => void }) {
  return (
    <div className="m-seg" role="radiogroup" aria-label={label}>
      {options.map(([id, text]) => <button key={id} role="radio" aria-checked={value === id} onClick={() => onChange(id)}>{text}</button>)}
    </div>
  )
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return <label className="m-field"><span className="label">{label}</span>{children}{hint && <span className="m-hint">{hint}</span>}</label>
}

export function RoomPick({ rooms, value, onChange }: { rooms: Room[]; value: string | null; onChange: (id: string | null) => void }) {
  const seen = new Map<string, number>()
  return (
    <Field label="Room">
      <select className="m-input" value={value ?? ''} onChange={(e) => onChange(e.target.value || null)}>
        <option value="">Not in a room</option>
        {rooms.map((r) => { const n = (seen.get(r.label) ?? 0) + 1; seen.set(r.label, n); const many = rooms.filter((x) => x.label === r.label).length > 1; return <option key={r.id} value={r.id}>{many ? `${r.label} ${n}` : r.label}</option> })}
      </select>
    </Field>
  )
}

/** The camera, through the system's own picker: the most reliable way to a full photo or video on both platforms. */
export function Camera({ label, video, onFile, quiet }: { label: string; video?: boolean; onFile: (f: File) => void; quiet?: boolean }) {
  const ref = useRef<HTMLInputElement>(null)
  return ( // no `capture`: the phone then offers camera or library, so a photo taken earlier works too (and in a simulator)
    <>
      <input ref={ref} className="sr" type="file" accept={video ? 'video/*' : 'image/*'} tabIndex={-1} aria-hidden="true"
        onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ''; if (f) onFile(f) }} />
      <button className={`btn m-btn${quiet ? '' : ' solid'}`} onClick={() => ref.current?.click()}>{label}</button>
    </>
  )
}

/** What to do about a sensor that is off, refused or absent. Renders nothing when it is on. */
export function SensorGate({ state, allow, name, fallback }: { state: Sense; allow: () => void; name: string; fallback: string }) {
  if (state === 'on' || state === 'unknown') return state === 'unknown' ? <p className="m-note skeleton" aria-busy="true">Waiting for the {name}</p> : null
  if (state === 'need-permission') return <div className="m-note"><p>This needs the phone's {name}.</p><button className="btn m-btn solid" onClick={allow}>Turn on motion sensors</button></div>
  return <div className="m-note warn"><p>{state === 'denied' ? `The ${name} is off for this page. On an iPhone, close this tab and open the link again to be asked.` : `This device has no ${name} a page can read.`} {fallback}</p></div>
}

export function Progress({ value, label }: { value: number | null; label: string }) {
  return <div className="m-progress" role="progressbar" aria-label={label} aria-valuenow={value == null ? undefined : Math.round(value * 100)} aria-valuemin={0} aria-valuemax={100}><span>{label}</span><i><b style={{ scale: `${value ?? 1} 1` }} /></i></div>
}

export function Row({ status, title, sub, right, onClick, done }: { status?: Status; title: string; sub?: ReactNode; right?: ReactNode; onClick?: () => void; done?: boolean }) {
  const body = <>{status && <span className="m-row-glyph"><StatusGlyph status={status} size={11} /></span>}<span className="m-row-text"><b>{title}</b>{sub && <span>{sub}</span>}</span>{right && <span className="m-row-right num">{right}</span>}{onClick && <Chevron />}</>
  return onClick ? <button className="m-row" data-done={done || undefined} onClick={onClick}>{body}</button> : <div className="m-row" data-done={done || undefined}>{body}</div>
}

/** What a task's capture settled. */
export function OutcomeCard({ outcome, task }: { outcome: Outcome; task: Pick<Task, 'unit' | 'scan_value' | 'threshold' | 'kind'> }) {
  return (
    <section className="m-card" data-status={outcome.status} aria-live="polite">
      <header><StatusGlyph status={outcome.status} size={11} /><b>{SAID[outcome.verdict]}</b><span className="src">{outcome.method === 'manual' ? (task.kind === 'floor_height' ? 'Counted' : task.kind === 'alarm' ? 'Your word' : task.kind === 'heading' ? 'Picked by hand' : 'Tape') : outcome.method === 'vision' ? 'Photo' : 'Sensor'} · {outcome.confidence}</span></header>
      <dl className="m-kv">
        {outcome.value != null && <><dt>On site</dt><dd className="num">{num(outcome.value, task.unit)}{outcome.err ? ` ± ${num(outcome.err, task.unit)}` : ''}</dd></>}
        {task.scan_value != null && task.kind !== 'floor_height' && <><dt>Scan</dt><dd className="num">{num(task.scan_value, task.unit)}</dd></>}
        {task.threshold != null && (task.kind === 'width' || task.kind === 'step') && <><dt>Limit</dt><dd className="num">{num(task.threshold, task.unit)}</dd></>}
      </dl>
      <p>{outcome.text}</p>
    </section>
  )
}

export function Problem({ text }: { text: string }) { return <p className="m-note warn" role="alert">{text}</p> }

function CheckRow({ c }: { c: Check }) {
  const claim = c.kind === 'claim'
  return <li><StatusGlyph status={c.status} size={9} /><span>{c.rule}</span><span className="num">{val(c.measured, c.unit)}{c.threshold != null && <i> {claim ? 'was' : 'of'} {val(c.threshold, c.unit)}</i>}</span></li>
}
function Evidence({ f }: { f: Finding }) {
  // a reading has no picture: only captures known to be photos or clips are asked for
  const caps = usePhone.getState().view?.captures ?? []
  const shots = f.media.filter((m) => m.kind === 'phone' && ['photo', 'video'].includes(caps.find((c) => c.id === m.ref.split('#')[0])?.kind ?? 'photo')).slice(0, 3)
  return (
    <li>
      <StatusGlyph status={f.status} size={9} />
      <div><b>{f.title}</b><p>{f.detail}</p>
        {shots.length > 0 && <div className="m-shots">{shots.map((m) => <img key={m.ref} src={m.ref.includes('#') ? captureFrame(m.ref) : captureFile(m.ref)} alt="" loading="lazy" width={96} height={72} onError={(e) => { e.currentTarget.style.display = 'none' }} />)}</div>}
        <span className="src">{f.source.layer} · {f.source.method} · {f.source.confidence}</span>
      </div>
    </li>
  )
}
/** One tool run, compact: the verdict, the numbers, the checks against their limits, the evidence. */
export function ResultCard({ r, open, actions }: { r: Result; open?: boolean; actions?: ReactNode }) {
  const [more, setMore] = useState(!!open)
  if (r.status === 'running') return <section className="m-card"><header><b>{toolTitle(r.tool)}</b><span className="m-running">running</span></header><p className="skeleton m-step">{r.step ?? 'Starting'}</p></section>
  if (!r.verdict) return <section className="m-card" data-status="unknown"><header><StatusGlyph status="unknown" size={11} /><b>{toolTitle(r.tool)}</b></header><p>{r.error ?? 'It did not finish.'}</p></section>
  return (
    <section className="m-card" data-status={r.verdict.status}>
      <header><StatusGlyph status={r.verdict.status} size={11} /><b>{toolTitle(r.tool)}</b>{r.at && <time className="num">{new Date(r.at * 1000).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}</time>}</header>
      <p>{r.verdict.text}</p>
      {r.metrics.length > 0 && <dl className="m-kv">{r.metrics.map((m) => <div key={m.id}><dt>{m.label}</dt><dd className="num">{val(m.value, m.unit)}</dd></div>)}</dl>}
      {(r.checks.length > 0 || r.findings.length > 0) && <button className="link" aria-expanded={more} onClick={() => setMore(!more)}>{more ? 'Hide the detail' : [r.checks.length && `${r.checks.length} check${r.checks.length > 1 ? 's' : ''}`, r.findings.length && `${r.findings.length} finding${r.findings.length > 1 ? 's' : ''}`].filter(Boolean).join(', ')}</button>}
      {more && r.checks.length > 0 && <ul className="m-checks">{r.checks.map((c) => <CheckRow key={c.id} c={c} />)}</ul>}
      {more && r.findings.length > 0 && <ul className="m-evidence">{r.findings.map((f) => <Evidence key={f.id} f={f} />)}</ul>}
      {actions}
    </section>
  )
}

/** A photo with the reference's corners and the two measured ends on it. The person drags a point to correct it. */
export function PointsEditor({ src, points, onChange }: { src: string; points: Points; onChange: (p: Points) => void }) {
  const box = useRef<HTMLDivElement>(null)
  const all: [string, [number, number]][] = [...points.corners.map((c, i) => [`Reference corner ${i + 1}`, c] as [string, [number, number]]), ['End A', points.a], ['End B', points.b]]
  const move = (i: number, e: React.PointerEvent) => {
    const r = box.current!.getBoundingClientRect()
    const p: [number, number] = [Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)), Math.min(1, Math.max(0, (e.clientY - r.top) / r.height))]
    onChange(i < 4 ? { ...points, corners: points.corners.map((c, j) => (j === i ? p : c)) } : i === 4 ? { ...points, a: p } : { ...points, b: p })
  }
  const pt = (p: [number, number]) => `${p[0] * 100},${p[1] * 100}`
  return (
    <div className="m-points" ref={box}>
      <img src={src} alt="Your photo with the measured points marked" />
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
        <polygon points={points.corners.map(pt).join(' ')} />
        <line x1={points.a[0] * 100} y1={points.a[1] * 100} x2={points.b[0] * 100} y2={points.b[1] * 100} />
      </svg>
      {all.map(([name, p], i) => (
        <button key={i} className={i < 4 ? 'ref' : 'end'} aria-label={name} style={{ left: `${p[0] * 100}%`, top: `${p[1] * 100}%` }}
          onPointerDown={(e) => e.currentTarget.setPointerCapture(e.pointerId)} onPointerMove={(e) => { if (e.currentTarget.hasPointerCapture(e.pointerId)) move(i, e) }}>{i === 4 ? 'A' : i === 5 ? 'B' : ''}</button>
      ))}
    </div>
  )
}
