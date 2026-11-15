import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readdirSync, readFileSync } from 'node:fs'
import { problems, type Flow } from './flow.ts'

const dir = new URL('./flows/', import.meta.url)
const files = readdirSync(dir).filter((f) => f.endsWith('.json'))

test('every demo flow can play', () => {
  assert.ok(files.length >= 6)
  const flows = files.map((f) => [f, JSON.parse(readFileSync(new URL(f, dir), 'utf8')) as Flow] as const)
  assert.deepEqual(flows.flatMap(([f, x]) => problems(x, f)), [])
  const ids = flows.map(([, x]) => x.id)
  assert.equal(new Set(ids).size, ids.length, 'flow ids are unique')
})

test('a broken flow is caught', () => {
  const bad = { id: 'x', title: 'X', track: 'T', steps: [{ do: 'jump' }, { do: 'tool', sid: '$nope' }] } as unknown as Flow
  assert.equal(problems(bad, 'bad.json').length, 3)
})
