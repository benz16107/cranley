import type { Building, Capture, Doc, Run, Status } from '../../../core/index.ts'

/* What the Home page lists, worked out from the workspace and the building list. Pure, so it runs under `node --test`.
   Nothing here measures anything: it picks, orders and counts rows that are already in the document. */

const WORST: Record<Status, number> = { fail: 0, warn: 1, unknown: 2, pass: 3 }

/** One building on Home: a scan to open, where it is (for its aerial photo), and what the investigation holds on it. */
export type HomeBuilding = {
  sid: string; name: string; address: string; lat: number; lon: number
  kept: boolean
  /** Results on this scan in the open investigation, and the worst of their verdicts. */
  results: number; worst?: Status
}

function place(all: Building[]): (sid: string) => { b: Building; name: string } | undefined {
  const by = new Map<string, { b: Building; name: string }>()
  for (const b of all) for (const s of b.scans) by.set(s.sid, { b, name: s.name })
  return (sid) => by.get(sid)
}

/** The buildings to get back to: the kept ones first, then the ones the investigation has results on, newest first.
    A scan the building list does not know (no position, so no photo) is left out. */
export function homeBuildings(doc: Doc, all: Building[], limit = 8): HomeBuilding[] {
  const at = place(all), kept = doc.shortlist.map((s) => s.sid)
  const worked = [...new Set(doc.panels.map((p) => p.sid).filter((s): s is string => !!s).reverse())]
  return [...new Set([...kept, ...worked])].flatMap((sid) => {
    const hit = at(sid)
    if (!hit) return []
    const verdicts = doc.panels.filter((p) => p.sid === sid).flatMap((p) => p.blocks).flatMap((b) => (b.type === 'VerdictHeader' ? [b.status] : []))
    return [{ sid, name: hit.name, address: hit.b.address, lat: hit.b.lat, lon: hit.b.lon, kept: kept.includes(sid),
      results: doc.panels.filter((p) => p.sid === sid).length, worst: verdicts.sort((a, b) => WORST[a] - WORST[b])[0] }]
  }).slice(0, limit)
}

/** Somewhere to start on a first visit: scanned addresses that also have a drone capture, the fullest first, from
    both cities. Chosen from the list alone, so it is the same six for everyone until the list changes. */
export function starterBuildings(all: Building[], limit = 6): HomeBuilding[] {
  const pick = (metro: string, n: number) => all.filter((b) => b.metro === metro && b.splat && b.scans.length > 0)
    .sort((a, b) => b.rooms - a.rooms || a.id.localeCompare(b.id)).slice(0, n)
  const hou = pick('hou', limit), la = pick('la', Math.min(2, limit))
  return [...hou.slice(0, limit - la.length), ...la].map((b) => ({ sid: b.scans[0].sid, name: b.scans[0].name, address: b.address, lat: b.lat, lon: b.lon, kept: false, results: 0 }))
}

/** One row of the activity feed. */
export type HomeEvent =
  | { kind: 'working'; id: string; text: string; run?: Run }
  | { kind: 'ask'; id: string; open: number }
  | { kind: 'run'; id: string; at: number; run: Run }
  | { kind: 'capture'; id: string; at: number; capture: Capture }

/** What is happening and what just happened, in the order a person needs it: work in progress, then a question that
    is holding the work up (not the ones the setup card is asking), then everything that ended (runs, failed ones among them, and what the phone sent),
    newest first. A run with no start time (scripted playback) keeps its place in the document's order. */
export function activity(doc: Doc, captures: Capture[], limit = 10): HomeEvent[] {
  const now: HomeEvent[] = []
  const step = doc.plan.find((s) => s.status === 'active'), running = doc.runs.filter((r) => r.status === 'running')
  if (step && !running.length) now.push({ kind: 'working', id: `step:${step.id}`, text: step.label })
  for (const r of running) now.push({ kind: 'working', id: r.id, text: r.summary ?? step?.label ?? 'Working', run: r })
  // during setup the questions are on the setup card itself, so the feed does not repeat them
  const setup = !!doc.brief && doc.plan.length === 0 && doc.panels.length === 0
  const open = doc.questions.filter((q) => q.answer == null).length
  if (open && !setup) now.push({ kind: 'ask', id: 'ask', open })
  const ended: Extract<HomeEvent, { at: number }>[] = [
    ...doc.runs.flatMap((r, i) => (r.status === 'running' ? [] : [{ kind: 'run' as const, id: r.id, at: r.at != null ? r.at + (r.ms ?? 0) : i, run: r }])),
    ...captures.map((c) => ({ kind: 'capture' as const, id: c.id, at: c.at * 1000, capture: c })),
  ]
  return [...now, ...ended.sort((a, b) => b.at - a.at)].slice(0, Math.max(limit, now.length))
}
