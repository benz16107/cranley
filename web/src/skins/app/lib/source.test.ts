import { test } from 'node:test'
import assert from 'node:assert/strict'
import { oneSource, sourceWords, splitChecks } from './source.ts'

test('a source is said in plain words', () => {
  assert.equal(sourceWords({ layer: 'matterport', method: 'geometry' }), 'Measured from the scan')
  assert.equal(sourceWords({ layer: 'matterport', method: 'vision' }), 'Seen in the scan’s photos')
  assert.equal(sourceWords({ layer: 'vexcel', method: 'vision' }), 'Seen in aerial photos')
  assert.equal(sourceWords({ layer: 'costar', method: 'lookup' }), 'From the property record')
  assert.equal(sourceWords({ layer: 'model', method: 'simulation' }), 'Simulated')
  assert.equal(sourceWords({ layer: 'matterport', method: 'simulation' }), 'Simulated from the scan')
  assert.equal(sourceWords({ layer: 'phone', method: 'sensor' }), 'Read on site by your phone')
  assert.equal(sourceWords({ layer: 'phone', method: 'manual' }), 'Measured on site by hand')
  assert.equal(sourceWords({ layer: 'lidar', method: 'geometry' }), 'Measured from lidar') // a layer added later is named as it came
  assert.equal(sourceWords({ layer: 'matterport', method: 'divined' }), 'From the scan, divined')
})

test('values from one place say the place once', () => {
  const scan = { layer: 'matterport', method: 'geometry', confidence: 'medium' }
  assert.equal(oneSource([scan, { ...scan }]), true)
  assert.equal(oneSource([scan, { ...scan, confidence: 'low' }]), false)
  assert.equal(oneSource([scan, { ...scan, note: 'walls from the drawing' }]), false)
  assert.equal(oneSource([]), false)
})

test('checks that need attention stay in view; the rest fold with a line that says what is in them', () => {
  const c = (status: string) => ({ status })
  const mixed = splitChecks([c('pass'), c('fail'), c('unknown'), c('warn'), c('pass')])
  assert.deepEqual(mixed.shown.map((x) => x.status), ['fail', 'warn'])
  assert.equal(mixed.folded.length, 3)
  assert.equal(mixed.summary, '3 more checks: 2 passed, 1 not measured')
  assert.equal(splitChecks([c('fail'), c('pass')]).summary, '1 more check: 1 passed')
  // nothing to attend to: a short list is shown whole, a long one folds
  assert.deepEqual(splitChecks([c('pass'), c('pass'), c('unknown')]), { shown: [c('pass'), c('pass'), c('unknown')], folded: [], summary: '' })
  const long = splitChecks([c('pass'), c('pass'), c('pass'), c('pass'), c('unknown')])
  assert.deepEqual([long.shown.length, long.folded.length, long.summary], [0, 5, '5 checks: 4 passed, 1 not measured'])
  // everything needs attention: nothing to fold
  assert.deepEqual(splitChecks([c('fail'), c('warn')]).folded, [])
})
