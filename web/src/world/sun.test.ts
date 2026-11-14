import assert from 'node:assert/strict'
import { test } from 'node:test'
import { sunDay, sunPosition, zonedInstant } from './sun.ts'

const HOU = [29.76, -95.37] as const

test('at solar noon on the June solstice the sun is 90 minus (latitude minus 23.44) degrees up, due south', () => {
  let best = { altitude: -90, azimuth: 0 }
  for (let m = 17 * 60; m < 20 * 60; m++) { // scan the hours round solar noon in Houston, in UTC
    const p = sunPosition(new Date(Date.UTC(2026, 5, 21, 0, m)), ...HOU)
    if (p.altitude > best.altitude) best = p
  }
  assert.ok(Math.abs(best.altitude - (90 - (29.76 - 23.44))) < 0.05, `altitude ${best.altitude}`)
  assert.ok(Math.abs(best.azimuth - 180) < 1.5, `azimuth ${best.azimuth}`)
})

test('at the March equinox the sun rises due east and the day is a little over twelve hours', () => {
  const d = sunDay(new Date(Date.UTC(2026, 2, 20, 18)), ...HOU)
  assert.ok(d.rise && d.set)
  assert.ok(Math.abs(d.hours - 12.13) < 0.08, `hours ${d.hours}`)
  const rise = sunPosition(d.rise!, ...HOU)
  assert.ok(Math.abs(rise.azimuth - 90) < 1.2, `azimuth ${rise.azimuth}`)
  assert.ok(Math.abs(rise.altitude + 0.833) < 0.1, `altitude ${rise.altitude}`)
})

test('agrees with the astral library (its own code for the same NOAA equations) at two instants in Houston', () => {
  // astral 3.2, Observer(29.76, -95.37), no refraction, run 2026-11-14
  const nov = sunPosition(new Date(Date.UTC(2026, 10, 14, 21)), ...HOU) // 15:00 CST
  assert.ok(Math.abs(nov.azimuth - 226.71) < 0.05 && Math.abs(nov.altitude - 26.149) < 0.05, JSON.stringify(nov))
  const jun = sunPosition(new Date(Date.UTC(2026, 5, 21, 15)), ...HOU) // 10:00 CDT
  assert.ok(Math.abs(jun.azimuth - 85.366) < 0.05 && Math.abs(jun.altitude - 44.466) < 0.05, JSON.stringify(jun))
  const day = sunDay(new Date(Date.UTC(2026, 10, 14, 18)), ...HOU) // astral: rise 12:45:36 UTC, set 23:25:56 UTC
  assert.ok(Math.abs(day.rise!.getTime() - Date.UTC(2026, 10, 14, 12, 45, 36)) < 60000 && Math.abs(day.set!.getTime() - Date.UTC(2026, 10, 14, 23, 25, 56)) < 60000)
})

test('the night sun is below the horizon', () => {
  assert.ok(sunPosition(new Date(Date.UTC(2026, 10, 14, 7)), ...HOU).altitude < -20)
})

test('a wall clock time in a zone becomes the right instant, in and out of daylight time', () => {
  assert.equal(zonedInstant(2026, 11, 14, 15 * 60, 'America/Chicago').toISOString(), '2026-11-14T21:00:00.000Z')
  assert.equal(zonedInstant(2026, 6, 21, 12 * 60, 'America/Los_Angeles').toISOString(), '2026-06-21T19:00:00.000Z')
})
