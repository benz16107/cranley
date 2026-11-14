// Furniture a person tries out on the plan: what each piece touches or blocks. Pure geometry on the ScanPlan, run in
// the browser on every drag; nothing here asks the server. No three.js and no DOM, so it runs under `node --test`.
import { centroid, openingSpan, pointInPolygon, roomAt, type Model } from './model.ts'
import type { FurnishCheck, Overlay, Placed, Status, Vec2, Vec3 } from './types.ts'

type Stood = Placed & { center: Vec3 } // a piece that has its place

export const TURN_M = 1.525   // the 60 in wheelchair turning circle, ADA 2010 section 304.3.1; the server's turning_space uses the same
const SWING_MAX_M = 1.3       // a doorway wider than this is a garage or double door: no single leaf swings across it
const REACH_M = 6             // a side with no wall this close gets no dimension
const SIDES = [['right', 1, 0], ['back', 0, 1], ['left', -1, 0], ['front', 0, -1]] as const // a piece's front faces its own -y

type Seg = { a: Vec2; b: Vec2; half: number }
const sub = (p: Vec2, q: Vec2): Vec2 => [p[0] - q[0], p[1] - q[1]]
const cross = (p: Vec2, q: Vec2) => p[0] * q[1] - p[1] * q[0]

/** The piece's four corners on the floor, counter-clockwise. */
export function footprint(p: Stood): Vec2[] {
  const a = (p.yaw_deg * Math.PI) / 180, c = Math.cos(a), s = Math.sin(a), hx = p.size[0] / 2, hy = p.size[1] / 2
  return ([[-hx, -hy], [hx, -hy], [hx, hy], [-hx, hy]] as Vec2[]).map(([x, y]) => [p.center[0] + x * c - y * s, p.center[1] + x * s + y * c])
}

function pointSeg(p: Vec2, a: Vec2, b: Vec2): number {
  const d = sub(b, a), l2 = d[0] * d[0] + d[1] * d[1], t = l2 ? Math.min(1, Math.max(0, ((p[0] - a[0]) * d[0] + (p[1] - a[1]) * d[1]) / l2)) : 0
  return Math.hypot(p[0] - a[0] - d[0] * t, p[1] - a[1] - d[1] * t)
}
const segsCross = (a: Vec2, b: Vec2, c: Vec2, d: Vec2) => cross(sub(b, a), sub(c, a)) * cross(sub(b, a), sub(d, a)) < 0 && cross(sub(d, c), sub(a, c)) * cross(sub(d, c), sub(b, c)) < 0

/** Distance from a convex outline to a segment; 0 when they touch or the segment is inside. */
export function polySeg(poly: Vec2[], a: Vec2, b: Vec2): number {
  if (pointInPolygon(a[0], a[1], poly) || pointInPolygon(b[0], b[1], poly)) return 0
  let d = Infinity
  for (let i = 0; i < poly.length; i++) {
    const p = poly[i], q = poly[(i + 1) % poly.length]
    if (segsCross(p, q, a, b)) return 0
    d = Math.min(d, pointSeg(p, a, b), pointSeg(a, p, q), pointSeg(b, p, q))
  }
  return d
}

/** Do two convex outlines overlap? (separating axes) */
export function overlap(A: Vec2[], B: Vec2[]): boolean {
  for (const P of [A, B]) for (let i = 0; i < P.length; i++) {
    const e = sub(P[(i + 1) % P.length], P[i]), n: Vec2 = [-e[1], e[0]]
    const span = (Q: Vec2[]) => { let lo = Infinity, hi = -Infinity; for (const q of Q) { const v = q[0] * n[0] + q[1] * n[1]; lo = Math.min(lo, v); hi = Math.max(hi, v) } return [lo, hi] }
    const [a0, a1] = span(A), [b0, b1] = span(B)
    if (a1 <= b0 + 1e-9 || b1 <= a0 + 1e-9) return false
  }
  return true
}

/** Where a door leaf could sweep: a quarter circle from each jamb on each side of the wall. The scan records neither
    the hinge side nor which way the door opens, so all four are kept clear. */
export function swings(m: Model, floor: number): { opening: string; zones: Vec2[][] }[] {
  const out = []
  for (const o of m.plan.openings) {
    const w = m.wallById.get(o.wall)
    if (o.type !== 'doorway' || !w || !o.width || o.width > SWING_MAX_M || m.floorOf.get(o.floor) !== floor) continue
    const L = Math.hypot(w.b[0] - w.a[0], w.b[1] - w.a[1]) || 1, d: Vec2 = [(w.b[0] - w.a[0]) / L, (w.b[1] - w.a[1]) / L], r = o.width
    const zones: Vec2[][] = []
    for (const j of [-1, 1]) for (const side of [-1, 1]) {
      const hinge: Vec2 = [o.center[0] + (d[0] * j * r) / 2, o.center[1] + (d[1] * j * r) / 2], zone: Vec2[] = [hinge]
      for (let k = 0; k <= 6; k++) { // from along the wall toward the other jamb, round to square off the wall
        const t = (k / 6) * (Math.PI / 2), ax = -j * Math.cos(t), ay = side * Math.sin(t)
        zone.push([hinge[0] + (d[0] * ax - d[1] * ay) * r, hinge[1] + (d[1] * ax + d[0] * ay) * r])
      }
      zones.push(zone)
    }
    out.push({ opening: o.id, zones })
  }
  return out
}

