import { test } from 'node:test'
import assert from 'node:assert/strict'
import { dur, int, num, plural } from './format.ts'

test('a value keeps the digits its size needs, and a missing one is a dash', () => {
  assert.equal(num(0.815), '0.82')
  assert.equal(num(15.44), '15.4')
  assert.equal(num(2098.4), '2,098')
  assert.equal(num(0.815, 3), '0.815')
  assert.equal(num(null), '–')
})
test('durations read in the unit a person would say', () => {
  assert.equal(dur(86), '86 ms')
  assert.equal(dur(1840), '1.8 s')
  assert.equal(dur(125_000), '2 min 5 s')
  assert.equal(dur(undefined), '')
})
test('counts take their noun', () => {
  assert.equal(plural(1, 'scan'), '1 scan')
  assert.equal(plural(3204, 'building'), '3,204 buildings')
  assert.equal(plural(2, 'criterion', 'criteria'), '2 criteria')
  assert.equal(int(4981), '4,981')
})
