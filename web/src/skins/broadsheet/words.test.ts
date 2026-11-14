import { test } from 'node:test'
import assert from 'node:assert/strict'
import { familyOf, headOf, leadOf, mediaParts, needLine, num, splitVerdict, unitOf, withUnit, word } from './words.ts'
import type { Block } from '../../core/index.ts'

const SRC = { layer: 'matterport', method: 'geometry', confidence: 'medium' } as const
const metric = (id: string, value: number | null) => ({ id, label: id, value, unit: 'm', source: SRC })
const check = (id: string, measured: number | null, threshold: number | null, status: 'pass' | 'warn' | 'fail' | 'unknown') => ({ id, rule: `Rule ${id}`, measured, threshold, unit: 'm', status, findings: [`f-${id}`] })

test('a failing check with a limit leads, and its number is the one in the block', () => {
  const blocks: Block[] = [
    { type: 'VerdictHeader', status: 'fail', text: 'x' }, { type: 'MetricRow', metrics: [metric('a', 4.11)] },
    { type: 'CheckList', checks: [check('none', null, 0.815, 'unknown'), check('hall', 1.031, 1.525, 'fail'), check('bed', 2.7, 1.525, 'pass')] },
  ]
  assert.deepEqual(leadOf(blocks), { label: 'Rule hall', value: 1.031, unit: 'm', need: 1.525, status: 'fail', source: null, finding: 'f-hall' })
})

test('a limit of zero is not a limit to hold a number against: the first measured metric leads', () => {
  const blocks: Block[] = [
    { type: 'VerdictHeader', status: 'fail', text: 'x' }, { type: 'MetricRow', metrics: [metric('gone', null), metric('depth', 0.35)] },
    { type: 'CheckList', checks: [check('garage', 0.503, 0, 'fail')] },
  ]
  assert.equal(leadOf(blocks)?.value, 0.35)
  assert.equal(leadOf(blocks)?.status, 'fail')
})

test('a passing story leads with its metric, and nothing measured leads with nothing', () => {
  assert.equal(leadOf([{ type: 'MetricRow', metrics: [metric('a', 2.5)] }, { type: 'CheckList', checks: [check('k', 2.5, 22.9, 'pass')] }])?.label, 'a')
  assert.equal(leadOf([{ type: 'Note', text: 'n' }, { type: 'MetricRow', metrics: [metric('a', null)] }]), null)
})

test('numbers are formatted, never changed', () => {
  assert.equal(num(0.354), '0.35')
  assert.equal(num(22.94), '22.9')
  assert.equal(num(1100), '1,100')
  assert.equal(num(null), 'not measured')
  assert.equal(withUnit(45, 'm2'), '45 m²')
  assert.equal(word(6), 'Six')
  assert.equal(word(4981), '4,981')
})

test('a verdict splits into a headline and a standfirst without touching its numbers', () => {
  assert.deepEqual(splitVerdict('No route wide enough to: kitchen. The entrance is a doorway with a room on one side only.'), ['No route wide enough to: kitchen.', 'The entrance is a doorway with a room on one side only.'])
  assert.deepEqual(splitVerdict('With water 0.60 m above the ground outside, water stands 0.35 m on the entry floor (0.22 to 0.44 m); 12 of 12 rooms take water.'),
    ['With water 0.60 m above the ground outside, water stands 0.35 m on the entry floor (0.22 to 0.44 m).', '12 of 12 rooms take water.'])
  assert.deepEqual(splitVerdict('Routed 2 rooms; the longest walk out is 2.5 m and the narrowest point 0.71 m. Hose stretch: 12 m.'), ['Routed 2 rooms; the longest walk out is 2.5 m and the narrowest point 0.71 m.', 'Hose stretch: 12 m.'])
  assert.deepEqual(splitVerdict('4 of 9 rooms cannot hold the turning circle in the empty room.'), ['4 of 9 rooms cannot hold the turning circle in the empty room.', ''])
  assert.equal(unitOf('count'), '')
})

test('families, limits and references', () => {
  assert.equal(familyOf('flood_rehearsal'), 'flood')
  assert.equal(familyOf('truck_access'), 'site')
  assert.equal(familyOf('something_new'), 'general')
  assert.equal(needLine('truth', 1100, 'ft²'), 'The record says 1,100 ft².')
  assert.equal(needLine('access', 0.815, 'm'), 'You need 0.815\u00a0m.')
  assert.equal(headOf('Step-free route, entrance to Bathroom 1: No walkable route'), 'Step-free route, entrance to Bathroom 1')
  assert.deepEqual(mediaParts('s/p/2', null), { sid: 's', a: 'p', b: '2' })
  assert.deepEqual(mediaParts('p', 's'), { sid: 's', a: 'p' })
  assert.equal(mediaParts('p', null), null)
})
