import { useEffect, useMemo, useState } from 'react'
import { create } from 'zustand'
import { userOp, useBuildings, useCatalog, useWorkspace, type Question } from '../../../core/index.ts'
import { serverDoc, turn } from '../../../core/server.ts'
import { Icon, RunState, ToolKey } from '../design/ui.tsx'

/** A slow or expensive step the agent paused before (deepagents human-in-the-loop). Its id starts `approve:`. */
export const isApproval = (q: Question) => q.id.startsWith('approve:')

/** Answer every open approval the same way, then let the paused turn carry on: one press where the agent asked
    several times for the same kind of step. */
export function ApproveAll({ open }: { open: Question[] }) {
  const all = (which: 0 | 1) => { for (const q of open) userOp({ op: 'question.answer', id: q.id, answer: (q.options ?? ['Run it', 'Skip it'])[which] }); void turn({}) }
  return <div className="row"><button type="button" className="btn solid sm" onClick={() => all(0)}>Run all {open.length}</button><button type="button" className="btn sm" onClick={() => all(1)}>Skip all</button></div>
}

/** Run it, skip it, or stop asking about this tool here. The answer is a workspace op, so every open copy of the
    workspace sees it; then the paused turn carries on from where it stopped. `qs` are approvals that read the same
    (the agent asked for the same step several times): one card answers them together. */
export function ApprovalCard({ qs }: { qs: Question[] }) {
  const q = qs[0]
  const tools = useWorkspace((s) => s.doc.tools)
  const all = useBuildings((s) => s.all)
  const [sent, setSent] = useState<string | null>(null)
  // the server names a property by its number: say its address when the building list has it
  const text = q.text.replace(/\b\d{5,}\b/, (id) => all.find((b) => b.id === `p${id}`)?.address.split(',')[0] ?? id)
  const [title, why] = text.includes(': ') ? [text.slice(0, text.indexOf(': ')), text.slice(text.indexOf(': ') + 2)] : [text, '']
  const name = tools.find((t) => t.id === q.tool)?.title ?? title
  const decide = (a: string) => {
    setSent(a)
    for (const x of qs) userOp({ op: 'question.answer', id: x.id, answer: a })
    // the turn resumes once every approval it asked for is answered; the server waits for the rest otherwise
    if (!useWorkspace.getState().doc.questions.some((x) => isApproval(x) && !qs.includes(x) && x.answer == null)) void turn({})
  }
  const [run, skip, always] = q.options ?? ['Run it', 'Skip it', 'Always run it here']
  return (
    <section className="approval" aria-label={`Approve ${name}`} data-sent={sent ? '' : undefined}>
      <header>
        <ToolKey id={q.tool ?? ''} title={name} />
        <span className="grow"><b>{title}{qs.length > 1 && <span className="count">{qs.length} times</span>}</b><span className="why">{why}</span></span>
      </header>
      {sent ? <RunState state="running">{sent === skip ? 'Skipped. The agent carries on without it' : 'Approved. The agent carries on'}</RunState> : (
        <div className="row wrap">
          <button className="btn solid sm" onClick={() => decide(run)}>{run}</button>
          <button className="btn sm" onClick={() => decide(skip)}>{skip}</button>
          <span className="grow" />
          <button className="btn sm quiet" onClick={() => decide(always)} title={`Do not ask again before ${name} in this investigation`}>{always}</button>
        </div>
      )}
    </section>
  )
}

type Lane = { id: string; agent: string; task: string; status: 'running' | 'waiting' | 'done' | 'failed'; tool: string | null; tools: string[]; started: number; finished: number | null }
type Live = { turn: string | null; status: 'idle' | 'running' | 'waiting' | 'done' | 'stopped'; lanes: Lane[] }

/** What the server's agents are doing now, from `/api/agent/{id}/live`: one stream for the whole shell. */
const useLive = create<{ snap: Live | null }>(() => ({ snap: null }))
export function LiveLink() {
  const live = useCatalog((s) => s.live)
  const id = useWorkspace((s) => s.doc.brief?.text) ? (serverDoc()?.id as string | undefined) : undefined
  useEffect(() => {
    useLive.setState({ snap: null })
    if (!live || !id) return
    const es = new EventSource(`/api/agent/${encodeURIComponent(id)}/live`)
    es.addEventListener('lanes', (e) => { try { useLive.setState({ snap: JSON.parse((e as MessageEvent).data) }) } catch { /* the next snapshot replaces it */ } })
    return () => es.close()
  }, [live, id])
  return null
}
/** The turn has ended with a plan step still marked active and nothing running: the agent stopped part-way. Without
    this the panel, the top bar and the plan say "working" for ever. Unknown (no stream yet) counts as not stopped. */
