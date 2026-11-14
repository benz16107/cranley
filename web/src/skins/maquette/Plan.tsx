import { useMemo } from 'react'
import { anchorFloor, type Anchor, type Overlay, type Pt, type ScanPlan, type Status } from '../../core/index.ts'

/* A floor plan as a sheet of paper on the table: rooms in card, walls in ink at their real thickness. A tool's
   overlays are drawn in the look's materials: the route is a strip of tape, water is blue acetate, a lens is pencil
   shading. Used for the starting sheets at the front door and for the FloorPlanMini block. Metres, y flipped. */

type Of<K extends Overlay['kind']> = Extract<Overlay, { kind: K }>
const flip = (p: readonly number[]): Pt => [p[0], -p[1]]
const poly = (ps: readonly (readonly number[])[]) => ps.map((p) => flip(p).join(',')).join(' ')
const mid = (ps: Pt[]): Pt => [ps.reduce((s, p) => s + p[0], 0) / ps.length, ps.reduce((s, p) => s + p[1], 0) / ps.length]

/** Where an anchor is on the plan, in metres, or null (a map anchor, another scan, an id the plan lacks). */
export function anchorPoint(plan: ScanPlan, a: Anchor | null | undefined): Pt | null {
  if (!a || !('sid' in a) || a.sid !== plan.sid) return null
  if ('point' in a) return [a.point[0], a.point[1]]
  if ('opening' in a) return plan.openings.find((o) => o.id === a.opening)?.center ?? null
  if ('room' in a) { const r = plan.rooms.find((x) => x.id === a.room); return r?.polygon.length ? mid(r.polygon) : null }
  if ('wall' in a) { const w = plan.walls.find((x) => x.id === a.wall); return w ? mid([w.a, w.b]) : null }
  const p = plan.panos.find((x) => x.id === a.pano)
  return p ? [p.position[0], p.position[1]] : null
}

function Mark({ status, r }: { status: Status; r: number }) {
  const c = `var(--${status})`
  if (status === 'pass') return <circle r={r} fill={c} stroke="var(--card)" strokeWidth={r * 0.3} />
  if (status === 'warn') return <path d={`M0 ${-r * 1.15} ${r * 1.15} ${r * 0.95}H${-r * 1.15}Z`} fill={c} stroke="var(--card)" strokeWidth={r * 0.3} />
  if (status === 'fail') return <rect x={-r} y={-r} width={r * 2} height={r * 2} fill={c} stroke="var(--card)" strokeWidth={r * 0.3} />
  return <circle r={r * 0.85} fill="var(--card)" stroke={c} strokeWidth={r * 0.4} strokeDasharray={`${r * 0.45} ${r * 0.4}`} />
}

