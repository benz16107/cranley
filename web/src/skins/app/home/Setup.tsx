import { investigate, startOver, useWorkspace } from '../../../core/index.ts'
import { Icon, RunState, ToolKey } from '../design/ui.tsx'
import { go } from '../lib/place.ts'
import { QuestionForm } from '../shell/RunPanel.tsx'

/** The brief is in: the tools arrive with their reasons, then the questions, then Start. */
export function Setup() {
  const doc = useWorkspace((s) => s.doc)
  const open = doc.questions.filter((q) => q.answer == null)
  const settled = doc.questions.length > 0 || doc.tools.length > 0
  return (
    <section className="card arrive" aria-labelledby="setup-h">
      <header>
        <h2 id="setup-h">Setting up the investigation</h2>
        <span className="grow" />
        <button className="btn quiet" onClick={() => { startOver(); go('home') }}>Start over</button>
      </header>
      <div className="body stack">
        <p className="said">{doc.brief!.text}</p>
        {!!doc.brief!.limits?.length && <div className="note"><Icon name="info" size={13} /><div><b>What the tools here cannot do</b>{doc.brief!.limits.map((l) => <p key={l}>{l}</p>)}</div></div>}
      </div>
      <div className="setup-cols">
        <div>
          <h3>Tools for this <span className="count">{doc.tools.length || ''}</span></h3>
          <ul className="picked" aria-live="polite">
            {doc.tools.map((t, i) => <li key={t.id} className="arrive" style={{ animationDelay: `${Math.min(i, 8) * 30}ms` }}><ToolKey id={t.id} title={t.title} /><span className="grow"><b>{t.title}</b><span className="why">{t.reason}</span></span><span className="muted">{t.by === 'agent' ? 'agent' : 'you'}</span></li>)}
            {!settled && <li><RunState state="running">Reading the brief and choosing tools</RunState></li>}
            {!settled && [72, 54, 63].map((w) => <li key={w}><span className="sk" style={{ width: `${w}%` }} /></li>)}
          </ul>
        </div>
        <div>
          <h3>Before the work starts <span className="count">{open.length ? `${open.length} open` : ''}</span></h3>
          {doc.questions.length === 0 ? <p className="muted">{settled ? 'No questions. The tools can run on their defaults.' : 'Questions appear here once the tools are chosen.'}</p> : <div className="stack">{doc.questions.map((q) => <QuestionForm key={q.id} q={q} />)}</div>}
        </div>
      </div>
      {settled && (
        <footer className="setup-go">
          <button className="btn solid" disabled={open.length > 0} onClick={() => void investigate()}>{open.length ? `${open.length} left to answer` : 'Start the investigation'}</button>
          {/* only when every open question has a value on offer: with none, the button could only refuse */}
          {open.length > 0 && open.every((q) => q.hint != null) && <button className="btn" onClick={() => void investigate()}>Use the defaults</button>}
          <span className="muted small">The agent searches, measures and ranks. Its plan and every run show in the agent panel and on the map.</span>
        </footer>
      )}
    </section>
  )
}
