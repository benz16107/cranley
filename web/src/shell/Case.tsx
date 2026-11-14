import { useState } from 'react'
import { Popover } from '@base-ui/react/popover'
import { Switch } from '@base-ui/react/switch'
import { useWorkspace, userOp } from '../workspace/store.ts'
import type { Pref, Question, Run } from '../workspace/types.ts'
import { answerPref, ask, compose, investigate, runToolHere } from '../workspace/agent.ts'
import { Icon, ToolKey } from '../design/ui.tsx'
import { navigate, useRoute } from '../lib/router.ts'

const prefText = (p: Pick<Pref, 'value' | 'unit'>) => (typeof p.value === 'boolean' ? (p.value ? 'yes' : 'no') : `${p.value}${p.unit ? ' ' + p.unit : ''}`)

/* ---------- questions the tools need answered, asked inline ---------- */
export function QuestionForm({ q }: { q: Question }) {
  const [n, setN] = useState(q.hint != null && q.kind !== 'choice' ? String(q.hint) : '')
  const started = useWorkspace((s) => s.doc.plan.length > 0)
  const answer = (a: string | number) => {
    userOp({ op: 'question.answer', id: q.id, answer: a })
    if (started && q.pref) userOp(answerPref(q, a)) // answered after the work began: it counts at once
  }
  return (
    <fieldset className="question">
      <legend>{q.text}</legend>
      {q.kind === 'choice' && (
        <div className="opts">{q.options?.map((o) => <button key={o} type="button" className="chip" aria-pressed={q.answer === o} onClick={() => answer(o)}><span className={/\d/.test(o) ? 'num' : ''}>{o}</span></button>)}</div>
      )}
      {q.kind === 'number' && (
        <form className="opts" onSubmit={(e) => { e.preventDefault(); if (n && Number.isFinite(+n)) answer(+n) }}>
          <input className="field num" inputMode="numeric" value={q.answer != null && !n ? String(q.answer) : n} onChange={(e) => setN(e.target.value)} aria-label={q.text} style={{ width: 96 }} />
          {q.unit && <span className="muted">{q.unit}</span>}
          <button className="btn sm" disabled={!n}>Set</button>
        </form>
      )}
      {q.kind === 'text' && (
        <form className="opts" onSubmit={(e) => { e.preventDefault(); answer(n.trim()) }}>
          <input className="field" value={q.answer != null && !n ? String(q.answer) : n} onChange={(e) => setN(e.target.value)} aria-label={q.text} />
          <button className="btn sm">Set</button>
        </form>
      )}
    </fieldset>
  )
}

/* ---------- the brief: who you are and what you need, editable ---------- */
export function BriefCard() {
  const doc = useWorkspace((s) => s.doc)
  const [editing, setEditing] = useState(false)
  const [text, setText] = useState('')
  const open = doc.questions.filter((q) => q.answer == null)
  if (!doc.brief) {
    return (
      <section className="sec brief" aria-labelledby="brief-h">
        <header><h2 id="brief-h" className="label">Brief</h2></header>
        <p className="empty">No brief yet. Say who you are and the right tools are brought to the dock.</p>
        <button className="btn solid" onClick={() => navigate('/')}>Write a brief</button>
        {open.length > 0 && <div className="asks">{open.map((q) => <QuestionForm key={q.id} q={q} />)}</div>}
      </section>
    )
  }
  return (
    <section className="sec brief" aria-labelledby="brief-h">
      <header>
        <h2 id="brief-h" className="label">Brief</h2>
        {!editing && <button className="link" onClick={() => { setText(doc.brief!.text); setEditing(true) }}>Edit</button>}
      </header>
      {editing ? (
        <form onSubmit={(e) => { e.preventDefault(); setEditing(false); if (text.trim() && text !== doc.brief!.text) void compose(text.trim()) }}>
          <textarea className="field" rows={4} value={text} onChange={(e) => setText(e.target.value)} aria-label="Who you are and what you need" autoFocus />
          <div className="row"><button className="btn solid sm">Save and compose again</button><button type="button" className="btn quiet sm" onClick={() => setEditing(false)}>Cancel</button></div>
        </form>
      ) : <p className="said">{doc.brief.text}</p>}
      {!editing && !!doc.brief.limits?.length && <div className="limits"><span className="label">What the tools here cannot do</span>{doc.brief.limits.map((l) => <p key={l} className="muted">{l}</p>)}</div>}
      {open.length > 0 && !editing && <div className="asks">{open.map((q) => <QuestionForm key={q.id} q={q} />)}</div>}
      {doc.questions.length > 0 && !doc.plan.length && !editing && (
        <button className="btn solid" disabled={open.length > 0} onClick={() => void investigate()}>{open.length ? `${open.length} to answer` : 'Start the investigation'}</button>
      )}
    </section>
  )
}

