import { toast } from 'sonner'
import { dispatch, useWorkspace } from './store.ts'
import type { Action, Block, Doc, Op, OpInput, Panel, ScanPlan, ToolResult } from './types.ts'
import { fetchPlan } from '../lib/api.ts'
import { currentRoute, navigate } from '../lib/router.ts'
import { CITIES, useBuildings, type Building } from '../map/buildings.ts'
import { ACCESS_DEFAULTS, accessAudit, accessPanel, type AccessPrefs } from '../fixtures/access.ts'
import { matchNeed, NEEDS, TOOLS, type Need } from '../fixtures/catalog.ts'

/* The link to the agent. It tries the server first (POST /api/agent/turn, a stream of workspace ops). When the
   server is not there it plays fixtures: scripted ops through the same dispatch, so the shell behaves the same. */

const say = (op: OpInput) => dispatch({ ...op, by: 'agent' } as Op)
const doc = () => useWorkspace.getState().doc

let live: boolean | null = null // is the agent server answering
let playing = 0 // a new playback cancels the one before it
let lastSids: string[] = []
let instant = false
const wait = (ms: number) => (instant ? Promise.resolve() : new Promise((r) => setTimeout(r, ms)))

async function serverTurn(text: string): Promise<boolean> {
  if (live === false) return false
  try {
    const r = await fetch('/api/agent/turn', { method: 'POST', headers: { 'content-type': 'application/json', accept: 'text/event-stream' },
      body: JSON.stringify({ workspace: doc().id, text }) })
    if (!r.ok || !r.body) { live = false; return false }
    live = true
    const reader = r.body.pipeThrough(new TextDecoderStream()).getReader()
    let buf = ''
    for (;;) {
      const { value, done } = await reader.read()
      if (done) break
      buf += value
      const events = buf.split('\n\n')
      buf = events.pop()!
      for (const e of events) {
        const data = e.split('\n').filter((l) => l.startsWith('data:')).map((l) => l.slice(5).trim()).join('')
        if (!data) continue
        try { dispatch({ by: 'agent', ...JSON.parse(data) }) } catch { /* a malformed event is skipped, the stream goes on */ }
      }
    }
    return true
  } catch { live = false; return false }
}

useWorkspace.setState({
  onUserOp: (op: Op) => {
    if (live) { void fetch(`/api/workspace/${doc().id}/ops`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ ops: [op] }) }); return }
    // fixtures: a changed access setting runs the audit again, as the server would
    if (op.op === 'pref.set' && op.key.startsWith('access.') && lastSids.length) void playAccess({ sids: lastSids, quick: true })
  },
})

/* ---------- composing: who you are, which tools, which questions ---------- */
export async function compose(sentence: string, needId?: string) {
  playing++
  useWorkspace.getState().reset()
  lastSids = []
  dispatch({ op: 'brief.set', by: 'user', brief: { text: sentence, facts: [] } })
  if (await serverTurn(sentence)) return
  const need = NEEDS.find((n) => n.id === needId) ?? matchNeed(sentence)
  const my = playing
  navigate('/', { city: need.city, composing: '1' }, { replace: true })
  for (const [id, reason] of need.tools) {
    await wait(520)
    if (my !== playing) return
    say({ op: 'tool.enable', tool: { ...TOOLS[id], reason } })
  }
  await wait(420)
  for (const q of need.questions) { if (my !== playing) return; say({ op: 'question.ask', question: q }); await wait(180) }
}

/** Every question answered: start the investigation. */
export async function investigate() {
  const d = doc()
  for (const q of d.questions) {
    if (q.answer == null || !q.pref) continue
    const value = q.answer === 'Yes' ? true : q.answer === 'No' ? false : typeof q.answer === 'string' && /^[\d.]+/.test(q.answer) ? parseFloat(q.answer) : q.answer
    say({ op: 'pref.set', key: q.pref, label: prefLabel(q.pref) ?? q.text, value, unit: typeof value === 'number' ? (q.unit ?? String(q.answer).replace(/^[\d.]+\s*/, '')) : undefined, from: `You answered “${q.text}”` })
  }
  if (live) { void serverTurn('Start the investigation.'); return }
  const need = matchNeed(d.brief?.text ?? '')
  if (!need.scripted || !d.tools.some((t) => t.id === 'access')) {
    navigate('/map', { city: need.city })
    toast('The tools are in the dock, ready.', { description: 'Without the agent server, only the step-free access investigation plays back.' })
    return
  }
  await playAccess({ city: need.city })
}