export function useStopped() {
  const over = useLive((s) => !!s.snap && s.snap.status !== 'running' && s.snap.status !== 'waiting')
  return useWorkspace((s) => over && s.doc.plan.some((p) => p.status === 'active') && !s.doc.runs.some((r) => r.status === 'running'))
}

const AGENT = { building: 'Building', property: 'Property', investigator: 'Lead agent' } as Record<string, string>
const STEP = { consider: 'Adding buildings', find_scans: 'Searching scans', find_properties: 'Searching properties', find_by_measure: 'Searching by measurement',
  rank: 'Ranking', shortlist: 'Shortlisting', focus: 'Pointing the camera', note: 'Writing a note', compose_panel: 'Building a panel', search_history: 'Searching past work',
  property_scans: 'Listing scans', run_on_property: 'Running across the property', coverage: 'Checking coverage', task: 'Starting a subagent' } as Record<string, string>
const STATE = { running: 'running', waiting: 'pending', done: 'done', failed: 'failed' } as const

/** The lead agent and each subagent it started, side by side while they work in parallel. Once the turn is over they
    fold to one line: the plan below is what is left to read. */
export function Lanes() {
  const snap = useLive((s) => s.snap)
  const tools = useWorkspace((s) => s.doc.tools)
  const all = useBuildings((s) => s.all)
  // a lane's task is the lead agent's own instruction, which names a scan or a property by its id: show its name instead
  const names = useMemo(() => new Map(all.flatMap((b) => [[b.id.replace(/^p/, ''), b.address.split(',')[0]] as const, ...b.scans.map((x) => [x.sid, [x.name, b.address.split(',')[0]].filter((v, i, a) => v && a.indexOf(v) === i).join(' · ')] as const)])), [all])
  const about = (task: string) => { for (const w of task.match(/[A-Za-z0-9_]{5,}/g) ?? []) { const n = names.get(w); if (n) return n } return task }
  const title = (t: string) => tools.find((x) => x.id === t)?.title ?? STEP[t] ?? t.replace(/_/g, ' ')
  if (!snap || !snap.lanes.length || snap.status === 'idle') return null
  const busy = snap.lanes.filter((l) => l.status === 'running' && l.id !== 'main').length
  const over = snap.status !== 'running' && snap.status !== 'waiting'
  const rows = (
    <ol>
      {snap.lanes.map((l) => (
        <li key={l.id} className="lane arrive" data-status={l.status}>
          <div className="lh">
            <span className="who">{l.id === 'main' ? AGENT.investigator : AGENT[l.agent] ?? l.agent}</span>
            <span className="grow trunc" title={l.task}>{l.id === 'main' ? 'Plans, searches and ranks' : about(l.task)}</span>
            <RunState state={STATE[l.status]}>{l.status === 'waiting' ? 'Waiting' : undefined}</RunState>
          </div>
          <div className="lt">
            {l.tool ? <><ToolKey id={l.tool} title={title(l.tool)} /><span className="trunc">{STEP[l.tool] ?? `Running ${title(l.tool)}`}</span></>
              : l.status === 'running' ? <span className="trunc muted">Deciding the next step</span>
              : l.tools.length ? <><Icon name="check" size={12} /><span className="trunc muted">{l.tools.map(title).join(', ')}</span></>
              : <span className="muted">No tools yet</span>}
          </div>
        </li>
      ))}
    </ol>
  )
  if (over) return <details className="lanes"><summary><Icon name="right" size={11} />{snap.lanes.length === 1 ? 'One agent' : `${snap.lanes.length} agents`} worked on this turn</summary>{rows}</details>
  return (
    <section className="lanes" aria-label="Agents at work" aria-live="polite">
      <header>
        <h3>{snap.status === 'waiting' ? 'Paused for your approval' : busy > 1 ? `${busy} agents working at once` : 'Agents working'}</h3>
        <span className="count">{snap.lanes.length}</span>
      </header>
      {rows}
    </section>
  )
}