/** The tool calls made for one step. A long run of them folds to the latest three. */
function StepRuns({ runs }: { runs: Run[] }) {
  const [all, setAll] = useState(false)
  if (!runs.length) return null
  const shown = all ? runs : runs.slice(-3)
  return (
    <ul className="runs">
      {runs.length > shown.length && <li><button className="link" onClick={() => setAll(true)}>{runs.length - shown.length} earlier</button></li>}
      {shown.map((r) => (
        <li key={r.id} data-status={r.status}>
          <span className="rl">{r.label}</span>
          <span className="num">{r.status === 'running' ? 'working' : r.status === 'failed' ? 'failed' : r.ms != null ? (r.ms < 1000 ? `${Math.round(r.ms)} ms` : `${(r.ms / 1000).toFixed(1)} s`) : ''}</span>
          {r.summary && <span className="rs">{r.summary}</span>}
        </li>
      ))}
    </ul>
  )
}

/* ---------- the plan: the agent's steps, live, with each tool call under the step it serves ---------- */
export function PlanCard() {
  const plan = useWorkspace((s) => s.doc.plan), runs = useWorkspace((s) => s.doc.runs)
  const follow = useWorkspace((s) => s.follow), setFollow = useWorkspace((s) => s.setFollow)
  if (!plan.length) return null
  const done = plan.filter((s) => s.status === 'done').length
  return (
    <section className="sec plan" aria-labelledby="plan-h">
      <header><h2 id="plan-h" className="label">Plan</h2><span className="label num" aria-label={`${done} of ${plan.length} steps done`}>{done} / {plan.length}</span></header>
      <ol>
        {plan.map((s, i) => (
          <li key={s.id} data-status={s.status} aria-current={s.status === 'active' ? 'step' : undefined}>
            <span className="num n">{String(i + 1).padStart(2, '0')}</span>
            <span className="t">{s.label}</span>
            <StepRuns runs={runs.filter((r) => r.step === s.id)} />
          </li>
        ))}
      </ol>
      <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={plan.length} aria-valuenow={done} aria-label="Plan progress"><i style={{ scale: `${done / plan.length} 1` }} /></div>
      <label className="follow">
        <Switch.Root className="switch" checked={follow} onCheckedChange={setFollow}><Switch.Thumb className="knob" /></Switch.Root>
        <span>Follow the agent’s view</span>
      </label>
    </section>
  )
}

/* ---------- what I have learned: every item names where it came from and can be undone ---------- */
export function LearnedCard() {
  const prefs = useWorkspace((s) => s.doc.prefs)
  if (!prefs.length) return null
  return (
    <section className="sec learned" aria-labelledby="learned-h">
      <header><h2 id="learned-h" className="label">What I have learned</h2><span className="label num">{prefs.length}</span></header>
      <ul>
        {prefs.map((p) => (
          <li key={p.key}>
            <span>{p.label} <b className={typeof p.value === 'number' ? 'num' : ''}>{prefText(p)}</b><small>{p.from}{p.prev != null && ` (was ${prefText({ value: p.prev, unit: p.unit })})`}</small></span>
            <button className="link" aria-label={`Undo: ${p.label}`}
              onClick={() => userOp({ op: 'pref.set', key: p.key, label: p.label, value: p.prev ?? null, unit: p.unit, from: p.prev != null ? 'You undid a change' : undefined })}>Undo</button>
          </li>
        ))}
      </ul>
    </section>
  )
}

