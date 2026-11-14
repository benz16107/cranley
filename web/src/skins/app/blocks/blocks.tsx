import { useEffect, useState, type ReactNode } from 'react'
import { Popover } from '@base-ui/react/popover'
import { Slider } from '@base-ui/react/slider'
import { Switch } from '@base-ui/react/switch'
import type { Action, Block, Doc, Finding, Panel, ScanPlan, Status } from '../../../core/index.ts'
import { fetchPlan, focusAnchor, focusFinding, navigate, panoFace, runAction, useWorkspace, userOp } from '../../../core/index.ts'
import { Icon, RunState, SourceChip, St, StatusGlyph, ToolKey } from '../design/ui.tsx'
import { dur, num as fmt } from '../lib/format.ts'
import { PlanDrawing } from '../shell/PlanDrawing.tsx'
import { oneSource, splitChecks } from '../lib/source.ts'

/* The twelve panel blocks, set at the density of a work tool. A panel is only ever built from these.
   Numbers arrive in the block's data from a tool result and are printed as they are; no text is parsed. */

type Ctx = { doc: Doc; panel: Panel }

function VerdictHeader({ b }: { b: Extract<Block, { type: 'VerdictHeader' }> }) {
  return (
    <div className="b-verdict"><St status={b.status} /><p>{b.text}</p></div>
  )
}

function MetricRow({ b }: { b: Extract<Block, { type: 'MetricRow' }> }) {
  // values that all came from one place say so once, under the row, not once each
  const one = oneSource(b.metrics.map((m) => m.source))
  return (
    <>
      <dl className="b-metrics">
        {b.metrics.map((m) => (
          <div key={m.id}>
            <dt title={m.label}>{m.label}</dt>
            <dd>{m.value == null ? <span className="nil hatch" title="Not measured" /> : <b className="num">{fmt(m.value)}</b>}{m.value != null && m.unit && <small>{m.unit}</small>}</dd>
            {!one && <SourceChip source={m.source} />}
          </div>
        ))}
      </dl>
      {one && <p className="b-from"><SourceChip source={b.metrics[0].source} /></p>}
    </>
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
  const onSite = b.checks.filter((c) => c.site).length
  // What needs the person's attention stays in view. What passed, or could not be measured, is one line to unfold.
  const { shown, folded, summary } = splitChecks(b.checks)
  const [more, setMore] = useState(false)
  const held = !!current && folded.some((c) => c.findings.includes(current)) // the finding in view is in the fold: open it
  const rows = (list: typeof b.checks) => (
    <ul className="b-checks">
      {list.map((c) => {
        const finding = ctx.doc.findings.find((f) => c.findings.includes(f.id))
        const on = !!current && c.findings.includes(current)
        return (
          <li key={c.id}>
            <button className="check" aria-current={on || undefined} disabled={!finding?.anchor} onClick={() => focusFinding(finding)}
              title={finding?.anchor ? 'Show this in the building' : 'This check has no place in the building to show'}>
              <StatusGlyph status={c.status} />
              <span className="rule">{c.rule}{c.standard && <small>{c.standard}</small>}</span>
              <span className="m">
                {c.measured == null ? <span className="none">not measured</span> : <span className="num">{fmt(c.measured)} {c.unit}</span>}
                {c.threshold != null && <small>{c.kind === 'claim' ? 'record says' : 'limit'} <span className="num">{!c.unit && Number.isInteger(c.threshold) && c.threshold > 1500 && c.threshold < 2200 ? c.threshold /* a year */ : fmt(c.threshold, 3)}</span></small>}
                {c.site && <small className="site">{c.site.measured ? <>measured on site{c.site.scan != null && <>, scan <span className="num">{fmt(c.site.scan)}</span></>}</> : 'settled on site, figure from the scan'}</small>}
              </span>
              {c.kind !== 'claim' && c.measured != null && c.threshold != null && <Gauge measured={c.measured} threshold={c.threshold} status={c.status} />}
            </button>
          </li>
        )
      })}
    </ul>
  )
  return (
    <>
    {/* the verdict above is the tool's sentence from the scan; a check the phone has since settled says so itself */}
    {onSite > 0 && <p className="b-sitenote"><Icon name="camera" size={13} /><span>{onSite === 1 ? 'One check was' : `${onSite} checks were`} settled on site with the phone after this ran. The summary above is still the scan’s.</span></p>}
    {shown.length > 0 && rows(shown)}
    {folded.length > 0 && (
      <details className="b-fold" open={more || held} onToggle={(e) => setMore(e.currentTarget.open)}>
        <summary><Icon name="right" size={11} />{summary}</summary>
        {rows(folded)}
      </details>
    )}
    </>
  )
}

function Thumb({ f, n }: { f: Finding; n: number }) {
  const [state, setState] = useState<'loading' | 'ok' | 'none'>('loading')
  const m = f.media?.find((x) => x.kind === 'pano')
  const sid = f.anchor && 'sid' in f.anchor ? f.anchor.sid : null
  // Contract 3: a panorama ref is "<sid>/<pano>/<face>". The fixtures give the position alone, on the finding's scan.
  const [a, b, c] = m?.ref.split('/') ?? []
  const src = m && b ? panoFace(a, b, c ? Number(c) : 1) : m && sid ? panoFace(sid, m.ref) : null
  return (
    <span className={`thumb ${state === 'loading' && src ? 'loading' : state !== 'ok' ? 'hatch' : ''}`}>
      {src && state !== 'none' && <img src={src} alt="" loading="lazy" width={640} height={640} data-ok={state === 'ok'} onLoad={() => setState('ok')} onError={() => setState('none')} />}
      <span className="cap"><StatusGlyph status={f.status} size={8} /> {n}</span>
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
            {!f.anchor && <span className="muted">No place to show</span>}
          </button>
        </li>
      ))}
    </ul>
  )
}

