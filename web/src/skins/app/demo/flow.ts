/* A demo flow file's shape (README.md). Kept apart from the player so the flow check runs without the app. */
export const DOS = ['new', 'open', 'ask', 'answer', 'tool', 'click', 'type', 'focus', 'agent', 'share', 'window', 'wait', 'say', 'firstrun'] as const

export type Step = {
  do: (typeof DOS)[number]
  say?: string
  /** ms the caption stays after the step is done (default 1500) */
  hold?: number
  /** ms before the step counts as failed (default 30000; ask 150000) */
  timeout?: number
  else?: Step
  [k: string]: unknown
}
export type Flow = { id: string; title: string; track: string; about?: string; vars?: Record<string, string>; steps: Step[] }

/** What is wrong with a flow, as sentences; [] when it can play. */
export function problems(f: Flow, file: string): string[] {
  const out: string[] = []
  for (const k of ['id', 'title', 'track'] as const) if (typeof f[k] !== 'string' || !f[k]) out.push(`${file}: "${k}" is missing`)
  if (!Array.isArray(f.steps) || !f.steps.length) out.push(`${file}: no "steps"`)
  const check = (s: Step, where: string) => {
    if (!DOS.includes(s?.do)) out.push(`${file} ${where}: unknown "do": ${JSON.stringify(s?.do)}`)
    for (const m of JSON.stringify(s).matchAll(/\$(\w+)/g)) if (!(f.vars && m[1] in f.vars)) out.push(`${file} ${where}: $${m[1]} is not in "vars"`)
    if (s?.do === 'tool' && !s.tool) out.push(`${file} ${where}: a tool step needs "tool"`)
    if (s?.do === 'click' && !s.label) out.push(`${file} ${where}: a click step needs "label"`)
    if (s?.do === 'ask' && !s.text) out.push(`${file} ${where}: an ask step needs "text"`)
    if (s?.else) check(s.else, `${where} else`)
  }
  ;(f.steps ?? []).forEach((s, i) => check(s, `step ${i + 1}`))
  return out
}
