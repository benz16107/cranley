import assert from 'node:assert/strict'
import { test } from 'node:test'
import { lensOverlays } from './lens.ts'

// Small hand-made documents: what core would hand the scene for scan "s1" is `scene`, in core's order.
const route = (floor: string) => ({ kind: 'route', floor, points: [[0, 0, 0], [1, 0, 0]], chokes: [], label: 'r' })
const pins = (anchor: object) => ({ kind: 'pins', pins: [{ id: 'p', anchor, label: 'l', status: 'fail' }] })
const water = { kind: 'water', level_m: 1, datum: 'scan_z' }
const doc = (overlays: object[]) => ({ overlays }) as never

test('only the sheet on top puts its marks on the model', () => {
  const a = route('f1'), b = water, c = pins({ sid: 's1', opening: 'o1' })
  const d = doc([{ id: '1', tool: 'access', sid: 's1', overlay: a }, { id: '2', tool: 'flood', sid: 's1', overlay: b }, { id: '3', tool: 'access', sid: 's1', overlay: c }])
  assert.deepEqual(lensOverlays(d, 's1', 'access', [a, b, c]), [a, c])
  assert.deepEqual(lensOverlays(d, 's1', 'flood', [a, b, c]), [b])
})

test('what core leaves to the map and to other scans is skipped the same way', () => {
  const a = route('f1')
  const d = doc([
    { id: '1', tool: 'site', sid: 's1', overlay: route('geo') },                      // an outdoor path: the map draws it
    { id: '2', tool: 'site', sid: 's1', overlay: pins({ geo: [0, 0] }) },             // pins on the map only
    { id: '3', tool: 'access', sid: 's2', overlay: route('f1') },                     // another scan
    { id: '4', tool: 'access', sid: 's1', overlay: a },
  ])
  assert.deepEqual(lensOverlays(d, 's1', 'access', [a]), [a])
  assert.deepEqual(lensOverlays(d, 's1', 'site', [a]), [])
})

test('no sheet on top, or a list that does not match core, shows everything', () => {
  const a = route('f1'), b = water
  const d = doc([{ id: '1', tool: 'access', sid: 's1', overlay: a }])
  assert.deepEqual(lensOverlays(d, 's1', undefined, [a]), [a])
  assert.deepEqual(lensOverlays(d, 's1', 'access', [a, b]), [a, b])
})
