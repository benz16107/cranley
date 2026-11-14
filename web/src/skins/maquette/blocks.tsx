import { useEffect, useState, type ReactNode } from 'react'
import NumberFlow from '@number-flow/react'
import { Popover } from '@base-ui/react/popover'
import { Slider } from '@base-ui/react/slider'
import { Switch } from '@base-ui/react/switch'
import { fetchPlan, focusAnchor, focusFinding, navigate, runAction, useWorkspace, userOp, type Block, type Doc, type Panel, type ScanPlan, type Status } from '../../core/index.ts'
import { Plan } from './Plan.tsx'
import { STATUS_WORD, findingPhoto, fmt, ms } from './lib.ts'
import { Glyph, Src } from './ui.tsx'

/* The twelve blocks, as they are set on a sheet of paper. Each is built once. Numbers are printed as they arrive in
   the block; nothing is parsed out of text and nothing is recomputed. */

type Of<T extends Block['type']> = Extract<Block, { type: T }>
type Ctx = { doc: Doc; panel: Panel }

const Verdict = ({ b }: { b: Of<'VerdictHeader'> }) => (
  <div className="b-verdict" data-s={b.status} data-long={b.text.length > 150 || undefined}>
    <span className="mq-caps"><Glyph status={b.status} size={12} /> {STATUS_WORD[b.status]}</span>
    <p>{b.text}</p>
  </div>
)

const Metrics = ({ b }: { b: Of<'MetricRow'> }) => (
  <dl className="b-metrics">
    {b.metrics.map((m) => (
      <div key={m.id}>
        <dt className="mq-caps">{m.label}</dt>
        <dd className="mq-num">{m.value == null ? <span className="b-nil">not measured</span> : <><NumberFlow value={m.value} format={{ maximumFractionDigits: 2 }} /><small>{m.unit}</small></>}</dd>
        <Src source={m.source} />
      </div>
    ))}
  </dl>
)

/** A check as a rule laid against the limit: the limit is the tick, the measurement is the mark. */
function Rule({ measured, threshold, status }: { measured: number; threshold: number; status: Status }) {
  const max = Math.max(measured, threshold) * 1.25 || 1
  return <span className="b-rule" aria-hidden="true"><u style={{ left: `${(threshold / max) * 100}%` }} /><i data-s={status} style={{ left: `${(measured / max) * 100}%` }} /></span>
}
function Checks({ b, ctx }: { b: Of<'CheckList'>; ctx: Ctx }) {
  const current = ctx.doc.camera?.finding
  return (
    <ul className="b-checks">
      {b.checks.map((c) => {
        const f = ctx.doc.findings.find((x) => c.findings.includes(x.id) && x.anchor) ?? ctx.doc.findings.find((x) => c.findings.includes(x.id))
        return (
          <li key={c.id}>
            <button aria-current={(!!current && c.findings.includes(current)) || undefined} disabled={!f?.anchor} onClick={() => focusFinding(f)}
              title={f?.anchor ? 'Show this in the building' : 'This check has no place in the building to show'}>
              <Glyph status={c.status} />
              <span className="b-check-rule">{c.rule}{c.standard && <small>{c.standard}</small>}</span>
              <span className="b-check-m mq-num">{c.measured == null ? 'not measured' : `${fmt(c.measured)} ${c.unit}`}{c.threshold != null && <small>limit {fmt(c.threshold, 3)}</small>}</span>
              {c.measured != null && c.threshold != null && <Rule measured={c.measured} threshold={c.threshold} status={c.status} />}
            </button>
          </li>
        )
      })}
    </ul>
  )
}

