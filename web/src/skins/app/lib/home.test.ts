import { test } from 'node:test'
import assert from 'node:assert/strict'
import { activity, homeBuildings, starterBuildings } from './home.ts'
import type { Building, Capture, Doc, Panel, Run } from '../../../core/index.ts'

const doc = (d: Partial<Doc>): Doc => ({ id: 'ws_1', brief: null, questions: [], tools: [], runs: [], findings: [], layers: [], overlays: [], panels: [], plan: [], prefs: [], shortlist: [], camera: null, log: [], ...d })
const building = (id: string, sids: string[], more: Partial<Building> = {}): Building => ({ id, lon: -95.4, lat: 29.7, address: `${id} Test St, Houston`, city: 'Houston', metro: 'hou',
  scans: sids.map((sid) => ({ sid, name: `Unit ${sid}`, rooms: 4, panos: 9, kind: 'apartment' })), count: sids.length, splat: false, defurnished: false, kinds: ['apartment'], rooms: 4, ...more })
const panel = (sid: string | undefined, status: 'pass' | 'warn' | 'fail', id = `p:${sid}:${status}`): Panel => ({ id, tool: 'doors', title: 'Door widths', sid, blocks: [{ type: 'VerdictHeader', status, text: '' }] })
const run = (id: string, status: Run['status'], more: Partial<Run> = {}): Run => ({ id, tool: 'doors', label: 'Door widths · Unit a', status, ...more })

test('buildings to get back to: kept first, then the ones with results, newest first', () => {
  const all = [building('1', ['a', 'b']), building('2', ['c'])]
  const d = doc({ shortlist: [{ sid: 'c', name: 'Unit c', address: '2 Test St' }], panels: [panel('a', 'pass'), panel('b', 'warn'), panel('a', 'fail', 'p:a:2'), panel(undefined, 'pass'), panel('gone', 'fail')] })
  assert.deepEqual(homeBuildings(d, all).map((x) => [x.sid, x.kept, x.results, x.worst]), [
    ['c', true, 0, undefined], // kept, nothing run on it yet
    ['a', false, 2, 'fail'], // its newest result is the last panel about a scan the list knows: the worst of its two verdicts shows
    ['b', false, 1, 'warn']]) // the city-wide panel and the scan the list does not know are left out
  assert.deepEqual(homeBuildings(d, all, 1).map((x) => x.sid), ['c'])
  assert.deepEqual(homeBuildings(doc({}), all), [])
})

test('a first visit is offered scanned addresses with a drone capture, from both cities', () => {
  const all = [building('h1', ['a'], { splat: true, rooms: 9 }), building('h2', ['b'], { splat: true, rooms: 12 }), building('h3', ['c'], { rooms: 30 }),
    building('l1', ['d'], { splat: true, metro: 'la', rooms: 3 }), building('h4', [], { splat: true, rooms: 40 })]
  assert.deepEqual(starterBuildings(all).map((x) => x.sid), ['b', 'a', 'd']) // fullest first; no capture or no scan: not offered
  assert.deepEqual(starterBuildings(all, 2).map((x) => x.sid), ['b', 'd']) // the other city keeps a place
  assert.deepEqual(starterBuildings([]), [])
})

test('the activity feed: work in progress, a question that holds it up, then what ended, newest first', () => {
  const capture: Capture = { id: 'cap_1', at: 2_000, kind: 'photo', note: 'Front doorway', file: 'cap_1.jpg' }
  const d = doc({ plan: [{ id: 's1', label: 'Measure each unit', status: 'active' }],
    questions: [{ id: 'q', text: 'How deep?', kind: 'number' }, { id: 'q2', text: 'How many?', kind: 'number', answer: 2 }],
    runs: [run('r1', 'done', { at: 1_000_000, ms: 500 }), run('r2', 'failed', { at: 1_500_000, ms: 100, summary: 'Give two or more scans.' }), run('r3', 'running', { at: 3_000_000, summary: 'Reading 2 panoramas' })] })
  assert.deepEqual(activity(d, [capture]).map((e) => [e.kind, e.id]), [
    ['working', 'r3'], ['ask', 'ask'], ['capture', 'cap_1'], ['run', 'r2'], ['run', 'r1']]) // the phone's photo (2,000 s) is newer than both runs
  const first = activity(d, [capture])[0]
  assert.equal(first.kind === 'working' && first.text, 'Reading 2 panoramas') // a running run says its latest progress line
  // a plan step with no run yet is still work in progress; a limit never hides what is happening now
  const thinking = activity(doc({ plan: d.plan, runs: [run('r1', 'done', { at: 1, ms: 1 }), run('r2', 'done', { at: 2, ms: 1 })] }), [], 1)
  assert.deepEqual(thinking.map((e) => [e.kind, e.id]), [['working', 'step:s1']])
  // scripted playback gives runs no time: they keep the document's order, newest last in it, first here
  assert.deepEqual(activity(doc({ runs: [run('a', 'done'), run('b', 'failed'), run('c', 'done')] }), []).map((e) => e.id), ['c', 'b', 'a'])
  // while the investigation is being set up its questions are on the setup card, not in the feed
  assert.deepEqual(activity(doc({ brief: { text: 'A brief', facts: [] }, questions: d.questions }), []), [])
  assert.deepEqual(activity(doc({}), []), [])
})
