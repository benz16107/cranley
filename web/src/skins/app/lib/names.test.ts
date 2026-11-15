import { test } from 'node:test'
import assert from 'node:assert/strict'
import { nameIds } from './names.ts'

const all = [
  { id: 'p<property-id>', address: '12 Elm St, Houston, TX', scans: [{ sid: '<scan-id>', name: 'Unit 2B', rooms: 4, panos: 9, kind: 'apartment_unit' as const }] },
  { id: 'a12+elm', address: '9 Oak Ave, Houston, TX', scans: [] },
]

test('a scan id and a property number are put in words; measured numbers and other words are untouched', () => {
  const { named, of } = nameIds(all as never)
  assert.equal(named('The bedroom in <scan-id> is 0.813 m from property <property-id>, zip 77082, run 1234567.'), 'The bedroom in Unit 2B is 0.813 m from property 12 Elm St, zip 77082, run 1234567.')
  assert.deepEqual(of('<scan-id>'), { name: 'Unit 2B', address: '12 Elm St' })
  assert.equal(of('a12+elm'), undefined)
})
