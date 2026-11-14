import { test } from 'node:test'
import assert from 'node:assert/strict'
import { apply, emptyDoc, inverse } from './reducer.ts'
import type { Doc, Op, Panel } from './types.ts'

const run = (ops: Op[], doc: Doc = emptyDoc()) => ops.reduce(apply, doc)
const src = { layer: 'matterport', method: 'geometry', confidence: 'high' } as const

test('every op is appended to the log, whoever sent it', () => {
  const d = run([
    { op: 'brief.set', by: 'user', brief: { text: 'I use a wheelchair', facts: [] } },
    { op: 'tool.enable', by: 'agent', tool: { id: 'access', title: 'Step-free access', reason: 'You use a wheelchair' } },
  ])
  assert.equal(d.log.length, 2)
  assert.equal(d.tools[0].by, 'agent')
})

test('a panel upsert replaces in place and never reorders', () => {
  const p = (id: string, text: string): Panel => ({ id, tool: 'access', title: id, blocks: [{ type: 'Note', text }] })
  const d = run([
    { op: 'panel.upsert', by: 'agent', panel: p('a', 'one') },
    { op: 'panel.upsert', by: 'agent', panel: p('b', 'two') },
    { op: 'panel.upsert', by: 'agent', panel: p('a', 'three') },
  ])
  assert.deepEqual(d.panels.map((x) => x.id), ['a', 'b'])
  assert.deepEqual(d.panels[0].blocks[0], { type: 'Note', text: 'three' })
})

test('agent panels are cleaned: unknown blocks dropped, metric rows capped at four', () => {
  const m = (id: string) => ({ id, label: id, value: 1, unit: 'm', source: src })
  const panel = { id: 'a', tool: 't', title: 'A', blocks: [
    { type: 'Marquee', html: '<b>hi</b>' },
    { type: 'MetricRow', metrics: ['a', 'b', 'c', 'd', 'e'].map(m) },
  ] } as unknown as Panel
  const d = run([{ op: 'panel.upsert', by: 'agent', panel }])
  assert.equal(d.panels[0].blocks.length, 1)
  assert.equal(d.panels[0].blocks[0].type === 'MetricRow' && d.panels[0].blocks[0].metrics.length, 4)
})

test('disabling a tool removes its panels and overlays', () => {
  const d = run([
    { op: 'tool.enable', by: 'agent', tool: { id: 'access', title: 'Access', reason: '' } },
    { op: 'panel.upsert', by: 'agent', panel: { id: 'p', tool: 'access', title: 'P', blocks: [] } },
    { op: 'overlay.upsert', by: 'agent', id: 'o', tool: 'access', overlay: { kind: 'water', level_m: 1, datum: 'scan_z' } },
    { op: 'tool.disable', by: 'user', id: 'access' },
  ])
  assert.deepEqual([d.tools.length, d.panels.length, d.overlays.length], [0, 0, 0])
})

test('a preference remembers where it came from and what it replaced, and marks results stale', () => {
  const d = run([
    { op: 'run.start', by: 'agent', id: 'r1', tool: 'access', label: 'Unit A' },
    { op: 'run.finish', by: 'agent', id: 'r1', ms: 12 },
    { op: 'pref.set', by: 'agent', key: 'door', label: 'Clear door width', value: 0.815, unit: 'm', from: 'Default' },
    { op: 'pref.set', by: 'user', key: 'door', value: 0.9, from: 'You edited it' },
  ])
  assert.deepEqual([d.prefs[0].value, d.prefs[0].prev, d.prefs[0].label], [0.9, 0.815, 'Clear door width'])
  assert.equal(d.runs[0].stale, true)
})

test('inverse undoes user ops in the same vocabulary', () => {
  const ops: Op[] = [
    { op: 'pref.set', by: 'agent', key: 'door', label: 'Door', value: 0.815, from: 'Default' },
    { op: 'shortlist.add', by: 'user', item: { sid: 's1', name: 'Unit', address: '1 Test St' } },
    { op: 'tool.enable', by: 'agent', tool: { id: 'access', title: 'Access', reason: '' } },
  ]
  const base = run(ops)
  for (const op of [
    { op: 'pref.set', by: 'user', key: 'door', value: 0.9 },
    { op: 'pref.set', by: 'user', key: 'new', value: 3 },
    { op: 'shortlist.remove', by: 'user', sid: 's1' },
    { op: 'shortlist.add', by: 'user', item: { sid: 's2', name: 'Other', address: '2 Test St' } },
    { op: 'tool.disable', by: 'user', id: 'access' },
  ] as Op[]) {
    const inv = inverse(base, op)
    assert.ok(inv, op.op)
    const back = apply(apply(base, op), inv)
    assert.deepEqual([back.prefs.map((p) => [p.key, p.value]), back.shortlist, back.tools.map((t) => t.id)],
      [base.prefs.map((p) => [p.key, p.value]), base.shortlist, base.tools.map((t) => t.id)], op.op)
  }
})

test('an op this build does not know leaves the document alone', () => {
  const d = emptyDoc()
  assert.equal(apply(d, { op: 'hologram.project', by: 'agent' } as unknown as Op), d)
})
