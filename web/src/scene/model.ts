// Pure geometry and style resolution for a ScanPlan. No three.js and no DOM here, so it runs under `node --test`.
import type { Anchor, Opening, Overlay, Pick, RuleStyle, ScanPlan, Status, Vec2, Vec3, Wall } from './types.ts'

export type RGB = [number, number, number]
export interface Palette { accent: RGB; pass: RGB; warn: RGB; fail: RGB; unknown: RGB; rampLo: RGB; rampHi: RGB }
export interface Bounds { minX: number; minY: number; maxX: number; maxY: number }

/** One style slot per element. Slot 0 is "no room"; then rooms, walls, openings in plan order. */
export interface Style { tint: RGB; amt: number; wash: number; height: number; alpha: number; outline: RGB | null }
export interface Box { floor: number; elem: number; kind: 0 | 1 | 2; cx: number; cy: number; dx: number; dy: number; s0: number; s1: number; z0: number; z1: number; t: number }

export const STUB = 0.18        // metres a dimmed wall keeps, so the plan still reads
const CAMERA_HEIGHT_GUESS = 1.45 // only used when a floor has no panoramas

export interface Model {
  plan: ScanPlan
  floorZ: number[]              // elevation of each floor in scan z, index = position in plan.floors
  floorH: number[]              // typical room height per floor
  floorOf: Map<string, number>
  bounds: Bounds; floorBounds: Bounds[]
  maxH: number
  elemCount: number
  roomElem: Map<string, number>; wallElem: Map<string, number>; openingElem: Map<string, number>
  wallById: Map<string, Wall>; openingById: Map<string, Opening>
  roomsByFloor: number[][]      // room indices per floor, largest first
  hasWalls: boolean
}

const median = (v: number[]) => { const s = [...v].sort((a, b) => a - b); return s.length ? s[s.length >> 1] : NaN }

export function buildModel(plan: ScanPlan): Model {
  const floorOf = new Map(plan.floors.map((f, i) => [f.id, i]))
  const panoZ = plan.floors.map((f) => median(plan.panos.filter((p) => p.floor === f.id).map((p) => p.position[2])))
  // The lowest floor sits at z = 0 in Matterport's frame; upper floors are offset by the tripod height difference.
  const base = Number.isFinite(panoZ[0]) ? panoZ[0] : CAMERA_HEIGHT_GUESS
  const floorH = plan.floors.map((f) => median(plan.rooms.filter((r) => r.floor === f.id && r.height).map((r) => r.height!)) || 2.6)
  let acc = 0
  const floorZ = plan.floors.map((_, i) => {
    const z = i === 0 ? 0 : Number.isFinite(panoZ[i]) ? panoZ[i] - base : acc
    acc = z + floorH[i] + 0.3
    return z
  })
  const empty = (): Bounds => ({ minX: Infinity, minY: Infinity, maxX: -Infinity, maxY: -Infinity })
  const floorBounds = plan.floors.map(empty)
  const grow = (b: Bounds | undefined, x: number, y: number) => { if (b) { b.minX = Math.min(b.minX, x); b.minY = Math.min(b.minY, y); b.maxX = Math.max(b.maxX, x); b.maxY = Math.max(b.maxY, y) } }
  for (const w of plan.walls) { grow(floorBounds[floorOf.get(w.floor)!], ...w.a); grow(floorBounds[floorOf.get(w.floor)!], ...w.b) }
  for (const r of plan.rooms) for (const p of r.polygon) grow(floorBounds[floorOf.get(r.floor)!], ...p)
  for (const p of plan.panos) grow(floorBounds[floorOf.get(p.floor ?? '')!], p.position[0], p.position[1])
  const bounds = empty()
  for (const b of floorBounds) if (Number.isFinite(b.minX)) { grow(bounds, b.minX, b.minY); grow(bounds, b.maxX, b.maxY) }
  if (!Number.isFinite(bounds.minX)) Object.assign(bounds, { minX: -5, minY: -5, maxX: 5, maxY: 5 })
  for (const b of floorBounds) if (!Number.isFinite(b.minX)) Object.assign(b, bounds)
  const R = plan.rooms.length, W = plan.walls.length
  return {
    plan, floorZ, floorH, floorOf, bounds, floorBounds,
    maxH: Math.max(2.4, ...plan.rooms.map((r) => r.height ?? 0)),
    elemCount: 1 + R + W + plan.openings.length,
    roomElem: new Map(plan.rooms.map((r, i) => [r.id, 1 + i])),
    wallElem: new Map(plan.walls.map((w, i) => [w.id, 1 + R + i])),
    openingElem: new Map(plan.openings.map((o, i) => [o.id, 1 + R + W + i])),
    wallById: new Map(plan.walls.map((w) => [w.id, w])),
    openingById: new Map(plan.openings.map((o) => [o.id, o])),
    roomsByFloor: plan.floors.map((f) => plan.rooms.map((r, i) => [r, i] as const).filter(([r]) => r.floor === f.id && r.polygon.length > 2)
      .sort((a, b) => polygonArea(b[0].polygon) - polygonArea(a[0].polygon)).map(([, i]) => i)),
    hasWalls: plan.walls.some((w) => w.type !== 'invisible'),
  }
}