export function Photo({ src, alt = '' }: { src: string | null; alt?: string }) {
  const [state, set] = useState<'wait' | 'ok' | 'none'>('wait')
  useEffect(() => set('wait'), [src])
  return (
    <span className="mq-photo" data-state={src ? state : 'none'}>
      {src && state !== 'none' && <img src={src} alt={alt} loading="lazy" width={640} height={640} onLoad={() => set('ok')} onError={() => set('none')} />}
    </span>
  )
}
/** Evidence is a row of photo prints. The one being looked at is taped down. */
function Evidence({ b, ctx }: { b: Of<'EvidenceStrip'>; ctx: Ctx }) {
  const items = b.findings.map((id) => ctx.doc.findings.find((f) => f.id === id)).filter((f): f is Doc['findings'][number] => !!f)
  if (!items.length) return null
  return (
    <ul className="b-evidence">
      {items.map((f, i) => (
        <li key={f.id}>
          <button className="mq-printlet" aria-current={ctx.doc.camera?.finding === f.id || undefined} disabled={!f.anchor} onClick={() => focusFinding(f)}>
            <Photo src={findingPhoto(f)} />
            <span className="cap"><Glyph status={f.status} size={9} /><span className="mq-num">{i + 1}</span><span className="t">{f.title}</span></span>
            {!f.anchor && <span className="mq-caps">No place in the building</span>}
          </button>
        </li>
      ))}
    </ul>
  )
}

