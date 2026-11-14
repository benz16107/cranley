import assert from 'node:assert/strict'
import { test } from 'node:test'
import { azOfBearing, bearingOfAz, freeRect, lookAngles } from './engine/camera.ts'

const near = (a, b) => assert.ok(Math.abs(a - b) < 1e-9, `${a} is not ${b}`)
// where the rig looks, in the scan frame: from the camera's position (at azimuth az around the target) back to the target
const lookDir = (az, pol) => [-Math.sin(pol) * Math.cos(az), -Math.sin(pol) * Math.sin(az), -Math.cos(pol)]

test('the free rectangle is what the insets leave, and its centre is the picture centre', () => {
  assert.deepEqual(freeRect(1440, 900, null), { w: 1440, h: 900, dx: 0, dy: 0 })
  assert.deepEqual(freeRect(1440, 900, { left: 576, bottom: 110 }), { w: 864, h: 790, dx: 288, dy: -55 }) // right of the type, above the dock
  assert.equal(freeRect(300, 200, { left: 400 }).w, 40) // never nothing
})

test('a bearing is the compass direction the camera looks toward', () => {
  const horizon = Math.PI / 2
  // no rotation: north is the scan's +y, east is +x
  for (const [bearing, want] of [[0, [0, 1]], [90, [1, 0]], [180, [0, -1]], [270, [-1, 0]]]) {
    const [x, y] = lookDir(azOfBearing(bearing, 0), horizon)
    near(x, want[0]); near(y, want[1])
  }
  // a scan turned 90 degrees counter-clockwise onto east/north: its +x points north
  const [x, y] = lookDir(azOfBearing(0, 90), horizon)
  near(x, 1); near(y, 0)
  for (const b of [0, 12.5, 90, 181, 359]) for (const yaw of [0, 37, -120]) near(bearingOfAz(azOfBearing(b, yaw), yaw), b)
})

test('a panorama look is yaw counter-clockwise from +x and pitch up', () => {
  let a = lookAngles({ yaw_deg: 0, pitch_deg: 0 }), d = lookDir(a.az, a.pol)
  near(d[0], 1); near(d[1], 0); near(d[2], 0)
  a = lookAngles({ yaw_deg: 90, pitch_deg: 30 }); d = lookDir(a.az, a.pol)
  near(d[0], 0); near(d[1], Math.cos(Math.PI / 6)); near(d[2], 0.5)
})