export function polygonArea(p: Vec2[]): number {
  let a = 0
  for (let i = 0; i < p.length; i++) { const q = p[(i + 1) % p.length]; a += p[i][0] * q[1] - q[0] * p[i][1] }
  return Math.abs(a) / 2
}

export function centroid(p: Vec2[]): Vec2 {
  let a = 0, x = 0, y = 0
  for (let i = 0; i < p.length; i++) {
    const q = p[(i + 1) % p.length], c = p[i][0] * q[1] - q[0] * p[i][1]
    a += c; x += (p[i][0] + q[0]) * c; y += (p[i][1] + q[1]) * c
  }
  return Math.abs(a) < 1e-9 ? p[0] ?? [0, 0] : [x / (3 * a), y / (3 * a)]
}

export function pointInPolygon(x: number, y: number, p: Vec2[]): boolean {
  let inside = false
  for (let i = 0, j = p.length - 1; i < p.length; j = i++) {
    if ((p[i][1] > y) !== (p[j][1] > y) && x < ((p[j][0] - p[i][0]) * (y - p[i][1])) / (p[j][1] - p[i][1]) + p[i][0]) inside = !inside
  }
  return inside
}

/** Index of the smallest room on this floor that contains the point, or -1. */
export function roomAt(m: Model, floor: number, x: number, y: number): number {
  const list = m.roomsByFloor[floor] ?? []
  for (let i = list.length - 1; i >= 0; i--) if (pointInPolygon(x, y, m.plan.rooms[list[i]].polygon)) return list[i]
  return -1
}

export function wallHeight(m: Model, w: Wall): number {
  const hs = w.rooms.map((id) => m.plan.rooms[m.roomElem.get(id)! - 1]?.height ?? 0)
  return Math.max(...hs, 0) || m.floorH[m.floorOf.get(w.floor) ?? 0] || 2.6
}

/** Where an opening sits on its wall: unit direction, clamped start and end along the wall, sill and head. */
export function openingSpan(m: Model, o: Opening) {
  const w = m.wallById.get(o.wall)!
  const L = w.length || 1e-6, dx = (w.b[0] - w.a[0]) / L, dy = (w.b[1] - w.a[1]) / L
  const s = (o.center[0] - w.a[0]) * dx + (o.center[1] - w.a[1]) * dy, half = (o.width ?? 0.8) / 2
  const sill = Math.max(0, o.sill ?? 0), H = wallHeight(m, w)
  return { w, dx, dy, s0: Math.max(0, s - half), s1: Math.min(L, s + half), sill, head: Math.min(H, sill + (o.height ?? 2.03)), H }
}

