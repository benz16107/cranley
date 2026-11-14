import assert from 'node:assert/strict'
import { test } from 'node:test'
import { A_STAGES, aWeight, bestFix, compassPoint, headingFromAlpha, headingMean, leq, spread, tilt, toMetres } from './dsp.ts'

const near = (a: number, b: number, tol: number) => assert.ok(Math.abs(a - b) <= tol, `${a} is not within ${tol} of ${b}`)

test('tilt: a phone flat on a 1:12 ramp reads 4.76 degrees along its long axis, whichever way gravity is signed', () => {
  const a = Math.atan(1 / 12)
  near(tilt({ x: 0, y: 9.81 * Math.sin(a), z: 9.81 * Math.cos(a) }).long, 4.76, 0.01)
  near(tilt({ x: 0, y: -9.81 * Math.sin(a), z: -9.81 * Math.cos(a) }).long, -4.76, 0.01) // the other platform's sign
  near(tilt({ x: 0.3, y: 0, z: 9.8 }).short, 1.75, 0.01)
  assert.deepEqual(tilt({ x: 0, y: 0, z: 0 }), { long: 0, short: 0 })
})

test('headings wrap: 350 and 10 average to north', () => {
  near(headingMean([350, 10]).mean % 360, 0, 1e-6)
  near(headingMean([88, 90, 92]).mean, 90, 1e-6)
  assert.ok(headingMean([0, 90, 180, 270]).spread > 100) // no direction at all
  assert.ok(headingMean([90, 90.5, 89.5]).spread < 1)
  assert.equal(headingFromAlpha(90), 270) // alpha runs counter-clockwise
  assert.deepEqual([0, 44, 90, 181, 359].map(compassPoint), ['N', 'NE', 'E', 'S', 'N'])
})

test('A-weighting matches the standard table', () => {
  near(aWeight(1000), 0, 0.05)
  near(aWeight(100), -19.1, 0.1)
  near(aWeight(10000), -2.5, 0.1)
  near(aWeight(31.5), -39.4, 0.2)
  near(A_STAGES[0].qDb, -6.02, 0.01) // Q 0.5: both poles on the same frequency
  near(A_STAGES[1].frequency, 281.9, 0.1)
})

test('level: a full-scale sine is 3 dB under the clipping level, and equal energy means equal Leq', () => {
  near(leq([0.5]), 116.99, 0.01)
  near(leq([0.01, 0.0001]), leq([0.00505, 0.00505]), 1e-9)
  assert.equal(spread([2, 2, 2]), 0)
})

test('best fix keeps the good fixes and tolerates no altitude', () => {
  const f = bestFix([{ lat: 29.76, lon: -95.37, accuracy_m: 5, altitude_m: 14, altitude_accuracy_m: 4 },
    { lat: 29.7602, lon: -95.37, accuracy_m: 8, altitude_m: 16, altitude_accuracy_m: 6 },
    { lat: 29.9, lon: -95.5, accuracy_m: 300, altitude_m: null, altitude_accuracy_m: null }])!
  near(f.lat, 29.7601, 1e-9); assert.equal(f.samples, 2); assert.equal(f.altitude_m, 15); assert.equal(f.altitude_accuracy_m, 4)
  assert.equal(bestFix([{ lat: 1, lon: 2, accuracy_m: null, altitude_m: null, altitude_accuracy_m: null }])!.altitude_m, null)
  assert.equal(bestFix([]), null)
})

test('typed lengths', () => {
  assert.equal(toMetres('84', 'cm'), 0.84); assert.equal(toMetres('33,5', 'in'), 0.8509)
  assert.equal(toMetres('', 'cm'), null); assert.equal(toMetres('-3', 'cm'), null); assert.equal(toMetres('abc', 'in'), null)
})
