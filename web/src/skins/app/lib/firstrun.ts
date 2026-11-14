import type { Doc, Status } from '../../../core/index.ts'

/* The guided first run, worked out from the workspace: which steps have happened, which building to open, and when
   there is something useful to end on. Pure, so it runs under `node --test`. It measures nothing: it counts rows that
   are in the document and passes on the verdict a tool wrote. */

/** Outside `threshold.app.`, so resetting the layout does not bring the first run back. */
export const FIRST_RUN_KEY = 'threshold.firstrun'

const WORST: Record<Status, number> = { fail: 0, warn: 1, unknown: 2, pass: 3 }

export type GuideStep = { id: 'brief' | 'tools' | 'answers' | 'plan' | 'building' | 'findings'; state: 'done' | 'active' | 'pending' | 'ask'; label: string }
export type Guide = {
  steps: GuideStep[]
  /** Scans the guide may open: the ones the agent has narrowed the work to, or else the first one a run names. */
  candidates: string[]
  /** The agent passed the opened scan over: it has no run, while these other scans already have two results each.
      The guide moves to one of them. Empty while the opened scan is still in the running. */
  instead: string[]
  /** On the opened scan: how many results, and the worst of their verdicts with the tool's own sentence. */
  results: number
  verdict?: { status: Status; text: string; title: string }
  /** A question only the person can answer is holding the work up. */
  ask: boolean
  /** The agent is still working (a plan step is active). */
  working: boolean
  /** There is something useful to end on: two results on the opened building, or one and the agent has stopped. */
  ready: boolean
}

/** `opened` is the scan the guide has gone to, when it has. */
export function guide(doc: Doc, opened: string | null): Guide {
  const tools = doc.tools.length, plan = doc.plan.length, open = doc.questions.filter((q) => q.answer == null)
  const started = plan > 0 || doc.runs.length > 0
  const ask = !started && open.some((q) => q.hint == null)
  const working = doc.plan.some((s) => s.status === 'active')
  const first = doc.runs.find((r) => r.sid)?.sid
  const candidates = doc.brief?.scope?.length ? doc.brief.scope : first ? [first] : []
  const mine = opened ? doc.panels.filter((p) => p.sid === opened) : []
  const verdicts = mine.flatMap((p) => p.blocks.flatMap((b) => (b.type === 'VerdictHeader' ? [{ status: b.status, text: b.text, title: p.title }] : [])))
  const results = mine.length
  const chosen = tools > 0 && (started || doc.questions.length > 0)
  const count = new Map<string, number>()
  for (const p of doc.panels) if (p.sid) count.set(p.sid, (count.get(p.sid) ?? 0) + 1)
  const instead = opened && !doc.runs.some((r) => r.sid === opened) ? [...count].filter(([, n]) => n >= 2).map(([sid]) => sid) : []
  const steps: GuideStep[] = [
    { id: 'brief', state: doc.brief ? 'done' : 'active', label: 'Your brief is read' },
    { id: 'tools', state: chosen ? 'done' : doc.brief ? 'active' : 'pending', label: chosen ? `${tools} ${tools === 1 ? 'tool' : 'tools'} chosen for you` : 'Choosing tools for you' },
  ]
  // a row for the questions only when the agent asked some: answered with what it offered, or waiting for the person
  if (doc.questions.length) steps.push({ id: 'answers', state: ask ? 'ask' : started || !open.length ? 'done' : 'active',
    label: ask ? (open.length === 1 ? 'One question needs your answer' : `${open.length} questions need your answer`) : started || !open.length ? 'Its questions are answered' : 'Its questions take the usual values' })
  steps.push(
    { id: 'plan', state: started ? 'done' : chosen && !ask ? 'active' : 'pending', label: plan ? `A plan of ${plan} ${plan === 1 ? 'step' : 'steps'}` : 'Planning the work' },
    { id: 'building', state: opened ? 'done' : started ? 'active' : 'pending', label: opened ? 'A building opened' : candidates.length > 1 ? `${candidates.length} buildings picked` : 'Finding a building to measure' },
    { id: 'findings', state: results ? 'done' : opened ? 'active' : 'pending', label: results ? `${results} ${results === 1 ? 'result' : 'results'} on it so far` : 'First results' },
  )
  return { steps, candidates, instead, results, verdict: verdicts.sort((a, b) => WORST[a.status] - WORST[b.status])[0], ask, working, ready: results >= 2 || (results >= 1 && !working) }
}

/** Would the building page open this scan on its site? The same rule as its opening view (pages/Building.tsx): the
    scan has a position, and that position was fitted to the aerial footprint or is tied to its own drone capture. */
export const onSite = (plan: { geo?: { lat?: number | null } | null; quality?: { georef?: unknown } | null; has?: { splat?: boolean } } | null | undefined) =>
  !!plan && plan.geo?.lat != null && (!!plan.quality?.georef || !!plan.has?.splat)

/** Which of the agent's picks the guide opens: one whose photoreal colour is made and that stands on its site, else
    one whose colour is made, else the first. `baked` and `sited` answer for each scan in turn. */
export function pickScan(sids: string[], baked: boolean[], sited: boolean[]): string | undefined {
  const best = sids.findIndex((_, i) => baked[i] && sited[i]), ok = baked.indexOf(true)
  return sids[best >= 0 ? best : ok >= 0 ? ok : 0]
}
