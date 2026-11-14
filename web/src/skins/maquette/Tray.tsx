import { useState } from 'react'
import { Popover } from '@base-ui/react/popover'
import { Switch } from '@base-ui/react/switch'
import { answerPref, ask, compose, investigate, navigate, startOver, useWorkspace, userOp, type Pref, type Question, type Run } from '../../core/index.ts'
import { Icon, ms, street } from './ui.tsx'

/* The job ticket: what the person asked for and what the agent is doing about it. It lies at the near edge of the
   table. One line each for the brief and the step in hand; the rest is behind a press. */

const prefText = (p: Pick<Pref, 'value' | 'unit'>) => (typeof p.value === 'boolean' ? (p.value ? 'yes' : 'no') : `${p.value}${p.unit ? ' ' + p.unit : ''}`)

/** A question a tool needs answered. All three kinds; the value on offer (the tool's default, or what the person
    already said) is marked on a choice and filled into a field. */
export function QuestionForm({ q }: { q: Question }) {
  const [n, setN] = useState(q.hint != null && q.kind !== 'choice' ? String(q.hint) : '')
  const started = useWorkspace((s) => s.doc.plan.length > 0)
  const answer = (a: string | number) => {
    userOp({ op: 'question.answer', id: q.id, answer: a })
    if (started && q.pref) userOp(answerPref(q, a)) // answered after the work began: it counts at once
  }
  const typed = q.answer != null && !n ? String(q.answer) : n
  return (
    <fieldset className="mq-q" data-open={q.answer == null || undefined}>
      <legend>{q.text}</legend>
      {q.kind === 'choice' ? (
        <div className="mq-row">{q.options?.map((o) => (
          <button key={o} type="button" className="mq-chip" aria-pressed={q.answer === o} onClick={() => answer(o)}>
            <span className={/\d/.test(o) ? 'mq-num' : ''}>{o}</span>{q.answer == null && q.hint === o && <small>suggested</small>}
          </button>
        ))}</div>
      ) : (
        <form className="mq-row" onSubmit={(e) => { e.preventDefault(); if (q.kind === 'text' ? typed.trim() : typed && Number.isFinite(+typed)) answer(q.kind === 'text' ? typed.trim() : +typed) }}>
          <input className={q.kind === 'number' ? 'mq-field mq-num' : 'mq-field'} style={{ width: q.kind === 'number' ? 112 : 220 }} inputMode={q.kind === 'number' ? 'decimal' : undefined} value={typed} onChange={(e) => setN(e.target.value)} aria-label={q.text} />
          {q.unit && <span className="mq-dim">{q.unit}</span>}
          <button className="mq-btn is-ink is-sm" disabled={!typed}>Set</button>
          {q.answer == null && q.hint != null && <span className="mq-dim">suggested</span>}
        </form>
      )}
    </fieldset>
  )
}

/** Questions still open, wherever the person is. One a tool asks after a run from the stack arrives here too,
    even with no brief. */
export function Questions() {
  const doc = useWorkspace((s) => s.doc)
  const open = doc.questions.filter((q) => q.answer == null)
  if (!open.length) return null
  return (
    <section className="mq-ask-card mq-paper" aria-label="Questions to answer">
      <h2 className="mq-caps">{open.length === 1 ? 'One question before this runs' : `${open.length} questions before this runs`}</h2>
      {open.map((q) => <QuestionForm key={q.id} q={q} />)}
      {doc.brief && !doc.plan.length && <button className="mq-link" onClick={() => void investigate()}>Use the suggested answers and start</button>}
    </section>
  )
}

function StepRuns({ runs }: { runs: Run[] }) {
  const [all, setAll] = useState(false)
  if (!runs.length) return null
  const shown = all ? runs : runs.slice(-3)
  return (
    <ul className="mq-runs">
      {runs.length > shown.length && <li><button className="mq-link" onClick={() => setAll(true)}>{runs.length - shown.length} earlier</button></li>}
      {shown.map((r) => (
        <li key={r.id} data-status={r.status}>
          <span>{r.label}</span><span className="mq-num">{r.status === 'running' ? 'working' : r.status === 'failed' ? 'failed' : r.ms != null ? ms(r.ms) : ''}</span>
          {r.summary && <small>{r.summary}</small>}
        </li>
      ))}
    </ul>
  )
}

