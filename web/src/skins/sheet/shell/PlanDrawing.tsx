import { useEffect, useMemo, useRef, useState } from 'react'
import { anchorFloor, type Anchor, type Overlay, type Pt, type ScanPlan, type Status } from '../../../core/index.ts'

/* A floor plan drawn from the wall graph in the manner of an architect's sheet: walls at their real thickness,
   door swings, room names and areas. It stands where <BuildingScene> will go (same props) until the scene
   workstream lands, and it stays as the FloorPlanMini block. Metres, y flipped so north-ish is up. */

type PlanView = { mode: 'dollhouse' | 'plan' | 'pano'; floor?: string; focus?: Anchor | null; agentAt?: Anchor | null }
type BuildingSceneProps = { plan: ScanPlan; overlays: Overlay[]; view: PlanView; onPick: (anchor: Anchor) => void }
type Box = [x: number, y: number, w: number, h: number]
const flip = ([x, y]: Pt | [number, number, number]): Pt => [x, -y]

export function anchorPoint(plan: ScanPlan, a: Anchor | null | undefined): Pt | null {
  if (!a || !('sid' in a) || a.sid !== plan.sid) return null
  if ('point' in a) return [a.point[0], a.point[1]]
  if ('opening' in a) return plan.openings.find((o) => o.id === a.opening)?.center ?? null
  if ('room' in a) return centroid(plan.rooms.find((r) => r.id === a.room)?.polygon ?? [])
  if ('wall' in a) { const w = plan.walls.find((x) => x.id === a.wall); return w ? [(w.a[0] + w.b[0]) / 2, (w.a[1] + w.b[1]) / 2] : null }
  if ('pano' in a) { const p = plan.panos.find((x) => x.id === a.pano); return p ? [p.position[0], p.position[1]] : null }
  return null
}
function centroid(poly: Pt[]): Pt | null {
  if (!poly.length) return null
  let x = 0, y = 0
  for (const p of poly) { x += p[0]; y += p[1] }
  return [x / poly.length, y / poly.length]
}
const sameAnchor = (a: Anchor, b: Anchor) => JSON.stringify(a) === JSON.stringify(b)

function StatusMark({ status, r }: { status: Status; r: number }) {
  const c = `var(--${status})`
  if (status === 'pass') return <circle r={r} fill={c} />
  if (status === 'warn') return <path d={`M0 ${-r * 1.1} ${r * 1.1} ${r * 0.9}H${-r * 1.1}Z`} fill={c} />
  if (status === 'fail') return <rect x={-r} y={-r} width={r * 2} height={r * 2} fill={c} />
  return <circle r={r * 0.85} fill="var(--pane)" stroke={c} strokeWidth={r * 0.35} strokeDasharray={`${r * 0.4} ${r * 0.35}`} />
}

type Props = BuildingSceneProps & { mini?: boolean; selected?: Anchor | null }

