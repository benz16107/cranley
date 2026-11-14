// Run: node --test src/scene/model.test.mjs   (from web/)
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { anchorPoint, buildModel, resolveStyles, roomAt, sightBlocked, wallBoxes } from './model.ts'

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
