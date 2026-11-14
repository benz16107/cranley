import { test } from 'node:test'
import assert from 'node:assert/strict'
import { resized, type Sized } from './split.ts'

test('only a pane the person resized is remembered', () => {
  const side: Sized = { id: 'side', last: 224 }, run: Sized = { id: 'run', last: 372 }
  // the person drags the sidebar's edge on a 1,600 px split: the page gives way, the agent panel does not move
  assert.deepEqual(resized([side, run], { side: 20, work: 56.75, run: 23.25 }, 1600, true), [['side', 320]])
  assert.equal(side.last, 320)
  // the window shrinks to 1,000 px and squeezes the agent panel: nothing is remembered, but its size is noted
  assert.deepEqual(resized([side, run], { side: 32, work: 36, run: 32 }, 1000, false), [])
  assert.equal(run.last, 320)
  // the person then moves the sidebar again: the squeezed agent panel keeps the width they chose for it earlier
  assert.deepEqual(resized([side, run], { side: 25, work: 43, run: 32 }, 1000, true), [['side', 250]])
})

test('a pane the split has not laid out yet, or a split with no size, remembers nothing', () => {
  const run: Sized = { id: 'run' } // just added: no size until the first layout that has it
  assert.deepEqual(resized([run], { side: 20, work: 80 }, 1600, true), [])
  assert.deepEqual(resized([run], { side: 20, work: 55, run: 25 }, 1600, true), []) // its first size is where it starts, not a choice
  assert.equal(run.last, 400)
  assert.deepEqual(resized([run], { run: 30 }, 0, true), [])
})
