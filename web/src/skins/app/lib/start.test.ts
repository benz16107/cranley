import { test } from 'node:test'
import assert from 'node:assert/strict'
import { encode, problem } from './start.ts'
import type { Field } from './tools.ts'

const f = (x: Partial<Field>): Field => ({ id: 'x', label: 'X', about: '', kind: 'text', required: false, first: true, ...x })

test('a required field left empty is a problem; an optional one is not', () => {
  assert.equal(problem(f({ required: true }), ' '), 'Needed to run')
  assert.equal(problem(f({}), ''), null)
})

test('a number is checked against its kind and its limits', () => {
  const n = f({ kind: 'number', min: 0, max: 3 })
  assert.equal(problem(n, 'abc'), 'A number')
  assert.equal(problem(n, '4'), 'At most 3')
  assert.equal(problem(n, '0.5'), null)
  assert.equal(problem(f({ kind: 'number', whole: true }), '2.5'), 'A whole number')
})

test('an input left at the tool\'s own default is not sent', () => {
  assert.equal(encode(f({ kind: 'number', fallback: 0.815 }), '0.815'), undefined)
  assert.equal(encode(f({ kind: 'number', fallback: 0.815 }), '0.9'), 0.9)
  assert.equal(encode(f({ kind: 'toggle', fallback: true }), true), undefined)
  assert.equal(encode(f({ kind: 'toggle', fallback: true }), false), false)
  assert.equal(encode(f({}), '  '), undefined)
})

test('criteria are read one per line as measure, comparison, value', () => {
  const c = f({ kind: 'criteria' })
  assert.deepEqual(encode(c, 'wheelchair_bath == 1\n bath_route_door>=0.81 \n\nlargest_room_label == Kitchen'), [
    { measure: 'wheelchair_bath', op: '==', value: 1 }, { measure: 'bath_route_door', op: '>=', value: 0.81 }, { measure: 'largest_room_label', op: '==', value: 'Kitchen' },
  ])
  assert.equal(problem(c, 'one floor please'), 'One per line, as: floors == 1')
})

test('a typed position is latitude then longitude, sent as [lon, lat]', () => {
  const p = f({ kind: 'point' })
  assert.deepEqual(encode(p, '29.7604, -95.3698'), [-95.3698, 29.7604])
  assert.notEqual(problem(p, '29.7604'), null)
})

test('one typed sound level becomes one reading', () => {
  assert.deepEqual(encode(f({ kind: 'reading' }), '48'), [{ leq_dba: 48, seconds: 30 }])
})
