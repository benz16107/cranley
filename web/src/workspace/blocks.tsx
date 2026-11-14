import { useEffect, useState, type ReactNode } from 'react'
import NumberFlow from '@number-flow/react'
import { Popover } from '@base-ui/react/popover'
import { Slider } from '@base-ui/react/slider'
import { Switch } from '@base-ui/react/switch'
import type { Action, Anchor, Block, Doc, Finding, Panel, ScanPlan, Status } from './types.ts'
import { useWorkspace, userOp } from './store.ts'
import { Icon, SourceChip, StatusGlyph, statusWord, ToolKey } from '../design/ui.tsx'
import { fetchPlan, panoFace } from '../lib/api.ts'
import { navigate } from '../lib/router.ts'
import { PlanDrawing } from '../shell/PlanDrawing.tsx'
import { runAction } from './agent.ts'

/* The twelve panel blocks. A panel is only ever built from these, each designed once.
   Numbers arrive in the block's data from a tool result and are printed as they are; no text is parsed. */

const fmt = (v: number | null | undefined, digits?: number) =>
  v == null ? '–' : new Intl.NumberFormat('en', { maximumFractionDigits: digits ?? (Math.abs(v) >= 100 ? 0 : Math.abs(v) >= 10 ? 1 : 2) }).format(v)

/** Looking at a finding: the building view frames its anchor and the matching rows light up. */
export function focusFinding(f: Finding | undefined) {
  if (!f?.anchor) return
  userOp({ op: 'camera.focus', anchor: f.anchor, finding: f.id })
}
export function focusAnchor(anchor: Anchor) { userOp({ op: 'camera.focus', anchor }) }

type Ctx = { doc: Doc; panel: Panel }

function VerdictHeader({ b }: { b: Extract<Block, { type: 'VerdictHeader' }> }) {
  return (
    <div className="b-verdict" data-status={b.status}>
      <StatusGlyph status={b.status} size={13} />
      <div><span className="label">{statusWord(b.status)}</span><p>{b.text}</p></div>
    </div>
  )
}

function MetricRow({ b }: { b: Extract<Block, { type: 'MetricRow' }> }) {
  return (
    <dl className="b-metrics" style={{ gridTemplateColumns: `repeat(${Math.min(b.metrics.length, 4)}, minmax(0, 1fr))` }}>
      {b.metrics.map((m) => (
        <div key={m.id}>
          <dt className="label">{m.label}</dt>
          <dd className="num">{m.value == null ? <span className="nil hatch" title="Not measured" /> : <NumberFlow value={m.value} format={{ maximumFractionDigits: 2 }} />}<small>{m.unit}</small></dd>
          <SourceChip source={m.source} />
        </div>
      ))}
    </dl>
  )
}

/** A check drawn as a dimension line: the threshold is the dashed tick, the measurement is the mark. */
function Gauge({ measured, threshold, status }: { measured: number; threshold: number; status: Status }) {
  const max = Math.max(measured, threshold) * 1.3 || 1
  return (
    <span className="gauge" aria-hidden="true">
      <u style={{ left: `${(threshold / max) * 100}%` }} />
      <i style={{ left: `${(measured / max) * 100}%`, background: `var(--${status})` }} />
    </span>
  )
}

function CheckList({ b, ctx }: { b: Extract<Block, { type: 'CheckList' }>; ctx: Ctx }) {
  const current = ctx.doc.camera?.finding
  return (
    <ul className="b-checks">
      {b.checks.map((c) => {
        const finding = ctx.doc.findings.find((f) => c.findings.includes(f.id))
        const on = !!current && c.findings.includes(current)
        return (
          <li key={c.id}>
            <button className="check" aria-current={on || undefined} disabled={!finding?.anchor} onClick={() => focusFinding(finding)}
              title={finding?.anchor ? 'Show this in the building' : 'This check has no place in the building to show'}>
              <StatusGlyph status={c.status} />
              <span className="rule">{c.rule}{c.standard && <small>{c.standard}</small>}</span>
              <span className="m num">{c.measured == null ? 'not measured' : `${fmt(c.measured)} ${c.unit}`}{c.threshold != null && <small>limit {fmt(c.threshold, 3)}</small>}</span>
              {c.measured != null && c.threshold != null && <Gauge measured={c.measured} threshold={c.threshold} status={c.status} />}
            </button>
          </li>
        )
      })}
    </ul>
  )
}