export function PlanDrawing({ plan, overlays, view, onPick, mini, selected }: Props) {
  const floor = view.floor ?? plan.floors[0]?.id
  const walls = useMemo(() => plan.walls.filter((w) => w.floor === floor), [plan, floor])
  const rooms = useMemo(() => plan.rooms.filter((r) => r.floor === floor && r.polygon.length > 2), [plan, floor])
  const openings = useMemo(() => plan.openings.filter((o) => o.floor === floor), [plan, floor])

  const full = useMemo<Box>(() => {
    const pts = [...walls.flatMap((w) => [w.a, w.b]), ...rooms.flatMap((r) => r.polygon)].map(flip)
    if (!pts.length) return [0, 0, 10, 10]
    const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1])
    const x0 = Math.min(...xs), y0 = Math.min(...ys), w = Math.max(...xs) - x0, h = Math.max(...ys) - y0
    const pad = Math.max(w, h) * (mini ? 0.04 : 0.1) + 0.4
    return [x0 - pad, y0 - pad, w + pad * 2, h + pad * 2]
  }, [walls, rooms, mini])

  // Looking at an anchor means framing a few metres around it. The move is short and can be interrupted.
  const focusPt = anchorPoint(plan, view.focus)
  const target = useMemo<Box>(() => {
    if (!focusPt || mini) return full
    const [x, y] = flip(focusPt)
    const span = Math.min(Math.max(full[2], full[3]), 9)
    return [x - span / 2, y - span / 2, span, span]
  }, [focusPt?.[0], focusPt?.[1], full, mini]) // eslint-disable-line react-hooks/exhaustive-deps
  const [box, setBox] = useState<Box>(target)
  const from = useRef(box)
  from.current = box
  useEffect(() => {
    const a = from.current
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches || a.every((v, i) => Math.abs(v - target[i]) < 0.01)) { setBox(target); return }
    const t0 = performance.now()
    let raf = requestAnimationFrame(function step(t) {
      const k = Math.min(1, (t - t0) / 420), e = 1 - (1 - k) ** 4
      setBox(a.map((v, i) => v + (target[i] - v) * e) as Box)
      if (k < 1) raf = requestAnimationFrame(step)
    })
    return () => cancelAnimationFrame(raf)
  }, [target])

  // What the overlays say about each room and opening.
  const { roomStyle, openingStyle, lens, pins, routes, water, boxes } = useMemo(() => readOverlays(overlays), [overlays])
  const u = Math.max(box[2], box[3]) / (mini ? 320 : 900) // one screen pixel, roughly, in metres
  const agentPt = anchorPoint(plan, view.agentAt)
  const selPt = anchorPoint(plan, selected)

  if (!walls.length && !rooms.length) {
    return <div className="plan-empty hatch"><p>This scan has no wall outlines or room shapes to draw.</p></div>
  }
  return (
    <svg className={mini ? 'drawing mini' : 'drawing'} viewBox={box.join(' ')} preserveAspectRatio="xMidYMid meet" role="img"
      aria-label={`Floor plan of ${plan.name}: ${rooms.length} rooms, ${openings.filter((o) => o.type === 'doorway').length} doorways.`}>
      {water && <rect className="water" x={full[0]} y={full[1]} width={full[2]} height={full[3]} />}
      {rooms.map((r) => {
        const style = roomStyle.get(r.id) ?? (r.label && roomStyle.get('label:' + r.label)) ?? ''
        const v = lens?.values[r.id]
        const step = lens && v != null ? Math.max(1, Math.min(6, 1 + Math.floor(((v - lens.legend.min) / (lens.legend.max - lens.legend.min || 1)) * 5.999))) : 0
        const c = centroid(r.polygon)!
        const named = r.label && r.label !== 'Void'
        return (
          <g key={r.id} className="room" data-style={style} data-sel={selected && 'room' in selected && selected.room === r.id || undefined}
            onClick={mini ? undefined : () => onPick({ sid: plan.sid, room: r.id })}>
            <polygon points={r.polygon.map((p) => flip(p).join(',')).join(' ')} style={step ? { fill: `var(--ramp-${step})`, fillOpacity: 0.75 } : undefined} />
            {!mini && named && (r.area ?? 0) > 2.5 && style !== 'hide' && (
              <text x={flip(c)[0]} y={flip(c)[1]} fontSize={u * 10.5} textAnchor="middle">
                <tspan className="rname">{r.label!.toUpperCase()}</tspan>
                {r.area != null && <tspan className="rarea" x={flip(c)[0]} dy={u * 13}>{r.area.toFixed(1)} m²</tspan>}
              </text>
            )}
          </g>
        )
      })}
      {walls.map((w) => (
        <line key={w.id} className={w.type === 'invisible' ? 'wall ghost' : 'wall'} x1={w.a[0]} y1={-w.a[1]} x2={w.b[0]} y2={-w.b[1]}
          strokeWidth={w.type === 'invisible' ? u : Math.max(w.thickness || 0.12, u * 1.6)} />
      ))}
      {openings.map((o) => {
        const w = plan.walls.find((x) => x.id === o.wall)
        if (!w) return null
        const dx = w.b[0] - w.a[0], dy = w.b[1] - w.a[1], len = Math.hypot(dx, dy) || 1
        const ux = dx / len, uy = dy / len, h = o.width / 2
        const [ax, ay] = flip([o.center[0] - ux * h, o.center[1] - uy * h]), [bx, by] = flip([o.center[0] + ux * h, o.center[1] + uy * h])
        const st = openingStyle.get(o.id)
        const isSel = selected && 'opening' in selected && selected.opening === o.id
        // the leaf stands square to the wall at one jamb; the swing is a quarter circle to the other jamb
        const lx = ax + uy * o.width, ly = ay + ux * o.width
        return (
          <g key={o.id} className="opening" data-type={o.type} data-status={st} data-sel={isSel || undefined}
            onClick={mini ? undefined : (e) => { e.stopPropagation(); onPick({ sid: plan.sid, opening: o.id }) }}>
            <line className="gap" x1={ax} y1={ay} x2={bx} y2={by} strokeWidth={(w.thickness || 0.12) + u * 2} />
            {o.type === 'doorway' && !mini && <path className="swing" d={`M${ax} ${ay}L${lx} ${ly}A${o.width} ${o.width} 0 0 1 ${bx} ${by}`} strokeWidth={u} />}
            {o.type === 'window' && <line className="pane-line" x1={ax} y1={ay} x2={bx} y2={by} strokeWidth={u * 1.2} />}
            {st && <line className="flag" x1={ax} y1={ay} x2={bx} y2={by} strokeWidth={u * 4} />}
            {!mini && (st || isSel) && o.type === 'doorway' && (
              <text className="dimtext" x={(ax + bx) / 2 + uy * u * 16} y={(ay + by) / 2 + ux * u * 16} fontSize={u * 10} textAnchor="middle" dominantBaseline="middle">{o.width.toFixed(2)}</text>
            )}
          </g>
        )
      })}
      {routes.map((r, i) => r.floor === floor && (
        <g key={i} className="route">
          <polyline points={r.points.map((p) => flip(p).join(',')).join(' ')} strokeWidth={u * 2.4} strokeDasharray={`${u * 7} ${u * 5}`} />
          {r.chokes.map((c, j) => <g key={j} transform={`translate(${flip(c.point).join(' ')})`}><StatusMark status={c.status} r={u * 4.5} /></g>)}
        </g>
      ))}
      {boxes.map((b, i) => (
        <g key={i} className="vbox" data-status={b.status} transform={`translate(${flip(b.center).join(' ')}) rotate(${-b.yaw_deg})`}>
          <rect x={-b.size[0] / 2} y={-b.size[1] / 2} width={b.size[0]} height={b.size[1]} strokeWidth={u * 1.5} />
        </g>
      ))}
      {!mini && plan.panos.filter((p) => p.floor === floor).map((p) => <circle key={p.id} className="pano" cx={p.position[0]} cy={-p.position[1]} r={u * 1.6} />)}
      {pins.map((p, i) => {
        const pt = anchorPoint(plan, p.anchor)
        if (!pt || (anchorFloor(plan, p.anchor) ?? floor) !== floor) return null
        const isSel = selected && sameAnchor(selected, p.anchor)
        return (
          <g key={p.id} className="pin" data-sel={isSel || undefined} transform={`translate(${flip(pt).join(' ')})`}
            onClick={mini ? undefined : (e) => { e.stopPropagation(); onPick(p.anchor) }}>
            {isSel && <circle className="halo" r={u * 13} strokeWidth={u * 1.5} />}
            <StatusMark status={p.status} r={u * (mini ? 7 : 6)} />
            {!mini && <text x={u * 10} y={u * 3.5} fontSize={u * 10.5}>{i + 1}</text>}
          </g>
        )
      })}
      {selPt && !mini && <g className="sight" transform={`translate(${flip(selPt).join(' ')})`}><circle r={u * 18} strokeWidth={u * 1.2} /><path d={`M${-u * 26} 0H${-u * 10}M${u * 10} 0H${u * 26}M0 ${-u * 26}V${-u * 10}M0 ${u * 10}V${u * 26}`} strokeWidth={u * 1.2} /></g>}
      {agentPt && !mini && (
        <g className="agent" transform={`translate(${flip(agentPt).join(' ')})`}>
          <circle className="pulse" r={u * 9} strokeWidth={u * 1.2} /><circle r={u * 3.2} />
          <text x={u * 14} y={-u * 10} fontSize={u * 9.5}>AGENT</text>
        </g>
      )}
      {!mini && <g className="barscale" transform={`translate(${box[0] + box[2] - u * 26 - 5} ${box[1] + box[3] - u * 22})`}>
        <rect width={1} height={u * 4} /><rect className="odd" x={1} width={1} height={u * 4} /><rect x={2} width={3} height={u * 4} className="odd2" />
        <text x={0} y={-u * 5} fontSize={u * 9.5}>0</text><text x={5} y={-u * 5} fontSize={u * 9.5} textAnchor="middle">5 m</text>
      </g>}
    </svg>
  )
}

