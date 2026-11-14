// A crisp 2D plan drawn from the wall graph, with the same overlays and the same hover and selection as the 3D views.
// Drawn in metres with y flipped (SVG y runs down); one transform on the root group places it, so panning costs nothing.
import { useEffect, useImperativeHandle, useLayoutEffect, useMemo, useRef, useState, type Ref } from 'react'
import { anchorPoint, buildModel, centroid, fmtM, isKnownOverlay, openingSpan, resolveStyles, statusColor, waterDepth, type Model, type RGB } from './model.ts'
import { useSceneLink } from './store.ts'
import { hex, readTokens, type Tokens } from './tokens.ts'
import type { Overlay, Pick, ScanPlan, Status } from './types.ts'

export interface FloorPlanHandle {
  /** Place the plan: pixels per metre and the pixel position of the scan origin. */
  set(scale: number, tx: number, ty: number): void
  /** Point the view cone. `null` hides it. */
  cone(look: { x: number; y: number; yaw: number; fov: number } | null): void
}
export interface FloorPlanProps {
  plan: ScanPlan; model?: Model; overlays?: Overlay[]
  floor?: string | null     // defaults to the lowest floor
  measures?: boolean        // opening widths
  compact?: boolean         // inset size: no text, no pins
  pano?: string | null      // current scan position
  driven?: boolean          // the parent places it through `handle`; otherwise it fits its own box
  handle?: Ref<FloorPlanHandle>
  onPick?: (p: Pick) => void
  className?: string
}
type Of<K extends string> = Extract<Overlay, { kind: K }>
const mixHex = (a: RGB, b: RGB, t: number) => hex([0, 1, 2].map((i) => a[i] + (b[i] - a[i]) * t) as RGB)
const n = (v: number) => +v.toFixed(3)