export function Tray() {
  const doc = useWorkspace((s) => s.doc), follow = useWorkspace((s) => s.follow), setFollow = useWorkspace((s) => s.setFollow)
  const canUndo = useWorkspace((s) => s.undoStack.length > 0), undo = useWorkspace((s) => s.undo)
  const [text, setText] = useState(''), [edit, setEdit] = useState<string | null>(null)
  const { brief, plan, runs, prefs, shortlist } = doc
  const done = plan.filter((s) => s.status === 'done').length, now = plan.find((s) => s.status === 'active')
  const running = runs.findLast((r) => r.status === 'running')
  const open = doc.questions.filter((q) => q.answer == null).length

  return (
    <section className="mq-tray mq-paper" aria-label="Your brief and the agent's work">
      {/* the brief: what the person said, its limits, and a way to say it again */}
      <Popover.Root onOpenChange={(o) => !o && setEdit(null)}>
        <Popover.Trigger className="mq-brief" aria-label={brief ? `Your brief: ${brief.text}` : 'No brief yet'}>
          <span className="mq-caps">Brief</span>
          <span className="said">{brief ? brief.text : 'Nothing asked yet. Say who you are and the right tools are laid out.'}</span>
        </Popover.Trigger>
        <Popover.Portal><Popover.Positioner side="top" align="start" sideOffset={10}><Popover.Popup className="mq-pop mq-brief-pop">
          <span className="mq-caps">Your brief</span>
          {edit != null ? (
            <form onSubmit={(e) => { e.preventDefault(); const t = edit.trim(); setEdit(null); if (t && t !== brief?.text) void compose(t) }}>
              <textarea className="mq-field" rows={4} value={edit} onChange={(e) => setEdit(e.target.value)} aria-label="Who you are and what you need" autoFocus />
              <div className="mq-row" style={{ marginTop: 10 }}><button className="mq-btn is-ink is-sm">Compose again</button><button type="button" className="mq-btn is-quiet is-sm" onClick={() => setEdit(null)}>Cancel</button></div>
            </form>
          ) : <h3>{brief?.text ?? 'No brief yet.'}</h3>}
          {!!brief?.limits?.length && edit == null && <div className="limits"><span className="mq-caps">What the tools here cannot do</span>{brief.limits.map((l) => <p key={l}>{l}</p>)}</div>}
          {edit == null && (
            <div className="mq-row">
              {brief ? <button className="mq-btn is-quiet is-sm" onClick={() => setEdit(brief.text)}>Edit</button> : <Popover.Close className="mq-btn is-ink is-sm" onClick={() => navigate('/')}>Write a brief</Popover.Close>}
              <Popover.Close className="mq-btn is-quiet is-sm" onClick={() => { startOver(); navigate('/', {}, { replace: true }) }}>Start over</Popover.Close>
            </div>
          )}
        </Popover.Popup></Popover.Positioner></Popover.Portal>
      </Popover.Root>

      {/* the plan: one line while it runs, every step and tool call behind it */}
      {plan.length > 0 || runs.length > 0 ? (
        <Popover.Root>
          <Popover.Trigger className="mq-planline" aria-label={plan.length ? `Plan: ${done} of ${plan.length} steps done. Open the plan.` : `${runs.length} tool runs. Open the list.`}>
            <span className="mq-caps">{now ? `Step ${plan.indexOf(now) + 1} of ${plan.length}` : !plan.length ? (running ? 'Working' : `${runs.length} ${runs.length === 1 ? 'run' : 'runs'}`) : done === plan.length ? `${plan.length} steps done` : `${done} of ${plan.length} done`}</span>
            <span className="now" data-live={!!now || !!running || undefined}>{now?.label ?? plan.at(-1)?.label ?? (running ?? runs.at(-1)!).label}</span>
            {plan.length > 0 && <span className="ticks" aria-hidden="true">{plan.map((s) => <i key={s.id} data-status={s.status} />)}</span>}
            {running && (plan.length > 0 || running.summary) && <span className="run">{plan.length > 0 && <span>{running.label}</span>}<small>{running.summary ?? 'working'}</small></span>}
          </Popover.Trigger>
          <Popover.Portal><Popover.Positioner side="top" align="start" sideOffset={10}><Popover.Popup className="mq-pop mq-plan-pop">
            <span className="mq-caps">{plan.length ? 'The plan' : 'Tool runs'}</span>
            <ol className="mq-steps">
              {plan.map((s, i) => (
                <li key={s.id} data-status={s.status} aria-current={s.status === 'active' ? 'step' : undefined}>
                  <span className="mq-num n">{i + 1}</span><span className="t">{s.label}</span>
                  <StepRuns runs={runs.filter((r) => r.step === s.id)} />
                </li>
              ))}
            </ol>
            <StepRuns runs={runs.filter((r) => !r.step || !plan.some((s) => s.id === r.step))} />
            <label className="mq-follow"><Switch.Root className="mq-switch" checked={follow} onCheckedChange={setFollow}><Switch.Thumb className="mq-knob" /></Switch.Root><span>Go where the agent looks</span></label>
          </Popover.Popup></Popover.Positioner></Popover.Portal>
        </Popover.Root>
      ) : brief && doc.questions.length > 0 ? (
        <div className="mq-planline is-idle">
          <span className="mq-caps">{open ? `${open} to answer` : 'Ready'}</span>
          <button className="mq-btn is-tape is-sm" disabled={open > 0} onClick={() => void investigate()}>Start the investigation</button>
          {open > 0 && <button className="mq-link" onClick={() => void investigate()}>Use the suggested answers</button>}
        </div>
      ) : null}

      <form className="mq-say" onSubmit={(e) => { e.preventDefault(); if (text.trim()) { void ask(text.trim()); setText('') } }}>
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Ask for a change" aria-label="Ask the agent for a change" autoComplete="off" enterKeyHint="send" />
        <button className="mq-btn is-ink is-sm" disabled={!text.trim()}>Ask</button>
      </form>

      <footer className="mq-tray-foot">
        <Popover.Root>
          <Popover.Trigger className="mq-count" aria-label={`What I have learned, ${prefs.length} items`}><span className="mq-num">{prefs.length}</span> learned</Popover.Trigger>
          <Popover.Portal><Popover.Positioner side="top" align="start" sideOffset={10}><Popover.Popup className="mq-pop">
            <span className="mq-caps">What I have learned</span>
            {!prefs.length && <p className="mq-dim">Nothing yet. An answer, a control you move or a correction you make is kept here, and each can be undone.</p>}
            <ul className="mq-learned">
              {prefs.map((p) => (
                <li key={p.key}>
                  <span>{p.label} <b className={typeof p.value === 'number' ? 'mq-num' : ''}>{prefText(p)}</b><small>{p.from}{p.prev != null && ` (was ${prefText({ value: p.prev, unit: p.unit })})`}</small></span>
                  <button className="mq-link" aria-label={`Undo: ${p.label}`} onClick={() => userOp({ op: 'pref.set', key: p.key, label: p.label, value: p.prev ?? null, unit: p.unit, from: p.prev != null ? 'You undid a change' : undefined })}>Undo</button>
                </li>
              ))}
            </ul>
          </Popover.Popup></Popover.Positioner></Popover.Portal>
        </Popover.Root>
        <Popover.Root>
          <Popover.Trigger className="mq-count" aria-label={`Shortlist, ${shortlist.length} kept`}><span className="mq-num">{shortlist.length}</span> kept</Popover.Trigger>
          <Popover.Portal><Popover.Positioner side="top" align="start" sideOffset={10}><Popover.Popup className="mq-pop">
            <span className="mq-caps">Kept</span>
            {!shortlist.length && <p className="mq-dim">Nothing kept yet. Keep a scan from its building and it is listed here.</p>}
            <ul className="mq-kept">
              {shortlist.map((s) => (
                <li key={s.sid}>
                  <Popover.Close className="open" onClick={() => navigate(`/scan/${s.sid}`, {}, { keep: true })}><b>{s.name}</b><small>{[street(s.address), s.note].filter(Boolean).join(' · ')}</small></Popover.Close>
                  <button className="mq-x" aria-label={`Remove ${s.name} from the kept list`} onClick={() => userOp({ op: 'shortlist.remove', sid: s.sid })}><Icon name="close" size={13} /></button>
                </li>
              ))}
            </ul>
          </Popover.Popup></Popover.Positioner></Popover.Portal>
        </Popover.Root>
        <button className="mq-count" disabled={!canUndo} onClick={undo} title="Undo your last change (Ctrl Z)"><Icon name="undo" size={13} /> Undo</button>
      </footer>
    </section>
  )
}
