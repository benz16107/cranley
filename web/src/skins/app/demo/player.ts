import { create } from 'zustand'
import { ask, focusFinding, investigate, runTool, shareWorkspace, startOver, userOp, useWorkspace } from '../../../core/index.ts'
import { idle, turn } from '../../../core/server.ts'
import { go, goInvestigation, goScan, type Page } from '../lib/place.ts'
import { useUi } from '../shell/store.ts'

/* Plays a scripted demo flow (flows/*.json, README.md beside this file) through the same calls a person's clicks
   make: the agent's turns, tool runs, the camera, and the page's own buttons found by their label. A step that fails
   or takes too long runs its `else` step, or is skipped with a note, and the flow goes on. */

export type Step = {
  do: 'new' | 'open' | 'ask' | 'answer' | 'tool' | 'click' | 'type' | 'focus' | 'agent' | 'share' | 'window' | 'wait' | 'say' | 'firstrun'
  say?: string
  /** ms the caption stays after the step is done (default 1500) */
  hold?: number
  /** ms before the step counts as failed (default 30000; ask 150000) */
  timeout?: number
  else?: Step
  [k: string]: unknown
}
export type Flow = { id: string; title: string; track: string; about?: string; vars?: Record<string, string>; steps: Step[] }

const files = import.meta.glob<{ default: Flow }>('./flows/*.json', { eager: true })
export const FLOWS: Flow[] = Object.values(files).map((m) => m.default).sort((a, b) => a.track.localeCompare(b.track))

type State = { flow: Flow | null; i: number; say: string; note: string; paused: boolean; started: number; pausedFor: number; done: boolean
  /** a popup the browser blocked: the caption bar offers a button that opens it from a real click */
  popup: string | null }
export const useDemo = create<State>(() => ({ flow: null, i: 0, say: '', note: '', paused: false, started: 0, pausedFor: 0, done: false, popup: null }))

let token = 0 // a new play or a stop ends the one before
let skip = false // "Next": leave the step's hold early
const doc = () => useWorkspace.getState().doc
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

/** Waits while paused; throws once the flow was stopped or replaced. */
async function gate(my: number) {
  while (useDemo.getState().paused && my === token) await sleep(150)
  if (my !== token) throw new Stopped()
}
class Stopped extends Error {}
/** A wait that pausing holds and "Next" cuts short. */
async function hold(my: number, ms: number) {
  let left = ms
  while (left > 0 && !skip) { await gate(my); await sleep(100); if (!useDemo.getState().paused) left -= 100 }
  skip = false
}
const within = <T,>(p: Promise<T>, ms: number, what: string) =>
  Promise.race([p, sleep(ms).then(() => { throw new Error(`${what} took longer than ${Math.round(ms / 1000)} s`) })])

function fill(v: unknown, vars: Record<string, string>): unknown {
  if (typeof v === 'string') return v.replace(/\$(\w+)/g, (m, k) => vars[k] ?? m)
  if (Array.isArray(v)) return v.map((x) => fill(x, vars))
  if (v && typeof v === 'object') return Object.fromEntries(Object.entries(v).map(([k, x]) => [k, fill(x, vars)]))
  return v
}

/* ---------- the page's own buttons, found the way a person reads them ---------- */
const CLICKABLE = 'button, [role=button], [role=tab], [role=menuitem], [role=menuitemradio], [role=radio], [role=option], a[href], summary'
const nameOf = (e: Element) => (e.getAttribute('aria-label') || e.getAttribute('title') || e.textContent || '').replace(/\s+/g, ' ').trim().toLowerCase()
const usable = (e: HTMLElement) => e.getClientRects().length > 0 && !(e as HTMLButtonElement).disabled && e.getAttribute('aria-disabled') !== 'true'
export function findAll(label: string, scope?: string): HTMLElement[] {
  const root = scope ? document.querySelector(scope) : document
  if (!root) return []
  const want = label.replace(/\s+/g, ' ').trim().toLowerCase()
  const els = [...root.querySelectorAll<HTMLElement>(CLICKABLE)].filter(usable)
  const text = (e: Element) => (e.textContent ?? '').replace(/\s+/g, ' ').trim().toLowerCase()
  const exact = els.filter((e) => nameOf(e) === want || text(e) === want)
  return exact.length ? exact : els.filter((e) => nameOf(e).startsWith(want) || text(e).startsWith(want))
}
async function waitFor<T>(my: number, get: () => T | null | undefined | false, ms: number, what: string): Promise<T> {
  const end = Date.now() + ms
  for (;;) {
    await gate(my)
    const v = get()
    if (v) return v
    if (Date.now() > end) throw new Error(what)
    await sleep(250)
  }
}
function press(el: HTMLElement) {
  el.scrollIntoView({ block: 'nearest', inline: 'nearest' })
  el.classList.add('demo-hit') // the audience sees what was pressed
  setTimeout(() => el.classList.remove('demo-hit'), 900)
  el.click()
}

