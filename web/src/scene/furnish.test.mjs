// Run: node --test src/scene/furnish.test.mjs   (from web/)
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { TURN_M, clearCircle, footprint, furnish, overlap, polySeg, standAt, swings } from './furnish.ts'
import { buildModel } from './model.ts'

// A hand-made 6 x 4 m plan: rooms A and B split by a wall at x = 3 with a 0.9 m doorway at y = 2. Walls are 0.1 m thick.
const wall = (id, a, b, rooms, openings = []) =>
  ({ id, floor: 'f', a, b, type: 'wall', thickness: 0.1, length: Math.hypot(b[0] - a[0], b[1] - a[1]), rooms, openings })
const plan = {
  schema: 'scanplan/1', sid: 't', name: null, address: null,
  has: { splat: false, defurnished: false, room_labels: true, openings: true },
  floors: [{ id: 'f', label: 'Floor 1', sequence: 0 }],
  walls: [
    wall('s', [0, 0], [6, 0], ['A', 'B']), wall('n', [0, 4], [6, 4], ['A', 'B']), wall('w', [0, 0], [0, 4], ['A'], ['win']),
    wall('e', [6, 0], [6, 4], ['B'], ['wide']), wall('mid', [3, 0], [3, 4], ['A', 'B'], ['door']),
  ],
  openings: [
    { id: 'door', wall: 'mid', floor: 'f', type: 'doorway', width: 0.9, height: 2, sill: 0, center: [3, 2], rooms: ['A', 'B'] },
    { id: 'win', wall: 'w', floor: 'f', type: 'window', width: 1.2, height: 1.2, sill: 0.9, center: [0, 2], rooms: ['A'] },
    { id: 'wide', wall: 'e', floor: 'f', type: 'doorway', width: 2.4, height: 2.1, sill: 0, center: [6, 2], rooms: ['B'] },
  ],
  rooms: [
    { id: 'A', floor: 'f', label: 'Living Room', polygon: [[0, 0], [3, 0], [3, 4], [0, 4]], area: 12, height: 2.5, walls: ['s', 'n', 'w', 'mid'] },
    { id: 'B', floor: 'f', label: 'Bedroom', polygon: [[3, 0], [6, 0], [6, 4], [3, 4]], area: 12, height: 2.5, walls: ['s', 'n', 'e', 'mid'] },
  ],
  panos: [], floorplans: [],
}
const m = buildModel(plan)
const piece = (id, x, y, l, d, yaw = 0) => ({ id, label: id, model: 'furniture/sofa', size: [l, d, 0.8], center: [x, y, 0.4], yaw_deg: yaw })
const near = (a, b, tol = 0.011) => assert.ok(Math.abs(a - b) <= tol, `${a} is not within ${tol} of ${b}`)
const one = (p, sel = null) => furnish(m, [p], sel).checks[0]

test('a piece turned a quarter stands on the same middle with its sides swapped', () => {
  const xs = footprint(piece('p', 1.5, 2, 2, 1, 90)).map((c) => c[0]), ys = footprint(piece('p', 1.5, 2, 2, 1, 90)).map((c) => c[1])
  near(Math.min(...xs), 1, 1e-9); near(Math.max(...xs), 2, 1e-9); near(Math.min(...ys), 1, 1e-9); near(Math.max(...ys), 3, 1e-9)
})

test('the outline tests: touching, apart, inside', () => {
  const sq = [[0, 0], [1, 0], [1, 1], [0, 1]]
  assert.equal(polySeg(sq, [0.5, -1], [0.5, 2]), 0)           // a wall through it
  assert.equal(polySeg(sq, [0.2, 0.2], [0.4, 0.4]), 0)        // a wall stub inside it
  near(polySeg(sq, [2, -5], [2, 5]), 1, 1e-9)
  assert.equal(overlap(sq, [[0.9, 0.9], [2, 0.9], [2, 2], [0.9, 2]]), true)
  assert.equal(overlap(sq, [[1, 0], [2, 0], [2, 1], [1, 1]]), false) // sharing an edge is not overlapping
})

test('clear of everything: each side measured to the wall face, nothing blocked', () => {
  const c = one(piece('sofa', 1.5, 0.6, 2, 0.9))
  assert.equal(c.status, 'pass'); assert.equal(c.room, 'A'); assert.equal(c.through, false); assert.deepEqual(c.doors, [])
  near(c.sides.front, 0.10); near(c.sides.back, 2.90); near(c.sides.left, 0.45); near(c.sides.right, 0.45)
  near(c.turning.before, 2.9, 0.03); assert.ok(c.turning.after >= TURN_M); assert.equal(c.turning.blocked, false)
})

test('in a door swing it fails, whichever side of the wall and whichever jamb is the hinge', () => {
  assert.deepEqual(one(piece('a', 2.4, 2, 2, 0.9, 90)).doors, ['door'])
  assert.equal(one(piece('b', 3.6, 1.4, 0.6, 0.6)).status, 'fail')  // the other room, off toward the other jamb
  assert.equal(one(piece('c', 1.0, 2, 0.6, 0.6)).status, 'pass')    // a leaf 0.9 m long cannot reach 1.7 m out
  assert.equal(swings(m, 0).length, 1)                               // a window has no swing; a 2.4 m door has no single leaf
})

test('standing in a wall fails', () => {
  const c = one(piece('p', 3, 1, 0.8, 0.8))
  assert.equal(c.through, true); assert.equal(c.status, 'fail')
})

test('standing in a doorway blocks the door; it is not in a wall', () => {
  const c = one(piece('p', 3, 2, 0.6, 0.6))
  assert.equal(c.through, false); assert.deepEqual(c.doors, ['door']); assert.equal(c.status, 'fail')
})

test('the piece that takes the turning circle is the one that turns red', () => {
  const { checks } = furnish(m, [piece('bed', 4.5, 2, 2.6, 2.0), piece('stool', 5.7, 3.7, 0.4, 0.4)], null)
  assert.ok(checks[0].turning.before >= TURN_M && checks[0].turning.after < TURN_M)
  assert.equal(checks[0].turning.blocked, true); assert.equal(checks[0].status, 'fail')
  assert.equal(checks[1].turning.blocked, false); assert.equal(checks[1].status, 'pass')
})

test('the clear circle of an empty room is its width less the wall faces', () => {
  near(clearCircle([[0, 0], [3, 0], [3, 4], [0, 4]], 0.05, []).d, 2.9, 0.03)
})

test('only the selected piece gets dimension lines; every piece is drawn as a box at its exact size', () => {
  const p = piece('sofa', 1.5, 0.6, 2, 0.9)
  const quiet = furnish(m, [p], null).overlays, on = furnish(m, [p], 'sofa').overlays
  assert.deepEqual(quiet.map((o) => o.kind), ['box']); assert.equal(quiet[0].quiet, true)
  assert.deepEqual(on[0].size, [2, 0.9, 0.8]); assert.equal(on[0].model, 'furniture/sofa')
  const marks = on.find((o) => o.kind === 'marks')
  assert.equal(marks.lines.length, 5)                                   // four sides and the room's circle
  assert.ok(marks.chips.some((c) => c.text === '0.45 m'))
})

test('a new piece stands where the camera looks, or in the largest room when that is outside', () => {
  assert.deepEqual(standAt(m, 0, 1, 1, [1, 1, 0.8]), [1, 1, 0.4])
  const c = standAt(m, 0, 40, 40, [1, 1, 0.8])
  assert.ok(c[0] > 0 && c[0] < 6 && c[1] > 0 && c[1] < 4)
})
