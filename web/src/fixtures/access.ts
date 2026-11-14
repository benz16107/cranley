import type { Check, Finding, Overlay, Panel, Pt, ScanPlan, Source, Status, ToolResult } from '../workspace/types.ts'

/* Fixtures only: a step-free access audit worked out in the browser from a ScanPlan, so the shell can be
   reviewed without the agent or the geometry engine. Every number below comes from the plan's own geometry
   and goes straight into the result object. The real tool lives on the server and will replace this. */

export const ACCESS_DEFAULTS = { 'access.door_clear': 0.815, 'access.turning': 1.525, 'access.turning_needed': true, 'access.route_to': 'Bedroom' }
export type AccessPrefs = { door: number; turning: number; turningNeeded: boolean; routeTo: string }

const GEOM: Source = { layer: 'matterport', method: 'geometry', confidence: 'medium',
  note: 'Width of the opening in the scan’s wall outline. With a door hung, the clear width is usually 4 to 5 cm less. Worked out in the browser in fixtures mode.' }
const ROUTE: Source = { layer: 'matterport', method: 'geometry', confidence: 'low',
  note: 'Straight lines between doorway centres. It does not go around furniture. Worked out in the browser in fixtures mode.' }
const BOX: Source = { layer: 'matterport', method: 'geometry', confidence: 'low',
  note: 'The shorter side of the room’s bounding box. Fixtures such as a vanity or a tub are not subtracted.' }

const dist = (a: Pt, b: Pt) => Math.hypot(a[0] - b[0], a[1] - b[1])
const centre = (poly: Pt[]): Pt => [poly.reduce((s, p) => s + p[0], 0) / poly.length, poly.reduce((s, p) => s + p[1], 0) / poly.length]
const grade = (measured: number, limit: number): Status => (measured >= limit ? 'pass' : measured >= limit - 0.05 ? 'warn' : 'fail')
const worst = (s: Status[]): Status => (s.includes('fail') ? 'fail' : s.includes('warn') ? 'warn' : s.includes('pass') ? 'pass' : 'unknown')

type Door = ScanPlan['openings'][number] & { open?: boolean }
type Hop = { via: Door; room: string }

/** From the entrance room, the route to every room that keeps the narrowest doorway as wide as possible. */
export function widestRoutes(plan: ScanPlan, start: string): Map<string, Hop[]> {
  // An "invisible" wall is a line between two parts of one open space: you can cross it anywhere.
  const open: Door[] = plan.walls.filter((w) => w.type === 'invisible' && w.rooms.length === 2).map((w) => ({
    id: w.id, wall: w.id, floor: w.floor, type: 'opening', width: Infinity, height: null, rooms: w.rooms, open: true,
    center: [(w.a[0] + w.b[0]) / 2, (w.a[1] + w.b[1]) / 2] }))
  const doors = [...plan.openings.filter((o) => o.type !== 'window' && o.rooms.length === 2), ...open]
  const best = new Map<string, { width: number; path: Hop[] }>([[start, { width: Infinity, path: [] }]])
  const done = new Set<string>()
  for (;;) {
    let at: string | null = null
    for (const [id, v] of best) if (!done.has(id) && (at === null || v.width > best.get(at)!.width)) at = id
    if (at === null) break
    done.add(at)
    const here = best.get(at)!
    for (const d of doors) {
      if (!d.rooms.includes(at)) continue
      const next = d.rooms[0] === at ? d.rooms[1] : d.rooms[0]
      const width = Math.min(here.width, d.width)
      if (!done.has(next) && width > (best.get(next)?.width ?? -1)) best.set(next, { width, path: [...here.path, { via: d, room: next }] })
    }
  }
  return new Map([...best].map(([id, v]) => [id, v.path]))
}

export function findEntrance(plan: ScanPlan): Door | null {
  // a "doorway" a few centimetres wide is a flaw in the outline, not a door
  const outside = plan.openings.filter((o) => o.type === 'doorway' && o.rooms.length === 1 && o.width >= 0.5)
  const label = (d: Door) => plan.rooms.find((r) => r.id === d.rooms[0])?.label ?? ''
  const rank = (d: Door) => (/entry|foyer|hall|living/i.test(label(d)) ? 2 : /garage|patio|balcon|closet|void|bed|bath/i.test(label(d)) ? 0 : 1)
  return outside.sort((a, b) => rank(b) - rank(a) || b.width - a.width)[0] ?? null
}