/** The agent's turn and every run it started have ended. */
async function settled(my: number, ms: number) {
  await sleep(300) // a turn just asked for is queued a tick later
  await within(idle(), ms, 'The agent')
  await waitFor(my, () => !doc().runs.some((r) => r.status === 'running'), ms, 'The runs did not finish')
}
const isApproval = (id: string) => id.startsWith('approve:')
const changes = () => { const d = doc(); return d.runs.length + d.questions.length + d.panels.length + d.tools.length + d.findings.length }

async function popup(url: string) {
  const w = window.open(url, 'threshold-second', 'popup,width=960,height=720')
  if (!w) useDemo.setState({ popup: url }) // blocked: a real click on the caption bar's button opens it
}

/* ---------- one step ---------- */
async function run(my: number, s: Step): Promise<void> {
  const ms = s.timeout ?? (s.do === 'ask' || s.do === 'answer' ? 150_000 : 30_000)
  switch (s.do) {
    case 'say': return
    case 'new': startOver(); await sleep(300); return
    case 'open': {
      if (s.sid) goScan(String(s.sid), (s.params as Record<string, string>) ?? undefined)
      else if (s.page === 'investigation') goInvestigation(doc().id)
      else go((s.page as Exclude<Page, 'building' | 'investigation'>) ?? 'home', (s.params as Record<string, string>) ?? undefined)
      await sleep(600)
      return
    }
    case 'ask': {
      if (s.sid) { goScan(String(s.sid)); await sleep(500) } // the turn is scoped to the scan in view
      const before = changes()
      // several scans: the turn names them all, as a brief over a shortlist does; one scan: the scan in view
      await within<unknown>(Array.isArray(s.sids) ? turn({ text: String(s.text), sids: s.sids as string[] }) : ask(String(s.text)), ms, 'The agent')
      if (s.answer !== false) await answerAll(my, s, ms)
      if (s.approve !== false) await approveAll(my, ms)
      if (changes() === before) throw new Error('The agent did not answer')
      return
    }
    case 'answer': { await answerAll(my, s, ms); if (s.approve !== false) await approveAll(my, ms); return }
    case 'tool': {
      const sid = (s.sid as string | undefined) ?? (location.pathname.match(/\/scan\/([^/?]+)/)?.[1] ?? null)
      const before = doc().runs.length
      await within(runTool(String(s.tool), (s.inputs as Record<string, unknown>) ?? {}, sid), ms, String(s.tool))
      const r = doc().runs.slice(before).findLast((x) => x.tool === s.tool)
      if (!r || r.status === 'failed') throw new Error(`${s.tool} did not run`)
      if (s.open !== false) { const p = doc().panels.findLast((x) => x.run === r.id || (x.tool === s.tool && x.sid === r.sid)); if (p) useUi.setState({ panel: p.id }) }
      return
    }
    case 'click': {
      const label = String(s.label)
      const els = await waitFor(my, () => { const f = findAll(label, s.within as string | undefined); return f.length ? f : null }, ms, `No “${label}” on the page`)
      for (const el of s.all ? els : [els[0]]) { press(el); await sleep(350) }
      return
    }
    case 'type': {
      const el = await waitFor(my, () => document.querySelector<HTMLInputElement | HTMLTextAreaElement>(String(s.into)), ms, `No ${s.into} on the page`)
      const set = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), 'value')?.set
      el.focus()
      for (const ch of String(s.text)) { set?.call(el, el.value + ch); el.dispatchEvent(new Event('input', { bubbles: true })); await sleep(18) } // typed, so it reads as typing
      return
    }
    case 'focus': {
      const fs = doc().findings.filter((f) => f.anchor && (!s.tool || f.tool === s.tool))
      const rank = { fail: 0, warn: 1, unknown: 2, pass: 3 } as const
      const f = s.finding === 'worst' ? [...fs].sort((a, b) => rank[a.status] - rank[b.status])[0] : typeof s.finding === 'number' ? fs[s.finding] : s.finding && s.finding !== 'first' ? fs.find((x) => x.id === s.finding) : fs[0]
      if (!f) throw new Error('No finding to look at')
      focusFinding(f)
      return
    }
    case 'agent': useUi.getState().setRun(s.open !== false); return
    case 'firstrun': useUi.setState({ first: 'ask' }); return
    case 'share': { const { url } = await within(shareWorkspace(), ms, 'The share link'); await popup(url); return }
    case 'window': await popup(s.url && s.url !== 'here' ? String(s.url) : location.href); return
    case 'wait': {
      if (s.for === 'agent') await settled(my, ms)
      else if (s.for) await waitFor(my, () => findAll(String(s.for)).length > 0, ms, `“${s.for}” never showed`)
      else await hold(my, Number(s.ms ?? 1000))
      return
    }
  }
  throw new Error(`Unknown step “${s.do}”`)
}

