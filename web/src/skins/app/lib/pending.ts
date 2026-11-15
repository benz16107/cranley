import { create } from 'zustand'
import { ask, currentRoute, fetchFactHistory, fetchFloodWet, isLive, navigate, useWorkspace, type Doc } from '../../../core/index.ts'

/* Everything in this file stands in for something asked of core in reports/core-requests.md ("App", 2026-11-14).
   Nothing here fetches: a look may not. Each part says which request replaces it. */

/* ---------- App 3: clients for the facts database. Used when core exports them; null until then. ---------- */
export type CensusPreset = { field: string; by: string; stat: string; label: string }
export type FloodLevel = { level_m: number; houses: number; rooms: number | string; rooms_wet: number | string; houses_wet: number; wet_area_m2: number | string }
type Facts = {
  fetchCensusPresets: () => Promise<Record<string, CensusPreset>>
  fetchCensus: (q: { preset?: string; city?: string }) => Promise<Record<string, unknown>>
  fetchFloodWet: () => Promise<FloodLevel[]>
  fetchFactHistory: (sid: string) => Promise<Record<string, unknown>[]>
}
// named, not `import * as core`: reading the whole namespace kept every export of core (MapLibre too) on every page
export const facts: Partial<Facts> = { fetchFloodWet, fetchFactHistory } as Partial<Facts>

/* ---------- App 4: past work. An index of the investigations this browser has seen, kept by the look. ---------- */
export type Seen = { id: string; brief: string; first: number; last: number; steps: number; done: number; runs: number; failed: number; findings: number; kept: number; tools: number; status: 'setup' | 'working' | 'waiting' | 'done'
  /** Up to three of its scans (kept first), for their pictures on Home. Missing on entries made before this was kept. */
  sids?: string[] }
const KEY = 'threshold.app.investigations'
const read = (): Record<string, Seen> => { try { return JSON.parse(localStorage.getItem(KEY) ?? '{}') } catch { return {} } }
export const useSeen = create<{ all: Record<string, Seen> }>(() => ({ all: read() }))

export function statusOf(d: Doc): Seen['status'] {
  if (d.runs.some((r) => r.status === 'running') || d.plan.some((s) => s.status === 'active')) return 'working'
  if (d.questions.some((q) => q.answer == null)) return 'waiting'
  return d.plan.length || d.panels.length ? 'done' : 'setup'
}
/** Is there anything in this workspace worth listing? */
export const started = (d: Doc) => !!d.brief || d.panels.length > 0 || d.runs.length > 0
const counts = (x: { done: number; runs: number; findings: number; kept: number; tools: number }) => [x.done, x.runs, x.findings, x.kept, x.tools].join('|')
const digest = (d: Doc) => [d.id, d.brief?.text, d.plan.map((s) => s.status).join(''), d.runs.map((r) => r.status[0]).join(''), d.findings.length, d.shortlist.length, d.tools.length, d.questions.filter((q) => q.answer == null).length].join('|')
let shown = ''
useWorkspace.subscribe(({ doc: d }) => {
  const key = digest(d)
  if (key === shown || !started(d)) return
  if (isLive() && !d.id.startsWith('ws_')) return // the brief is shown before the server has named the workspace: that is not a second investigation
  shown = key
  const all = { ...useSeen.getState().all }, now = Date.now(), old = all[d.id]
  const next = { id: d.id, brief: d.brief?.text ?? old?.brief ?? '', first: old?.first ?? now, last: now,
    steps: d.plan.length, done: d.plan.filter((s) => s.status === 'done').length, runs: d.runs.length, failed: d.runs.filter((r) => r.status === 'failed').length,
    findings: d.findings.length, kept: d.shortlist.length, tools: d.tools.length, status: statusOf(d),
    sids: [...new Set([...d.shortlist.map((s) => s.sid), ...d.runs.flatMap((r) => (r.sid ? [r.sid] : [])).reverse()])].slice(0, 3) }
  if (old && counts(old) === counts(next)) next.last = old.last // a reload shows the same work again: not a change
  all[d.id] = next
  useSeen.setState({ all })
  try { localStorage.setItem(KEY, JSON.stringify(all)) } catch { /* private window: the list lasts for this visit */ }
})

/** Leave a read-only link for this browser's own work: the look's front door, loaded afresh. */
export const leaveShared = () => window.location.assign(window.location.pathname.replace(/^(\/[^/]+).*/, '$1'))

export function forgetSeen(id: string) {
  const all = { ...useSeen.getState().all }
  delete all[id]
  useSeen.setState({ all })
  try { localStorage.setItem(KEY, JSON.stringify(all)) } catch { /* nothing to do */ }
}
/** Make an older investigation the current one. Core has no call for it, so this sets core's stored workspace id and
    loads the page again, as a reload on that workspace would. Replace with openWorkspace(id). */
export function openSeen(id: string) {
  try { localStorage.setItem('threshold.workspace', id) } catch { return }
  window.location.assign(window.location.pathname.replace(/^(\/[^/]+).*/, `$1/investigations/${encodeURIComponent(id)}`))
}

/* ---------- App 6: a request to the agent made from a page of this look stays on that page. ----------
   Core moves the view to the map when a turn starts from any place it reads as the front door, and this look's own
   pages all read as that. A move the person did not make (no click or key just before it) is undone, once. */
let input = 0
for (const ev of ['pointerdown', 'keydown'] as const) window.addEventListener(ev, () => { input = performance.now() }, true)
export async function askHere(text: string) {
  const place = window.location.pathname.replace(/^\/[^/]+/, '') || '/', params = Object.fromEntries(new URLSearchParams(window.location.search))
  if (currentRoute().path !== '/') return ask(text) // on the map or a building the move is wanted
  const watch = setInterval(() => {
    if (currentRoute().path !== '/map') return
    clearInterval(watch)
    if (performance.now() - input > 500) navigate(place, params, { replace: true })
  }, 120)
  try { await ask(text) } finally { clearInterval(watch) }
}