/* ---------- the dock: enabled tools as chips, why each is here, add and remove, the shortlist, one line to ask ---------- */
export function Dock({ onAddTool }: { onAddTool: () => void }) {
  const tools = useWorkspace((s) => s.doc.tools), shortlist = useWorkspace((s) => s.doc.shortlist)
  const canUndo = useWorkspace((s) => s.undoStack.length > 0), undo = useWorkspace((s) => s.undo)
  const { sid } = useRoute()
  const [text, setText] = useState('')
  return (
    <footer className="pane dock" aria-label="Tools">
      <ul className="tools">
        {tools.map((t) => (
          <li key={t.id} className="arrive">
            <Popover.Root>
              <Popover.Trigger className="tool" aria-label={`${t.title}. Why this is here.`}><ToolKey id={t.id} title={t.title} code={t.code} /><span>{t.title}</span></Popover.Trigger>
              <Popover.Portal><Popover.Positioner side="top" align="start" sideOffset={10}><Popover.Popup className="pop whypop">
                <Popover.Title className="ttl"><ToolKey id={t.id} title={t.title} code={t.code} /> {t.title}</Popover.Title>
                <span className="label">Why this is here</span>
                <p className="reason">{t.reason || 'You added it.'}</p>
                {t.summary && <p className="muted">{t.summary}</p>}
                <dl><dt>Works on</dt><dd>{t.coverage ?? 'Not stated'}</dd><dt>Added by</dt><dd>{t.by === 'agent' ? 'The agent, from your brief' : 'You'}</dd></dl>
                <div className="row">
                  {sid && <Popover.Close className="btn solid sm" onClick={() => runToolHere(t.id, sid)}>Run on this scan</Popover.Close>}
                  <Popover.Close className="btn sm" onClick={() => userOp({ op: 'tool.disable', id: t.id })}>Remove</Popover.Close>
                </div>
              </Popover.Popup></Popover.Positioner></Popover.Portal>
            </Popover.Root>
          </li>
        ))}
        <li><button className="tool add" onClick={onAddTool}><Icon name="plus" size={13} /><span>{tools.length ? 'Add' : 'Add a tool'}</span></button></li>
      </ul>
      <form className="ask" onSubmit={(e) => { e.preventDefault(); if (text.trim()) { void ask(text.trim()); setText('') } }}>
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Ask for a change" aria-label="Ask the agent for a change" autoComplete="off" />
      </form>
      {canUndo && <button className="btn quiet sm" onClick={undo} title="Undo your last change (Ctrl Z)"><Icon name="undo" size={14} /> Undo</button>}
      <Popover.Root>
        <Popover.Trigger className="tray" aria-label={`Shortlist, ${shortlist.length} kept`}><Icon name="keep" size={15} /><span className="num">{shortlist.length}</span></Popover.Trigger>
        <Popover.Portal><Popover.Positioner side="top" align="end" sideOffset={10}><Popover.Popup className="pop listpop">
          <Popover.Title className="label">Shortlist</Popover.Title>
          {shortlist.length === 0 && <p className="muted" style={{ paddingTop: 6 }}>Nothing kept yet. Use the bookmark beside a scan to keep it here.</p>}
          <ul className="blist">
            {shortlist.map((s) => (
              <li key={s.sid} className="kept">
                <button onClick={() => navigate(`/scan/${s.sid}`, {}, { keep: true })}><span>{s.name}</span><span className="muted">{s.address.split(',')[0]}</span></button>
                <button className="btn icon quiet sm" aria-label={`Remove ${s.name} from the shortlist`} onClick={() => userOp({ op: 'shortlist.remove', sid: s.sid })}><Icon name="close" size={12} /></button>
              </li>
            ))}
          </ul>
        </Popover.Popup></Popover.Positioner></Popover.Portal>
      </Popover.Root>
    </footer>
  )
}
