import { notify } from './notices.ts'
import { dispatch, useWorkspace } from './store.ts'
import type { Action, Block, Doc, Op, OpInput, Panel, Question, ScanPlan, ToolResult } from './types.ts'
import * as server from './server.ts'
import { fetchPlan } from './api.ts'
import { currentRoute, navigate } from './router.ts'
import { CITIES, useBuildings, type Building, type CityId } from './buildings.ts'
import { ACCESS_DEFAULTS, accessAudit, accessPanel, type AccessPrefs } from './fixtures/access.ts'
import { matchNeed, NEEDS, TOOLS, type Need } from './fixtures/catalog.ts'

/* The link to the agent. With a server (server.ts) the server owns the workspace: turns stream its ops and the
   shell shows the document after each. When no server answers it plays fixtures: scripted ops through the same
   dispatch, so the shell behaves the same. */

const say = (op: OpInput) => dispatch({ ...op, by: 'agent' } as Op)
const doc = () => useWorkspace.getState().doc

let playing = 0 // a new playback cancels the one before it
let lastSids: string[] = []
let instant = false
const wait = (ms: number) => (instant ? Promise.resolve() : new Promise((r) => setTimeout(r, ms)))

/** One turn on the agent server. False when no server answers, and the fixtures play instead. */
async function serverTurn(body: { text?: string; sids?: string[] } = {}): Promise<boolean> {
  if (!(await server.connect())) return false
  try {
    const done = await server.turn(body)
    if (done?.status === 'needs_scope') { navigate('/map', {}, { keep: true }); notify('Pick a building to look at.', { description: 'Open a scan from the map, then run a tool from the dock or ask again.' }) }
    if (done?.budget?.stopped_by) notify(`The agent stopped at its limit of ${done.budget.stopped_by}.`, { description: 'Ask again to carry on from here.' })
  } catch { notify.error('The agent server did not answer.') }
  return true
}

useWorkspace.setState({
  onUserOp: (op: Op) => {
    if (server.isLive()) { void server.onUserOp(op); return }
    // fixtures: a changed access setting runs the audit again, as the server would
    if (op.op === 'pref.set' && op.key.startsWith('access.') && lastSids.length) void playAccess({ sids: lastSids, quick: true })
  },
})
void server.resume()

/** Start over: a new brief means a new workspace, on the server too. */
export function startOver() { playing++; server.forget(); useWorkspace.getState().reset(); lastSids = [] }

/* ---------- composing: who you are, which tools, which questions ---------- */
export async function compose(sentence: string, needId?: string) {
  startOver()
  const live = await server.connect()
  // shown at once; with a server this never reaches it as an op, the turn below carries the sentence
  useWorkspace.setState({ doc: { ...doc(), brief: { text: sentence, facts: [] } } })
  if (live) { navigate('/', {}, { replace: true }); void serverTurn({ text: sentence }); return }
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
  if (server.isLive()) { // unanswered questions take the value on offer; the server will not start with one open
    const open = d.questions.filter((q) => q.answer == null)
    if (open.some((q) => q.hint == null)) { notify('Answer the questions first.', { description: 'The tools cannot run without them.' }); return }
    for (const q of open) dispatch({ op: 'question.answer', by: 'user', id: q.id, answer: q.hint! })
    await new Promise((r) => setTimeout(r, open.length ? 600 : 0)) // let the answers land before the turn reads them
    void serverTurn()
    return
  }
  for (const q of d.questions) if (q.answer != null && q.pref) say(answerPref(q, q.answer))
  const need = matchNeed(d.brief?.text ?? '')
  if (!need.scripted || !d.tools.some((t) => t.id === 'access')) {
    navigate('/map', { city: need.city })
    notify('The tools are in the dock, ready.', { description: 'Without the agent server, only the step-free access investigation plays back.' })
    return
  }
  await playAccess({ city: need.city })
}