export function FloorPlan({ plan, model, overlays = [], floor, measures, compact, pano, driven, handle, onPick, className }: FloorPlanProps) {
  const svg = useRef<SVGSVGElement>(null), root = useRef<SVGGElement>(null), cone = useRef<SVGGElement>(null)
  const scaleRef = useRef(0)
  const m = useMemo(() => model ?? buildModel(plan), [plan, model])
  const [tok, setTok] = useState<Tokens | null>(null)
  const hover = useSceneLink((s) => s.hover), selected = useSceneLink((s) => s.selected)
  const { setHover, setSelected } = useSceneLink.getState()
  const fIdx = (floor && m.floorOf.get(floor)) || 0, fid = plan.floors[fIdx]?.id
  const known = useMemo(() => overlays.filter(isKnownOverlay), [overlays])
  const down = useRef<[number, number]>([0, 0])

  const place = (s: number, tx: number, ty: number) => {
    root.current?.setAttribute('transform', `translate(${tx.toFixed(2)} ${ty.toFixed(2)}) scale(${s.toFixed(4)})`)
    if (Math.abs(s - scaleRef.current) / s < 0.02) return // text and hairlines only need care when the zoom changes
    scaleRef.current = s
    const el = svg.current!
    el.style.setProperty('--k', String(1 / s))
    el.querySelectorAll<SVGGElement>('[data-span]').forEach((g) => { g.style.display = Number(g.dataset.span) * s >= Number(g.dataset.min ?? 54) ? '' : 'none' })
  }
  const aim: FloorPlanHandle['cone'] = (look) => {
    const g = cone.current
    if (!g) return
    g.style.display = look ? '' : 'none'
    if (look) g.setAttribute('transform', `translate(${n(look.x)} ${n(-look.y)}) rotate(${n((-look.yaw * 180) / Math.PI)})`)
  }
  useImperativeHandle(handle, () => ({ set: place, cone: aim }))

  useLayoutEffect(() => { // on its own, the plan fits its box
    const el = svg.current
    if (!el || driven) return
    const fit = () => {
      const r = el.getBoundingClientRect(), b = m.floorBounds[fIdx], pad = compact ? 0.8 : 1.6
      if (!r.width || !r.height) return
      const s = Math.min(r.width / (b.maxX - b.minX + pad * 2), r.height / (b.maxY - b.minY + pad * 2))
      scaleRef.current = 0
      place(s, r.width / 2 - (s * (b.minX + b.maxX)) / 2, r.height / 2 + (s * (b.minY + b.maxY)) / 2)
    }
    fit()
    const ro = new ResizeObserver(fit); ro.observe(el)
    return () => ro.disconnect()
  }, [m, fIdx, driven, compact])
  useEffect(() => { scaleRef.current = 0 }, [m, fIdx, measures, known]) // new labels need a fresh visibility pass

  useLayoutEffect(() => setTok(readTokens(svg.current!)), [])
  const styles = useMemo(() => (tok ? resolveStyles(m, known, tok, hover, selected) : null), [m, known, tok, hover, selected])

  const pick = (p: Pick) => (e: React.MouseEvent) => {
    if (Math.hypot(e.clientX - down.current[0], e.clientY - down.current[1]) > 5) return // that was a pan, not a click
    e.stopPropagation(); if (p.kind !== 'pano') setSelected(p); onPick?.(p)
  }
  const over = (p: Pick | null) => () => setHover(p)

  const body = useMemo(() => {
    if (!tok || !styles) return null
    const paper = tok.paper, ink = tok.ink
    const rooms = plan.rooms.filter((r) => r.floor === fid && r.polygon.length > 2)
    const walls = plan.walls.filter((w) => w.floor === fid)
    const water = known.find((o): o is Of<'water'> => o.kind === 'water' && typeof (o as Of<'water'>).level_m === 'number')
    const depth = water ? waterDepth(m, fIdx, water.level_m) : 0
    const b = m.floorBounds[fIdx]
    return (
      <>
        <g className="fp-rooms">
          {rooms.map((r) => {
            const s = styles[m.roomElem.get(r.id)!]
            if (s.alpha < 0.5) return null
            const base = mixHex(paper, tok.stage, s.wash * 0.9)
            return <path key={r.id} d={`M${r.polygon.map((p) => `${n(p[0])} ${n(-p[1])}`).join('L')}Z`} fill={s.amt > 0.02 ? mixHex(paper, s.tint, Math.min(1, s.amt * 1.05)) : base}
              stroke={s.outline ? hex(s.outline) : 'none'} className="fp-room" onPointerEnter={over({ kind: 'room', id: r.id, point: [0, 0, 0] })} onPointerLeave={over(null)}
              onClick={pick({ kind: 'room', id: r.id, point: [...centroid(r.polygon), m.floorZ[fIdx]] })} />
          })}
        </g>
        {depth > 0.005 && <rect className="fp-water" x={b.minX - 1} y={-b.maxY - 1} width={b.maxX - b.minX + 2} height={b.maxY - b.minY + 2} fill={hex(tok.water)} />}
        <g className="fp-walls">
          {walls.map((w) => {
            const s = styles[m.wallElem.get(w.id)!], L = w.length || 1, dx = (w.b[0] - w.a[0]) / L, dy = (w.b[1] - w.a[1]) / L, t = w.thickness || 0.1
            if (s.alpha < 0.5) return null
            const at = (d: number, off = 0) => `${n(w.a[0] + dx * d - dy * off)} ${n(-(w.a[1] + dy * d + dx * off))}`
            if (w.type === 'invisible') return <path key={w.id} d={`M${at(0)}L${at(L)}`} className="fp-invisible" />
            const spans = w.openings.map((id) => m.openingById.get(id)).filter((o) => !!o).map((o) => ({ o: o!, ...openingSpan(m, o!) })).sort((a, c) => a.s0 - c.s0)
            let d = '', cur = -t / 2
            for (const sp of spans) { if (sp.s0 > cur) d += `M${at(cur)}L${at(sp.s0)}`; cur = Math.max(cur, sp.s1) }
            if (L + t / 2 > cur) d += `M${at(cur)}L${at(L + t / 2)}`
            // dimension text goes on the side away from the room when the wall has only one (an outside wall)
            const own = w.rooms.length === 1 ? plan.rooms[m.roomElem.get(w.rooms[0])! - 1] : null
            const rc = own && own.polygon.length > 2 ? centroid(own.polygon) : null
            const side = rc && (rc[0] - w.a[0]) * -dy + (rc[1] - w.a[1]) * dx > 0 ? -1 : 1
            const colour = s.amt > 0.5 ? hex(s.tint) : s.height < 0.5 ? mixHex(ink, tok.stage, 0.62) : hex(ink)
            const pk: Pick = { kind: 'wall', id: w.id, point: [(w.a[0] + w.b[0]) / 2, (w.a[1] + w.b[1]) / 2, m.floorZ[fIdx]] }
            return (
              <g key={w.id}>
                <path d={d} className="fp-wall" stroke={colour} style={{ ['--t' as string]: `${t}px` }} />
                {!compact && <path d={d} className="fp-hit" onPointerEnter={over(pk)} onPointerLeave={over(null)} onClick={pick(pk)} />}
                {spans.map(({ o, s0, s1 }) => {
                  const os = styles[m.openingElem.get(o.id)!], hot = os.amt > 0.5
                  const pk2: Pick = { kind: 'opening', id: o.id, point: [o.center[0], o.center[1], m.floorZ[fIdx]] }
                  return (
                    <g key={o.id} className={`fp-opening${hot ? ' fp-hot' : ''}`} style={hot ? { color: hex(os.tint) } : undefined}>
                      {o.type === 'window'
                        ? <><path d={`M${at(s0, -t / 2)}L${at(s1, -t / 2)}L${at(s1, t / 2)}L${at(s0, t / 2)}Z`} className="fp-window" fill={hex(paper)} /><path d={`M${at(s0)}L${at(s1)}`} className="fp-window" /></>
                        : <path d={`M${at(s0)}L${at(s1)}`} className="fp-door" />}
                      {!compact && <path d={`M${at(s0)}L${at(s1)}`} className="fp-hit" onPointerEnter={over(pk2)} onPointerLeave={over(null)} onClick={pick(pk2)} />}
                      {measures && !compact && o.width && (
                        <g transform={`translate(${at((s0 + s1) / 2, side * (t / 2))})`} data-span={o.width} data-min={22}>
                          <g className="fp-unscale"><text className="fp-measure" textAnchor="middle" x={n(-dy * side * 11)} y={n(-dx * side * 11)} dy="0.34em">{o.width.toFixed(2)}</text></g>
                        </g>
                      )}
                    </g>
                  )
                })}
              </g>
            )
          })}
        </g>
        <g className="fp-panos">
          {plan.panos.filter((p) => p.floor === fid).map((p) => (
            <g key={p.id} transform={`translate(${n(p.position[0])} ${n(-p.position[1])})`} className={`fp-pano${p.id === pano ? ' fp-current' : ''}${hover?.kind === 'pano' && hover.id === p.id ? ' fp-hover' : ''}`}
              onPointerEnter={over({ kind: 'pano', id: p.id })} onPointerLeave={over(null)} onClick={pick({ kind: 'pano', id: p.id })}>
              <circle className="fp-unscale fp-hitdot" r={compact ? 4 : 7} /><circle className="fp-unscale fp-dot" r={p.id === pano ? 4 : compact ? 1.2 : 2.2} />
            </g>
          ))}
        </g>
        {!compact && (
          <g className="fp-labels">
            {rooms.filter((r) => r.label !== 'Void' && styles[m.roomElem.get(r.id)!].alpha > 0.5).map((r) => {
              const c = centroid(r.polygon)
              return (
                <g key={r.id} transform={`translate(${n(c[0])} ${n(-c[1])})`} data-span={Math.sqrt(r.area ?? 4)} data-min={r.label ? 58 : 70}>
                  <text className="fp-unscale fp-name" textAnchor="middle">
                    {r.label && <tspan x="0" dy="-0.15em">{r.label}</tspan>}
                    {r.area && <tspan x="0" dy={r.label ? '1.25em' : '0.35em'} className="fp-num">{r.area.toFixed(1)} m²</tspan>}
                  </text>
                </g>
              )
            })}
          </g>
        )}
        <g className="fp-overlays">
          {known.map((ov, oi) => {
            if (ov.kind === 'route') {
              const r = ov as Of<'route'>
              if (r.floor !== fid || !Array.isArray(r.points) || r.points.length < 2) return null
              const d = `M${r.points.map((p) => `${n(p[0])} ${n(-p[1])}`).join('L')}`
              return (
                <g key={oi} className="fp-route">
                  <path d={d} className="fp-casing" /><path d={d} className="fp-core" />
                  {(r.chokes ?? []).map((c, ci) => (
                    <g key={ci} transform={`translate(${n(c.point[0])} ${n(-c.point[1])})`} style={{ color: hex(statusColor(c.status, tok)) }}>
                      <circle r={c.width / 2} className="fp-choke" />
                      {!compact && <g className="fp-unscale"><Tag status={c.status} text={fmtM(c.width)} y={-16} /></g>}
                    </g>
                  ))}
                </g>
              )
            }
            if (ov.kind === 'box') {
              const bx = ov as Of<'box'>
              if (!Array.isArray(bx.center) || !Array.isArray(bx.size) || anchorPoint(m, { point: bx.center })?.floor !== fIdx) return null
              return (
                <g key={oi} transform={`translate(${n(bx.center[0])} ${n(-bx.center[1])}) rotate(${-(bx.yaw_deg ?? 0)})`} style={{ color: hex(statusColor(bx.status, tok)) }}>
                  <rect x={-bx.size[0] / 2} y={-bx.size[1] / 2} width={bx.size[0]} height={bx.size[1]} className="fp-box" />
                  {!compact && <g className="fp-unscale" transform={`rotate(${bx.yaw_deg ?? 0})`}><Tag status={bx.status} text={`${bx.label ?? 'Object'}  ${bx.size[0].toFixed(2)} × ${bx.size[1].toFixed(2)} m`} y={-18} /></g>}
                </g>
              )
            }
            if (ov.kind === 'pins') {
              return ((ov as Of<'pins'>).pins ?? []).map((p, i) => {
                const at = anchorPoint(m, p.anchor)
                if (!at || at.floor !== fIdx) return null
                return (
                  <g key={`${oi}.${p.id}`} transform={`translate(${n(at.point[0])} ${n(-at.point[1])})`} className="fp-pin" data-status={p.status} onClick={pick({ kind: 'pin', id: p.id })}>
                    <g className="fp-unscale">
                      <PinMark status={p.status} r={compact ? 4 : 9} />
                      {!compact && <><text className="fp-pin-n" textAnchor="middle" dy="0.34em">{i + 1}</text><text className="fp-pin-label" x={14} dy="0.34em">{p.label}</text></>}
                    </g>
                  </g>
                )
              })
            }
            return null
          })}
          {depth > 0.005 && !compact && rooms.filter((r) => r.label !== 'Void').sort((a, c) => (c.area ?? 0) - (a.area ?? 0)).slice(0, 3).map((r) => {
            const c = centroid(r.polygon)
            return <g key={r.id} transform={`translate(${n(c[0])} ${n(-c[1])})`}><g className="fp-unscale"><Tag status={null} text={`depth ${fmtM(depth)}`} y={22} /></g></g>
          })}
        </g>
        <g ref={cone} className="fp-cone" style={{ display: 'none' }}><path className="fp-unscale" d="M0 0L38 -17A42 42 0 0 1 38 17Z" /></g>
      </>
    )
  }, [tok, styles, plan, m, fid, fIdx, known, measures, compact, pano, hover]) // eslint-disable-line

  return (
    <svg ref={svg} className={`th-plan-svg${compact ? ' fp-compact' : ''} ${className ?? ''}`} role="img" aria-label={`Floor plan, ${plan.floors[fIdx]?.label ?? 'floor'}`}
      onPointerDown={(e) => (down.current = [e.clientX, e.clientY])}>
      <g ref={root}>{body}</g>
    </svg>
  )
}

/** Status shape: a circle passes, a diamond warns, a square fails, a ring is unknown. Colour is never the only signal. */
function PinMark({ status, r }: { status: Status; r: number }) {
  const cls = `fp-mark fp-${status}`
  if (status === 'warn') return <rect className={cls} x={-r} y={-r} width={r * 2} height={r * 2} rx={1.5} transform="rotate(45) scale(0.86)" />
  if (status === 'fail') return <rect className={cls} x={-r} y={-r} width={r * 2} height={r * 2} rx={2} transform="scale(0.9)" />
  return <circle className={cls} r={r} />
}

function Tag({ status, text, y }: { status: Status | null; text: string; y: number }) {
  const w = text.length * 6.3 + (status ? 22 : 12)
  return (
    <g transform={`translate(${-w / 2} ${y - 9})`} className="fp-tag">
      <rect width={w} height={18} rx={3} />
      {status && <g transform="translate(10 9)"><PinMark status={status} r={3.5} /></g>}
      <text x={status ? 18 : 6} y={9} dy="0.34em" className="fp-num">{text}</text>
    </g>
  )
}
