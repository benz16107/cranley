import { test } from 'node:test'
import assert from 'node:assert/strict'
import { prefName, settled, toDoc, toQuestion, toServerOp, type Manifest } from './serverDoc.ts'
import { apply, inverse } from './reducer.ts'

const src = { layer: 'matterport', method: 'geometry', confidence: 'high' }
const ws = {
  id: 'ws_1', brief: { text: 'I use a wheelchair', limits: ['Nothing here checks parking.'], scope: { sids: ['s1'] } },
  questions: [{ id: 'q1', key: 'access.door_width_m', text: 'How wide?', tools: ['doors'], input: { type: 'number', 'x-unit': 'm' }, answer: 0.9, answered: false }],
  tools: [{ id: 'doors', enabled: true, reason: 'Doors matter.', by: 'agent' }, { id: 'gone', enabled: false }],
  runs: [
    { id: 'r1', tool: 'doors', sid: 's1', status: 'done', started: 10, finished: 12.5, steps: ['Measured 3 doors'], inputs: { min_width_m: 0.9 }, stale: true, plan_step: 'p1',
      result: { verdict: { status: 'fail', text: 'One door is too narrow.' },
        metrics: [{ id: 'narrowest', label: 'Narrowest', value: 0.7, unit: 'm', source: src }, { id: 'doors', label: 'Doors', value: 3, unit: '', source: src }],
        checks: [{ id: 'c_ok', rule: 'Hall', measured: 0.95, threshold: 0.9, unit: 'm', status: 'pass' }, { id: 'c_bad', rule: 'Bedroom', measured: 0.7, threshold: 0.9, unit: 'm', status: 'fail', findings: ['f1'] }],
        assumptions: [{ id: 'access.door_width_m', label: 'Width you need', value: 0.9, unit: 'm', editable: true }], actions: [{ id: 'turn', label: 'Check turning', tool: 'turning', inputs: { scan: 's1' } }] } },
    { id: 'r2', tool: 'doors', sid: 's2', status: 'error', error: 'needs min_width_m' },
    { id: 'r3', tool: 'doors', sid: 's3', status: 'running', steps: ['Reading the plan'] },
  ],
  findings: [{ id: 'f1', title: 'Bedroom door', status: 'fail', detail: '', anchor: { sid: 's1', opening: 'o1' }, source: src, tool: 'doors', run: 'r1' },
    { id: 'f_old', title: 'Old', status: 'warn', detail: '', anchor: null, source: src, superseded_by: 'r1' },
    { id: 'f_no', title: 'Rejected', status: 'warn', detail: '', anchor: null, source: src, feedback: { verdict: 'rejected' } }],
  overlays: [{ id: 'o_on', sid: 's1', tool: 'doors', visible: true, overlay: { kind: 'water', level_m: 1, datum: 'scan_z' } }, { id: 'o_off', sid: 's1', tool: 'doors', visible: false, overlay: { kind: 'water', level_m: 2, datum: 'scan_z' } }],
  panels: [{ id: 'panel:doors:s1', title: 'Door widths', tool: 'doors', run: 'r1', blocks: [
    { type: 'VerdictHeader', run: 'r1' }, { type: 'MetricRow', run: 'r1', metrics: ['narrowest', 'missing'] }, { type: 'CheckList', run: 'r1', checks: null, status: null },
    { type: 'Controls', tool: 'doors', controls: [{ input: 'min_width_m', pref: 'access.door_width_m', label: 'Width', kind: 'slider', min: 0.3, max: 2 }, { input: 'strict', pref: null, label: 'Strict', kind: 'toggle' }] },
    { type: 'AssumptionChips', run: 'r1' }, { type: 'StepLog', run: 'r1' }, { type: 'ActionBar', run: 'r1' }, { type: 'MiniChart', run: 'r9', title: 'No such run', metrics: ['x'] },
    { type: 'RankedTable', title: 'Compare', columns: [{ metric: 'narrowest', label: 'Narrowest', better: 'higher' }], rows: ['r1', 'r2'] }, { type: 'Hologram' }] }],
  plan: [{ id: 'p1', text: 'Measure the doors', status: 'in_progress' }], shortlist: [{ sid: 's1', note: '' }], camera: null,
}
const manifests = new Map<string, Manifest>([['doors', { id: 'doors', title: 'Door widths', summary: 'Measures doors.', status: 'ready', inputs: {} }]])
const names = (sid: string) => (sid === 's1' ? { name: 'Unit A', address: '1 Test St' } : undefined)

