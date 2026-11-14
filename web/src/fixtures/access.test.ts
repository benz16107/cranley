import { test } from 'node:test'
import assert from 'node:assert/strict'
import { accessAudit, findEntrance, widestRoutes } from './access.ts'
import type { ScanPlan } from '../workspace/types.ts'

// A hand-made flat: hall -> living -> bedroom, hall -> bathroom, and a second, wider way into the bedroom.
const sq = (x: number, y: number, w: number, h: number): [number, number][] => [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]
const room = (id: string, label: string, poly: [number, number][]) => ({ id, floor: 'f', label, polygon: poly, area: 9, width: null, depth: null })
const door = (id: string, rooms: string[], width: number, center: [number, number], type: 'doorway' | 'window' = 'doorway') =>
  ({ id, wall: 'w', floor: 'f', type, width, height: 2, center, rooms })
const plan: ScanPlan = {
  schema: 'scanplan/1', sid: 'test', name: 'Test flat', address: '1 Test St', city: 'Nowhere', segment: 'commercial', geo: null,
  has: { splat: false, defurnished: false, room_labels: true, openings: true },
  floors: [{ id: 'f', label: '1', sequence: 0 }], walls: [],
  rooms: [room('hall', 'Hallway', sq(0, 0, 2, 4)), room('living', 'Living Room', sq(2, 0, 4, 4)), room('bed', 'Bedroom', sq(6, 0, 3, 4)), room('bath', 'Bathroom', sq(0, 4, 1.45, 2))],
  openings: [
    door('front', ['hall'], 0.9, [0, 2]),
    door('hall-living', ['hall', 'living'], 1.2, [2, 2]),
    door('living-bed-narrow', ['living', 'bed'], 0.7, [6, 1]),
    door('living-bed-wide', ['living', 'bed'], 0.85, [6, 3]),
    door('hall-bath', ['hall', 'bath'], 0.72, [1, 4]),
    door('window', ['bed'], 1.5, [9, 2], 'window'),
  ],
  panos: [{ id: 'p1', label: '1', position: [1, 2, 1.4], floor: 'f', room: 'hall' }],
}
const prefs = { door: 0.815, turning: 1.525, turningNeeded: true, routeTo: 'Bedroom' }

test('the entrance is the door to the outside, never a window', () => {
  assert.equal(findEntrance(plan)?.id, 'front')
})

test('routes keep the narrowest doorway as wide as possible', () => {
  const r = widestRoutes(plan, 'hall')
  assert.deepEqual(r.get('bed')!.map((h) => h.via.id), ['hall-living', 'living-bed-wide'])
  assert.deepEqual(r.get('bath')!.map((h) => h.via.id), ['hall-bath'])
})

test('the audit grades each check against the limit and anchors every finding', () => {
  const a = accessAudit(plan, prefs)
  const by = Object.fromEntries(a.checks.map((c) => [c.id, c]))
  assert.equal(by.entrance.status, 'pass')
  assert.deepEqual([by['route:Bedroom'].measured, by['route:Bedroom'].status], [0.85, 'pass'])
  assert.deepEqual([by['route:Bathroom'].measured, by['route:Bathroom'].status], [0.72, 'fail'])
  assert.deepEqual([by.turning.measured, by.turning.status], [1.45, 'warn']) // within 8% of 1.525
  assert.equal(a.verdict.status, 'fail')
  assert.ok(a.findings.every((f) => f.anchor && f.source.layer === 'matterport'))
  assert.equal(a.metrics.find((m) => m.id === 'narrowest')!.value, 0.72)
  assert.equal(a.metrics.find((m) => m.id === 'under')!.value, 1)
  const route = a.overlays.find((o) => o.kind === 'route')
  assert.equal(route?.kind === 'route' && route.points.length, 4) // entrance, two doorways, bedroom centre
})

test('open space between rooms is crossed without a doorway to measure', () => {
  const open: ScanPlan = { ...plan, openings: plan.openings.filter((o) => !o.id.startsWith('living-bed')),
    walls: [{ id: 'line', floor: 'f', a: [6, 0], b: [6, 4], type: 'invisible', thickness: 0, rooms: ['living', 'bed'], openings: [] }] }
  const r = widestRoutes(open, 'hall')
  assert.deepEqual(r.get('bed')!.map((h) => h.via.id), ['hall-living', 'line'])
  assert.equal(accessAudit(open, prefs).checks.find((c) => c.id === 'route:Bedroom')!.measured, 1.2)
})

test('a wider limit turns a pass into a fail, and nothing is measured without doorways', () => {
  assert.equal(accessAudit(plan, { ...prefs, door: 1 }).checks[0].status, 'fail')
  assert.equal(accessAudit(plan, { ...prefs, door: 0.88 }).checks.find((c) => c.id === 'route:Bedroom')!.status, 'warn')
  const bare = accessAudit({ ...plan, openings: [] }, prefs)
  assert.deepEqual([bare.verdict.status, bare.checks.length], ['unknown', 0])
})
