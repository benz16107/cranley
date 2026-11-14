import { test } from 'node:test'
import assert from 'node:assert/strict'
import { tally, worstVerdict } from './verdict.ts'
import type { Panel } from '../../../core/index.ts'

const panel = (id: string, status: 'pass' | 'warn' | 'fail' | 'unknown', text = `${id} is ${status}`): Panel => ({ id, tool: 't', title: `Tool ${id}`, blocks: [{ type: 'VerdictHeader', status, text }, { type: 'Note', text: 'more' }] })

test('the verdict to read first is the worst one, in its tool’s own words', () => {
  assert.deepEqual(worstVerdict([panel('a', 'pass'), panel('b', 'warn'), panel('c', 'unknown')]), { status: 'warn', text: 'b is warn', title: 'Tool b', panel: 'b' })
  assert.equal(worstVerdict([panel('a', 'warn'), panel('b', 'fail'), panel('c', 'warn')])?.panel, 'b')
  assert.equal(worstVerdict([panel('a', 'pass'), panel('b', 'pass')])?.panel, 'b') // among equals, the newest
  assert.equal(worstVerdict([panel('a', 'unknown'), panel('b', 'pass')])?.status, 'unknown') // not measured is not a pass
  assert.equal(worstVerdict([]), undefined)
  assert.equal(worstVerdict([{ id: 'n', tool: 't', title: 'A note', blocks: [{ type: 'Note', text: 'no verdict' }] }]), undefined)
})

test('the results are counted by verdict, worst first', () => {
  assert.equal(tally([panel('a', 'pass'), panel('b', 'fail'), panel('c', 'pass'), panel('d', 'warn')]), '1 failed, 1 needs a look, 2 passed')
  assert.equal(tally([panel('a', 'warn'), panel('b', 'warn'), panel('c', 'unknown')]), '2 need a look, 1 not measured')
  assert.equal(tally([]), '')
})
