import { useEffect, useState, type ReactNode } from 'react'
import { Popover } from '@base-ui/react/popover'
import { Slider } from '@base-ui/react/slider'
import { Switch } from '@base-ui/react/switch'
import {
  currentRoute, droneImage, fetchPlan, focusAnchor, focusFinding, navigate, panoFace, runAction, setQuery, useWorkspace, userOp,
  type Block, type Check, type Doc, type Finding, type Overlay, type Panel, type ScanPlan,
} from '../../core/index.ts'
import { Fig, Fold, G, Mark, Src, Stat, Val } from './parts.tsx'
import { useCurrent } from './stories.tsx'
import { STATUS_WORD, familyOf, headOf, headSize, leadOf, limit, mediaParts, ms, needLine, num, plain, splitVerdict, unitOf, withUnit, type Family } from './words.ts'

/* A panel, set as a story: the verdict is the headline, the measured number sits under the marker, the evidence is
   numbered figures. The twelve blocks are each set once here. Numbers are printed from the block they arrive in. */

type Of<T extends Block['type']> = Extract<Block, { type: T }>
type Ctx = { doc: Doc; panel: Panel; family: Family; current: string | undefined }
type F = Doc['findings'][number]

/** Look at a finding: the figure goes to it. A place outside the building (a roof, a dock, a parking stall) is shown on
    the aerial photograph of this building, so the page stays on its story. On a phone the figure is at the top of the
    page, so the page goes there too. */
export function look(f: Finding | undefined) {
  if (!f?.anchor) return
  const here = currentRoute().path === '/scan'
  if ('geo' in f.anchor && here) setQuery({ b_v: 'air', f: f.id }, false)
  else { focusFinding(f); if (here) setQuery({ b_v: null }) }
  if (window.matchMedia('(max-width: 760px)').matches) window.scrollTo({ top: 0, behavior: 'smooth' })
}

/** The picture a finding carries, and the box drawn on it. */
export function pictureOf(f: Finding): { src: string; box?: number[] | null; kind: string } | null {
  const m = f.media?.[0]
  if (!m) return null
  if (m.ref.startsWith('/api/')) return { src: m.ref, box: m.box, kind: m.kind }
  const p = mediaParts(m.ref, f.anchor && 'sid' in f.anchor ? f.anchor.sid : null)
  if (!p) return null
  return { src: m.kind === 'drone' ? droneImage(p.sid, p.a) : panoFace(p.sid, p.a, p.b ? Number(p.b) : 1), box: m.box, kind: m.kind }
}

/* ---------- MetricRow ---------- */
function Metrics({ b }: { b: Of<'MetricRow'> }) {
  return (
    <section className="sec"><h2>The numbers</h2>
      <dl className="metrics">
        {b.metrics.map((m) => <div key={m.id}><dt>{m.label}</dt><dd><Val v={m.value} unit={m.unit} /></dd><Src source={m.source} /></div>)}
      </dl>
    </section>
  )
}