/** Every wall as boxes in its floor's own z (0 = floor): solid runs, sills under windows, lintels, glass panes, thresholds. */
export function wallBoxes(m: Model): Box[] {
  const out: Box[] = []
  for (const w of m.plan.walls) {
    if (w.type === 'invisible' || w.length < 1e-4) continue
    const floor = m.floorOf.get(w.floor) ?? 0, elem = m.wallElem.get(w.id)!, t = w.thickness || 0.1, H = wallHeight(m, w)
    const dx = (w.b[0] - w.a[0]) / w.length, dy = (w.b[1] - w.a[1]) / w.length
    const base = { floor, cx: w.a[0], cy: w.a[1], dx, dy, t }
    const spans = w.openings.map((id) => m.openingById.get(id)).filter((o): o is Opening => !!o)
      .map((o) => ({ o, ...openingSpan(m, o) })).filter((s) => s.s1 - s.s0 > 0.02).sort((a, b) => a.s0 - b.s0)
    let at = -t / 2 // run past each end by half the thickness so corners close
    for (const sp of spans) {
      if (sp.s0 > at + 1e-3) out.push({ ...base, elem, kind: 0, s0: at, s1: sp.s0, z0: 0, z1: H })
      if (sp.sill > 0.05) out.push({ ...base, elem, kind: 0, s0: sp.s0, s1: sp.s1, z0: 0, z1: sp.sill })
      if (sp.head < H - 0.02) out.push({ ...base, elem, kind: 0, s0: sp.s0, s1: sp.s1, z0: sp.head, z1: H })
      const oe = m.openingElem.get(sp.o.id)!
      if (sp.o.type === 'window') out.push({ ...base, elem: oe, kind: 1, s0: sp.s0, s1: sp.s1, z0: sp.sill, z1: sp.head, t: 0.02 })
      else out.push({ ...base, elem: oe, kind: 2, s0: sp.s0, s1: sp.s1, z0: 0, z1: 0.012, t })
      at = Math.max(at, sp.s1)
    }
    if (w.length + t / 2 > at + 1e-3) out.push({ ...base, elem, kind: 0, s0: at, s1: w.length + t / 2, z0: 0, z1: H })
  }
  return out
}

/** World position (scan frame, before floors are pulled apart) and floor index for an anchor. */
export function anchorPoint(m: Model, a: Anchor): { point: Vec3; floor: number } | null {
  const fz = (id: string | null | undefined) => m.floorOf.get(id ?? '') ?? 0
  if ('point' in a) {
    let floor = 0
    m.floorZ.forEach((z, i) => { if (a.point[2] >= z - 0.3) floor = i })
    return { point: a.point, floor }
  }
  if ('room' in a) {
    const r = m.plan.rooms[(m.roomElem.get(a.room) ?? 0) - 1]
    if (!r) return null
    const floor = fz(r.floor)
    const pano = m.plan.panos.find((p) => p.room === r.id)
    const c = r.polygon.length > 2 ? centroid(r.polygon) : pano ? [pano.position[0], pano.position[1]] : null
    return c && { point: [c[0], c[1], m.floorZ[floor] + 0.05], floor }
  }
  if ('opening' in a) {
    const o = m.openingById.get(a.opening)
    if (!o) return null
    const floor = fz(o.floor), sp = openingSpan(m, o)
    return { point: [o.center[0], o.center[1], m.floorZ[floor] + (sp.sill + sp.head) / 2], floor }
  }
  if ('wall' in a) {
    const w = m.wallById.get(a.wall)
    if (!w) return null
    const floor = fz(w.floor)
    return { point: [(w.a[0] + w.b[0]) / 2, (w.a[1] + w.b[1]) / 2, m.floorZ[floor] + Math.min(1.4, wallHeight(m, w) * 0.6)], floor }
  }
  if ('pano' in a) {
    const p = m.plan.panos.find((q) => q.id === a.pano)
    if (!p) return null
    const yaw = (a.yaw_deg * Math.PI) / 180, pitch = (a.pitch_deg * Math.PI) / 180
    const dir: Vec3 = [Math.cos(pitch) * Math.cos(yaw), Math.cos(pitch) * Math.sin(yaw), Math.sin(pitch)]
    // Walk the ray to the first wall it meets on this floor (walls as vertical planes), capped at 6 m.
    let t = 6
    for (const w of m.plan.walls) {
      if (w.floor !== p.floor || w.type === 'invisible') continue
      const ex = w.b[0] - w.a[0], ey = w.b[1] - w.a[1], den = dir[0] * ey - dir[1] * ex
      if (Math.abs(den) < 1e-9) continue
      const ox = w.a[0] - p.position[0], oy = w.a[1] - p.position[1]
      const tt = (ox * ey - oy * ex) / den, u = (ox * dir[1] - oy * dir[0]) / den
      if (tt > 0.05 && u >= 0 && u <= 1) t = Math.min(t, tt)
    }
    const floor = fz(p.floor), fzv = m.floorZ[floor]
    if (dir[2] < -1e-3) t = Math.min(t, (fzv - p.position[2]) / dir[2])
    t = Math.max(0.3, t - 0.03)
    return { point: [p.position[0] + dir[0] * t, p.position[1] + dir[1] * t, p.position[2] + dir[2] * t], floor }
  }
  return null
}

