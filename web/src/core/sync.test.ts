import { test } from 'node:test'
import assert from 'node:assert/strict'
import { gate, serial, single } from './sync.ts'

const later = <T>(ms: number, v: T) => new Promise<T>((r) => setTimeout(() => r(v), ms))

test('a slow response never replaces a newer document', () => {
  const g = gate(), asked = g.now()
  assert.equal(g.take(asked, 12), true) // the turn ended: the document at log length 12 is on screen
  assert.equal(g.take(asked, 9), false) // a sync asked earlier arrives late
  assert.equal(g.at(), 12)
  assert.equal(g.take(asked, 12), true) // the same length is the same document (its busy list may differ)
  assert.equal(g.take(asked, 13), true)
})

test('a response that arrives after start-over is from the workspace left behind', () => {
  const g = gate(), old = g.now()
  g.take(old, 40)
  g.next()
  assert.equal(g.take(old, 41), false) // would have set the old workspace id again
  assert.equal(g.take(g.now(), 0), true) // the new workspace starts from an empty log
})

test('a server whose log was replaced is believed again after three shorter answers in a row', () => {
  const g = gate(), asked = g.now()
  g.take(asked, 50)
  assert.equal(g.take(asked, 4), false)
  assert.equal(g.take(asked, 4), false)
  assert.equal(g.take(asked, 4), true)
  assert.equal(g.at(), 4)
  g.take(asked, 9)
  assert.equal(g.take(asked, 8), false) // and a single late one after that is still just late
})

test('a response with no log length is judged by its generation alone', () => {
  const g = gate()
  g.take(g.now(), 5)
  assert.equal(g.take(g.now()), true)
  assert.equal(g.at(), 5)
})

test('callers that ask at the same moment share one request', async () => {
  let made = 0
  const ensure = single(async () => { made++; await later(5, null); return made })
  const [a, b] = await Promise.all([ensure(), ensure()])
  assert.deepEqual([a, b, made], [1, 1, 1]) // two ops before any workspace: one workspace
  assert.equal(await ensure(), 2) // once it has finished, the next caller asks again
})

test('writes go out in the order they were made, and idle waits for them', async () => {
  const w = serial(), sent: string[] = []
  void w.run(async () => { await later(15, null); sent.push('answer 1') })
  void w.run(async () => { await later(1, null); sent.push('answer 2') })
  await w.idle() // what investigate() awaits before the turn
  assert.deepEqual(sent, ['answer 1', 'answer 2'])
})

test('a write that fails does not hold up the next', async () => {
  const w = serial()
  const bad = w.run(async () => { throw new Error('refused') })
  const good = w.run(async () => 'ok')
  await assert.rejects(bad)
  assert.equal(await good, 'ok')
  await w.idle()
})