/* ---------- CheckList: three settings, by the kind of story ---------- */
/** Measured against its limit on one line: the tick is the limit, the glyph is the measurement. */
function Scale({ c }: { c: Check }) {
  const max = Math.max(c.measured!, c.threshold!) * 1.25 || 1
  return <span className="scale" aria-hidden="true"><i className="lim" style={{ left: `${(c.threshold! / max) * 100}%` }} /><i className="at" data-s={c.status} style={{ left: `${(c.measured! / max) * 100}%` }}><G s={c.status} /></i></span>
}
function Checks({ b, ctx }: { b: Of<'CheckList'>; ctx: Ctx }) {
  const current = ctx.current
  // a check whose rule sets one source against another ("listing vs scan") is a claim beside a measurement, not a limit
  const truth = b.checks.some((c) => / vs /.test(c.rule))
  // checks with nothing to be held against (a depth in each room, the minutes each task takes) are set as bars on one scale
  const bars = !truth && b.checks.every((c) => c.measured != null && !c.threshold) && new Set(b.checks.map((c) => c.unit)).size === 1
  const listed = bars && /^\d+\. /.test(b.checks[0]?.rule ?? '')
  const deepest = Math.max(...b.checks.map((c) => c.measured ?? 0)) || 1
  // a standard every check shares is said once, under the heading
  const shared = b.checks.length > 1 && b.checks.every((c) => c.standard && c.standard === b.checks[0].standard) ? b.checks[0].standard : null
  const std = (c: Check) => !shared && c.standard && <small>{c.standard}</small>
  const row = (c: Check) => {
    const year = /\byear\b/i.test(c.rule), fmt = (x: number | null, lim?: boolean) => (x == null ? null : year ? plain(x) : lim ? limit(x, c.unit) : withUnit(x, c.unit))
    const f = ctx.doc.findings.find((x) => c.findings.includes(x.id) && x.anchor)
    const on = !!current && c.findings.includes(current)
    const props = { 'aria-current': on || undefined, disabled: !f, onClick: () => look(f), title: f ? 'Show this in the figure' : undefined } as const
    if (truth) return (
      <button className="compare" data-status={c.status} {...props}>
        <span data-s={c.status}><G s={c.status} /></span><span className="rule"><span className="t">{c.rule.replace(/, listing vs .*$/, '')}</span>{std(c)}</span>
        <span className="val says">{fmt(c.threshold, true) ?? <i>not stated</i>}</span>
        <span className="val" data-s={c.status}>{fmt(c.measured) ?? <i>not measured</i>}</span>
      </button>
    )
    return (
      <button className="check" {...props}>
        <span data-s={c.status}><G s={c.status} /></span><span className="rule"><span className="t">{c.rule}</span>{std(c)}</span>
        <span className="val" data-s={c.status}>{fmt(c.measured) ?? <i>not measured</i>}{c.threshold != null && c.threshold !== 0 && <small>limit {fmt(c.threshold, true)}</small>}</span>
        {bars ? <span className="depth" style={{ ['--w' as string]: `${(c.measured! / deepest) * 100}%` }} aria-hidden="true" />
          : c.measured != null && c.threshold != null && c.threshold !== 0 && <Scale c={c} />}
      </button>
    )
  }
  return (
    <section className="sec"><h2>{truth ? 'The record against the scan' : listed ? 'In this order' : bars ? (ctx.family === 'flood' ? 'Room by room' : 'One by one') : 'Checked against the limit'}</h2>
      {shared && <p className="fig" style={{ margin: '0.625rem 0 0.25rem' }}>{shared}</p>}
      {truth && <div className="compare headrow cap" aria-hidden="true"><span>Claim</span><span>Record says</span><span>Scan measures</span></div>}
      <Fold items={b.checks} show={7} noun="checks">{(shown) => <ul className="checks">{shown.map((c) => <li key={c.id}>{row(c)}</li>)}</ul>}</Fold>
    </section>
  )
}