/** The agent's open questions: the flow's `answers` (a word or phrase of the question -> the answer), else the answer
    on offer; then the investigation starts, as "Start the investigation" does. Throws when one has neither. */
async function answerAll(my: number, s: Step, ms: number) {
  const given = Object.entries((s.answers as Record<string, string | number>) ?? {})
  const open = doc().questions.filter((q) => q.answer == null && !isApproval(q.id))
  if (!open.length) return
  for (const q of open) {
    const hit = given.find(([k]) => q.text.toLowerCase().includes(k.toLowerCase()))
    if (hit) userOp({ op: 'question.answer', id: q.id, answer: hit[1] })
    else if (q.hint == null && q.options?.length) userOp({ op: 'question.answer', id: q.id, answer: q.options[0] }) // a choice: the first
    else if (q.hint == null) throw new Error(`The agent asked “${q.text}” and the flow has no answer for it (add it to "answers")`)
  }
  await investigate()
  await settled(my, ms)
}

/** Every approval the agent paused for: run it, then let the turn carry on. */
async function approveAll(my: number, ms: number) {
  for (let n = 0; n < 4; n++) {
    const open = doc().questions.filter((q) => isApproval(q.id) && q.answer == null)
    if (!open.length) return
    for (const q of open) userOp({ op: 'question.answer', id: q.id, answer: q.options?.[0] ?? 'Run it' })
    await within(turn({}), ms, 'The agent')
    await settled(my, ms)
  }
}

/* ---------- a whole flow ---------- */
export async function play(flow: Flow) {
  const my = ++token
  skip = false
  const vars = { ...(flow.vars ?? {}) }
  useDemo.setState({ flow, i: 0, say: flow.about ?? flow.title, note: '', paused: false, started: Date.now(), pausedFor: 0, done: false, popup: null })
  // A fresh profile per play: nothing learned in a rehearsal changes what the agent is asked, so a recorded turn
  // still matches (scripts/demo-llm) and the agent starts from the same place every time.
  try { localStorage.setItem('threshold.profile', `demo_${flow.id}_${Date.now().toString(36)}`) } catch { /* private window */ }
  if (!flow.steps[0] || flow.steps[0].keep !== true) startOver()
  try {
    for (let i = 0; i < flow.steps.length; i++) {
      await gate(my)
      const s = fill(flow.steps[i], vars) as Step
      useDemo.setState({ i, say: s.say ?? useDemo.getState().say, note: '' })
      try {
        await run(my, s)
      } catch (e) {
        if (e instanceof Stopped) throw e
        const why = (e as Error).message
        if (s.else) {
          useDemo.setState({ note: `${why.replace(/\.$/, '')}. ${s.else.say ? '' : 'Showing the fallback.'}`, say: s.else.say ?? useDemo.getState().say })
          try { await run(my, s.else) } catch (e2) { if (e2 instanceof Stopped) throw e2; useDemo.setState({ note: `Skipped: ${(e2 as Error).message}` }) }
        } else useDemo.setState({ note: `Skipped: ${why}` })
      }
      await hold(my, s.hold ?? 1500)
    }
    if (my === token) useDemo.setState({ done: true, say: 'End of the flow.', note: '' })
  } catch (e) { if (!(e instanceof Stopped)) throw e }
}

export function stop() { token++; useDemo.setState({ flow: null, done: false, paused: false, popup: null }) }
export function pause(on: boolean) {
  const s = useDemo.getState()
  useDemo.setState({ paused: on, pausedFor: on ? Date.now() : 0, started: !on && s.pausedFor ? s.started + (Date.now() - s.pausedFor) : s.started })
}
export function next() { skip = true }

// For recordings and rehearsal from the console: thresholdDemo.play('costar'). A link with ?play=<flow id> starts it.
const byId = (id: string) => FLOWS.find((f) => f.id === id)
Object.assign(window, { thresholdDemo: { play: (id: string) => { const f = byId(id); if (f) void play(f); return !!f }, stop, pause, next, flows: FLOWS.map((f) => f.id), state: () => useDemo.getState() } })
const asked = new URLSearchParams(location.search).get('play')
if (asked && byId(asked)) setTimeout(() => void play(byId(asked)!), 2500) // after the buildings and the catalog load