const prefLabel = (key: string) => ({ 'access.door_clear': 'Clear door width', 'access.turning': 'Turning circle', 'access.turning_needed': 'Turning space in the bathroom', 'access.route_to': 'Route drawn to' } as Record<string, string>)[key]

function accessPrefs(d: Doc): AccessPrefs {
  const get = <K extends keyof typeof ACCESS_DEFAULTS>(k: K) => (d.prefs.find((p) => p.key === k)?.value ?? ACCESS_DEFAULTS[k]) as (typeof ACCESS_DEFAULTS)[K]
  return { door: get('access.door_clear'), turning: get('access.turning'), turningNeeded: get('access.turning_needed'), routeTo: get('access.route_to') }
}

async function buildings(): Promise<Building[]> {
  const s = useBuildings.getState()
  if (s.state === 'ready') return s.all
  s.load()
  return new Promise((res) => { const off = useBuildings.subscribe((x) => { if (x.state !== 'loading') { off(); res(x.all) } }) })
}
const buildingOf = (all: Building[], sid: string) => all.find((b) => b.scans.some((s) => s.sid === sid))

/** Addresses with two or more one-bedroom units, nearest the middle of the city first: small, fair sets to compare. */
function candidateAddresses(all: Building[], city: Need['city']): { b: Building; sids: string[] }[] {
  const [cx, cy] = CITIES[city].center
  const one = (b: Building) => b.scans.filter((s) => /\b1 ?(br|bed)/i.test(s.name))
  return all.filter((x) => x.metro === city && one(x).length >= 2)
    .sort((p, q) => Math.hypot(p.lon - cx, p.lat - cy) - Math.hypot(q.lon - cx, q.lat - cy))
    .slice(0, 4).map((b) => ({ b, sids: one(b).slice(0, 3).map((s) => s.sid) }))
}

const STEPS = ['Find one-bedroom units to compare', 'Read each floor plan', 'Trace the way in and measure every doorway', 'Rank the units', 'Show what decides it']
const planSteps = (active: number) => STEPS.map((label, i) => ({ id: `s${i + 1}`, label, status: i < active ? 'done' as const : i === active ? 'active' as const : 'pending' as const }))
const rank = { pass: 0, warn: 1, unknown: 2, fail: 3 }

