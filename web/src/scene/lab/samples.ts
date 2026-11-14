// Sample overlays for the lab, computed from the plan itself so every number shown is a real measurement of that scan.
import { anchorPoint, buildModel, centroid } from '../model.ts'
import type { Overlay, ScanPlan, Status, Vec3 } from '../types.ts'

export const SAMPLE_KINDS = ['lens', 'status', 'rule', 'doors', 'pins', 'route', 'water', 'box', 'unknown'] as const
export type SampleKind = (typeof SAMPLE_KINDS)[number]
export const SAMPLE_LABEL: Record<SampleKind, string> = {
  lens: 'Lens: area', status: 'Lens: narrowest door', rule: 'Rule: hallways solid', doors: 'Rule: door widths', pins: 'Pins', route: 'Route', water: 'Water', box: 'Box', unknown: 'Unknown kind',
}
const CLEAR = 0.815 // metres: the usual clear width for a wheelchair

export function sampleOverlays(plan: ScanPlan, on: Set<SampleKind>, waterDepth: number): Overlay[] {
  const m = buildModel(plan), out: Overlay[] = []
  const rooms = m.plan.rooms.filter((r) => r.polygon.length > 2 && r.label !== 'Void')
  const doors = plan.openings.filter((o) => o.type !== 'window' && o.width)
  const status = (w: number): Status => (w >= CLEAR ? 'pass' : w >= 0.7 ? 'warn' : 'fail')

  if (on.has('lens')) {
    const areas = rooms.filter((r) => r.area).map((r) => r.area!)
    out.push({ kind: 'lens', values: Object.fromEntries(rooms.filter((r) => r.area).map((r) => [r.id, r.area!])), ramp: 'sequential', legend: { title: 'Floor area', unit: 'm²', min: Math.floor(Math.min(...areas)), max: Math.ceil(Math.max(...areas)) } })
  }
  if (on.has('status')) {
    const narrow = new Map<string, number>()
    for (const o of doors) for (const r of o.rooms) narrow.set(r, Math.min(narrow.get(r) ?? Infinity, o.width!))
    out.push({ kind: 'lens', values: Object.fromEntries(narrow), ramp: 'status', legend: { title: 'Narrowest door', unit: 'm', min: 0.6, max: 1 } })
  }
  if (on.has('rule')) {
    const hall = rooms.some((r) => r.label === 'Hallway')
    out.push({ kind: 'rule', select: hall ? { room_labels: ['Hallway'] } : { rooms: [...rooms].sort((a, b) => (b.area ?? 0) - (a.area ?? 0)).slice(0, 5).map((r) => r.id) }, style: 'solid' })
  }
  if (on.has('doors')) {
    for (const st of ['pass', 'warn', 'fail'] as const) out.push({ kind: 'rule', select: { openings: doors.filter((o) => status(o.width!) === st).map((o) => o.id) }, style: st })
  }
  if (on.has('pins')) {
    const narrowest = [...doors].sort((a, b) => a.width! - b.width!)[0], big = [...rooms].sort((a, b) => (b.area ?? 0) - (a.area ?? 0))
    const wall = plan.walls.find((w) => w.type !== 'invisible' && w.length > 2.5), pano = plan.panos.find((p) => p.room === big[0]?.id) ?? plan.panos[0]
    const pins: Extract<Overlay, { kind: 'pins' }>['pins'] = []
    if (big[0]) pins.push({ id: 'a', anchor: { room: big[0].id }, label: `${big[0].label ?? 'Largest room'} checked`, status: 'pass' })
    if (narrowest) pins.push({ id: 'b', anchor: { opening: narrowest.id }, label: `Narrowest doorway`, status: status(narrowest.width!) })
    if (wall) pins.push({ id: 'c', anchor: { wall: wall.id }, label: 'Wall to inspect', status: 'warn' })
    if (big[1]) { const c = centroid(big[1].polygon); pins.push({ id: 'd', anchor: { point: [c[0], c[1], m.floorZ[m.floorOf.get(big[1].floor) ?? 0] + 0.9] }, label: 'Not yet assessed', status: 'unknown' }) }
    if (pano) pins.push({ id: 'e', anchor: { pano: pano.id, yaw_deg: 40, pitch_deg: -8 }, label: 'Seen from this position', status: 'fail' })
    out.push({ kind: 'pins', pins })
  }
  if (on.has('route')) {
    const r = sampleRoute(plan)
    if (r) {
      const fz = m.floorZ[m.floorOf.get(r.floor) ?? 0]
      // a doorway the path passes through is a choke point; its width is the opening's measured width
      const chokes = doors.filter((o) => o.floor === r.floor).map((o) => ({ o, d: Math.min(...r.points.slice(1).map((b, i) => segDist(o.center, r.points[i], b))) }))
        .filter((c) => c.d < 0.45).sort((a, b) => a.o.width! - b.o.width!).slice(0, 4)
        .map(({ o }) => ({ point: [o.center[0], o.center[1], fz] as Vec3, width: o.width!, status: status(o.width!) }))
      out.push({ kind: 'route', floor: r.floor, points: r.points, chokes, label: 'Way out' })
    }
  }
  if (on.has('water')) out.push({ kind: 'water', level_m: m.floorZ[0] + waterDepth, datum: 'scan_z' })
  if (on.has('box')) {
    const big = [...rooms].sort((a, b) => (b.area ?? 0) - (a.area ?? 0))[0]
    const at = big && anchorPoint(m, { room: big.id })
    if (at) out.push({ kind: 'box', center: [at.point[0] + 0.6, at.point[1] + 0.4, m.floorZ[at.floor] + 0.4], size: [2.1, 0.95, 0.8], yaw_deg: 18, label: 'Sofa', status: 'pass' })
  }
  if (on.has('unknown')) out.push({ kind: 'sparkles', intensity: 11 }) // must be ignored by every view
  return out
}

function segDist(p: [number, number], a: Vec3, b: Vec3) {
  const dx = b[0] - a[0], dy = b[1] - a[1], L2 = dx * dx + dy * dy || 1
  const t = Math.min(1, Math.max(0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2))
  return Math.hypot(p[0] - a[0] - dx * t, p[1] - a[1] - dy * t)
}

/** The longest shortest walk between two scan positions on the lowest floor, along the neighbour links. */
function sampleRoute(plan: ScanPlan): { floor: string; points: Vec3[] } | null {
  const floor = plan.floors[0]?.id, panos = plan.panos.filter((p) => p.floor === floor && p.room)
  if (panos.length < 2) return null
  const byId = new Map(panos.map((p) => [p.id, p]))
  const bfs = (start: string) => {
    const prev = new Map<string, string | null>([[start, null]]), q = [start]
    let last = start
    while (q.length) { const id = q.shift()!; last = id; for (const n of byId.get(id)!.neighbors) if (byId.has(n) && !prev.has(n)) { prev.set(n, id); q.push(n) } }
    return { prev, last }
  }
  const a = bfs(panos[0].id).last, { prev, last } = bfs(a)
  const m = buildModel(plan), z = m.floorZ[0] + 0.02, pts: Vec3[] = []
  for (let id: string | null = last; id; id = prev.get(id) ?? null) { const p = byId.get(id)!; pts.push([p.position[0], p.position[1], z]) }
  return pts.length > 1 ? { floor, points: pts } : null
}