function Ranked({ b }: { b: Of<'RankedTable'> }) {
  // The rows arrive in rank order (the agent's, or the tool's) and keep it until the person sorts by a column.
  const [sort, setSort] = useState<{ col: string | null; dir: 1 | -1 }>({ col: null, dir: -1 })
  const rows = sort.col == null ? b.rows : [...b.rows].sort((x, y) => ((x.values[sort.col!] ?? -Infinity) - (y.values[sort.col!] ?? -Infinity)) * sort.dir)
  return (
    <div className="b-table">
      <table>
        <thead><tr>
          <th scope="col"><button onClick={() => setSort({ col: null, dir: -1 })} aria-label="Back to the ranked order">{sort.col == null ? 'Ranked' : 'Rank'}</button></th>
          {b.columns.map((c) => (
            <th key={c.id} scope="col" aria-sort={sort.col === c.id ? (sort.dir === 1 ? 'ascending' : 'descending') : 'none'}>
              <button onClick={() => setSort({ col: c.id, dir: sort.col === c.id ? (sort.dir === 1 ? -1 : 1) : c.better === 'lower' ? 1 : -1 })}>
                {c.label}{c.unit && <span className="mq-num"> {c.unit}</span>}{sort.col === c.id && <span aria-hidden="true">{sort.dir === 1 ? ' ↑' : ' ↓'}</span>}
              </button>
            </th>
          ))}
        </tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} data-first={(sort.col == null && r === rows[0]) || undefined}>
              <th scope="row">
                <button disabled={!r.anchor} onClick={() => r.anchor && ('sid' in r.anchor ? navigate(`/scan/${r.anchor.sid}`, {}, { keep: true }) : focusAnchor(r.anchor))}>
                  <span className="mq-num n">{b.rows.indexOf(r) + 1}</span>{r.status && <Glyph status={r.status} size={9} />}<span className="t">{r.label}</span>
                </button>
              </th>
              {b.columns.map((c) => <td key={c.id} className="mq-num">{r.values[c.id] == null ? <Glyph status="unknown" size={9} /> : fmt(r.values[c.id])}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
      <Src source={b.source} />
    </div>
  )
}

function Chart({ b }: { b: Of<'MiniChart'> }) {
  const max = Math.max(...b.bars.map((x) => x.value), b.mark?.value ?? 0) * 1.1 || 1
  return (
    <figure className="b-chart">
      <figcaption><span className="mq-caps">{b.title}</span><Src source={b.source} /></figcaption>
      <div className="bars" role="img" aria-label={`${b.title}: ${b.bars.map((x) => `${x.label} ${fmt(x.value)} ${b.unit}`).join(', ')}`}>
        {b.mark && <span className="limit" style={{ bottom: `${(b.mark.value / max) * 100}%` }}><span className="mq-num">{b.mark.label}</span></span>}
        {b.bars.map((x, i) => <span key={i} className="col" title={`${x.label}: ${fmt(x.value)} ${b.unit}`}><i data-s={x.status} style={{ height: `${(x.value / max) * 100}%` }} /></span>)}
      </div>
      <div className="axis mq-num"><span>{b.bars[0]?.label}</span><span>{b.unit}</span><span>{b.bars.at(-1)?.label}</span></div>
    </figure>
  )
}

function Mini({ b, ctx }: { b: Of<'FloorPlanMini'>; ctx: Ctx }) {
  const [plan, setPlan] = useState<ScanPlan | null>(null)
  const [failed, setFailed] = useState(false)
  useEffect(() => { let on = true; setPlan(null); setFailed(false); fetchPlan(b.sid).then((p) => on && setPlan(p), () => on && setFailed(true)); return () => { on = false } }, [b.sid])
  const overlays = ctx.doc.overlays.filter((o) => o.tool === ctx.panel.tool && (!o.sid || o.sid === b.sid)).map((o) => o.overlay)
  if (failed) return <p className="b-plan b-nil">The plan did not load.</p>
  return (
    <button className="b-plan" data-wait={!plan || undefined} aria-label="Open this scan in the building view" onClick={() => navigate(`/scan/${b.sid}`, {}, { keep: true })}>
      {plan && <Plan plan={plan} overlays={overlays} current={ctx.doc.camera?.anchor} px={340} />}
    </button>
  )
}

function Controls({ b }: { b: Of<'Controls'> }) {
  return (
    <div className="b-controls">
      {b.controls.map((c) => {
        const set = (value: number | boolean | string) => userOp({ op: 'pref.set', key: c.id, label: c.label, value, unit: c.unit, from: 'You moved the control' })
        return (
          <div key={c.id} className="b-control" data-kind={c.kind}>
            <span className="lab">{c.label}</span>
            {c.kind === 'slider' && <SlideTo value={c.value as number} min={c.min} max={c.max} step={c.step} unit={c.unit} label={c.label} onCommit={set} />}
            {c.kind === 'toggle' && <Switch.Root className="mq-switch" checked={c.value as boolean} onCheckedChange={set} aria-label={c.label}><Switch.Thumb className="mq-knob" /></Switch.Root>}
            {c.kind === 'select' && <select className="mq-field" value={c.value as string} onChange={(e) => set(e.target.value)} aria-label={c.label}>{c.options?.map((o) => <option key={o}>{o}</option>)}</select>}
          </div>
        )
      })}
    </div>
  )
}
/** The value follows the thumb while it is dragged and is sent once, on release: the tool runs again then. */
function SlideTo({ value, min, max, step, unit, label, onCommit }: { value: number; min?: number; max?: number; step?: number; unit?: string; label: string; onCommit: (v: number) => void }) {
  const [v, setV] = useState(value)
  useEffect(() => setV(value), [value])
  return (
    <>
      <Slider.Root value={v} min={min} max={max} step={step} onValueChange={(x) => setV(x as number)} onValueCommitted={(x) => onCommit(x as number)} aria-label={label}>
        <Slider.Control className="mq-slider"><Slider.Track className="mq-track"><Slider.Indicator className="mq-range" /><Slider.Thumb className="mq-thumb" /></Slider.Track></Slider.Control>
      </Slider.Root>
      <span className="mq-num val">{fmt(v)} {unit}</span>
    </>
  )
}

function Assumed({ b, ctx }: { b: Of<'AssumptionChips'>; ctx: Ctx }) {
  return (
    <div className="b-assume">
      <span className="mq-caps">Assumed</span>
      {b.assumptions.map((a) => {
        const mine = ctx.doc.prefs.find((p) => p.key === a.id)?.by === 'user'
        const body = <>{a.label} <span className="mq-num">{String(a.value)}{a.unit ? ` ${a.unit}` : ''}</span>{mine && <small>yours</small>}</>
        if (!a.editable || typeof a.value !== 'number') return <span key={a.id} className="mq-chip is-fixed">{body}</span>
        return (
          <Popover.Root key={a.id}>
            <Popover.Trigger className="mq-chip" aria-label={`${a.label}: ${a.value} ${a.unit ?? ''}. Change it.`}>{body}</Popover.Trigger>
            <Popover.Portal><Popover.Positioner sideOffset={6} align="start"><Popover.Popup className="mq-pop"><AssumeEdit a={a as typeof a & { value: number }} /></Popover.Popup></Popover.Positioner></Popover.Portal>
          </Popover.Root>
        )
      })}
    </div>
  )
}
function AssumeEdit({ a }: { a: { id: string; label: string; value: number; unit?: string; min?: number; max?: number } }) {
  const [v, setV] = useState(String(a.value))
  const n = Number(v), ok = v.trim() !== '' && Number.isFinite(n) && (a.min == null || n >= a.min) && (a.max == null || n <= a.max)
  return (
    <form onSubmit={(e) => { e.preventDefault(); if (ok && n !== a.value) userOp({ op: 'pref.set', key: a.id, label: a.label, value: n, unit: a.unit, from: `You changed it from ${a.value} ${a.unit ?? ''}`.trim() }) }}>
      <label><span className="mq-caps">{a.label}</span>
        <span className="mq-row" style={{ marginTop: 6 }}><input className="mq-field mq-num" style={{ width: 120 }} inputMode="decimal" value={v} onChange={(e) => setV(e.target.value)} aria-invalid={!ok} autoFocus />{a.unit && <span className="mq-num">{a.unit}</span>}</span>
      </label>
      {!ok && <p className="mq-dim" style={{ marginTop: 6 }}>Enter a number{a.min != null && a.max != null ? ` from ${a.min} to ${a.max}` : ''}.</p>}
      <Popover.Close className="mq-btn is-ink is-sm" type="submit" disabled={!ok} style={{ marginTop: 10 }}>Apply and run again</Popover.Close>
    </form>
  )
}

const Steps = ({ b }: { b: Of<'StepLog'> }) => (
  <ol className="b-steps">
    {b.steps.map((s, i) => <li key={s.id}><span className="mq-num n">{i + 1}</span><span>{s.label}{s.detail && <small>{s.detail}</small>}</span>{s.ms != null && <span className="mq-num t">{ms(s.ms)}</span>}</li>)}
  </ol>
)

function BlockView({ b, ctx }: { b: Block; ctx: Ctx }): ReactNode {
  switch (b.type) {
    case 'VerdictHeader': return <Verdict b={b} />
    case 'MetricRow': return <Metrics b={b} />
    case 'CheckList': return <Checks b={b} ctx={ctx} />
    case 'EvidenceStrip': return <Evidence b={b} ctx={ctx} />
    case 'RankedTable': return <Ranked b={b} />
    case 'MiniChart': return <Chart b={b} />
    case 'FloorPlanMini': return <Mini b={b} ctx={ctx} />
    case 'Controls': return <Controls b={b} />
    case 'AssumptionChips': return <Assumed b={b} ctx={ctx} />
    case 'StepLog': return <Steps b={b} />
    case 'Note': return <p className="b-note">{b.text}</p>
    case 'ActionBar': return <div className="b-actions">{b.actions.map((a) => <button key={a.id} className="mq-btn is-quiet is-sm" onClick={() => runAction(a, ctx.panel)}>{a.label}</button>)}</div>
  }
}

/** One sheet: a tool's result for one place, set from the blocks in the order they came. */
export function PanelSheet({ panel }: { panel: Panel }) {
  const doc = useWorkspace((s) => s.doc)
  const run = doc.runs.find((r) => r.id === panel.run)
  return (
    <article className="mq-panel" aria-labelledby={`p-${panel.id}`}>
      <header>
        <h2 id={`p-${panel.id}`}>{panel.title}</h2>
        {panel.scope && <p className="mq-dim">{panel.scope}</p>}
      </header>
      {run?.stale && <p className="b-stale">A setting changed after this ran. <button className="mq-link" onClick={() => runAction({ id: 'rerun', label: 'Run again' }, panel)}>Run again</button></p>}
      {run?.status === 'running' && <p className="b-working mq-caps">{run.summary ?? 'Working'}</p>}
      {panel.blocks.map((b, i) => <BlockView key={i} b={b} ctx={{ doc, panel }} />)}
    </article>
  )
}
