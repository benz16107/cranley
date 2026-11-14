import { test } from 'node:test'
import assert from 'node:assert/strict'
import { guide, onSite, pickScan } from './firstrun.ts'
import type { Doc, Panel } from '../../../core/index.ts'

const doc = (d: Partial<Doc>): Doc => ({ id: 'ws_1', brief: null, questions: [], tools: [], runs: [], findings: [], layers: [], overlays: [], panels: [], plan: [], prefs: [], shortlist: [], camera: null, log: [], ...d })
const tool = (id: string) => ({ id, title: id, reason: 'because', by: 'agent' as const })
const panel = (sid: string, status: 'pass' | 'warn' | 'fail', title: string): Panel => ({ id: `${sid}:${title}`, tool: 'doors', title, sid, blocks: [{ type: 'VerdictHeader', status, text: `${title} says ${status}` }] })
const states = (d: Doc, opened: string | null = null) => guide(d, opened).steps.map((s) => `${s.id}:${s.state}`)
const brief = { text: 'I use a wheelchair', facts: [] }

test('the steps follow the workspace as the agent builds it', () => {
  assert.deepEqual(states(doc({ brief })), ['brief:done', 'tools:active', 'plan:pending', 'building:pending', 'findings:pending'])
  // tools arriving one at a time are still being chosen until the agent moves on
  assert.deepEqual(states(doc({ brief, tools: [tool('a')] })), ['brief:done', 'tools:active', 'plan:pending', 'building:pending', 'findings:pending'])
  const planned = doc({ brief, tools: [tool('a'), tool('b')], plan: [{ id: 's1', label: 'Find homes', status: 'active' }] })
  assert.deepEqual(states(planned), ['brief:done', 'tools:done', 'plan:done', 'building:active', 'findings:pending'])
  assert.equal(guide(planned, null).steps[1].label, '2 tools chosen for you')
  // a run names a scan: that is the building to open; once opened, its results are what the guide waits for
  const running = doc({ ...planned, runs: [{ id: 'r0', tool: 'search', label: 'Search', status: 'done' }, { id: 'r1', tool: 'doors', label: 'Door widths · Unit a', sid: 'a', status: 'running' }] })
  assert.deepEqual(guide(running, null).candidates, ['a'])
  // the agent's own short list comes sooner than its first run, and is what the guide picks from
  const picked = doc({ ...planned, brief: { ...brief, scope: ['x', 'y', 'z'] } })
  assert.deepEqual(guide(picked, null).candidates, ['x', 'y', 'z'])
  assert.equal(guide(picked, null).steps[3].label, '3 buildings picked')
  assert.deepEqual(states(running, 'a').slice(3), ['building:done', 'findings:active'])
})

test('it ends on something useful: two results on the open building, or one when the agent has stopped', () => {
  const plan = [{ id: 's1', label: 'Measure', status: 'active' as const }]
  const one = doc({ brief, tools: [tool('a')], plan, panels: [panel('a', 'pass', 'Door widths'), panel('b', 'fail', 'Elsewhere')] })
  assert.equal(guide(one, 'a').ready, false) // one result and the agent still working: more is coming
  assert.equal(guide(one, 'a').results, 1) // the other building's result is not this one's
  assert.equal(guide(doc({ ...one, plan: [{ ...plan[0], status: 'done' }] }), 'a').ready, true)
  const two = guide(doc({ ...one, panels: [...one.panels, panel('a', 'warn', 'Turning space')] }), 'a')
  assert.equal(two.ready, true)
  assert.deepEqual(two.verdict, { status: 'warn', text: 'Turning space says warn', title: 'Turning space' }) // the worst verdict, in the tool's own words
  assert.equal(two.steps.at(-1)!.label, '2 results on it so far')
})

test('when the agent measures other buildings than the one opened, the guide moves to one it did measure', () => {
  const plan = [{ id: 's1', label: 'Measure', status: 'active' as const }]
  const base = { brief: { ...brief, scope: ['a', 'b', 'c'] }, tools: [tool('t')], plan }
  // 'a' is open; the agent's runs are on 'b' so far, with one result: too soon to say 'a' was passed over
  const early = doc({ ...base, runs: [{ id: 'r1', tool: 'doors', label: 'x', sid: 'b', status: 'done' }], panels: [panel('b', 'pass', 'Door widths')] })
  assert.deepEqual(guide(early, 'a').instead, [])
  // 'b' has two results and 'a' still has no run: move there
  const passed = doc({ ...early, panels: [...early.panels, panel('b', 'warn', 'Turning space')] })
  assert.deepEqual(guide(passed, 'a').instead, ['b'])
  // a run on the opened scan means it is being measured: stay
  assert.deepEqual(guide(doc({ ...passed, runs: [...passed.runs, { id: 'r2', tool: 'doors', label: 'y', sid: 'a', status: 'running' }] }), 'a').instead, [])
  assert.deepEqual(guide(passed, null).instead, [])
})

test('a question with no answer on offer waits for the person; the others take the usual values', () => {
  const tools = [tool('a')]
  const offered = doc({ brief, tools, questions: [{ id: 'q', text: 'Chair width?', kind: 'number', hint: 0.7 }] })
  assert.equal(guide(offered, null).ask, false)
  assert.deepEqual(states(offered).slice(1, 4), ['tools:done', 'answers:active', 'plan:active'])
  const needs = doc({ brief, tools, questions: [{ id: 'q', text: 'Which address?', kind: 'text' }] })
  assert.equal(guide(needs, null).ask, true)
  assert.deepEqual(states(needs).slice(2, 4), ['answers:ask', 'plan:pending'])
  assert.equal(guide(needs, null).steps[2].label, 'One question needs your answer')
  // once the work has started the questions are behind it
  assert.deepEqual(states(doc({ ...offered, plan: [{ id: 's', label: 'x', status: 'active' }] })).slice(2, 4), ['answers:done', 'plan:done'])
})

test('the building it opens is a photoreal one on its site when the agent picked one', () => {
  const sids = ['a', 'b', 'c']
  assert.equal(pickScan(sids, [false, true, true], [true, false, true]), 'c') // made and on its site
  assert.equal(pickScan(sids, [false, true, false], [true, false, false]), 'b') // made, though it stands alone
  assert.equal(pickScan(sids, [false, false, false], [true, true, true]), 'a') // none made: the first, drawn as measured
  assert.equal(pickScan([], [], []), undefined)
  assert.equal(onSite({ geo: { lat: 29.7 }, quality: { georef: { fit: 0.9 } }, has: { splat: false } }), true)
  assert.equal(onSite({ geo: { lat: 29.7 }, quality: null, has: { splat: true } }), true) // tied to its own drone capture
  assert.equal(onSite({ geo: { lat: 29.7 }, quality: null, has: { splat: false } }), false) // placed, but the placing is not checked
  assert.equal(onSite({ geo: null, quality: { georef: {} }, has: { splat: true } }), false)
  assert.equal(onSite(null), false)
})
