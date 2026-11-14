import { useEffect, useState } from 'react'
import { userOp, useCatalog, useWorkspace, type Question } from '../../../core/index.ts'
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
    workspace sees it; then the paused turn carries on from where it stopped. */
export function ApprovalCard({ q }: { q: Question }) {
  const tools = useWorkspace((s) => s.doc.tools)
  const [sent, setSent] = useState<string | null>(null)
  const [title, why] = q.text.includes(': ') ? [q.text.slice(0, q.text.indexOf(': ')), q.text.slice(q.text.indexOf(': ') + 2)] : [q.text, '']
  const name = tools.find((t) => t.id === q.tool)?.title ?? title
  const decide = (a: string) => {
    setSent(a)
    userOp({ op: 'question.answer', id: q.id, answer: a })
    // the turn resumes once every approval it asked for is answered; the server waits for the rest otherwise
    if (!useWorkspace.getState().doc.questions.some((x) => isApproval(x) && x.id !== q.id && x.answer == null)) void turn({})
  }
  const [run, skip, always] = q.options ?? ['Run it', 'Skip it', 'Always run it here']
  return (
    <section className="approval" aria-label={`Approve ${name}`} data-sent={sent ? '' : undefined}>
      <header>
        <ToolKey id={q.tool ?? ''} title={name} />
        <span className="grow"><b>{title}</b><span className="why">{why}</span></span>
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

/** What the server's agents are doing now, from `/api/agent/{id}/live`. */
function useLive(): Live | null {
  const live = useCatalog((s) => s.live)
  const id = useWorkspace((s) => s.doc.brief?.text) ? (serverDoc()?.id as string | undefined) : undefined
  const [snap, setSnap] = useState<Live | null>(null)
  useEffect(() => {
    if (!live || !id) return
    const es = new EventSource(`/api/agent/${encodeURIComponent(id)}/live`)
    es.addEventListener('lanes', (e) => { try { setSnap(JSON.parse((e as MessageEvent).data)) } catch { /* the next snapshot replaces it */ } })
    return () => es.close()
  }, [live, id])
  return snap
}

const AGENT = { building: 'Building', property: 'Property', investigator: 'Lead agent' } as Record<string, string>
const STEP = { consider: 'Adding buildings', find_scans: 'Searching scans', find_properties: 'Searching properties', find_by_measure: 'Searching by measurement',
  rank: 'Ranking', shortlist: 'Shortlisting', focus: 'Pointing the camera', note: 'Writing a note', compose_panel: 'Building a panel', search_history: 'Searching past work',
  property_scans: 'Listing scans', run_on_property: 'Running across the property', coverage: 'Checking coverage', task: 'Starting a subagent' } as Record<string, string>
const STATE = { running: 'running', waiting: 'pending', done: 'done', failed: 'failed' } as const

/** The lead agent and each subagent it started, side by side while they work in parallel. */
export function Lanes() {
  const snap = useLive()
  const tools = useWorkspace((s) => s.doc.tools)
  const title = (t: string) => tools.find((x) => x.id === t)?.title ?? STEP[t] ?? t.replace(/_/g, ' ')
  if (!snap || !snap.lanes.length || snap.status === 'idle') return null
  const busy = snap.lanes.filter((l) => l.status === 'running' && l.id !== 'main').length
  return (
    <section className="lanes" aria-label="Agents at work" aria-live="polite">
      <header>
        <h3>{snap.status === 'running' ? (busy > 1 ? `${busy} agents working at once` : 'Agents working') : snap.status === 'waiting' ? 'Paused for your approval' : 'Agents this turn'}</h3>
        <span className="count">{snap.lanes.length}</span>
      </header>
      <ol>
        {snap.lanes.map((l) => (
          <li key={l.id} className="lane arrive" data-status={l.status}>
            <div className="lh">
              <span className="who">{l.id === 'main' ? AGENT.investigator : AGENT[l.agent] ?? l.agent}</span>
              <span className="grow trunc" title={l.task}>{l.id === 'main' ? 'Plans, searches and ranks' : l.task}</span>
              <RunState state={STATE[l.status]}>{l.status === 'waiting' ? 'Waiting' : undefined}</RunState>
            </div>
            <div className="lt">
              {l.tool ? <><ToolKey id={l.tool} title={title(l.tool)} /><span className="trunc">{STEP[l.tool] ?? `Running ${title(l.tool)}`}</span></>
                : l.status === 'running' ? <span className="trunc muted">Deciding the next step{l.tools.length ? ` after ${l.tools.map(title).join(', ')}` : ''}</span>
                : l.tools.length ? <><Icon name="check" size={12} /><span className="trunc muted">{l.tools.map(title).join(', ')}</span></>
                : <span className="muted">No tools yet</span>}
            </div>
          </li>
        ))}
      </ol>
    </section>
  )
}