function readOverlays(overlays: Overlay[]) {
  const roomStyle = new Map<string, string>(), openingStyle = new Map<string, string>()
  let lens: Extract<Overlay, { kind: 'lens' }> | null = null
  const pins: Extract<Overlay, { kind: 'pins' }>['pins'] = [], routes: Extract<Overlay, { kind: 'route' }>[] = [], boxes: Extract<Overlay, { kind: 'box' }>[] = []
  let water: Extract<Overlay, { kind: 'water' }> | null = null
  for (const o of overlays) {
    if (o.kind === 'lens') lens = o
    else if (o.kind === 'rule') {
      o.select.rooms?.forEach((id) => roomStyle.set(id, o.style))
      o.select.room_labels?.forEach((l) => roomStyle.set('label:' + l, o.style))
      if (['pass', 'warn', 'fail', 'highlight'].includes(o.style)) o.select.openings?.forEach((id) => openingStyle.set(id, o.style))
    } else if (o.kind === 'pins') pins.push(...o.pins)
    else if (o.kind === 'route') routes.push(o)
    else if (o.kind === 'water') water = o
    else if (o.kind === 'box') boxes.push(o)
    // any other kind is one this renderer does not know, and is ignored
  }
  return { roomStyle, openingStyle, lens, pins, routes, water, boxes }
}

export function LensLegend({ overlays }: { overlays: Overlay[] }) {
  const lens = overlays.find((o) => o.kind === 'lens')
  if (!lens || lens.kind !== 'lens') return null
  return (
    <div className="pane lenslegend">
      <span className="label">{lens.legend.title}</span>
      <span className="steps" aria-hidden="true">{[1, 2, 3, 4, 5, 6].map((i) => <i key={i} style={{ background: `var(--ramp-${i})` }} />)}</span>
      <span className="num ends"><span>{lens.legend.min.toFixed(0)}</span><span>{lens.legend.max.toFixed(0)} {lens.legend.unit}</span></span>
    </div>
  )
}
