import { useState } from 'react'
import { Switch } from '@base-ui/react/switch'
import { answerPref, compose, investigate, navigate, startOver, useWorkspace, userOp, type Pref, type Question, type Run } from '../../core/index.ts'
import { ms } from './words.ts'

/* The desk: what the person said, what the agent asked, its plan as it is written, what it has learned, and what was
   kept. These run under the story on every page, and the open questions run above it. */

const prefText = (p: Pick<Pref, 'value' | 'unit'>) => (typeof p.value === 'boolean' ? (p.value ? 'yes' : 'no') : `${p.value}${p.unit ? ' ' + p.unit : ''}`)

/** One question, in the form its kind needs, with the value on offer shown. */
export function Ask({ q }: { q: Question }) {
  const [text, setText] = useState(q.hint != null && q.kind !== 'choice' ? String(q.hint) : '')
  const started = useWorkspace((s) => s.doc.plan.length > 0)
  const answer = (a: string | number) => {
    userOp({ op: 'question.answer', id: q.id, answer: a })
    if (started && q.pref) userOp(answerPref(q, a)) // answered after the work began: it counts at once
  }
  const value = q.answer != null && !text ? String(q.answer) : text
  return (
    <fieldset className="ask" data-open={q.answer == null || undefined}>
      <legend>{q.text}</legend>
      {q.kind === 'choice' && <div className="opts">{q.options?.map((o) => <button key={o} type="button" className="btn line" aria-pressed={q.answer === o} onClick={() => answer(o)}>{o}</button>)}
        {q.hint != null && q.answer == null && <span className="hint">Offered: {String(q.hint)}</span>}</div>}
      {q.kind === 'number' && (
        <form className="opts" onSubmit={(e) => { e.preventDefault(); if (value && Number.isFinite(+value)) answer(+value) }}>
          <input className="field" inputMode="decimal" value={value} onChange={(e) => setText(e.target.value)} aria-label={q.text} />
          {q.unit && <span className="hint">{q.unit}</span>}
          <button className="btn" disabled={!value || !Number.isFinite(+value)}>{q.answer != null ? 'Change' : 'Set'}</button>
          {q.hint != null && <span className="hint">Offered: {String(q.hint)}{q.unit ? ` ${q.unit}` : ''}</span>}
        </form>
      )}
      {q.kind === 'text' && (
        <form className="opts" onSubmit={(e) => { e.preventDefault(); if (value.trim()) answer(value.trim()) }}>
          <input className="field wide" value={value} onChange={(e) => setText(e.target.value)} aria-label={q.text} />
          <button className="btn" disabled={!value.trim()}>{q.answer != null ? 'Change' : 'Set'}</button>
          {q.hint != null && <span className="hint">Offered: {String(q.hint)}</span>}
        </form>
      )}
    </fieldset>
  )
}

/** Questions still open, wherever the person is. A tool run from the masthead can ask one before any brief exists. */
export function OpenQuestions() {
  const open = useWorkspace((s) => s.doc.questions).filter((q) => q.answer == null)
  const waiting = useWorkspace((s) => s.doc.plan.length === 0 && !!s.doc.brief && s.doc.questions.length > 0)
  if (!open.length && !waiting) return null
  return (
    <section className="sec" style={{ marginTop: 0, marginBottom: '2.25rem' }} aria-label="Questions">
      <h2>{open.length ? 'Before this can be written' : 'Ready to start'}</h2>
      <div className="asks" style={{ marginTop: '1rem' }}>{open.map((q) => <Ask key={q.id} q={q} />)}</div>
      {waiting && <div className="row" style={{ marginTop: '1rem' }}><StartButtons open={open.length} /></div>}
    </section>
  )
}
export function StartButtons({ open }: { open: number }) {
  return (
    <>
      <button className="btn" disabled={open > 0} onClick={() => void investigate()}>{open ? `${open} left to answer` : 'Start the investigation'}</button>
      {open > 0 && <button className="link" onClick={() => void investigate()}>Use the defaults</button>}
      <button className="link" onClick={() => { startOver(); navigate('/', {}, { replace: true }) }}>Start over</button>
    </>
  )
}

function Brief() {
  const doc = useWorkspace((s) => s.doc)
  const [editing, setEditing] = useState(false), [text, setText] = useState('')
  const answered = doc.questions.filter((q) => q.answer != null)
  return (
    <section className="sec brief" aria-labelledby="brief-h">
      <header><h2 id="brief-h">The brief</h2>{doc.brief && !editing && <button className="link" onClick={() => { setText(doc.brief!.text); setEditing(true) }}>Edit</button>}</header>
      {!doc.brief && <><p className="empty">No brief yet. Say who you are and the sections that fit are brought to the masthead.</p><button className="btn" onClick={() => navigate('/')}>Write a brief</button></>}
      {doc.brief && (editing ? (
        <form onSubmit={(e) => { e.preventDefault(); setEditing(false); if (text.trim() && text !== doc.brief!.text) void compose(text.trim()) }}>
          <textarea rows={3} value={text} onChange={(e) => setText(e.target.value)} aria-label="Who you are and what you need" autoFocus />
          <div className="row" style={{ marginTop: '0.75rem' }}><button className="btn">Save and compose again</button><button type="button" className="link" onClick={() => setEditing(false)}>Cancel</button></div>
        </form>
      ) : <blockquote>{doc.brief.text}</blockquote>)}
      {!!doc.brief?.limits?.length && !editing && <div className="limits"><span className="cap">What no section here can do</span>{doc.brief.limits.map((l) => <p key={l}>{l}</p>)}</div>}
      {answered.length > 0 && !editing && <div className="asks" style={{ marginTop: '1rem' }}>{answered.map((q) => <Ask key={q.id} q={q} />)}</div>}
      {doc.brief && !editing && <div className="row" style={{ marginTop: '0.75rem' }}><button className="link" onClick={() => { startOver(); navigate('/', {}, { replace: true }) }}>Start over with a new brief</button></div>}
    </section>
  )
}

