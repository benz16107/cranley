import type { Panel, Status } from '../../../core/index.ts'

/* The verdict a set of results adds up to. Pure, so it runs under `node --test`. Nothing is judged here: each result
   carries its own verdict from its tool, and this picks the one a person should read first. */

const WORST: Record<Status, number> = { fail: 0, warn: 1, unknown: 2, pass: 3 }

export type Verdict = { status: Status; text: string; title: string; panel: string }

/** The worst verdict among these results, in the tool's own words: a failure before a caution, a caution before
    something not measured, and a pass only when everything passed. Among equals the newest result speaks. */
export function worstVerdict(panels: Panel[]): Verdict | undefined {
  let worst: Verdict | undefined
  for (const p of panels) for (const b of p.blocks) {
    if (b.type !== 'VerdictHeader') continue
    if (!worst || WORST[b.status] <= WORST[worst.status]) worst = { status: b.status, text: b.text, title: p.title, panel: p.id }
  }
  return worst
}

/** How many of these results carry each verdict, worst first, for one line under the headline ("1 failed, 2 passed"). */
export function tally(panels: Panel[]): string {
  const n: Record<Status, number> = { fail: 0, warn: 0, unknown: 0, pass: 0 }
  for (const p of panels) { const v = p.blocks.find((b) => b.type === 'VerdictHeader'); if (v?.type === 'VerdictHeader') n[v.status]++ }
  const said: [Status, string][] = [['fail', 'failed'], ['warn', n.warn === 1 ? 'needs a look' : 'need a look'], ['unknown', 'not measured'], ['pass', 'passed']]
  return said.filter(([s]) => n[s] > 0).map(([s, w]) => `${n[s]} ${w}`).join(', ')
}