const wallCache = new WeakMap<Model, Seg[][]>()
/** The solid runs of every wall on a floor: doorways and open passages are gaps (a piece in one blocks a door, it is
    not in a wall); a window is wall, since nothing stands in it. */
function walls(m: Model, floor: number): Seg[] {
  let all = wallCache.get(m)
  if (!all) {
    all = m.plan.floors.map(() => [])
    for (const w of m.plan.walls) {
      if (w.type !== 'wall') continue
      const gaps = w.openings.map((id) => m.openingById.get(id)).filter((o) => o && o.type !== 'window').map((o) => openingSpan(m, o!)).sort((a, b) => a.s0 - b.s0)
      const L = w.length || Math.hypot(w.b[0] - w.a[0], w.b[1] - w.a[1]), d: Vec2 = [(w.b[0] - w.a[0]) / (L || 1), (w.b[1] - w.a[1]) / (L || 1)]
      let from = 0
      for (const run of [...gaps.map((g) => [g.s0, g.s1]), [L, L]]) {
        if (run[0] - from > 0.02) all[m.floorOf.get(w.floor) ?? 0]?.push({ a: [w.a[0] + d[0] * from, w.a[1] + d[1] * from], b: [w.a[0] + d[0] * run[0], w.a[1] + d[1] * run[0]], half: (w.thickness || 0.1) / 2 })
        from = Math.max(from, run[1])
      }
    }
    wallCache.set(m, all)
  }
  return all[floor] ?? []
}

/** Largest clear circle in a room, metres across, wall face to wall face, with these outlines standing in it.
    shortcut: a 10 cm grid refined once to 2 cm, so the answer can be about a centimetre short of the true circle. */
export function clearCircle(room: Vec2[], half: number, pieces: Vec2[][]): { d: number; at: Vec2 } {
  const xs = room.map((p) => p[0]), ys = room.map((p) => p[1])
  const radius = (x: number, y: number) => {
    if (!pointInPolygon(x, y, room)) return 0
    let r = Infinity
    for (let i = 0; i < room.length; i++) r = Math.min(r, pointSeg([x, y], room[i], room[(i + 1) % room.length]) - half)
    for (const q of pieces) { if (pointInPolygon(x, y, q)) return 0; for (let i = 0; i < 4; i++) r = Math.min(r, pointSeg([x, y], q[i], q[(i + 1) % 4])) }
    return Math.max(0, r)
  }
  let best = { r: 0, at: centroid(room) }
  const scan = (x0: number, x1: number, y0: number, y1: number, step: number) => {
    for (let x = x0; x <= x1; x += step) for (let y = y0; y <= y1; y += step) { const r = radius(x, y); if (r > best.r) best = { r, at: [x, y] } }
  }
  scan(Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys), 0.1)
  scan(best.at[0] - 0.1, best.at[0] + 0.1, best.at[1] - 0.1, best.at[1] + 0.1, 0.02)
  return { d: best.r * 2, at: best.at }
}

const median = (v: number[]) => { const s = [...v].sort((a, b) => a - b); return s.length ? (s[(s.length - 1) >> 1] + s[s.length >> 1]) / 2 : NaN }
/** The floor a piece stands on, from the bottom of its box. */
export const floorUnder = (m: Model, p: Stood) => { let f = 0; m.floorZ.forEach((fz, i) => { if (p.center[2] - p.size[2] / 2 >= fz - 0.3) f = i }); return f }

/** Stand a new piece in the room at (x, y) on `floor`, or in that floor's largest room when the point is in none. */
export function standAt(m: Model, floor: number, x: number, y: number, size: Vec3): Vec3 {
  const ri = roomAt(m, floor, x, y) >= 0 ? -1 : m.roomsByFloor[floor]?.[0] ?? -1
  const c = ri >= 0 ? centroid(m.plan.rooms[ri].polygon) : [x, y]
  return [c[0], c[1], m.floorZ[floor] + size[2] / 2]
}

/**
 * Every piece checked against the walls, the doors and the wheelchair turning circle of the room it stands in, and
 * what to draw for it: the piece as a Contract 4 box, and lines and chips for the one that is selected.
 * A piece is "fail" when it stands in a wall, in a door's swing, or takes away a turning circle its room had.
 */
