import { test } from 'node:test'
import assert from 'node:assert/strict'
import { kindOf, matches, readFilters, search, toBuildings } from './buildings.ts'

const feature = (lon: number, lat: number, address: string, names: string[], segment = 'commercial', extra = {}) => ({
  geometry: { coordinates: [lon, lat] as [number, number] },
  properties: { address, city: '', segment, count: names.length, splat: false, defurnished: false, ...extra,
    scans: names.map((name, i): [string, string, string | null, number, number] => [`s${i}`, name, null, 3 + i, 5]) },
})
const all = toBuildings([
  feature(-95.4, 29.7, '1 Test St', ['1BR, 1BA - 700SF', 'Fitness Center']),
  feature(-118.3, 34.0, '2 Sample Ave', ['Suite 400 - 2,000 SF'], 'commercial', { defurnished: true }),
  feature(-95.5, 29.8, '3 Example Ln', ['3 Example Ln'], 'residential', { splat: true }),
])

test('kind is read from the scan name and segment', () => {
  assert.equal(kindOf('2BR, 2BA - B1', 'commercial'), 'apartment')
  assert.equal(kindOf('Studio - 552SF', 'commercial'), 'apartment')
  assert.equal(kindOf('Pool', 'commercial'), 'amenity')
  assert.equal(kindOf('14th Floor', 'commercial'), 'office')
  assert.equal(kindOf('9 Any Rd', 'residential'), 'home')
  assert.equal(kindOf('Warehouse', 'commercial'), 'other')
})

test('the server\'s kind per scan wins over the guess from the name', () => {
  const [b] = toBuildings([{ geometry: { coordinates: [-95.4, 29.7] }, properties: { id: 'p1', address: null, city: null, segment: 'commercial', count: 2, splat: false, defurnished: false,
    scans: [['a', 'Pool', 'apartment_unit', 4, 9], ['b', 'Dock', 'warehouse', null, 3]] } }])
  assert.deepEqual([b.id, b.address, b.kinds, b.rooms, b.scans[1].rooms], ['p1', 'Address not recorded', ['apartment', 'other'], 4, 0])
})

test('filters read from the URL and narrow the list', () => {
  const f = (s: string) => all.filter((b) => matches(b, readFilters(new URLSearchParams(s)))).map((b) => b.address)
  assert.deepEqual(f(''), ['1 Test St', '3 Example Ln'])
  assert.deepEqual(f('city=la'), ['2 Sample Ave'])
  assert.deepEqual(f('kind=home'), ['3 Example Ln'])
  assert.deepEqual(f('kind=apartment,amenity'), ['1 Test St'])
  assert.deepEqual(f('drone=1'), ['3 Example Ln'])
  assert.deepEqual(f('city=la&empty=1'), ['2 Sample Ave'])
  assert.deepEqual(f('rooms=4-'), ['1 Test St'])
  assert.deepEqual(f('rooms=1-3'), ['3 Example Ln'])
})

test('search needs every word, in the address or a scan name, in either city', () => {
  assert.deepEqual(search(all, 'sample ave').map((b) => b.address), ['2 Sample Ave'])
  assert.deepEqual(search(all, 'fitness').map((b) => b.address), ['1 Test St'])
  assert.deepEqual(search(all, 'test nothing'), [])
})