export function Plan({ plan, overlays = [], floor, current, px = 300 }: { plan: ScanPlan; overlays?: Overlay[]; floor?: string; current?: Anchor | null; /** about how wide it is drawn, for line weights */ px?: number }) {
  const f = floor ?? plan.floors[0]?.id
  const { walls, rooms, openings, box } = useMemo(() => {
    const walls = plan.walls.filter((w) => w.floor === f && w.type !== 'invisible')
    const rooms = plan.rooms.filter((r) => r.floor === f && r.polygon.length > 2 && r.label !== 'Void')
    const all = [...walls.flatMap((w) => [w.a, w.b]), ...rooms.flatMap((r) => r.polygon)].map(flip)
    if (!all.length) return { walls, rooms, openings: [], box: [0, 0, 10, 10] }
    const xs = all.map((p) => p[0]), ys = all.map((p) => p[1]), x0 = Math.min(...xs), y0 = Math.min(...ys), w = Math.max(...xs) - x0, h = Math.max(...ys) - y0, pad = Math.max(w, h) * 0.05 + 0.3
    return { walls, rooms, openings: plan.openings.filter((o) => o.floor === f), box: [x0 - pad, y0 - pad, w + pad * 2, h + pad * 2] }
  }, [plan, f])
  const o = useMemo(() => {
    const room = new Map<string, string>(), door = new Map<string, string>()
    for (const r of overlays.filter((x): x is Of<'rule'> => x.kind === 'rule')) {
      r.select.rooms?.forEach((id) => room.set(id, r.style)); r.select.openings?.forEach((id) => door.set(id, r.style))
      r.select.room_labels?.forEach((l) => plan.rooms.forEach((x) => x.label === l && room.set(x.id, r.style)))
    }
    return {
      room, door, lens: overlays.find((x): x is Of<'lens'> => x.kind === 'lens'), water: overlays.some((x) => x.kind === 'water'),
      routes: overlays.filter((x): x is Of<'route'> => x.kind === 'route' && x.floor === f), boxes: overlays.filter((x): x is Of<'box'> => x.kind === 'box'),
      pins: overlays.flatMap((x) => (x.kind === 'pins' ? x.pins : [])),
    }
  }, [overlays, plan, f])
  const u = Math.max(box[2], box[3]) / px // one screen pixel in metres, roughly
  const cur = anchorPoint(plan, current)

  if (!walls.length && !rooms.length) return <p className="mq-plan-none">No wall outlines in this scan.</p>
  return (
    <svg className="mq-plan" viewBox={box.join(' ')} preserveAspectRatio="xMidYMid meet" role="img" aria-label={`Floor plan: ${rooms.length} rooms, ${openings.filter((x) => x.type === 'doorway').length} doorways`}>
      {rooms.map((r) => {
        const style = o.room.get(r.id), v = o.lens?.values[r.id]
        const t = o.lens && v != null ? Math.max(0, Math.min(1, (v - o.lens.legend.min) / (o.lens.legend.max - o.lens.legend.min || 1))) : null
        return <polygon key={r.id} className="mq-plan-room" data-style={style} data-wet={o.water || undefined} points={poly(r.polygon)}
          style={t != null ? { fill: `color-mix(in oklab, var(--ramp-hi) ${Math.round(t * 100)}%, var(--ramp-lo))` } : undefined} />
      })}
      {walls.map((w) => <line key={w.id} className="mq-plan-wall" x1={w.a[0]} y1={-w.a[1]} x2={w.b[0]} y2={-w.b[1]} strokeWidth={Math.max(w.thickness || 0.12, u * 1.5)} />)}
      {openings.map((x) => {
        const w = plan.walls.find((y) => y.id === x.wall)
        if (!w) return null
        const dx = w.b[0] - w.a[0], dy = w.b[1] - w.a[1], len = Math.hypot(dx, dy) || 1, h = x.width / 2
        const a = flip([x.center[0] - (dx / len) * h, x.center[1] - (dy / len) * h]), b = flip([x.center[0] + (dx / len) * h, x.center[1] + (dy / len) * h])
        const st = o.door.get(x.id)
        return (
          <g key={x.id} data-style={st}>
            <line className="mq-plan-gap" data-type={x.type} x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} strokeWidth={(w.thickness || 0.12) + u * 1.5} />
            {st && <line className="mq-plan-flag" x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} strokeWidth={u * 4.5} />}
          </g>
        )
      })}
      {o.routes.map((r, i) => (
        <g key={i}>
          <polyline className="mq-plan-tape" points={poly(r.points)} strokeWidth={u * 5.5} pathLength={1} />
          {r.chokes.map((c, j) => <g key={j} transform={`translate(${flip(c.point).join(' ')})`}><Mark status={c.status} r={u * 4.5} /></g>)}
        </g>
      ))}
      {o.boxes.map((b, i) => (
        <rect key={i} className="mq-plan-box" data-s={b.status} transform={`translate(${flip(b.center).join(' ')}) rotate(${-b.yaw_deg})`} x={-b.size[0] / 2} y={-b.size[1] / 2} width={b.size[0]} height={b.size[1]} strokeWidth={u * 1.6} />
      ))}
      {o.pins.map((p) => {
        const at = anchorPoint(plan, p.anchor)
        if (!at || (anchorFloor(plan, p.anchor) ?? f) !== f) return null
        return <g key={p.id} transform={`translate(${flip(at).join(' ')})`}><Mark status={p.status} r={u * 5} /></g>
      })}
      {cur && <circle className="mq-plan-cur" cx={cur[0]} cy={-cur[1]} r={u * 11} strokeWidth={u * 3} />}
    </svg>
  )
}