test('the server document becomes the shell document, numbers untouched', () => {
  const d = toDoc(ws, [{ key: 'access.door_width_m', text: 'You need 0.9 m doors', by: 'user', at: 5 }], manifests, names)
  assert.deepEqual(d.brief, { text: 'I use a wheelchair', facts: [], limits: ['Nothing here checks parking.'] })
  assert.deepEqual(d.tools.map((t) => [t.id, t.title, t.by]), [['doors', 'Door widths', 'agent']])
  assert.deepEqual(d.runs.map((r) => [r.label, r.status, r.ms, r.summary, r.stale]), [
    ['Door widths · Unit A', 'done', 2500, undefined, true], ['Door widths · s2', 'failed', undefined, 'needs min_width_m', false], ['Door widths · s3', 'running', undefined, 'Reading the plan', false]])
  assert.deepEqual(d.findings.map((f) => f.id), ['f1'])
  assert.deepEqual(d.overlays.map((o) => o.id), ['o_on'])
  assert.deepEqual(d.plan, [{ id: 'p1', label: 'Measure the doors', status: 'active' }])
  assert.deepEqual(d.shortlist, [{ sid: 's1', name: 'Unit A', address: '1 Test St', note: undefined }])
  const [p] = d.panels
  assert.deepEqual([p.sid, p.scope, p.run, p.role], ['s1', 'Unit A', 'r1', 'tool'])
  assert.deepEqual(d.runs.map((r) => r.sid), ['s1', 's2', 's3']) // a run names its scan, not only in its label
  const roles = toDoc({ id: 'w', panels: ['agent:summary', 'agent:ranked', 'compare:doors', 'agent:notes', 'custom:x'].map((id) => ({ id, title: id, blocks: [] })) }, [], manifests, names).panels.map((x) => x.role)
  assert.deepEqual(roles, ['summary', 'ranking', 'ranking', 'note', 'note'])
  assert.deepEqual(p.blocks.map((b) => b.type), ['VerdictHeader', 'MetricRow', 'CheckList', 'Controls', 'AssumptionChips', 'StepLog', 'ActionBar', 'RankedTable'])
  const block = <T extends string>(t: T) => p.blocks.find((b) => b.type === t) as Extract<(typeof p.blocks)[number], { type: T }>
  assert.deepEqual(block('VerdictHeader'), { type: 'VerdictHeader', status: 'fail', text: 'One door is too narrow.' })
  assert.deepEqual(block('MetricRow').metrics.map((m) => [m.id, m.value]), [['narrowest', 0.7]])
  assert.deepEqual(block('CheckList').checks.map((c) => c.id), ['c_bad', 'c_ok']) // worst first
  assert.deepEqual(block('Controls').controls.map((c) => [c.id, c.value]), [['access.door_width_m', 0.9], ['input:doors:strict', false]])
  assert.deepEqual(block('RankedTable').rows.map((r) => [r.label, r.values.narrowest]), [['Unit A', 0.7]]) // a run with no result is not a row
})

test('questions and user ops cross in both directions', () => {
  assert.deepEqual(toQuestion(ws.questions[0]), { id: 'q1', text: 'How wide?', pref: 'access.door_width_m', tool: 'doors', unit: 'm', kind: 'number', options: undefined, answer: undefined, hint: 0.9 })
  assert.equal(toQuestion({ id: 'q', key: 'k', text: 't', input: { type: 'boolean' }, answer: true, answered: true }).answer, 'Yes')
  assert.equal(toQuestion({ id: 'q', key: 'k', text: 't', input: { type: 'string', enum: ['a', 'b'] } }).kind, 'choice')
  const q = { questions: [{ id: 'qb', input: { type: 'boolean' } }, { id: 'qi', input: { type: 'integer' } }] }
  assert.deepEqual(toServerOp({ op: 'question.answer', by: 'user', id: 'qb', answer: 'No' }, q), { op: 'question.answer', id: 'qb', value: false })
  assert.deepEqual(toServerOp({ op: 'question.answer', by: 'user', id: 'qi', answer: 24 }, q), { op: 'question.answer', id: 'qi', value: 24 })
  assert.deepEqual(toServerOp({ op: 'tool.disable', by: 'user', id: 'doors' }, null), { op: 'tool.disable', tool: 'doors' })
  assert.equal(toServerOp({ op: 'camera.focus', by: 'user', anchor: { sid: 's1', room: 'r' } }, null), null) // where the person looks stays in the browser
  assert.equal(toServerOp({ op: 'pref.set', by: 'user', key: 'input:doors:strict', value: true }, null), null) // a run input, not a preference
})