export function accessAudit(plan: ScanPlan, p: AccessPrefs): ToolResult {
  const sid = plan.sid
  const base = { tool: 'access', scope: { sid }, assumptions: [
    { id: 'access.door_clear', label: 'Clear door width', value: p.door, unit: 'm', editable: true, min: 0.6, max: 1.2, step: 0.005 },
    { id: 'access.turning', label: 'Turning circle', value: p.turning, unit: 'm', editable: true, min: 1.2, max: 2, step: 0.005 },
  ], actions: [{ id: 'compare_address', label: 'Compare the other units at this address', tool: 'access' }] }
  const entrance = findEntrance(plan)
  const doorways = plan.openings.filter((o) => o.type === 'doorway')
  if (!doorways.length || !entrance) {
    return { ...base, verdict: { status: 'unknown', text: doorways.length ? 'No door to the outside is marked in this scan, so there is no entrance to start the route from.' : 'This scan has no doorways in its wall outline, so door widths cannot be measured.' },
      metrics: [], checks: [], findings: [], overlays: [] }
  }
  const routes = widestRoutes(plan, entrance.rooms[0])
  const room = (id: string) => plan.rooms.find((r) => r.id === id)
  const named = (re: RegExp) => plan.rooms.filter((r) => r.label && re.test(r.label) && routes.has(r.id))
  const nearestPano = (at: Pt, floor: string) => plan.panos.filter((x) => x.floor === floor).sort((a, b) => dist([a.position[0], a.position[1]], at) - dist([b.position[0], b.position[1]], at))[0]
  const findings: Finding[] = [], checks: Check[] = []
  const doorFinding = (d: Door, title: string) => {
    const id = `access:${sid}:${d.id}`
    if (!findings.some((f) => f.id === id)) {
      const pano = nearestPano(d.center, d.floor)
      findings.push({ id, title, status: grade(d.width, p.door), anchor: { sid, opening: d.id }, source: GEOM, media: pano ? [{ kind: 'pano', ref: pano.id }] : [] })
    }
    return id
  }

  checks.push({ id: 'entrance', rule: 'Entrance door', measured: entrance.width, threshold: p.door, unit: 'm', status: grade(entrance.width, p.door),
    standard: '2010 ADA Standards 404.2.3', findings: [doorFinding(entrance, 'Entrance door')] })

  const targets: [string, RegExp][] = [['Bedroom', /bed/i], ['Bathroom', /bath/i], ['Kitchen', /kitchen/i]]
  const onRoutes = new Map<string, Door>()
  for (const [name, re] of targets) {
    const rooms = named(re)
    if (!rooms.length) {
      if (plan.has.room_labels) continue
      break
    }
    // the hardest of that kind to reach decides: the check is about the narrowest doorway on its route
    const hard = rooms.map((r) => ({ r, path: routes.get(r.id)! })).filter((x) => x.path.length)
      .sort((a, b) => Math.min(...a.path.map((h) => h.via.width)) - Math.min(...b.path.map((h) => h.via.width)))[0]
    if (!hard) continue
    const real = hard.path.map((h) => h.via).filter((d) => !d.open)
    if (!real.length) continue // reached across open space, with no doorway to measure
    const narrow = real.sort((a, b) => a.width - b.width)[0]
    real.forEach((d) => onRoutes.set(d.id, d))
    checks.push({ id: `route:${name}`, rule: `Narrowest doorway on the way to the ${name.toLowerCase()}`, measured: narrow.width, threshold: p.door, unit: 'm',
      status: grade(narrow.width, p.door), standard: '2010 ADA Standards 404.2.3', findings: [doorFinding(narrow, `Doorway to the ${(room(hard.path.at(-1)!.room)?.label ?? name).toLowerCase()}`)] })
  }
  if (!plan.has.room_labels) {
    // offices carry no room names: every doorway that can be reached is checked instead
    for (const path of routes.values()) path.forEach((h) => { if (!h.via.open) onRoutes.set(h.via.id, h.via) })
    const narrow = [...onRoutes.values()].sort((a, b) => a.width - b.width)[0]
    if (narrow) checks.push({ id: 'route:all', rule: 'Narrowest doorway that can be reached', measured: narrow.width, threshold: p.door, unit: 'm',
      status: grade(narrow.width, p.door), standard: '2010 ADA Standards 404.2.3', findings: [doorFinding(narrow, 'Narrowest doorway')] })
  }

  const bath = named(/bath/i)[0]
  if (p.turningNeeded && bath) {
    const xs = bath.polygon.map((q) => q[0]), ys = bath.polygon.map((q) => q[1])
    const short = bath.polygon.length > 2 ? Math.min(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys)) : null
    const id = `access:${sid}:turn:${bath.id}`
    const status: Status = short == null ? 'unknown' : short >= p.turning ? 'pass' : short >= p.turning * 0.92 ? 'warn' : 'fail'
    findings.push({ id, title: 'Turning space in the bathroom', status, anchor: { sid, room: bath.id }, source: BOX,
      media: short != null && nearestPano(centre(bath.polygon), bath.floor) ? [{ kind: 'pano', ref: nearestPano(centre(bath.polygon), bath.floor).id }] : [] })
    checks.push({ id: 'turning', rule: 'Turning circle in the bathroom', measured: short, threshold: p.turning, unit: 'm', status, standard: '2010 ADA Standards 304.3.1', findings: [id] })
  }

  // the drawn route: entrance, then each doorway centre, then the middle of the room asked for
  const want = named(new RegExp(p.routeTo.slice(0, 4), 'i'))[0] ?? named(/bed/i)[0] ?? [...routes.keys()].map(room).find((r) => r && routes.get(r.id)!.length)
  const path = want ? routes.get(want.id)! : []
  const pts: Pt[] = [entrance.center, ...path.map((h) => h.via.center), ...(want && want.polygon.length ? [centre(want.polygon)] : [])]
  const length = pts.slice(1).reduce((s, q, i) => s + dist(pts[i], q), 0)
  const under = [...onRoutes.values(), entrance].filter((d, i, all) => all.findIndex((x) => x.id === d.id) === i && d.width < p.door)
  const narrowest = [...onRoutes.values(), entrance].sort((a, b) => a.width - b.width)[0]
  const status = worst(checks.map((c) => c.status))
  const openingsBy = (s: Status) => [...onRoutes.values(), entrance].filter((d) => grade(d.width, p.door) === s).map((d) => d.id)

  const overlays: Overlay[] = [
    { kind: 'route', floor: entrance.floor, label: `Entrance to the ${(want?.label ?? 'far room').toLowerCase()}`, points: pts.map((q) => [q[0], q[1], 0]),
      chokes: path.filter((h) => !h.via.open).map((h) => ({ point: [h.via.center[0], h.via.center[1], 0], width: h.via.width, status: grade(h.via.width, p.door) })) },
    ...(['pass', 'warn', 'fail'] as const).filter((s) => openingsBy(s).length).map((s) => ({ kind: 'rule' as const, select: { openings: openingsBy(s) }, style: s })),
    { kind: 'pins', pins: findings.filter((f) => f.status !== 'pass').map((f) => ({ id: f.id, anchor: f.anchor!, label: f.title, status: f.status })) },
  ]
  const text = status === 'pass' ? 'Every doorway on the way in is at least as wide as your limit.'
    : status === 'warn' ? 'The way in works on paper, but at least one measurement is within a few centimetres of your limit.'
    : status === 'fail' ? (under.length === 1 ? 'One doorway on the way in is narrower than your limit.' : 'Several doorways on the way in are narrower than your limit.')
    : 'There is not enough geometry in this scan to judge the way in.'
  return { ...base, verdict: { status, text }, checks, findings, overlays,
    metrics: [
      { id: 'narrowest', label: 'Narrowest door', value: narrowest.width, unit: 'm', source: GEOM },
      { id: 'under', label: 'Doors under limit', value: under.length, unit: `of ${onRoutes.size + (onRoutes.has(entrance.id) ? 0 : 1)}`, source: GEOM },
      { id: 'route', label: 'Route length', value: length, unit: 'm', source: ROUTE },
      { id: 'reached', label: 'Rooms reached', value: routes.size, unit: `of ${plan.rooms.filter((r) => r.label !== 'Void').length}`, source: ROUTE },
    ] }
}

/** A bound panel: the blocks a tool's manifest says it fills, pointed at its result. No model is involved. */
export function accessPanel(result: ToolResult, plan: ScanPlan, run: string, extra: Panel['blocks'] = [], steps: { id: string; label: string; detail?: string; ms?: number }[] = []): Panel {
  return { id: 'access', tool: 'access', title: 'Step-free access', scope: plan.name, sid: plan.sid, run, blocks: [
    { type: 'VerdictHeader', ...result.verdict },
    ...(result.metrics.length ? [{ type: 'MetricRow' as const, metrics: result.metrics }] : []),
    ...(result.checks.length ? [{ type: 'CheckList' as const, checks: result.checks }] : []),
    { type: 'FloorPlanMini', sid: plan.sid },
    { type: 'EvidenceStrip', findings: result.findings.filter((f) => f.status !== 'pass').map((f) => f.id) },
    ...extra,
    { type: 'AssumptionChips', assumptions: result.assumptions },
    ...(steps.length ? [{ type: 'StepLog' as const, steps }] : []),
    { type: 'ActionBar', actions: result.actions },
  ] }
}