function RankedTable({ b, panel }: { b: Extract<Block, { type: 'RankedTable' }>; panel: Panel }) {
  // The rows arrive in rank order (the agent's, or the tool's). They keep it until the person sorts by a column.
  const [sort, setSort] = useState<{ col: string | null; dir: 1 | -1 }>({ col: null, dir: -1 })
  const rows = sort.col == null ? b.rows : [...b.rows].sort((x, y) => ((x.values[sort.col!] ?? -Infinity) - (y.values[sort.col!] ?? -Infinity)) * sort.dir)
  const best = Object.fromEntries(b.columns.map((c) => {
    const vals = b.rows.map((r) => r.values[c.id]).filter((v): v is number => v != null)
    return [c.id, vals.length ? (c.better === 'lower' ? Math.min(...vals) : Math.max(...vals)) : null]
  }))
  return (
    <div className="b-table">
      {/* the table's own title names the grouping ("City census by zip code"); the panel's title, repeated, says nothing */}
      {b.title && b.title !== panel.title && <p className="cap">{b.title}</p>}
      <table className="tbl">
        <thead><tr>
          {/* rows that open a building are candidates; a run's own rows (a rollup's groups, a search's homes) are named, and the table's title says of what */}
          <th scope="col">{b.rows.some((r) => r.anchor) ? 'Candidate' : 'Name'}</th>
          {b.columns.map((c) => (
            <th key={c.id} scope="col" className="r" aria-sort={sort.col === c.id ? (sort.dir === 1 ? 'ascending' : 'descending') : 'none'}>
              <button onClick={() => setSort({ col: c.id, dir: sort.col === c.id ? (sort.dir === 1 ? -1 : 1) : c.better === 'lower' ? 1 : -1 })}>
                {c.label}{c.unit && <span className="muted"> {c.unit}</span>}{sort.col === c.id && <span aria-hidden="true">{sort.dir === 1 ? '↑' : '↓'}</span>}
              </button>
            </th>
          ))}
        </tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <th scope="row">
                <button disabled={!r.anchor} onClick={() => r.anchor && ('sid' in r.anchor ? navigate(`/scan/${r.anchor.sid}`, {}, { keep: true }) : focusAnchor(r.anchor))}>
                  {r.status && <StatusGlyph status={r.status} size={8} />}<span className="trunc">{r.label}</span>
                </button>
              </th>
              {b.columns.map((c) => <td key={c.id} className="r num" data-best={r.values[c.id] != null && r.values[c.id] === best[c.id] || undefined}>{fmt(r.values[c.id])}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
      <SourceChip source={b.source} />
    </div>
  )
}

function MiniChart({ b }: { b: Extract<Block, { type: 'MiniChart' }> }) {
  const max = Math.max(...b.bars.map((x) => x.value), b.mark?.value ?? 0) || 1
  return (
    <figure className="b-chart">
      <figcaption><span>{b.title}{b.unit && <span className="muted">, {b.unit}</span>}</span><SourceChip source={b.source} /></figcaption>
      <ol>
        {b.bars.map((x, i) => (
          <li key={i}>
            <span className="l trunc" title={x.label}>{x.status && <StatusGlyph status={x.status} size={7} />}{x.label}</span>
            <span className="track"><i style={{ width: `${(x.value / max) * 100}%`, background: x.status ? `color-mix(in srgb, var(--${x.status}) 55%, var(--pane))` : undefined }} />
              {b.mark && <u style={{ left: `${(b.mark.value / max) * 100}%` }} />}</span>
            <span className="num v">{fmt(x.value)}</span>
          </li>
        ))}
      </ol>
      {b.mark && <p className="mark"><u />{b.mark.label} <span className="num">{fmt(b.mark.value)} {b.unit}</span></p>}
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
    <button className={`b-plan ${plan ? '' : 'loading'}`} aria-label="Open this scan in the building view" onClick={() => navigate(`/scan/${b.sid}`, {}, { keep: true })}>
      {plan && <PlanDrawing plan={plan} overlays={overlays} view={{ mode: 'plan' }} onPick={() => {}} mini selected={ctx.doc.camera?.anchor} />}
    </button>
  )
}

function Controls({ b }: { b: Extract<Block, { type: 'Controls' }> }) {
  return (
    <div className="b-controls">
      {b.controls.map((c) => {
        // the server keeps `from` as the learned item's wording, so it says what was set
        const set = (value: number | boolean | string) => userOp({ op: 'pref.set', key: c.id, label: c.label, value, unit: c.unit, from: `You set “${c.label}” to ${value === true ? 'yes' : value === false ? 'no' : value}${c.unit ? ` ${c.unit}` : ''}` })
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
      <span className="muted">Assumed</span>
      {b.assumptions.map((a) => {
        const mine = ctx.doc.prefs.find((p) => p.key === a.id)?.by === 'user'
        const body = <>{a.label} {typeof a.value === 'boolean' ? <span className="dim">{a.value ? 'yes' : 'no'}</span> : <span className="num">{String(a.value)}{a.unit ? ` ${a.unit}` : ''}</span>}{mine && <span className="mine" title="You set this" />}</>
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
    <form className="assume-edit" onSubmit={(e) => { e.preventDefault(); if (ok && n !== a.value) userOp({ op: 'pref.set', key: a.id, label: a.label, value: n, unit: a.unit, from: `You changed “${a.label}” from ${a.value} to ${n}${a.unit ? ` ${a.unit}` : ''}` }) }}>
      <label className="fld"><span>{a.label}</span>
        <span className="row"><input className="field" inputMode="decimal" value={v} onChange={(e) => setV(e.target.value)} aria-invalid={!ok} autoFocus />{a.unit && <span className="num">{a.unit}</span>}</span>
      </label>
      {!ok && <p className="muted">Enter a number{a.min != null && a.max != null ? ` from ${a.min} to ${a.max}` : ''}.</p>}
      <Popover.Close className="btn solid sm" type="submit" disabled={!ok}>Apply and run again</Popover.Close>
    </form>
  )
}

/** How the tool got there, step by step, with its queries and timings: for whoever wants to check the working. */
function StepLog({ b }: { b: Extract<Block, { type: 'StepLog' }> }) {
  if (!b.steps.length) return null
  return (
    <details className="b-fold">
      <summary><Icon name="right" size={11} />How this was worked out</summary>
      <ol className="b-steps">
        {b.steps.map((s, i) => (
          <li key={s.id}><span className="n">{i + 1}</span><span>{s.label}{s.detail && <small>{s.detail}</small>}</span>{s.ms != null && <span className="num t">{dur(s.ms)}</span>}</li>
        ))}
      </ol>
    </details>
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
    case 'RankedTable': return <RankedTable b={b} panel={ctx.panel} />
    case 'MiniChart': return <MiniChart b={b} />
    case 'FloorPlanMini': return <FloorPlanMini b={b} ctx={ctx} />
    case 'Controls': return <Controls b={b} />
    case 'AssumptionChips': return <AssumptionChips b={b} ctx={ctx} />
    case 'StepLog': return <StepLog b={b} />
    case 'Note': return <p className="b-note">{b.text}</p>
    case 'ActionBar': return <ActionBar b={b} ctx={ctx} />
  }
}

/** One result. `bare` leaves the header out, for a drawer or a tab that already names it. */
export function PanelView({ panel, bare = false, folded = false, open: held, onOpen }: { panel: Panel; bare?: boolean; folded?: boolean; /** when given, the parent decides */ open?: boolean; onOpen?: (open: boolean) => void }) {
  const doc = useWorkspace((s) => s.doc)
  const [own, setOwn] = useState(!folded)
  const open = held ?? own, setOpen = (o: boolean) => { setOwn(o); onOpen?.(o) }
  const tool = doc.tools.find((t) => t.id === panel.tool)
  const run = doc.runs.find((r) => r.id === panel.run)
  const verdict = panel.blocks.find((b): b is Extract<Block, { type: 'VerdictHeader' }> => b.type === 'VerdictHeader')
  const id = `panel-${panel.id}`
  const body = (
    <>
      {run?.stale && <p className="b-stale"><Icon name="info" size={13} />A setting changed after this ran.<button className="btn sm" onClick={() => runAction({ id: 'rerun', label: 'Run again' }, panel)}><Icon name="rerun" size={12} />Run again</button></p>}
      {run?.status === 'running' && !panel.blocks.length && <div className="b-loading" aria-label="Working"><RunState state="running">{run.summary ?? 'Working'}</RunState><span className="sk" style={{ width: '70%' }} /><span className="sk" style={{ width: '46%' }} /></div>}
      {run?.status === 'failed' && !panel.blocks.length && <p className="note" data-kind="fail"><Icon name="warn" size={13} /><span>{run.summary ?? 'This run failed.'}</span></p>}
      {panel.blocks.map((b, i) => <BlockView key={i} block={b} ctx={{ doc, panel }} />)}
    </>
  )
  if (bare) return <div className="panel bare">{body}</div>
  return (
    <section className="panel" aria-labelledby={id} data-open={open}>
      <header>
        <button className="fold" aria-expanded={open} aria-label={open ? `Fold ${panel.title}` : `Unfold ${panel.title}`} onClick={() => setOpen(!open)}><Icon name={open ? 'down' : 'right'} size={12} /></button>
        {panel.role && panel.role !== 'tool' ? <span className="chip">{panel.role === 'summary' ? 'Summary' : panel.role === 'ranking' ? 'Ranking' : 'Note'}</span> : <ToolKey id={panel.tool} title={tool?.title ?? panel.title} />}
        <h3 id={id} className="trunc">{panel.title}</h3>
        {/* the verdict shows on the row when it is folded; unfolded, it is the first thing inside */}
        {!open && verdict && <St status={verdict.status} />}
        {run?.status === 'running' && <RunState state="running" />}
      </header>
      {open && body}
    </section>
  )
}