test('a learned item keeps its value, so undoing a later change puts the old value back', () => {
  const tools = new Map<string, Manifest>([['flood', { id: 'flood', title: 'Flood rehearsal', summary: '', status: 'ready',
    inputs: { properties: { depth_m: { title: 'Depth M', type: 'number', 'x-pref': 'flood.depth_m', 'x-unit': 'm' }, riser_m: { title: 'Riser M', type: 'number' } } } }]])
  const learned = [{ key: 'flood.depth_m', value: 0.5, text: 'You answered “How deep could the water get?”', by: 'user', at: 7 }]
  const d = toDoc({ id: 'ws_1' }, learned, tools, names)
  assert.deepEqual(d.prefs, [{ key: 'flood.depth_m', label: 'Depth', unit: 'm', value: 0.5, from: 'You answered “How deep could the water get?”', by: 'user', at: 7000 }])
  // the person moves the depth to 1 m, then presses Ctrl Z: the op that goes back to the server carries 0.5, not ''
  const change = { op: 'pref.set', by: 'user', key: 'flood.depth_m', value: 1 } as const
  const undo = inverse(d, change)
  assert.equal(undo?.op === 'pref.set' && undo.value, 0.5)
  assert.deepEqual(toServerOp(undo!, null), { op: 'pref.set', key: 'flood.depth_m', value: 0.5, reason: 'You answered “How deep could the water get?”' })
  assert.equal(apply(apply(d, change), undo!).prefs[0].value, 0.5)
})

test('a learned item is named by the input it sets, or by what kind of note it is', () => {
  const tools = new Map<string, Manifest>([['stairs', { id: 'stairs', title: 'Stairs', summary: '', status: 'ready', inputs: { properties: { riser_m: { title: 'Riser M', 'x-unit': 'm' } } } }]])
  assert.deepEqual(prefName('stairs.riser_m', tools), { label: 'Riser', unit: 'm' }) // no x-pref: the key is <tool>.<input>
  assert.deepEqual(prefName('label.s1.r4', tools), { label: 'Room name' })
  assert.deepEqual(prefName('tool.off.flood', tools), { label: 'Tool switched off' })
  assert.deepEqual(prefName('access.turning_needed', tools), { label: 'Turning needed' })
})

test('a ranked table inside one run (a census by group) reads its cells from that run, in the order given', () => {
  const m = (id: string, label: string, value: number | null, unit = '') => ({ id, label, value, unit, source: src })
  const census = { id: 'ws_2', runs: [{ id: 'r_c', tool: 'city_census', status: 'done', result: { verdict: { status: 'pass', text: 'Two groups.' },
    metrics: [m('groups', 'Groups', 2), m('g0/share', 'home', 33, '%'), m('g0/scans', 'home', 120), m('g1/share', 'office', 44.4, '%'), m('g1/scans', 'office', 9)] } }],
    panels: [{ id: 'panel:city_census:', title: 'City census', tool: 'city_census', run: 'r_c', blocks: [{ type: 'RankedTable', title: 'City census by property type', run: 'r_c', rows: ['g1', 'g0', 'g9'], labels: { g1: 'Offices' },
      columns: [{ metric: 'share', label: 'Share', better: 'higher' }, { metric: 'scans', label: 'Scans', better: 'higher' }, { metric: 'median', label: 'Median' }] }] }] }
  const [table] = toDoc(census, [], manifests, names).panels[0].blocks
  assert.deepEqual(table, { type: 'RankedTable', title: 'City census by property type', source: src,
    columns: [{ id: 'share', label: 'Share', unit: '%', better: 'higher' }, { id: 'scans', label: 'Scans', unit: undefined, better: 'higher' }, { id: 'median', label: 'Median', unit: undefined, better: undefined }],
    rows: [ // the tool's order is kept; a row the block labels takes that label, the other its metric's; a key with no metric is left out
      { id: 'g1', label: 'Offices', values: { share: 44.4, scans: 9, median: null } },
      { id: 'g0', label: 'home', values: { share: 33, scans: 120, median: null } }] })
  // and a table whose run has no such metrics draws nothing, as before
  assert.deepEqual(toDoc({ ...census, panels: [{ id: 'p', title: 't', blocks: [{ type: 'RankedTable', run: 'r_c', rows: ['x'], columns: [{ metric: 'share', label: 'Share' }] }] }] }, [], manifests, names).panels[0].blocks, [])
})

