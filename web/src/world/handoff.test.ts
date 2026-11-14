import assert from 'node:assert/strict'
import { test } from 'node:test'
import { cameraOf, groundScale, lngLatOf, rangeOfZoom, zoomOfRange, type Stand } from './handoff.ts'

const anchor = { lat: 29.76, lon: -95.37 }
const st: Stand = { anchor, target: { e: 10, n: -20, up: 2 }, ring: [], fit: 40, enter: 110, leave: 400, leaveAlone: 100, verified: true }

test('a point east and north of the anchor is that many of the map\'s metres from it in Web Mercator', () => {
  const [lon, lat] = lngLatOf(anchor, 100, 250)
  const R = 6378137, y = (d: number) => Math.log(Math.tan(Math.PI / 4 + (d * Math.PI) / 360)), k = R * Math.cos((anchor.lat * Math.PI) / 180)
  assert.ok(Math.abs(((lon - anchor.lon) * Math.PI) / 180 * k - 100) < 1e-6)
  assert.ok(Math.abs((y(lat) - y(anchor.lat)) * k - 250) < 1e-6)
})

test('true ground distance: the ellipsoid\'s scale is the series for the length of a degree at 29.76 N', () => {
  const g = groundScale(29.76) // 110,848 m per degree of latitude, 96,718 m per degree of longitude
  assert.ok(Math.abs((g.east * Math.PI) / 180 - 96718) < 2, `${(g.east * Math.PI) / 180}`)
  assert.ok(Math.abs((g.north / Math.cos((29.76 * Math.PI) / 180)) * (Math.PI / 180) - 110848) < 2, `${(g.north / Math.cos((29.76 * Math.PI) / 180)) * (Math.PI / 180)}`)
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