/* ---------- EvidenceStrip: numbered figures ---------- */
type Pic = NonNullable<ReturnType<typeof pictureOf>>
/** A photograph as a plate. With a box, the plate is square (panorama faces and aerial patches are) and closes in on it. */
function Photo({ pic }: { pic: Pic }) {
  const [ok, setOk] = useState<boolean | null>(null)
  if (ok === false) return <span className="photo none"><span className="unset" /></span>
  const [x0, y0, x1, y1] = pic.box ?? [0, 0, 1, 1]
  const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2, k = pic.box ? Math.min(3.2, Math.max(1, 0.42 / Math.max(x1 - x0, y1 - y0))) : 1
  // keep the frame inside the picture: the centre can move only as far as the zoom leaves room
  const room = (1 - 1 / k) / 2, mx = Math.min(room, Math.max(-room, 0.5 - cx)), my = Math.min(room, Math.max(-room, 0.5 - cy))
  return (
    <span className="photo" data-boxed={pic.box ? '' : undefined}>
      <span className="zoom" style={pic.box ? { transform: `scale(${k}) translate(${mx * 100}%, ${my * 100}%)` } : undefined}>
        <img src={pic.src} alt="" loading="lazy" width={640} height={pic.box ? 640 : 480} data-ok={ok === true} onLoad={() => setOk(true)} onError={() => setOk(false)} />
        {ok && pic.box && <i className="box" style={{ left: `${x0 * 100}%`, top: `${y0 * 100}%`, width: `${(x1 - x0) * 100}%`, height: `${(y1 - y0) * 100}%`, ['--k' as string]: k }} />}
      </span>
    </span>
  )
}
function Evidence({ b, ctx, from }: { b: Of<'EvidenceStrip'>; ctx: Ctx; from: number }) {
  const items = b.findings.map((id) => ctx.doc.findings.find((f) => f.id === id)).filter((f): f is F => !!f).map((f, i) => ({ f, n: from + i, pic: pictureOf(f) }))
  if (!items.length) return null
  const current = ctx.current
  const groups = new Map<string, typeof items>()
  for (const it of items) if (it.pic) { const key = it.pic.src + (it.pic.box ?? []).join(','); groups.set(key, [...(groups.get(key) ?? []), it]) }
  const plates = [...groups.values()], lines = items.filter((it) => !it.pic)
  return (
    <section className="sec"><h2>The evidence</h2>
      {plates.length > 0 && (
        <Fold items={plates} show={4} noun="photographs">{(shown) => (
          <div className="plates" data-one={plates.length === 1 || undefined}>
            {shown.map((group) => (
              <figure key={group[0].f.id} className="plate">
                <button className="platebtn" aria-label={`Show in the figure: ${group[0].f.title}`} aria-current={group.some((x) => x.f.id === current) || undefined} disabled={!group[0].f.anchor} onClick={() => look(group[0].f)}><Photo pic={group[0].pic!} /></button>
                {group.map(({ f, n }) => <Fig key={f.id} n={n}><b className="stat" data-s={f.status}><G s={f.status} />{f.title}.</b> {f.detail} <Src source={f.source} /></Fig>)}
              </figure>
            ))}
          </div>
        )}</Fold>
      )}
      {lines.length > 0 && (
        <Fold items={lines} show={5} noun="findings">{(shown) => (
          <ul className="items">
            {shown.map(({ f, n }) => (
              <li key={f.id}>
                <button className="item" aria-current={current === f.id || undefined} disabled={!f.anchor} onClick={() => look(f)}>
                  <span className="no">{n}</span><span><b>{f.title}</b>{f.detail && <small>{f.detail}</small>}<small>{!f.anchor && 'No place in the building to show. '}<Src source={f.source} className="" /></small></span>
                  <span data-s={f.status}><G s={f.status} /><span className="sr">{STATUS_WORD[f.status]}</span></span>
                </button>
              </li>
            ))}
          </ul>
        )}</Fold>
      )}
    </section>
  )
}