export function furnish(m: Model, items: Stood[], selected: string | null): { checks: FurnishCheck[]; overlays: Overlay[] } {
  const prints = items.map(footprint), floors = items.map((p) => floorUnder(m, p))
  const rooms = items.map((p, i) => roomAt(m, floors[i], p.center[0], p.center[1]))
  const checks: FurnishCheck[] = [], overlays: Overlay[] = []
  // Per room: the largest clear circle empty and furnished, and which pieces took it away. A piece is to blame when
  // the room would have its circle back without it; when no single piece is, every piece in the room is.
  const circles = new Map<number, { before: number; after: { d: number; at: Vec2 }; lost: boolean; blame: Set<number> }>()
  for (const ri of new Set(rooms)) {
    if (ri < 0) continue
    const room = m.plan.rooms[ri], ts = room.walls.map((id) => m.wallById.get(id)?.thickness).filter((t): t is number => !!t)
    const half = (ts.length ? median(ts) : 0.12) / 2 // as the server: the room outline runs down the middle of its walls
    const inside = items.map((_, i) => i).filter((i) => rooms[i] === ri), circle = (skip = -1) => clearCircle(room.polygon, half, inside.filter((i) => i !== skip).map((i) => prints[i]))
    const before = clearCircle(room.polygon, half, []).d, after = circle(), lost = before >= TURN_M && after.d < TURN_M
    const alone = lost ? inside.filter((i) => circle(i).d >= TURN_M) : []
    circles.set(ri, { before, after, lost, blame: new Set(lost ? (alone.length ? alone : inside) : []) })
  }
  items.forEach((p, i) => {
    const f = floors[i], fp = prints[i], ws = walls(m, f), on = p.id === selected
    const a = (p.yaw_deg * Math.PI) / 180, cs = Math.cos(a), sn = Math.sin(a), z = m.floorZ[f]
    const through = ws.some((w) => polySeg(fp, w.a, w.b) < w.half - 0.005)
    const sides = {} as FurnishCheck['sides']
    const lines: { points: Vec3[]; status: Status }[] = [], chips: { point: Vec3; text: string; status: Status }[] = []
    for (const [name, lx, ly] of SIDES) { // straight out from the middle of each side to the first wall face
      const n: Vec2 = [lx * cs - ly * sn, lx * sn + ly * cs], o: Vec2 = [p.center[0] + (n[0] * p.size[lx ? 0 : 1]) / 2, p.center[1] + (n[1] * p.size[lx ? 0 : 1]) / 2]
      let gap = Infinity
      for (const w of ws) {
        const e = sub(w.b, w.a), den = cross(n, e)
        if (Math.abs(den) < 1e-9) continue
        const t = cross(sub(w.a, o), e) / den, u = cross(sub(w.a, o), n) / den
        if (t >= 0 && u >= 0 && u <= 1) gap = Math.min(gap, t - w.half / Math.max(0.2, Math.abs(den) / Math.hypot(e[0], e[1])))
      }
      sides[name] = gap < REACH_M ? Math.max(0, gap) : null
      if (on && gap < REACH_M && gap > 0.03) {
        lines.push({ points: [[o[0], o[1], z + 0.04], [o[0] + n[0] * gap, o[1] + n[1] * gap, z + 0.04]], status: 'unknown' })
        chips.push({ point: [o[0] + (n[0] * gap) / 2, o[1] + (n[1] * gap) / 2, z + 0.1], text: `${gap.toFixed(2)} m`, status: 'unknown' })
      }
    }
    const doors: string[] = []
    for (const s of swings(m, f)) {
      const hit = s.zones.filter((zone) => overlap(fp, zone))
      if (!hit.length) continue
      doors.push(s.opening)
      for (const zone of hit) lines.push({ points: [...zone, zone[0]].map((q) => [q[0], q[1], z + 0.05] as Vec3), status: 'fail' })
    }
    const c = circles.get(rooms[i])
    let turning: FurnishCheck['turning'] = null
    if (c) {
      turning = { before: c.before, after: c.after.d, need: TURN_M, blocked: c.blame.has(i) }
      if (on) {
        const st: Status = c.after.d >= TURN_M ? 'pass' : c.lost ? 'fail' : 'unknown', r = c.after.d / 2, ring: Vec3[] = []
        for (let k = 0; k <= 48; k++) ring.push([c.after.at[0] + Math.cos((k / 48) * 2 * Math.PI) * r, c.after.at[1] + Math.sin((k / 48) * 2 * Math.PI) * r, z + 0.03])
        if (r > 0.05) { lines.push({ points: ring, status: st }); chips.push({ point: [c.after.at[0], c.after.at[1], z + 0.1], text: `${c.after.d.toFixed(2)} m circle`, status: st }) }
      }
    }
    const status: Status = through || doors.length || turning?.blocked ? 'fail' : 'pass'
    checks.push({ id: p.id, status, room: rooms[i] >= 0 ? m.plan.rooms[rooms[i]].id : null, through, sides, doors, turning })
    overlays.push({ kind: 'box', center: p.center, size: p.size, yaw_deg: p.yaw_deg, label: p.label, status, model: p.model, quiet: !on })
    if (lines.length || chips.length) overlays.push({ kind: 'marks', floor: f, id: p.id, lines, chips })
  })
  return { checks, overlays }
}
