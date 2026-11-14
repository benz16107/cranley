// Run: node --test src/scene/model.test.mjs   (from web/)
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { anchorPoint, buildModel, interiorTest, openingSpan, outlineFromWalls, polygonArea, resolveStyles, roomAt, sightBlocked, wallBoxes } from './model.ts'

// A hand-made 6 x 4 m plan: two rooms split by a wall at x = 3 with a 0.9 m doorway, and a window on the west wall.
const wall = (id, a, b, rooms, openings = []) =>
  ({ id, floor: 'f', a, b, type: 'wall', thickness: 0.1, length: Math.hypot(b[0] - a[0], b[1] - a[1]), rooms, openings })
const plan = {
  schema: 'scanplan/1', sid: 't', name: null, address: null,
  has: { splat: false, defurnished: false, room_labels: true, openings: true },
  floors: [{ id: 'f', label: 'Floor 1', sequence: 0 }],
  walls: [
    wall('s', [0, 0], [6, 0], ['A', 'B']), wall('n', [0, 4], [6, 4], ['A', 'B']),
    wall('w', [0, 0], [0, 4], ['A'], ['win']), wall('e', [6, 0], [6, 4], ['B']), wall('mid', [3, 0], [3, 4], ['A', 'B'], ['door']),
  ],
  openings: [
    { id: 'door', wall: 'mid', floor: 'f', type: 'doorway', width: 0.9, height: 2, sill: 0, center: [3, 2], rooms: ['A', 'B'] },
    { id: 'win', wall: 'w', floor: 'f', type: 'window', width: 1.2, height: 1.2, sill: 0.9, center: [0, 2], rooms: ['A'] },
  ],
  rooms: [
    { id: 'A', floor: 'f', label: 'Hallway', polygon: [[0, 0], [3, 0], [3, 4], [0, 4]], area: 12, height: 2.5, walls: [] },
    { id: 'B', floor: 'f', label: 'Bedroom', polygon: [[3, 0], [6, 0], [6, 4], [3, 4]], area: 12, height: 2.5, walls: [] },
  ],
  panos: [{ id: 'p', label: '1', position: [1, 2, 1.5], rotation: null, floor: 'f', room: 'A', neighbors: [] }],
  floorplans: [],
}
const pal = { accent: [0, 0, 1], pass: [0, 1, 0], warn: [1, 1, 0], fail: [1, 0, 0], unknown: [.5, .5, .5], rampLo: [1, 1, 1], rampHi: [0, 0, 0] }
const m = buildModel(plan)

test('walls are cut where openings are', () => {
  const mid = wallBoxes(m).filter((b) => b.elem === m.wallElem.get('mid'))
  // two solid runs either side of the doorway and a lintel from 2.0 to 2.5 m
  assert.equal(mid.length, 3)
  const lintel = mid.find((b) => b.z0 > 0)
  assert.ok(Math.abs(lintel.s1 - lintel.s0 - 0.9) < 1e-9 && Math.abs(lintel.z0 - 2) < 1e-9 && lintel.z1 === 2.5)
  const west = wallBoxes(m).filter((b) => b.elem === m.wallElem.get('w'))
  assert.equal(west.length, 4) // two runs, the sill below the window and the lintel above it
  assert.equal(wallBoxes(m).filter((b) => b.kind === 1).length, 1) // one glass pane
})

test('room lookup and anchors', () => {
  assert.equal(plan.rooms[roomAt(m, 0, 4, 1)].id, 'B')
  assert.equal(roomAt(m, 0, 9, 9), -1)
  assert.deepEqual(anchorPoint(m, { room: 'A' })?.point.slice(0, 2), [1.5, 2])
  // a panorama direction looking east from (1, 2) stops at the dividing wall at x = 3
  const hit = anchorPoint(m, { pano: 'p', yaw_deg: 0, pitch_deg: 0 })?.point
  assert.ok(Math.abs(hit[0] - 2.97) < 1e-6 && hit[1] === 2)
})

test('a solid rule dims everything else, and unknown overlay kinds are ignored', () => {
  const s = resolveStyles(m, [{ kind: 'rule', select: { room_labels: ['hallway'] }, style: 'solid' }, { kind: 'sparkles', x: 1 }], pal, null, null)
  const A = s[m.roomElem.get('A')], B = s[m.roomElem.get('B')]
  assert.equal(A.height, 1); assert.equal(A.wash, 0)
  assert.equal(B.height, 0); assert.ok(B.wash > 0.5)
  assert.equal(s[m.wallElem.get('e')].height, 0)   // borders only the dim room
  assert.equal(s[m.wallElem.get('mid')].height, 1) // borders the solid room
})

