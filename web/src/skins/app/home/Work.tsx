import { useState } from 'react'
import type { Doc } from '../../../core/index.ts'
import { Icon, RunState } from '../design/ui.tsx'
import { ago } from '../lib/format.ts'
import { openSeen, started, statusOf, useSeen, type Seen } from '../lib/pending.ts'
import { go, goInvestigation } from '../lib/place.ts'
import { useUi } from '../shell/store.ts'
import { Activity } from './Activity.tsx'

export const STATUS: Record<Seen['status'], { label: string; state: 'pending' | 'running' | 'done' }> = {
  setup: { label: 'Setting up', state: 'pending' }, working: { label: 'Working', state: 'running' }, waiting: { label: 'Needs an answer', state: 'pending' }, done: { label: 'Finished', state: 'done' },
}

/** The person's investigations, the open one first: one line each, a status, and when it last changed. Kept in this
    browser. What is happening in the open one (runs, failures, what a paired phone sent) is behind Activity. */
export function Work({ doc, composing }: { doc: Doc; composing: boolean }) {
  const seen = useSeen((s) => s.all)
  const [act, setAct] = useState(false)
  const open = started(doc) && !composing // while it is being set up, the setup card above is the open investigation
  const others = Object.values(seen).filter((s) => s.id !== doc.id).sort((a, b) => b.last - a.last)
  const asks = doc.questions.filter((q) => q.answer == null).length
  if (!open && others.length === 0) return null
  const now = statusOf(doc)
  return (
    <section className="h-work" aria-labelledby="h-work-h">
      <header>
        <h2 id="h-work-h">Recent</h2>
        {open && <button type="button" className="btn sm quiet" aria-expanded={act} aria-controls="h-work-act" onClick={() => setAct(!act)}>Activity</button>}
        <button type="button" className="btn sm quiet" onClick={() => go('investigations')}>All<Icon name="go" size={11} /></button>
      </header>
      <ul>
        {open && (
          <li data-open="">
            <button type="button" className="row" onClick={() => goInvestigation(doc.id)}>
              <span className="t trunc">{doc.brief?.text ?? 'Tools run by hand, with no brief'}</span>
              <RunState state={STATUS[now].state}>{STATUS[now].label}</RunState>
              <span className="w">Open</span>
            </button>
            {asks > 0 && <button type="button" className="btn sm" onClick={() => useUi.getState().setRun(true)}>Answer</button>}
          </li>
        )}
        {others.slice(0, open ? 4 : 5).map((s) => (
          <li key={s.id}>
            <button type="button" className="row" onClick={() => openSeen(s.id)}>
              <span className="t trunc">{s.brief || 'Tools run by hand'}</span>
              <RunState state={STATUS[s.status].state}>{STATUS[s.status].label}</RunState>
              <span className="w">{ago(s.last)}</span>
            </button>
          </li>
        ))}
      </ul>
      {open && act && <div id="h-work-act"><Activity doc={doc} /></div>}
    </section>
  )
}