const mix = (a: RGB, b: RGB, t: number): RGB => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t]

/** Colour for a lens value already normalised to 0..1. "status" runs fail, warn, pass from low to high. */
export function rampColor(t: number, ramp: 'sequential' | 'status', pal: Palette): RGB {
  t = Math.min(1, Math.max(0, t))
  if (ramp === 'status') return t < 0.5 ? mix(pal.fail, pal.warn, t * 2) : mix(pal.warn, pal.pass, t * 2 - 1)
  return mix(pal.rampLo, pal.rampHi, t)
}

export const statusColor = (s: Status | RuleStyle | string, pal: Palette): RGB =>
  s === 'pass' ? pal.pass : s === 'warn' ? pal.warn : s === 'fail' ? pal.fail : s === 'highlight' ? pal.accent : pal.unknown

export const isKnownOverlay = (o: Overlay): boolean => ['lens', 'rule', 'pins', 'route', 'water', 'box'].includes(o.kind)

/**
 * The look of every room, wall and opening after lenses, rules, hover and selection.
 * A rule with style "solid" makes everything it does not select dim ("only hallways solid").
 */
export function resolveStyles(m: Model, overlays: Overlay[], pal: Palette, hover: Pick | null, selected: Pick | null): Style[] {
  const { plan } = m
  const rules = overlays.filter((o): o is Extract<Overlay, { kind: 'rule' }> => o.kind === 'rule' && !!o.select)
  const focus = rules.some((r) => r.style === 'solid')
  const blank = (): Style => ({ tint: [0, 0, 0], amt: 0, wash: 0, height: 1, alpha: 1, outline: null })
  const styles = Array.from({ length: m.elemCount }, blank)
  const roomStyle = (id: string) => styles[m.roomElem.get(id) ?? -1]
  if (focus) plan.rooms.forEach((r) => Object.assign(roomStyle(r.id), { wash: 0.86, height: 0 }))

  for (const o of overlays) {
    if (o.kind !== 'lens' || !o.values) continue
    const lens = o as Extract<Overlay, { kind: 'lens' }>
    const span = (lens.legend?.max ?? 1) - (lens.legend?.min ?? 0) || 1
    for (const r of plan.rooms) {
      const v = lens.values[r.id], s = roomStyle(r.id)
      if (typeof v === 'number') Object.assign(s, { tint: rampColor((v - (lens.legend?.min ?? 0)) / span, lens.ramp, pal), amt: 0.84 })
      else s.wash = Math.max(s.wash, 0.7)
    }
  }

  const apply = (s: Style | undefined, style: RuleStyle, strong: boolean) => {
    if (!s) return
    if (style === 'solid') Object.assign(s, { wash: 0, height: 1, alpha: 1 })
    else if (style === 'dim') Object.assign(s, { wash: 0.86, height: 0 })
    else if (style === 'hide') s.alpha = 0
    else { const c = statusColor(style, pal); Object.assign(s, { tint: c, amt: strong ? 0.92 : style === 'highlight' ? 0.34 : 0.5, outline: c }) }
  }
  for (const r of rules) {
    const labels = new Set((r.select.room_labels ?? []).map((l) => l.toLowerCase()))
    const ids = new Set(r.select.rooms ?? [])
    for (const room of plan.rooms) if (ids.has(room.id) || (room.label && labels.has(room.label.toLowerCase()))) apply(roomStyle(room.id), r.style, false)
    for (const id of r.select.walls ?? []) apply(styles[m.wallElem.get(id) ?? -1], r.style, true)
    for (const id of r.select.openings ?? []) apply(styles[m.openingElem.get(id) ?? -1], r.style, true)
  }

  // A wall stands as tall, and stays as visible, as the most present room it borders, unless a rule set it directly.
  const direct = new Set(rules.flatMap((r) => r.select.walls ?? []))
  for (const w of plan.walls) {
    const s = styles[m.wallElem.get(w.id)!], rs = w.rooms.map(roomStyle).filter(Boolean)
    if (!rs.length || direct.has(w.id)) continue
    s.height = Math.max(...rs.map((r) => (r.alpha > 0 ? r.height : 0)))
    s.alpha = Math.max(...rs.map((r) => r.alpha))
  }
  for (const o of plan.openings) { // glass and thresholds follow their wall down
    const ws = styles[m.wallElem.get(o.wall)!], os = styles[m.openingElem.get(o.id)!]
    if (ws) { os.alpha = ws.alpha; os.height = ws.height }
  }

  const mark = (p: Pick | null, amt: number) => {
    if (!p || p.kind === 'pano' || p.kind === 'pin') return
    const s = styles[(p.kind === 'room' ? m.roomElem : p.kind === 'wall' ? m.wallElem : m.openingElem).get(p.id) ?? -1]
    if (!s) return
    if (s.amt < 0.05) s.tint = pal.accent
    s.amt = Math.max(s.amt, p.kind === 'room' ? amt : 0.9)
    s.outline = pal.accent
  }
  mark(hover, 0.14)
  mark(selected, 0.24)
  return styles
}