test('lens colours rooms along the ramp', () => {
  const s = resolveStyles(m, [{ kind: 'lens', values: { A: 0, B: 10 }, ramp: 'sequential', legend: { title: 'x', min: 0, max: 10 } }], pal, null, null)
  assert.deepEqual(s[m.roomElem.get('A')].tint, [1, 1, 1])
  assert.deepEqual(s[m.roomElem.get('B')].tint, [0, 0, 0])
})

test('a wall blocks the line of sight, a doorway does not', () => {
  assert.equal(sightBlocked(m, 'f', 1, 0.5, 5, 0.5), true)  // through the dividing wall
  assert.equal(sightBlocked(m, 'f', 1, 2, 5, 2), false)     // through the doorway at y = 2
})

test('a room outline is recovered from walls that include a dead-end divider', () => {
  const sq = [[[0, 0], [4, 0]], [[4, 0], [4, 3]], [[4, 3], [2, 3]], [[2, 3], [0, 3]], [[0, 3], [0, 0]], [[2, 3], [2, 1.5]]] // last one sticks into the room
  const poly = outlineFromWalls(sq)
  assert.equal(poly.length, 5)
  assert.equal(polygonArea(poly), 12)
})

test('interiorTest: inside the rooms and under the ceiling, but not near the outer walls, above them or outside', () => {
  const m = buildModel(plan), inside = interiorTest(m), top = m.floorH[0]
  assert.equal(inside(1.5, 2, 1), true)            // the middle of the west room
  assert.equal(inside(3, 2, 1), true)              // on the wall between the two rooms: still inside the building
  assert.equal(inside(0.1, 2, 1), false)           // against the outer wall, where a capture's own wall stands
  assert.equal(inside(1.5, 2, top + 0.5), false)   // the roof
  assert.equal(inside(-2, 2, 1), false)            // the garden
})

test('floors stand at their own scan z: a ground floor under the scan origin, and an upper floor by its own sills', () => {
  // the same plan scanned from upstairs: its doorway sill is 3.18 m under the origin, with a second floor at the origin
  const dz = -3.18, up = { ...plan.rooms[0], id: 'U', floor: 'g' }
  const low = { ...plan, floors: [...plan.floors, { id: 'g', label: 'Floor 2', sequence: 1 }], rooms: [...plan.rooms, up],
    openings: [...plan.openings.map((o) => ({ ...o, sill: o.sill + dz })), { id: 'updoor', wall: 'mid', floor: 'g', type: 'doorway', width: 0.9, height: 2, sill: 0.02, center: [3, 2], rooms: ['U'] }],
    panos: plan.panos.map((p) => ({ ...p, position: [p.position[0], p.position[1], p.position[2] + dz] })) }
  const m = buildModel(low), near = (a, b) => assert.ok(Math.abs(a - b) < 1e-9, `${a} is not ${b}`)
  near(m.floorZ[0], dz); near(m.floorZ[1], 0.02)
  near(openingSpan(m, m.openingById.get('win')).sill, 0.9)       // a sill is drawn by its height above its own floor
  near(openingSpan(m, m.openingById.get('updoor')).sill, 0)      // an upstairs doorway is open down to its floor
  assert.equal(anchorPoint(m, { point: [1, 1, dz + 0.9] }).floor, 0) // a truck parked on the ground floor is on the ground floor
  near(anchorPoint(m, { room: 'A' }).point[2], dz + 0.05)
  const inside = interiorTest(m)
  assert.equal(inside(1.5, 2, dz + 1), true); assert.equal(inside(1.5, 2, dz - 1), false)
})

test('the ground floor is the lowest floor that is not a basement', () => {
  const two = (a, b) => buildModel({ ...plan, floors: [{ id: 'f', label: a, sequence: 0 }, { id: 'g', label: b, sequence: 1 }] }).groundFloor
  assert.equal(two('Floor 1', 'Floor 2'), 0); assert.equal(two('Basement', 'Floor 1'), 1); assert.equal(two('Basement', 'Cellar'), 0)
})

test('a floor with no doorway stands a tripod height under its panoramas, and one with nothing at 0', () => {
  near2(buildModel({ ...plan, openings: [] }).floorZ[0], 1.5 - 1.4)
  near2(buildModel({ ...plan, openings: [], panos: [] }).floorZ[0], 0)
})
function near2(a, b) { assert.ok(Math.abs(a - b) < 1e-9, `${a} is not ${b}`) }
