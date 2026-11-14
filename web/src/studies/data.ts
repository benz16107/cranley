// What every study shows: one real investigation, read live from the API. Nothing here is typed in by hand
// except scan ids and the brief; every count and width on screen comes from /api or from the audit's result object.
import { useEffect, useState } from 'react'
import { fetchPlan } from '../lib/api.ts'
import { accessAudit, type AccessPrefs } from '../fixtures/access.ts'
import { buildModel, sightBlocked } from '../scene/model.ts'
import type { Overlay as SceneOverlay, ScanPlan as ScenePlan, View } from '../scene/types.ts'
import type { Check, ScanPlan, ToolResult } from '../workspace/types.ts'

/** The house the studies are about. Which scan is sponsor data, so no id is written here: `?sid=<scan>` picks it and
    is remembered in this browser; with none, it is the first Houston house with a drone capture in the feed. */
const asked = typeof location === 'undefined' ? null : new URLSearchParams(location.search).get('sid')
if (asked) try { localStorage.setItem('threshold.study.sid', asked) } catch { /* private window */ }
const FOCUS = asked ?? (typeof localStorage === 'undefined' ? null : localStorage.getItem('threshold.study.sid'))
export const PREFS: AccessPrefs = { door: 0.815, turning: 1.525, turningNeeded: true, routeTo: 'Bedroom' }
export const BRIEF = 'I use a power wheelchair and I want a single-storey house near Clear Lake.'
export const STEPS = ['Find houses with a drone capture nearby', 'Read each floor plan', 'Trace the way in and measure every doorway', 'Rank the houses', 'Show what decides it']
/** Starting points, each with the kind of scan it opens (the server's kind; the first such scan in the feed). */
export const STARTERS: [who: string, need: string, kind: string][] = [
  ['A wheelchair user', 'choosing a house', 'apartment_unit'], ['A fire captain', 'pre-planning a block', 'apartment_unit'],
  ['A homeowner', 'before a hurricane', 'house'], ['An office tenant', 'fitting a team', 'office'], ['A property manager', 'scoping a unit turn', 'apartment_unit'],
]
/** One scan per starting point, taken from the feed: the focus house for houses, else the nth scan of that kind. */
export const starterSids = (c: City) => STARTERS.map(([, , kind], i) => (kind === 'house' ? c.focus.sid : c.houston.filter((p) => p.kind === kind && p.scans === 1)[i]?.sid ?? c.focus.sid))

export type Place = { sid: string; lon: number; lat: number; street: string; city: string; scans: number; splat: boolean; kind: string; rooms: number }
type Feature = { geometry: { coordinates: [number, number] }; properties: { address: string; city: string; count: number; splat: boolean; scans: (unknown[] | { sid: string; name: string; rooms: number })[] } }
const inHouston = (p: Place) => p.lon > -96.6 && p.lon < -94 && p.lat > 28.8 && p.lat < 31
const km = (a: Place, b: Place) => Math.hypot((a.lon - b.lon) * 96.6, (a.lat - b.lat) * 110.9)

export const NONE: Place[] = []
export type City = { all: Place[]; houston: Place[]; scans: number; focus: Place; candidates: Place[] }
let city: Promise<City> | null = null
const loadCity = () => (city ??= fetch('/api/buildings').then((r) => r.json()).then((g: { features: Feature[] }) => {
  const all = g.features.map(({ geometry: { coordinates: [lon, lat] }, properties: p }): Place => {
    const s = p.scans[0], first = Array.isArray(s) ? { sid: String(s[0]), kind: String(s[2] ?? ''), rooms: Number(s[3] ?? 0) } : { sid: s?.sid ?? '', kind: '', rooms: s?.rooms ?? 0 }
    return { ...first, lon, lat, street: (p.address || 'Address not recorded').split(',')[0], city: p.city, scans: p.count, splat: p.splat }
  })
  const houston = all.filter(inHouston), focus = houston.find((p) => p.sid === FOCUS) ?? houston.find((p) => p.splat && p.scans === 1 && p.kind === 'house') ?? houston[0]
  // the agent's shortlist: single houses with a drone capture, nearest first
  const candidates = houston.filter((p) => p.splat && p.scans === 1).sort((a, b) => km(a, focus) - km(b, focus)).slice(0, 10)
  return { all, houston, scans: all.reduce((n, p) => n + p.scans, 0), focus, candidates }
}))
export function useCity(): City | null {
  const [c, set] = useState<City | null>(null)
  useEffect(() => { void loadCity().then(set) }, [])
  return c
}