/* ---------- RankedTable: a league table that keeps the given order until the person sorts ---------- */
function League({ b }: { b: Of<'RankedTable'> }) {
  const [sort, setSort] = useState<{ col: string | null; dir: 1 | -1 }>({ col: null, dir: -1 })
  const rows = sort.col == null ? b.rows : [...b.rows].sort((x, y) => ((x.values[sort.col!] ?? -Infinity) - (y.values[sort.col!] ?? -Infinity)) * sort.dir)
  const best = Object.fromEntries(b.columns.map((c) => {
    const vals = b.rows.map((r) => r.values[c.id]).filter((v): v is number => v != null)
    return [c.id, vals.length ? (c.better === 'lower' ? Math.min(...vals) : Math.max(...vals)) : null]
  }))
  return (
    <section className="sec"><header><h2>{sort.col == null ? 'Ranked' : 'Sorted by you'}</h2><Src source={b.source} /></header>
      <div className="scrollx">
        <table className="league">
          <thead><tr>
            <th scope="col" className="rank"><span className="sr">Rank</span></th><th scope="col" style={{ textAlign: 'left' }}><span className="sr">Candidate</span></th>
            {b.columns.map((c) => (
              <th key={c.id} scope="col" aria-sort={sort.col === c.id ? (sort.dir === 1 ? 'ascending' : 'descending') : 'none'}>
                <button onClick={() => setSort({ col: c.id, dir: sort.col === c.id ? (sort.dir === 1 ? -1 : 1) : c.better === 'lower' ? 1 : -1 })}>
                  {c.label}{c.unit && ` ${unitOf(c.unit)}`}{sort.col === c.id && <span aria-hidden="true">{sort.dir === 1 ? ' ↑' : ' ↓'}</span>}
                </button>
              </th>
            ))}
          </tr></thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={r.id}>
                <td className="rank">{i + 1}</td>
                <th scope="row">
                  <button disabled={!r.anchor} onClick={() => r.anchor && ('sid' in r.anchor ? navigate(`/scan/${r.anchor.sid}`, {}, { keep: true }) : focusAnchor(r.anchor))}>
                    {r.status && <G s={r.status} />}<span className="nm" data-s={undefined}>{r.label}</span>
                  </button>
                </th>
                {b.columns.map((c) => <td key={c.id} data-best={(r.values[c.id] != null && r.values[c.id] === best[c.id]) || undefined}>{r.values[c.id] == null ? '–' : num(r.values[c.id])}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

/* ---------- MiniChart: columns for a series, ruled bars with their names when the names matter ---------- */
function Chart({ b, n }: { b: Of<'MiniChart'>; n: number }) {
  const max = Math.max(...b.bars.map((x) => x.value), b.mark?.value ?? 0) * 1.08 || 1
  const named = b.bars.length <= 14
  const label = `${b.title}: ${b.bars.map((x) => `${x.label} ${num(x.value)} ${unitOf(b.unit)}`).join(', ')}`
  return (
    <section className="sec"><h2>{b.title}</h2>
      <figure className="chart">
        {named ? (
          <ul className="hbars" role="img" aria-label={label}>
            {b.bars.map((x, i) => <li key={i} data-s={x.status}><span>{x.label}</span><i style={{ transform: `scaleX(${Math.max(0.004, x.value / max)})`, background: x.status ? 'currentColor' : undefined }} /><span className="n">{withUnit(x.value, b.unit)}</span></li>)}
          </ul>
        ) : (
          <>
            <div className="bars" role="img" aria-label={label}>
              {b.mark && <span className="limit" style={{ bottom: `${(b.mark.value / max) * 100}%` }}><span>{b.mark.label}</span></span>}
              {b.bars.map((x, i) => <span key={i} className="bar" data-s={x.status} title={`${x.label}: ${withUnit(x.value, b.unit)}`}><i data-s={x.status} style={{ height: `${(x.value / max) * 100}%` }} /></span>)}
            </div>
            <div className="axis"><span>{b.bars[0]?.label}</span><span>{b.bars.at(-1)?.label}</span></div>
          </>
        )}
        <Fig n={n}>{b.title}{unitOf(b.unit) && `, in ${unitOf(b.unit)}`}.{named && b.mark && ` The mark is ${b.mark.label}.`} <Src source={b.source} /></Fig>
      </figure>
    </section>
  )
}

/* ---------- FloorPlanMini: the plan as a small figure, with this story's overlays drawn on it ---------- */
export function PlanFigure({ plan, overlays }: { plan: ScanPlan; overlays: Overlay[] }) {
  const floor = plan.floors[0]?.id
  const walls = plan.walls.filter((w) => w.floor === floor), rooms = plan.rooms.filter((r) => r.floor === floor && r.polygon.length > 2)
  const pts = [...walls.flatMap((w) => [w.a, w.b]), ...rooms.flatMap((r) => r.polygon)]
  if (!pts.length) return null
  const xs = pts.map((p) => p[0]), ys = pts.map((p) => -p[1])
  const x0 = Math.min(...xs), y0 = Math.min(...ys), w = Math.max(...xs) - x0, h = Math.max(...ys) - y0, pad = Math.max(w, h) * 0.06 + 0.3
  const u = Math.max(w, h) / 420 // about one screen pixel, in metres
  const lens = overlays.find((o) => o.kind === 'lens'), water = overlays.some((o) => o.kind === 'water')
  const tint = new Map<string, string>()
  for (const o of overlays) if (o.kind === 'rule' && ['pass', 'warn', 'fail'].includes(o.style)) o.select.rooms?.forEach((id) => tint.set(id, o.style))
  const at = (a: Finding['anchor']): [number, number] | null => {
    if (!a || !('sid' in a)) return null
    if ('point' in a) return [a.point[0], -a.point[1]]
    if ('opening' in a) { const o = plan.openings.find((x) => x.id === a.opening); return o ? [o.center[0], -o.center[1]] : null }
    if ('room' in a) { const r = plan.rooms.find((x) => x.id === a.room); return r?.polygon.length ? [r.polygon.reduce((s, p) => s + p[0], 0) / r.polygon.length, -r.polygon.reduce((s, p) => s + p[1], 0) / r.polygon.length] : null }
    return null
  }
  return (
    <svg viewBox={`${x0 - pad} ${y0 - pad} ${w + pad * 2} ${h + pad * 2}`} role="img" aria-label={`Floor plan of ${plan.name}`}>
      {rooms.map((r) => {
        const v = lens?.kind === 'lens' ? lens.values[r.id] : undefined
        const k = lens?.kind === 'lens' && v != null ? Math.min(1, Math.max(0, (v - lens.legend.min) / (lens.legend.max - lens.legend.min || 1))) : null
        const s = tint.get(r.id)
        return <polygon key={r.id} className="pl-room" points={r.polygon.map((p) => `${p[0]},${-p[1]}`).join(' ')} style={k != null ? { fill: `color-mix(in srgb, #5b5347 ${Math.round(8 + k * 80)}%, #fbf9f4)` } : s ? { fill: `color-mix(in srgb, var(--${s}) 26%, #fbf9f4)` } : undefined} />
      })}
      {water && rooms.map((r) => <polygon key={r.id} className="pl-water" points={r.polygon.map((p) => `${p[0]},${-p[1]}`).join(' ')} />)}
      {walls.filter((x) => x.type !== 'invisible').map((x) => <line key={x.id} className="pl-wall" x1={x.a[0]} y1={-x.a[1]} x2={x.b[0]} y2={-x.b[1]} strokeWidth={Math.max(x.thickness || 0.12, u * 2)} />)}
      {plan.openings.filter((o) => o.floor === floor).map((o) => {
        const wl = plan.walls.find((x) => x.id === o.wall); if (!wl) return null
        const dx = wl.b[0] - wl.a[0], dy = wl.b[1] - wl.a[1], len = Math.hypot(dx, dy) || 1, hx = (dx / len) * o.width / 2, hy = (dy / len) * o.width / 2
        return <line key={o.id} className="pl-gap" x1={o.center[0] - hx} y1={-(o.center[1] - hy)} x2={o.center[0] + hx} y2={-(o.center[1] + hy)} strokeWidth={(wl.thickness || 0.12) + u * 2.5} />
      })}
      {overlays.map((o, i) => o.kind === 'route' && o.floor !== 'geo' && <polyline key={i} className="pl-route" points={o.points.map((p) => `${p[0]},${-p[1]}`).join(' ')} strokeWidth={u * 4} />)}
      {overlays.map((o, i) => o.kind === 'box' && <rect key={i} className="pl-box" data-s={o.status} x={-o.size[0] / 2} y={-o.size[1] / 2} width={o.size[0]} height={o.size[1]} strokeWidth={u * 3} transform={`translate(${o.center[0]} ${-o.center[1]}) rotate(${-o.yaw_deg})`} />)}
      {overlays.flatMap((o) => (o.kind === 'pins' ? o.pins : [])).map((p) => {
        const c = at(p.anchor); if (!c) return null
        const r = u * 8
        return <g key={p.id} data-s={p.status} transform={`translate(${c[0]} ${c[1]})`} fill="currentColor" stroke="#fbf9f4" strokeWidth={u * 1.5}>
          {p.status === 'pass' ? <circle r={r} /> : p.status === 'warn' ? <path d={`M0 ${-r * 1.1}L${r * 1.1} ${r * 0.9}H${-r * 1.1}Z`} /> : p.status === 'fail' ? <rect x={-r} y={-r} width={r * 2} height={r * 2} /> : <circle r={r} fill="#fbf9f4" stroke="currentColor" strokeWidth={u * 3} strokeDasharray={`${u * 4} ${u * 3}`} />}
        </g>
      })}
    </svg>
  )
}
function PlanMini({ b, ctx, n }: { b: Of<'FloorPlanMini'>; ctx: Ctx; n: number }) {
  const [plan, setPlan] = useState<ScanPlan | null>(null), [failed, setFailed] = useState(false)
  useEffect(() => { let on = true; fetchPlan(b.sid).then((p) => on && setPlan(p), () => on && setFailed(true)); return () => { on = false } }, [b.sid])
  const overlays = ctx.doc.overlays.filter((o) => o.tool === ctx.panel.tool && (!o.sid || o.sid === b.sid)).map((o) => o.overlay)
  const lens = overlays.find((o) => o.kind === 'lens')
  if (failed) return <p className="empty">The plan for this figure did not load.</p>
  return (
    <figure className="sec">
      <button className="planfig" aria-label="Open this scan with the plan as the figure" onClick={() => navigate(`/scan/${b.sid}`, { v: 'plan' }, { keep: true })}>
        {plan ? <PlanFigure plan={plan} overlays={overlays} /> : <span className="unset" style={{ height: '14rem' }} />}
        <Fig n={n}>The floor plan{plan ? ` of ${plan.name}` : ''}, with what this section found drawn on it.{lens?.kind === 'lens' && ` Shading: ${lens.legend.title}, ${num(lens.legend.min)} to ${num(lens.legend.max)} ${unitOf(lens.legend.unit)}.`}</Fig>
      </button>
    </figure>
  )
}

/* ---------- Controls and AssumptionChips ---------- */
function Controls({ b }: { b: Of<'Controls'> }) {
  return (
    <section className="sec"><h2>Change it and run again</h2>
      <div className="controls">
        {b.controls.map((c) => {
          const set = (value: number | boolean | string) => userOp({ op: 'pref.set', key: c.id, label: c.label, value, unit: c.unit, from: 'You moved the control' })
          return (
            <div key={c.id} className="control">
              <span>{c.label}</span>
              {c.kind === 'slider' && <SliderControl c={c} set={set} />}
              {c.kind === 'toggle' && <Switch.Root className="switch" checked={c.value as boolean} onCheckedChange={set} aria-label={c.label}><Switch.Thumb className="knob" /></Switch.Root>}
              {c.kind === 'select' && <select className="field" value={c.value as string} onChange={(e) => set(e.target.value)} aria-label={c.label}>{c.options?.map((o) => <option key={o}>{o}</option>)}</select>}
            </div>
          )
        })}
      </div>
    </section>
  )
}
function SliderControl({ c, set }: { c: Of<'Controls'>['controls'][number]; set: (v: number) => void }) {
  const [v, setV] = useState(c.value as number)
  useEffect(() => setV(c.value as number), [c.value])
  return (
    <>
      <span className="n">{withUnit(v, c.unit)}</span>
      <Slider.Root className="sliderroot" value={v} min={c.min} max={c.max} step={c.step} onValueChange={(x) => setV(x as number)} onValueCommitted={(x) => set(x as number)} aria-label={c.label}>
        <Slider.Control className="slider"><Slider.Track className="track"><Slider.Indicator className="range" /><Slider.Thumb className="thumb" /></Slider.Track></Slider.Control>
      </Slider.Root>
    </>
  )
}
function Assumed({ b, ctx }: { b: Of<'AssumptionChips'>; ctx: Ctx }) {
  return (
    <section className="sec"><h2>This rests on</h2>
      <ul className="assume">
        {b.assumptions.map((a) => {
          const mine = ctx.doc.prefs.find((p) => p.key === a.id)?.by === 'user'
          const value = typeof a.value === 'boolean' ? null : typeof a.value === 'number' ? <span className="n">{withUnit(a.value, a.unit)}</span> : <em>{a.value}{a.unit ? ` ${unitOf(a.unit)}` : ''}</em>
          if (!a.editable || typeof a.value !== 'number') return <li key={a.id}>{a.label}{value && <>: {value}</>}{a.value === false && ': no'}</li>
          return (
            <li key={a.id}>{a.label}:{' '}
              <Popover.Root>
                <Popover.Trigger className="edit" aria-label={`${a.label}: ${a.value} ${a.unit ?? ''}. Change it.`}>{value}</Popover.Trigger>
                <Popover.Portal><Popover.Positioner className="pos" sideOffset={8} align="start"><Popover.Popup className="slip"><AssumeEdit a={a as typeof a & { value: number }} /></Popover.Popup></Popover.Positioner></Popover.Portal>
              </Popover.Root>
              {mine && <span className="mine">yours</span>}
            </li>
          )
        })}
      </ul>
    </section>
  )
}
function AssumeEdit({ a }: { a: { id: string; label: string; value: number; unit?: string; min?: number; max?: number } }) {
  const [v, setV] = useState(String(a.value))
  const x = Number(v), ok = v.trim() !== '' && Number.isFinite(x) && (a.min == null || x >= a.min) && (a.max == null || x <= a.max)
  return (
    <form onSubmit={(e) => { e.preventDefault(); if (ok && x !== a.value) userOp({ op: 'pref.set', key: a.id, label: a.label, value: x, unit: a.unit, from: `You changed it from ${a.value} ${a.unit ?? ''}`.trim() }) }}>
      <label><span className="cap">{a.label}{a.unit && `, ${unitOf(a.unit)}`}</span>
        <input className="field n" style={{ fontStyle: 'normal' }} inputMode="decimal" value={v} onChange={(e) => setV(e.target.value)} aria-invalid={!ok} autoFocus />
      </label>
      {!ok && <p className="fig">Enter a number{a.min != null && a.max != null ? ` from ${a.min} to ${a.max}` : ''}.</p>}
      <Popover.Close className="btn" type="submit" disabled={!ok}>Apply and run again</Popover.Close>
    </form>
  )
}

function Steps({ b }: { b: Of<'StepLog'> }) {
  return (
    <section className="sec"><h2>How it was worked out</h2>
      <ol className="steps">{b.steps.map((s) => <li key={s.id}><span>{s.label}{s.detail && <small>{s.detail}</small>}</span>{s.ms != null && <span className="n">{ms(s.ms)}</span>}</li>)}</ol>
    </section>
  )
}

/* The order a story is told in. A flood leads with the dial that raises the water and then the rooms; a record check
   leads with the claims; an office or a ranking leads with its table. The rest keep the order the tool gave. */
const ORDER: Partial<Record<Family, Block['type'][]>> = {
  flood: ['Controls', 'CheckList', 'MetricRow', 'EvidenceStrip'],
  truth: ['CheckList', 'EvidenceStrip', 'MetricRow'],
  office: ['MetricRow', 'RankedTable', 'MiniChart', 'CheckList'],
  data: ['RankedTable', 'MiniChart', 'MetricRow'],
  site: ['EvidenceStrip', 'MetricRow', 'CheckList'],
  fire: ['MetricRow', 'CheckList', 'EvidenceStrip'],
}
const TAIL: Block['type'][] = ['AssumptionChips', 'StepLog', 'Note', 'ActionBar']
function ordered(blocks: Block[], family: Family): Block[] {
  const lead = ORDER[family] ?? []
  const at = (b: Block) => (lead.includes(b.type) ? lead.indexOf(b.type) : TAIL.includes(b.type) ? 100 + TAIL.indexOf(b.type) : 50)
  return blocks.map((b, i) => ({ b, i })).sort((x, y) => at(x.b) - at(y.b) || x.i - y.i).map((x) => x.b)
}

/** The headline of a story. The verdict's first sentence is the headline, in the tool's own words; under it the
    measured number that decides it sits beneath the marker, with what it measures, what it is held against and where
    it came from. `brief` leaves out the standfirst (the caption on an open figure). */
export function Headline({ panel, family, as: H = 'h1', brief }: { panel: Panel; family: Family; as?: 'h1' | 'h2'; brief?: boolean }) {
  const findings = useWorkspace((s) => s.doc.findings)
  const verdict = panel.blocks.find((b): b is Of<'VerdictHeader'> => b.type === 'VerdictHeader')
  const lead = leadOf(panel.blocks, family)
  const source = lead?.source ?? findings.find((f) => f.id === lead?.finding)?.source
  // a panel with no verdict (the agent's own summary) leads with its note, in the agent's words
  const note = panel.blocks.find((b): b is Of<'Note'> => b.type === 'Note')
  const [head, rest] = verdict ? splitVerdict(verdict.text) : note ? splitVerdict(note.text) : [panel.title, '']
  return (
    <div key={`${head}:${lead?.value}`}>
      <H className="head" data-size={headSize(head)}>{head}</H>
      {lead && (
        <div className="lead" data-family={family}>
          <span className="bignum"><Mark><Val v={lead.value} unit={lead.unit} /></Mark></span>
          <p className="leadcap"><b>{headOf(lead.label)}</b>{lead.need != null && <span className="need">{needLine(family, lead.need, lead.unit)}</span>}{source && <Src source={source} />}</p>
        </div>
      )}
      {rest && !brief && <p className="deck">{rest}</p>}
    </div>
  )
}

/** `more` are further panels about the same place (the agent's ranking beside its notes): their blocks follow this one's. */
export function Story({ panel, place, end, more = [] }: { panel: Panel; place?: ReactNode; end?: ReactNode; more?: Panel[] }) {
  const doc = useWorkspace((s) => s.doc)
  const run = doc.runs.find((r) => r.id === panel.run)
  const family = familyOf(panel.tool)
  const verdict = panel.blocks.find((b): b is Of<'VerdictHeader'> => b.type === 'VerdictHeader')
  const ctx: Ctx = { doc, panel, family, current: useCurrent() }
  const led = !verdict && panel.blocks.find((b) => b.type === 'Note') // the note that became the headline
  // the page in order: this story's blocks, then each further panel under a subhead of its own
  type Item = { panel: Panel; family: Family; b?: Block; fig: number }
  const items: Item[] = ordered(panel.blocks.filter((b) => b.type !== 'VerdictHeader' && b !== led), family).map((b) => ({ panel, family, b, fig: 0 }))
  for (const p of more) {
    const f = familyOf(p.tool)
    items.push({ panel: p, family: f, fig: 0 }, ...ordered(p.blocks.filter((b) => b.type !== 'VerdictHeader'), f).map((b) => ({ panel: p, family: f, b, fig: 0 })))
  }
  const writing = run?.status === 'running' && !panel.blocks.length
  // figure 1 is the model on the page; the rest are numbered in the order they are set
  items.reduce((n, it) => { it.fig = n + 1; return n + (it.b?.type === 'EvidenceStrip' ? it.b.findings.length : it.b?.type === 'MiniChart' || it.b?.type === 'FloorPlanMini' ? 1 : 0) }, 1)
  return (
    <article className="story" data-family={family} aria-labelledby={`story-${panel.id}`}>
      <p className="kicker cap">{place ?? <span>{panel.title}</span>}{verdict && <Stat s={verdict.status}>{STATUS_WORD[verdict.status]}</Stat>}{end}</p>
      <div id={`story-${panel.id}`}>
        {writing ? <h1 className="head" data-size="m"><span className="reading">Writing this section</span></h1> : <Headline panel={panel} family={family} />}
      </div>
      {run?.stale && <p className="stale"><span>A setting changed after this was written.</span><button className="link" onClick={() => runAction({ id: 'rerun', label: 'Run again' }, panel)}>Run again</button></p>}
      {writing && <div className="writing" aria-label="Working">{run?.summary && <p className="deck"><em>{run.summary}</em></p>}<i className="unset" /><i className="unset" /><i className="unset" /><i className="unset" /></div>}
      {items.map(({ panel: of, family: fam, b, fig }, i) => {
        const c: Ctx = { ...ctx, panel: of, family: fam }
        if (!b) {
          const v = of.blocks.find((x): x is Of<'VerdictHeader'> => x.type === 'VerdictHeader')
          return (
            <header key={i} className="another" data-family={fam}>
              <p className="kicker cap"><span>{of.title}</span>{v && <Stat s={v.status}>{STATUS_WORD[v.status]}</Stat>}</p>
              {v && <h2 className="head" data-size="s">{splitVerdict(v.text)[0]}</h2>}
              {v && splitVerdict(v.text)[1] && <p className="deck">{splitVerdict(v.text)[1]}</p>}
            </header>
          )
        }
        switch (b.type) {
          case 'MetricRow': return <Metrics key={i} b={b} />
          case 'CheckList': return <Checks key={i} b={b} ctx={c} />
          case 'EvidenceStrip': return <Evidence key={i} b={b} ctx={c} from={fig} />
          case 'RankedTable': return <League key={i} b={b} />
          case 'MiniChart': return <Chart key={i} b={b} n={fig} />
          case 'FloorPlanMini': return <PlanMini key={i} b={b} ctx={c} n={fig} />
          case 'Controls': return <Controls key={i} b={b} />
          case 'AssumptionChips': return <Assumed key={i} b={b} ctx={c} />
          case 'StepLog': return <Steps key={i} b={b} />
          case 'Note': return <p key={i} className="note">{b.text}</p>
          case 'ActionBar': return <div key={i} className="actions">{b.actions.map((a) => <button key={a.id} className="btn line" onClick={() => runAction(a, of)}>{a.label}</button>)}</div>
          default: return null
        }
      })}
    </article>
  )
}
