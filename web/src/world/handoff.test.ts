import assert from 'node:assert/strict'
import { test } from 'node:test'
import { cameraOf, lngLatOf, rangeOfZoom, zoomOfRange, type Stand } from './handoff.ts'

const anchor = { lat: 29.76, lon: -95.37 }
const st: Stand = { anchor, target: { e: 10, n: -20, up: 2 }, ring: [], fit: 40, enter: 110, leave: 400, verified: true }

test('a hundred metres north or east moves the point by the right angle', () => {
  const [lon, lat] = lngLatOf(anchor, 100, 100)
  // WGS84 at 29.76 N, from the series for the length of a degree: 110,848 m of latitude and 96,718 m of longitude
  assert.ok(Math.abs((lat - anchor.lat) * 110848 - 100) < 0.02, `north ${(lat - anchor.lat) * 110848}`)
  assert.ok(Math.abs((lon - anchor.lon) * 96718 - 100) < 0.02, `east ${(lon - anchor.lon) * 96718}`)
})

test('looking straight down the camera is over its target at its range; tilted north it stands to the south', () => {
  const down = cameraOf(st, { bearing: 0, pitch: 0, range: 200 })
  assert.deepEqual(down.lngLat, lngLatOf(anchor, 10, -20))
  assert.equal(down.altitude, 202)
  const tilted = cameraOf(st, { bearing: 0, pitch: 60, range: 200 })
  assert.ok(tilted.lngLat[1] < down.lngLat[1] && Math.abs(tilted.lngLat[0] - down.lngLat[0]) < 1e-9)
  assert.ok(Math.abs(tilted.altitude - 102) < 1e-9)
  const east = cameraOf(st, { bearing: 90, pitch: 60, range: 200 }) // looking east: the camera is west of the target
  assert.ok(east.lngLat[0] < down.lngLat[0])
})

test('zoom and range are inverse, and one zoom level halves the range', () => {
  const r = rangeOfZoom(18, 29.76, 900)
  assert.ok(Math.abs(zoomOfRange(r, 29.76, 900) - 18) < 1e-9)
  assert.ok(Math.abs(rangeOfZoom(19, 29.76, 900) * 2 - r) < 1e-6)
})