export type Audit = { plan: ScanPlan; result: ToolResult; worst: Check | null; under: number; doors: number; traced: boolean }
const audits = new Map<string, Promise<Audit>>()
export function audit(sid: string): Promise<Audit> {
  let a = audits.get(sid)
  if (!a) {
    a = fetchPlan(sid).then((plan) => {
      const result = accessAudit(plan, PREFS)
      const measured = result.checks.filter((c) => c.measured != null && c.id !== 'turning')
      const worst = [...measured].sort((x, y) => x.measured! - y.measured!)[0] ?? null
      const reached = Number(result.metrics.find((m) => m.id === 'reached')?.value ?? 0)
      return { plan, result, worst, under: Number(result.metrics.find((m) => m.id === 'under')?.value ?? 0), doors: plan.openings.filter((o) => o.type === 'doorway').length, traced: reached > 1 }
    })
    audits.set(sid, a)
  }
  return a
}
export function useAudit(sid: string | null | undefined): Audit | null {
  const [a, set] = useState<Audit | null>(null)
  useEffect(() => { if (sid) void audit(sid).then(set, () => {}) }, [sid])
  return a
}
/** Audits for a list of scans, read one at a time so the shared API sees one request at once. */
export function useAudits(sids: string[]): Record<string, Audit> {
  const [out, set] = useState<Record<string, Audit>>({})
  const key = sids.join(',')
  useEffect(() => {
    let live = true
    void (async () => { for (const sid of sids) { const a = await audit(sid).catch(() => null); if (!live) return; if (a) set((o) => ({ ...o, [sid]: a })) } })()
    return () => { live = false }
  }, [key]) // eslint-disable-line react-hooks/exhaustive-deps
  return out
}

export const m2 = (v: number) => v.toFixed(2)
/** Fewest doorways to fix first, then the widest narrow doorway. A scan whose route could not be traced goes last. */
export const rank = (a: Audit, b: Audit) => Number(b.traced) - Number(a.traced) || a.under - b.under || (b.worst?.measured ?? 0) - (a.worst?.measured ?? 0)

export const scenePlan = (p: ScanPlan) => p as unknown as ScenePlan
export const sceneOverlays = (r: ToolResult) => r.overlays as unknown as SceneOverlay[]
/** Stand at the nearest scan position that can see this doorway and face it. */
export function lookAtDoor(plan: ScanPlan, openingId: string | undefined, want = 3.2): View | null {
  const sp = scenePlan(plan), o = sp.openings.find((x) => x.id === openingId)
  if (!o) return null
  const m = buildModel(sp)
  // face the doorway square on where a scan position allows it: a doorway seen along its wall cannot be judged by eye
  const wall = sp.walls.find((x) => x.id === o.wall), len = wall ? Math.hypot(wall.b[0] - wall.a[0], wall.b[1] - wall.a[1]) || 1 : 1
  const normal = wall ? [-(wall.b[1] - wall.a[1]) / len, (wall.b[0] - wall.a[0]) / len] : null
  const pano = sp.panos.filter((p) => p.floor === o.floor).map((p) => {
    const dx = o.center[0] - p.position[0], dy = o.center[1] - p.position[1], d = Math.hypot(dx, dy)
    return { p, d, score: (normal ? Math.abs((dx * normal[0] + dy * normal[1]) / d) : 1) - 0.12 * Math.abs(d - want) }
  }).filter((x) => x.d > 1.3 && x.d < 7 && !sightBlocked(m, o.floor, x.p.position[0], x.p.position[1], o.center[0], o.center[1], o.wall)).sort((a, b) => b.score - a.score)[0]?.p
  if (!pano) return null
  const yaw = (Math.atan2(o.center[1] - pano.position[1], o.center[0] - pano.position[0]) * 180) / Math.PI
  return { mode: 'pano', pano: pano.id, focus: { pano: pano.id, yaw_deg: yaw, pitch_deg: -4 }, measures: true }
}
/** The doorway a check is about: its finding's anchor. */
export const doorOf = (r: ToolResult, c: Check | null | undefined) => {
  const f = r.findings.find((x) => x.id === c?.findings?.[0]), a = f?.anchor as { opening?: string } | undefined
  return { finding: f, opening: a?.opening }
}