/** The scripted investigation: an accessibility audit of apartments, as ops. */
export async function playAccess(opts: { sids?: string[]; city?: Need['city']; quick?: boolean; instantly?: boolean }) {
  const my = ++playing
  const alive = () => my === playing
  instant = !!opts.instantly
  const pace = opts.quick ? 0.25 : 1
  const t0 = performance.now()
  const log: { id: string; label: string; detail?: string; ms?: number }[] = []
  const all = await buildings()
  if (!doc().tools.some((t) => t.id === 'access')) say({ op: 'tool.enable', tool: { ...TOOLS.access, reason: 'You asked for it on this scan.' } })

  say({ op: 'plan.set', steps: planSteps(0) })
  // Either the scans were named, or the agent tries addresses in turn until one has doorways to measure.
  const named = opts.sids?.length ? [{ b: buildingOf(all, opts.sids[0]), sids: opts.sids }] : null
  const tries = named ?? candidateAddresses(all, opts.city ?? 'hou')
  if (!tries.length) { toast.error('No one-bedroom units found to compare in this city.'); say({ op: 'plan.set', steps: [] }); return }
  let home: Building | undefined, sids: string[] = []
  const plans: ScanPlan[] = []
  for (const [n, t] of tries.entries()) {
    home = t.b; sids = t.sids; plans.length = 0
    if (!named) { navigate('/map', { city: home?.metro ?? undefined }, { keep: true }); await wait(n ? 300 : 900 * pace) }
    if (!alive()) return
    if (home && !opts.quick) say({ op: 'camera.focus', anchor: { geo: [home.lon, home.lat] } })
    await wait(1400 * pace)
    say({ op: 'plan.set', steps: planSteps(1) })
    for (const sid of sids) {
      if (!alive()) return
      const id = `read:${sid}`, t1 = performance.now()
      const name = home?.scans.find((x) => x.sid === sid)?.name ?? sid
      say({ op: 'run.start', id, tool: 'access', label: name, step: 's2' })
      try {
        const plan = await fetchPlan(sid)
        plans.push(plan)
        await wait(350 * pace)
        say({ op: 'run.finish', id, ms: performance.now() - t1, summary: `${plan.rooms.length} rooms, ${plan.openings.filter((o) => o.type === 'doorway').length} doorways` })
      } catch (e) { say({ op: 'run.finish', id, status: 'failed', summary: (e as Error).message }) }
    }
    if (named || plans.some((p) => p.openings.some((o) => o.type === 'doorway')) || n === tries.length - 1) break
    log.push({ id: `skip${n}`, label: `No wall outline at ${home?.address.split(',')[0]}`, detail: 'Trying the next address', ms: performance.now() - t0 })
    say({ op: 'plan.set', steps: planSteps(0) })
  }
  if (!alive()) return
  lastSids = sids
  log.push({ id: 'l1', label: STEPS[0], detail: home ? home.address.split(',')[0] : undefined, ms: performance.now() - t0 })
  if (!plans.length) { toast.error('None of the plans loaded.', { description: 'Check that the data server is running.' }); return }
  log.push({ id: 'l2', label: STEPS[1], detail: `${plans.length} of ${sids.length} loaded`, ms: performance.now() - t0 })

  say({ op: 'plan.set', steps: planSteps(2) })
  const prefs = accessPrefs(doc())
  const results: { plan: ScanPlan; r: ToolResult }[] = []
  for (const plan of plans) {
    const id = `audit:${plan.sid}`, t = performance.now()
    say({ op: 'run.start', id, tool: 'access', label: plan.name, step: 's3' })
    const r = accessAudit(plan, prefs)
    results.push({ plan, r })
    await wait(500 * pace)
    if (!alive()) return
    say({ op: 'run.finish', id, ms: performance.now() - t, summary: r.verdict.text })
  }
  log.push({ id: 'l3', label: STEPS[2], detail: `Limit ${prefs.door} m`, ms: performance.now() - t0 })

  say({ op: 'plan.set', steps: planSteps(3) })
  const val = (r: ToolResult, id: string) => r.metrics.find((m) => m.id === id)?.value ?? null
  results.sort((a, b) => rank[a.r.verdict.status] - rank[b.r.verdict.status] || (val(b.r, 'narrowest') ?? 0) - (val(a.r, 'narrowest') ?? 0))
  const best = results[0]
  for (const f of best.r.findings) say({ op: 'finding.add', tool: 'access', finding: f })
  const doors = best.r.overlays.flatMap((o) => (o.kind === 'route' ? o.chokes : []))
  const extra: Block[] = [
    ...(results.length > 1 ? [{ type: 'RankedTable' as const, source: best.r.metrics[0]?.source ?? { layer: 'matterport' as const, method: 'geometry' as const, confidence: 'medium' as const },
      columns: [{ id: 'narrowest', label: 'Narrowest', unit: 'm', better: 'higher' as const }, { id: 'under', label: 'Under limit', better: 'lower' as const }, { id: 'route', label: 'Route', unit: 'm', better: 'lower' as const }],
      rows: results.map(({ plan, r }) => ({ id: plan.sid, label: plan.name, status: r.verdict.status, anchor: { sid: plan.sid, point: [0, 0, 0] as [number, number, number] },
        values: { narrowest: val(r, 'narrowest'), under: val(r, 'under'), route: val(r, 'route') } })) }] : []),
    ...(doors.length > 1 ? [{ type: 'MiniChart' as const, title: 'Doorways along the route, in order', unit: 'm', source: best.r.metrics[0].source,
      bars: doors.map((c, i) => ({ label: `Door ${i + 1}`, value: c.width, status: c.status })), mark: { value: prefs.door, label: `limit ${prefs.door}` } }] : []),
    { type: 'Controls', controls: [
      { id: 'access.route_to', label: 'Draw the route to', kind: 'select', value: prefs.routeTo, options: ['Bedroom', 'Bathroom', 'Kitchen'] },
      { id: 'access.turning_needed', label: 'Check turning space', kind: 'toggle', value: prefs.turningNeeded },
    ] },
    { type: 'Note', text: results.length > 1
      ? 'Ranked by verdict, then by the narrowest doorway. Widths are openings in the scan’s wall outline, so a hung door leaf can take a few centimetres more.'
      : 'Widths are openings in the scan’s wall outline, so a hung door leaf can take a few centimetres more.' },
  ]
  log.push({ id: 'l4', label: STEPS[3], detail: results.length > 1 ? `${results.length} units compared` : 'One unit', ms: performance.now() - t0 })
  say({ op: 'panel.upsert', panel: accessPanel(best.r, best.plan, `audit:${best.plan.sid}`, extra, log) })
  const overlayOf = (kind: string, style?: string) => best.r.overlays.find((o) => o.kind === kind && (!style || (o.kind === 'rule' && o.style === style))) ?? null
  say({ op: 'overlay.upsert', id: 'access:route', tool: 'access', sid: best.plan.sid, overlay: overlayOf('route') })
  for (const s of ['pass', 'warn', 'fail']) say({ op: 'overlay.upsert', id: `access:rule:${s}`, tool: 'access', sid: best.plan.sid, overlay: overlayOf('rule', s) })
  say({ op: 'overlay.upsert', id: 'access:pins', tool: 'access', sid: best.plan.sid, overlay: overlayOf('pins') })
  await wait(1100 * pace)
  if (!alive()) return

  say({ op: 'plan.set', steps: planSteps(4) })
  const worstFirst = [...best.r.findings].sort((a, b) => rank[b.status] - rank[a.status])
  if (!opts.quick) {
    const entrance = best.r.findings[0]
    if (entrance?.anchor) say({ op: 'camera.focus', anchor: entrance.anchor, finding: entrance.id })
    await wait(1700)
    if (!alive()) return
    if (worstFirst[0]?.anchor && worstFirst[0].id !== entrance?.id) say({ op: 'camera.focus', anchor: worstFirst[0].anchor, finding: worstFirst[0].id })
    await wait(900)
  }
  if (alive()) say({ op: 'plan.set', steps: planSteps(5) })
  instant = false
}