function Runs({ runs }: { runs: Run[] }) {
  const [all, setAll] = useState(false)
  if (!runs.length) return null
  const shown = all ? runs : runs.slice(-3)
  return (
    <ul className="runs">
      {runs.length > shown.length && <li><button className="link" onClick={() => setAll(true)}>{runs.length - shown.length} earlier</button></li>}
      {shown.map((r) => (
        <li key={r.id} data-status={r.status}>
          <span><span className={r.status === 'running' ? 'reading' : undefined}>{r.label}</span></span>
          <span className="n">{r.status === 'running' ? 'working' : r.status === 'failed' ? 'failed' : r.ms != null ? ms(r.ms) : ''}</span>
          {r.summary && <span className="rs">{r.summary}</span>}
        </li>
      ))}
    </ul>
  )
}

/** The agent's plan, as the page being written: finished steps are set in type, the one in hand is under the pencil,
    and the ones to come are ruled lines. */
export function Plan() {
  const plan = useWorkspace((s) => s.doc.plan), runs = useWorkspace((s) => s.doc.runs)
  const follow = useWorkspace((s) => s.follow), setFollow = useWorkspace((s) => s.setFollow)
  const loose = runs.filter((r) => !r.step || !plan.some((s) => s.id === r.step))
  if (!plan.length && !loose.length) return null
  const done = plan.filter((s) => s.status === 'done').length
  return (
    <section className="sec" aria-labelledby="plan-h">
      <header><h2 id="plan-h">The work</h2>{plan.length > 0 && <span className="cap" aria-label={`${done} of ${plan.length} steps done`}>{done} of {plan.length}</span>}</header>
      <ol className="plan">
        {plan.map((s, i) => (
          <li key={s.id} data-status={s.status} aria-current={s.status === 'active' ? 'step' : undefined}>
            <span className="no">{String(i + 1).padStart(2, '0')}</span>
            <span className={s.status === 'active' ? 't reading' : 't'}>{s.label}</span>
            {s.status === 'pending' && <i className="unset" />}
            <Runs runs={runs.filter((r) => r.step === s.id)} />
          </li>
        ))}
        {loose.length > 0 && <li data-status="done"><span className="no">{plan.length ? '+' : '01'}</span><span className="t">Run from the masthead</span><Runs runs={loose} /></li>}
      </ol>
      {plan.length > 0 && (
        <label className="follow">
          <Switch.Root className="switch" checked={follow} onCheckedChange={setFollow}><Switch.Thumb className="knob" /></Switch.Root>
          <span>Turn the page to where the agent is looking</span>
        </label>
      )}
    </section>
  )
}

function Learned() {
  const prefs = useWorkspace((s) => s.doc.prefs)
  if (!prefs.length) return null
  return (
    <section className="sec" aria-labelledby="learned-h">
      <header><h2 id="learned-h">What I have learned</h2><span className="cap">{prefs.length}</span></header>
      <ul className="learned">
        {prefs.map((p) => (
          <li key={p.key}>
            <span>{p.label}{prefText(p) && <> <b className="n">{prefText(p)}</b></>}<small>{p.from}{p.prev != null && ` (was ${prefText({ value: p.prev, unit: p.unit })})`}</small></span>
            <button className="link" aria-label={`Undo: ${p.label}`}
              onClick={() => userOp({ op: 'pref.set', key: p.key, label: p.label, value: p.prev ?? null, unit: p.unit, from: p.prev != null ? 'You undid a change' : undefined })}>Undo</button>
          </li>
        ))}
      </ul>
    </section>
  )
}

export function Kept({ empty = false }: { empty?: boolean }) {
  const shortlist = useWorkspace((s) => s.doc.shortlist)
  if (!shortlist.length && !empty) return null
  return (
    <section className="sec" aria-labelledby="kept-h">
      <header><h2 id="kept-h">Kept</h2><span className="cap">{shortlist.length}</span></header>
      {!shortlist.length && <p className="empty">Nothing kept yet. Use Keep beside a scan to put it here.</p>}
      <ul className="kept">
        {shortlist.map((s) => (
          <li key={s.sid}>
            <button onClick={() => navigate(`/scan/${s.sid}`, {}, { keep: true })}><span>{s.name}</span><small>{[s.address.split(',')[0], s.note].filter(Boolean).join(' · ')}</small></button>
            <button className="link" aria-label={`Remove ${s.name} from the kept list`} onClick={() => userOp({ op: 'shortlist.remove', sid: s.sid })}>Remove</button>
          </li>
        ))}
      </ul>
    </section>
  )
}

export function Desk() {
  return <><Learned /><Kept /><Brief /></>
}
