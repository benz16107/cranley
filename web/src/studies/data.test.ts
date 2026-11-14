import { test } from 'node:test'
import assert from 'node:assert/strict'
import { rank, type Audit } from './data.ts'

const a = (traced: boolean, under: number, width: number) => ({ traced, under, worst: { measured: width } }) as unknown as Audit

test('rank: fewest doorways to widen first, then the widest narrow doorway, untraced scans last', () => {
  const twoNarrow = a(true, 2, 0.54), twoWide = a(true, 2, 0.7), five = a(true, 5, 0.79), untraced = a(false, 0, 2.8)
  assert.deepEqual([five, untraced, twoNarrow, twoWide].sort(rank), [twoWide, twoNarrow, five, untraced])
})