/** An answer to a tool's question becomes a preference, with the question kept as where it came from. */
export function answerPref(q: Question, answer: string | number) {
  const value = answer === 'Yes' ? true : answer === 'No' ? false : typeof answer === 'string' && /^[\d.]+/.test(answer) ? parseFloat(answer) : answer
  return { op: 'pref.set' as const, key: q.pref!, label: prefLabel(q.pref!) ?? q.text, value,
    unit: typeof value === 'number' ? (q.unit ?? String(answer).replace(/^[\d.]+\s*/, '')) : undefined, from: `You answered “${q.text}”` }
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
function candidateAddresses(all: Building[], city: CityId): { b: Building; sids: string[] }[] {
  const [cx, cy] = CITIES[city].center
  const one = (b: Building) => b.scans.filter((s) => /\b1 ?(br|bed)/i.test(s.name))
  return all.filter((x) => x.metro === city && one(x).length >= 2)
    .sort((p, q) => Math.hypot(p.lon - cx, p.lat - cy) - Math.hypot(q.lon - cx, q.lat - cy))
    .slice(0, 10).map((b) => ({ b, sids: one(b).slice(0, 3).map((s) => s.sid) }))
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
  const hasDoors = (p: ScanPlan) => p.openings.some((o) => o.type === 'doorway')
  let home: Building | undefined, sids = opts.sids ?? []
  if (sids.length) home = buildingOf(all, sids[0])
  else {
    // Many unit scans carry rooms but no wall outline. Probe one scan per address, nearest the centre first
    // and at most ten, until one has doorways to measure. Each probe is one cached request.
    const tries = candidateAddresses(all, opts.city ?? 'hou')
    if (!tries.length) { notify.error('No one-bedroom units found to compare in this city.'); say({ op: 'plan.set', steps: [] }); return }
    navigate('/map', { city: opts.city ?? 'hou' }, { keep: true })
    await wait(700 * pace)
    for (const t of tries) {
      if (!alive()) return
      const id = `probe:${t.sids[0]}`, t1 = performance.now()
      say({ op: 'run.start', id, tool: 'access', label: t.b.address.split(',')[0], step: 's1', sid: t.sids[0] })
      const ok = await fetchPlan(t.sids[0]).then(hasDoors, () => false)
      await wait(260 * pace)
      say({ op: 'run.finish', id, ms: performance.now() - t1, summary: ok ? 'Has a wall outline with doorways' : 'No wall outline, so nothing to measure' })
      home = t.b; sids = t.sids
      if (ok) break
    }
    if (!alive()) return
  }
  lastSids = sids
  // show the address on the map only when the agent chose it; a named scan is already in view
  if (home && !opts.sids?.length) say({ op: 'camera.focus', anchor: { geo: [home.lon, home.lat] } })
  log.push({ id: 'l1', label: STEPS[0], detail: home ? home.address.split(',')[0] : undefined, ms: performance.now() - t0 })
  await wait(1500 * pace)

  say({ op: 'plan.set', steps: planSteps(1) })
  const plans: ScanPlan[] = []
  for (const sid of sids) {
    if (!alive()) return
    const id = `read:${sid}`, t1 = performance.now()
    const name = home?.scans.find((x) => x.sid === sid)?.name ?? sid
    say({ op: 'run.start', id, tool: 'access', label: name, step: 's2', sid })
    try {
      const plan = await fetchPlan(sid)
      plans.push(plan)
      await wait(350 * pace)
      say({ op: 'run.finish', id, ms: performance.now() - t1, summary: `${plan.rooms.length} rooms, ${plan.openings.filter((o) => o.type === 'doorway').length} doorways` })
    } catch (e) { say({ op: 'run.finish', id, status: 'failed', summary: (e as Error).message }) }
  }
  if (!alive()) return
  if (!plans.length) { notify.error('None of the plans loaded.', { description: 'Check that the data server is running.' }); return }
  log.push({ id: 'l2', label: STEPS[1], detail: `${plans.length} of ${sids.length} loaded`, ms: performance.now() - t0 })

  say({ op: 'plan.set', steps: planSteps(2) })
  const prefs = accessPrefs(doc())
  const results: { plan: ScanPlan; r: ToolResult }[] = []
  for (const plan of plans) {
    const id = `audit:${plan.sid}`, t = performance.now()
    say({ op: 'run.start', id, tool: 'access', label: plan.name, step: 's3', sid: plan.sid })
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
    // open the chosen scan even when nothing in it could be measured
    say({ op: 'camera.focus', anchor: entrance?.anchor ?? { sid: best.plan.sid, point: [0, 0, 0] }, finding: entrance?.id })
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
  if (server.isLive()) {
    const sid = (action.inputs?.scan as string | undefined) ?? panel.sid
    const { scan: _scan, ...inputs } = action.inputs ?? {}
    if (sid) void server.runTool(action.id === 'rerun' ? panel.tool : action.tool ?? panel.tool, sid, action.id === 'rerun' ? {} : inputs)
    return
  }
  if (panel.tool !== 'access') { notify('This action needs the agent server.'); return }
  if (action.id === 'rerun') { void playAccess({ sids: lastSids.length ? lastSids : panel.sid ? [panel.sid] : [], quick: true }); return }
  if (action.id === 'compare_address' && panel.sid) {
    const b = buildingOf(await buildings(), panel.sid)
    const sids = b?.scans.filter((s) => s.kind === 'apartment' || s.kind === 'home').slice(0, 4).map((s) => s.sid) ?? []
    if (sids.length < 2) { notify('This address has no other unit to compare.'); return }
    void playAccess({ sids: [panel.sid, ...sids.filter((s) => s !== panel.sid)].slice(0, 4), quick: true })
  }
}

/** Run a tool on the scan in view, from the dock. */
export function runToolHere(tool: string, sid: string) {
  if (server.isLive()) { void server.runTool(tool, sid); return }
  if (tool !== 'access') { notify(`${TOOLS[tool]?.title ?? tool} needs the agent server.`, { description: 'Fixtures mode plays only the step-free access audit.' }); return }
  void playAccess({ sids: [sid], quick: true })
}

/** The one-line command bar. */
export async function ask(text: string) {
  const sid = currentRoute().sid, known: string[] = server.serverDoc()?.brief?.scope?.sids ?? []
  if (await serverTurn({ text, sids: sid && !known.includes(sid) ? [...known, sid] : undefined })) return
  if (/access|wheel|door|step/i.test(text) && currentRoute().sid) { runToolHere('access', currentRoute().sid!); return }
  notify('The agent server is not connected.', { description: 'Fixtures mode can replay the step-free access audit. Open a scan and add that tool from the dock.' })
}