function Thumb({ f, n }: { f: Finding; n: number }) {
  const [state, setState] = useState<'loading' | 'ok' | 'none'>('loading')
  const m = f.media?.find((x) => x.kind === 'pano')
  const sid = f.anchor && 'sid' in f.anchor ? f.anchor.sid : null
  return (
    <span className={`thumb ${state === 'loading' && m ? 'skeleton' : state !== 'ok' ? 'hatch' : ''}`}>
      {m && sid && state !== 'none' && <img src={panoFace(sid, m.ref)} alt="" loading="lazy" width={640} height={640} data-ok={state === 'ok'} onLoad={() => setState('ok')} onError={() => setState('none')} />}
      <span className="cap num"><StatusGlyph status={f.status} size={8} /> {n}</span>
    </span>
  )
}
function EvidenceStrip({ b, ctx }: { b: Extract<Block, { type: 'EvidenceStrip' }>; ctx: Ctx }) {
  const items = b.findings.map((id) => ctx.doc.findings.find((f) => f.id === id)).filter((f): f is Doc['findings'][number] => !!f)
  if (!items.length) return null
  return (
    <ul className="b-evidence">
      {items.map((f, i) => (
        <li key={f.id}>
          <button aria-current={ctx.doc.camera?.finding === f.id || undefined} disabled={!f.anchor} onClick={() => focusFinding(f)}>
            <Thumb f={f} n={i + 1} />
            <span className="t">{f.title}</span>
            {!f.anchor && <span className="label">Unanchored</span>}
          </button>
        </li>
      ))}
    </ul>
  )
}