test('a check follows its finding once the phone has settled it on site', () => {
  const check = (id: string, measured: number) => ({ id, rule: `Doorway ${id}`, measured, threshold: 0.815, unit: 'm', status: 'warn', findings: [`doors:s1:${id}`] })
  const finding = (id: string, status: string, layer: string, more = {}) => ({ id: `doors:s1:${id}`, title: id, status, detail: '', anchor: { sid: 's1', opening: id }, source: { layer, method: layer === 'phone' ? 'manual' : 'geometry', confidence: 'high' }, tool: 'doors', run: 'r1', ...more })
  const site = (value: number, unit = 'm') => ({ value: { verdict: 'contradicted', status: 'pass', value, unit }, by: 'user' })
  const doc = { id: 'ws_3',
    runs: [{ id: 'r1', tool: 'doors', sid: 's1', status: 'done', result: { verdict: { status: 'warn', text: 'Three doorways are close to the limit.' }, metrics: [], checks: [check('a', 0.832), check('b', 0.79), check('c', 0.8), check('d', 0.81)] } }],
    findings: [finding('a', 'pass', 'phone'), finding('b', 'warn', 'matterport'), finding('c', 'fail', 'phone'), finding('d', 'pass', 'phone', { superseded_by: 'r2' })],
    prefs: { 'site.width:s1:a': site(0.84), 'site.width:s1:c': site(0.78), 'site.step:s1:c': site(0.02), 'site.width:s1:b': site(0.9), 'site.slope:s1:a': site(4, '%') },
    panels: [{ id: 'panel:doors:s1', title: 'Door widths', tool: 'doors', run: 'r1', blocks: [{ type: 'CheckList', run: 'r1', checks: null, status: null }] }] }
  const [list] = toDoc(doc, [], manifests, names).panels[0].blocks
  assert.equal(list.type, 'CheckList')
  const rows = list.type === 'CheckList' ? list.checks.map((c) => [c.id, c.status, c.measured, c.site]) : []
  assert.deepEqual(rows, [ // worst first, by what each check is now
    ['c', 'fail', 0.8, { scan: 0.8, measured: false }], // settled on site, but a width and a step are both held for this doorway: no figure is guessed
    ['b', 'warn', 0.79, undefined], // its finding is still the scan's: an on-site value alone changes nothing
    ['d', 'warn', 0.81, undefined], // the phone's finding was superseded by a later run
    ['a', 'pass', 0.84, { scan: 0.832, measured: true }]]) // the 0.83 m caution is now the 0.84 m measured at the door (the slope there is in %, not this check's unit)
  // a block that lists only cautions no longer lists the door the phone passed
  const only = toDoc({ ...doc, panels: [{ ...doc.panels[0], blocks: [{ type: 'CheckList', run: 'r1', checks: null, status: ['warn'] }] }] }, [], manifests, names).panels[0].blocks[0]
  assert.deepEqual(only.type === 'CheckList' && only.checks.map((c) => c.id), ['b', 'd'])
  // a check with no finding, and a workspace with no findings or prefs at all, pass through
  assert.deepEqual(settled({ id: 'x', status: 'warn', measured: 1, unit: 'm' }, {}), { id: 'x', status: 'warn', measured: 1, unit: 'm' })
})