/** True when a wall stands between two points on a floor. Openings let the line of sight through. */
export function sightBlocked(m: Model, floorId: string, ax: number, ay: number, bx: number, by: number, skipWall?: string): boolean {
  const dx = bx - ax, dy = by - ay
  for (const w of m.plan.walls) {
    if (w.floor !== floorId || w.type === 'invisible' || w.id === skipWall) continue
    const ex = w.b[0] - w.a[0], ey = w.b[1] - w.a[1], den = dx * ey - dy * ex
    if (Math.abs(den) < 1e-9) continue
    const t = ((w.a[0] - ax) * ey - (w.a[1] - ay) * ex) / den, u = ((w.a[0] - ax) * dy - (w.a[1] - ay) * dx) / den
    if (t < 0.02 || t > 0.97 || u < 0 || u > 1) continue
    const s = u * w.length
    if (!w.openings.some((id) => { const o = m.openingById.get(id); if (!o) return false; const sp = openingSpan(m, o); return s >= sp.s0 && s <= sp.s1 })) return true
  }
  return false
}

/** Depth of water over a floor, in metres. Zero or less means dry. */
export const waterDepth = (m: Model, floor: number, level: number) => level - m.floorZ[floor]

export const fmtM = (v: number) => `${v.toFixed(2)} m`