/** A link with ?demo=access replays the whole audit on that scan at once, so the view it names can be opened cold. */
export function replayDemo(sid: string) {
  if (doc().log.length) return
  const need = NEEDS[0]
  say({ op: 'brief.set', brief: { text: need.sentence, facts: [] } })
  for (const [id, reason] of need.tools) say({ op: 'tool.enable', tool: { ...TOOLS[id], reason } })
  void playAccess({ sids: [sid], instantly: true })
}

/** Follow-up commands from a panel's ActionBar, and "run again". */
export async function runAction(action: Action, panel: Panel) {
  if (live) { void serverTurn(`Run action ${action.id} on panel ${panel.id}.`); return }
  if (panel.tool !== 'access') { toast('This action needs the agent server.'); return }
  if (action.id === 'rerun') { void playAccess({ sids: lastSids.length ? lastSids : panel.sid ? [panel.sid] : [], quick: true }); return }
  if (action.id === 'compare_address' && panel.sid) {
    const b = buildingOf(await buildings(), panel.sid)
    const sids = b?.scans.filter((s) => s.kind === 'apartment' || s.kind === 'home').slice(0, 4).map((s) => s.sid) ?? []
    if (sids.length < 2) { toast('This address has no other unit to compare.'); return }
    void playAccess({ sids: [panel.sid, ...sids.filter((s) => s !== panel.sid)].slice(0, 4), quick: true })
  }
}

/** Run a tool on the scan in view, from the dock. */
export function runToolHere(tool: string, sid: string) {
  if (live) { void serverTurn(`Run ${tool} on scan ${sid}.`); return }
  if (tool !== 'access') { toast(`${TOOLS[tool]?.title ?? tool} needs the agent server.`, { description: 'Fixtures mode plays only the step-free access audit.' }); return }
  void playAccess({ sids: [sid], quick: true })
}

/** The one-line command bar. */
export async function ask(text: string) {
  if (await serverTurn(text)) return
  if (/access|wheel|door|step/i.test(text) && currentRoute().sid) { runToolHere('access', currentRoute().sid!); return }
  toast('The agent server is not connected.', { description: 'Fixtures mode can replay the step-free access audit. Open a scan and add that tool from the dock.' })
}
