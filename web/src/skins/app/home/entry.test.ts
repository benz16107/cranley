import assert from 'node:assert/strict'
import { test } from 'node:test'
import { entry, lines } from './entry.ts'

const one = { id: 'b1', metro: 'hou', scans: [{ sid: 's1' }] }, two = { id: 'b2', metro: null, scans: [{ sid: 's1' }, { sid: 's2' }] }

test('a sentence alone composes; nothing given does nothing', () => {
  assert.deepEqual(entry('  I rent  ', null), { do: 'compose', text: 'I rent' })
  assert.deepEqual(entry('   ', null), { do: 'nothing' })
})
test('a sentence about a building is asked on its first scan', () => {
  assert.deepEqual(entry('Does it flood?', two), { do: 'ask', text: 'Does it flood?', sid: 's1' })
})
test('a building alone opens: one scan directly, several on the map', () => {
  assert.deepEqual(entry('', one), { do: 'scan', sid: 's1' })
  assert.deepEqual(entry('', two), { do: 'explore', city: undefined, b: 'b2' })
  assert.deepEqual(entry('hello', { id: 'b3', metro: 'la', scans: [] }), { do: 'explore', city: 'la', b: 'b3' })
})
test('an address splits into the street and the rest', () => {
  assert.deepEqual(lines('1 Main St, Houston, TX'), ['1 Main St', 'Houston, TX'])
  assert.deepEqual(lines('Address not recorded'), ['Address not recorded', ''])
})