function RankedTable({ b }: { b: Extract<Block, { type: 'RankedTable' }> }) {
  const [sort, setSort] = useState<{ col: string; dir: 1 | -1 }>(() => ({ col: b.columns[0]?.id, dir: b.columns[0]?.better === 'lower' ? 1 : -1 }))
  const rows = [...b.rows].sort((x, y) => ((x.values[sort.col] ?? -Infinity) - (y.values[sort.col] ?? -Infinity)) * sort.dir)
  const best = Object.fromEntries(b.columns.map((c) => {
    const vals = b.rows.map((r) => r.values[c.id]).filter((v): v is number => v != null)
    return [c.id, vals.length ? (c.better === 'lower' ? Math.min(...vals) : Math.max(...vals)) : null]
  }))
  return (
    <div className="b-table">
      <table>
        <thead><tr>
          <th scope="col">Candidate</th>
          {b.columns.map((c) => (
            <th key={c.id} scope="col" aria-sort={sort.col === c.id ? (sort.dir === 1 ? 'ascending' : 'descending') : 'none'}>
              <button onClick={() => setSort({ col: c.id, dir: sort.col === c.id ? (sort.dir === 1 ? -1 : 1) : c.better === 'lower' ? 1 : -1 })}>
                {c.label}{c.unit && <span className="num"> {c.unit}</span>}{sort.col === c.id && <span aria-hidden="true">{sort.dir === 1 ? ' ↑' : ' ↓'}</span>}
              </button>
            </th>
          ))}
        </tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <th scope="row">
                <button disabled={!r.anchor} onClick={() => r.anchor && ('sid' in r.anchor ? navigate(`/scan/${r.anchor.sid}`, {}, { keep: true }) : focusAnchor(r.anchor))}>
                  {r.status && <StatusGlyph status={r.status} size={8} />} {r.label}
                </button>
              </th>
              {b.columns.map((c) => <td key={c.id} className="num" data-best={r.values[c.id] != null && r.values[c.id] === best[c.id] || undefined}>{fmt(r.values[c.id])}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
      <SourceChip source={b.source} />
    </div>
  )
}

function MiniChart({ b }: { b: Extract<Block, { type: 'MiniChart' }> }) {
  const max = Math.max(...b.bars.map((x) => x.value), b.mark?.value ?? 0) * 1.08 || 1
  return (
    <figure className="b-chart">
      <figcaption><span className="label">{b.title}</span><SourceChip source={b.source} /></figcaption>
      <div className="bars" role="img" aria-label={`${b.title}: ${b.bars.map((x) => `${x.label} ${fmt(x.value)} ${b.unit}`).join(', ')}`}>
        {b.mark && <span className="limit" style={{ bottom: `${(b.mark.value / max) * 100}%` }}><span className="num">{b.mark.label}</span></span>}
        {b.bars.map((x, i) => (
          <span key={i} className="col" title={`${x.label}: ${fmt(x.value)} ${b.unit}`}>
            <i style={{ height: `${(x.value / max) * 100}%`, background: x.status ? `var(--${x.status})` : 'var(--ramp-4)' }} />
          </span>
        ))}
      </div>
      <div className="axis num"><span>{b.bars[0]?.label}</span><span>{b.bars.at(-1)?.label}</span></div>
    </figure>
  )
}

function FloorPlanMini({ b, ctx }: { b: Extract<Block, { type: 'FloorPlanMini' }>; ctx: Ctx }) {
  const [plan, setPlan] = useState<ScanPlan | null>(null)
  const [failed, setFailed] = useState(false)
  useEffect(() => { let on = true; fetchPlan(b.sid).then((p) => on && setPlan(p), () => on && setFailed(true)); return () => { on = false } }, [b.sid])
  const overlays = ctx.doc.overlays.filter((o) => o.tool === ctx.panel.tool && (!o.sid || o.sid === b.sid)).map((o) => o.overlay)
  if (failed) return <div className="b-plan hatch"><p className="muted">The plan did not load.</p></div>
  return (
    <button className={`b-plan ${plan ? '' : 'skeleton'}`} aria-label="Open this scan in the building view" onClick={() => navigate(`/scan/${b.sid}`, {}, { keep: true })}>
      {plan && <PlanDrawing plan={plan} overlays={overlays} view={{ mode: 'plan' }} onPick={() => {}} mini selected={ctx.doc.camera?.anchor} />}
    </button>
  )
}

function Controls({ b }: { b: Extract<Block, { type: 'Controls' }> }) {
  return (
    <div className="b-controls">
      {b.controls.map((c) => {
        const set = (value: number | boolean | string) => userOp({ op: 'pref.set', key: c.id, label: c.label, value, unit: c.unit, from: 'You moved the control' })
        return (
          <div key={c.id} className="control">
            <span className="lab">{c.label}</span>
            {c.kind === 'slider' && (
              <>
                <Slider.Root value={c.value as number} min={c.min} max={c.max} step={c.step} onValueCommitted={(v) => set(v as number)} aria-label={c.label}>
                  <Slider.Control className="slider"><Slider.Track className="track"><Slider.Indicator className="range" /><Slider.Thumb className="thumb" /></Slider.Track></Slider.Control>
                </Slider.Root>
                <span className="num val">{fmt(c.value as number)} {c.unit}</span>
              </>
            )}
            {c.kind === 'toggle' && <Switch.Root className="switch" checked={c.value as boolean} onCheckedChange={set} aria-label={c.label}><Switch.Thumb className="knob" /></Switch.Root>}
            {c.kind === 'select' && <select className="field" value={c.value as string} onChange={(e) => set(e.target.value)} aria-label={c.label}>{c.options?.map((o) => <option key={o}>{o}</option>)}</select>}
          </div>
        )
      })}
    </div>
  )
}

function AssumptionChips({ b, ctx }: { b: Extract<Block, { type: 'AssumptionChips' }>; ctx: Ctx }) {
  return (
    <div className="b-assume">
      <span className="label">Assumed</span>
      {b.assumptions.map((a) => {
        const mine = ctx.doc.prefs.find((p) => p.key === a.id)?.by === 'user'
        const body = <>{a.label} <span className="num">{String(a.value)}{a.unit ? ` ${a.unit}` : ''}</span>{mine && <span className="mine" title="You set this" />}</>
        if (!a.editable || typeof a.value !== 'number') return <span key={a.id} className="chip">{body}</span>
        return (
          <Popover.Root key={a.id}>
            <Popover.Trigger className="chip" aria-label={`${a.label}: ${a.value} ${a.unit ?? ''}. Change it.`}>{body}</Popover.Trigger>
            <Popover.Portal><Popover.Positioner sideOffset={6} align="start"><Popover.Popup className="pop">
              <AssumptionEdit a={a as typeof a & { value: number }} />
            </Popover.Popup></Popover.Positioner></Popover.Portal>
          </Popover.Root>
        )
      })}
    </div>
  )
}
function AssumptionEdit({ a }: { a: { id: string; label: string; value: number; unit?: string; min?: number; max?: number; step?: number } }) {
  const [v, setV] = useState(String(a.value))
  const n = Number(v)
  const ok = v.trim() !== '' && Number.isFinite(n) && (a.min == null || n >= a.min) && (a.max == null || n <= a.max)
  return (
    <form className="assume-edit" onSubmit={(e) => { e.preventDefault(); if (ok && n !== a.value) userOp({ op: 'pref.set', key: a.id, label: a.label, value: n, unit: a.unit, from: `You changed it from ${a.value} ${a.unit ?? ''}`.trim() }) }}>
      <label><span className="label">{a.label}</span>
        <span className="row"><input className="field num" inputMode="decimal" value={v} onChange={(e) => setV(e.target.value)} aria-invalid={!ok} autoFocus />{a.unit && <span className="num">{a.unit}</span>}</span>
      </label>
      {!ok && <p className="muted">Enter a number{a.min != null && a.max != null ? ` from ${a.min} to ${a.max}` : ''}.</p>}
      <Popover.Close className="btn solid sm" type="submit" disabled={!ok}>Apply and run again</Popover.Close>
    </form>
  )
}

function StepLog({ b }: { b: Extract<Block, { type: 'StepLog' }> }) {
  return (
    <ol className="b-steps">
      {b.steps.map((s, i) => (
        <li key={s.id}><span className="num n">{String(i + 1).padStart(2, '0')}</span><span>{s.label}{s.detail && <small>{s.detail}</small>}</span>{s.ms != null && <span className="num t">{s.ms < 1000 ? `${Math.round(s.ms)} ms` : `${(s.ms / 1000).toFixed(1)} s`}</span>}</li>
      ))}
    </ol>
  )
}

function ActionBar({ b, ctx }: { b: Extract<Block, { type: 'ActionBar' }>; ctx: Ctx }) {
  return <div className="b-actions">{b.actions.map((a: Action) => <button key={a.id} className="btn sm" onClick={() => runAction(a, ctx.panel)}>{a.label}</button>)}</div>
}

function BlockView({ block: b, ctx }: { block: Block; ctx: Ctx }): ReactNode {
  switch (b.type) {
    case 'VerdictHeader': return <VerdictHeader b={b} />
    case 'MetricRow': return <MetricRow b={b} />
    case 'CheckList': return <CheckList b={b} ctx={ctx} />
    case 'EvidenceStrip': return <EvidenceStrip b={b} ctx={ctx} />
    case 'RankedTable': return <RankedTable b={b} />
    case 'MiniChart': return <MiniChart b={b} />
    case 'FloorPlanMini': return <FloorPlanMini b={b} ctx={ctx} />
    case 'Controls': return <Controls b={b} />
    case 'AssumptionChips': return <AssumptionChips b={b} ctx={ctx} />
    case 'StepLog': return <StepLog b={b} />
    case 'Note': return <p className="b-note">{b.text}</p>
    case 'ActionBar': return <ActionBar b={b} ctx={ctx} />
  }
}

export function PanelView({ panel, index }: { panel: Panel; index: number }) {
  const doc = useWorkspace((s) => s.doc)
  const [open, setOpen] = useState(true)
  const tool = doc.tools.find((t) => t.id === panel.tool)
  const run = doc.runs.find((r) => r.id === panel.run)
  const id = `panel-${panel.id}`
  return (
    <section className="panel" aria-labelledby={id} data-open={open}>
      <header>
        <ToolKey id={panel.tool} title={tool?.title ?? panel.title} code={tool?.code} />
        <h3 id={id}>{panel.title}{panel.scope && <span className="scope">{panel.scope}</span>}</h3>
        <span className="num code">{String(index + 1).padStart(2, '0')}</span>
        <button className="btn icon quiet sm" aria-expanded={open} aria-label={open ? `Fold ${panel.title}` : `Unfold ${panel.title}`} onClick={() => setOpen(!open)}><Icon name="down" size={13} /></button>
      </header>
      {open && run?.stale && (
        <p className="stale"><span className="hatch" />A setting changed after this ran. <button className="link" onClick={() => runAction({ id: 'rerun', label: 'Run again' }, panel)}>Run again</button></p>
      )}
      {open && run?.status === 'running' && !panel.blocks.length && <div className="panel-loading skeleton" aria-label="Working" />}
      {open && panel.blocks.map((b, i) => <BlockView key={i} block={b} ctx={{ doc, panel }} />)}
    </section>
  )
}
