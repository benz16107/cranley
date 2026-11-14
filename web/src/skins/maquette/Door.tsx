import { useEffect, useMemo, useRef, useState } from 'react'
import { NEEDS, compose, currentRoute, fetchPlan, investigate, navigate, startOver, useMapModel, useWorkspace, type Building, type Kind, type Need, type ScanPlan } from '../../core/index.ts'
import { Plan } from './Plan.tsx'
import { QuestionForm } from './Tray.tsx'
import { Big, Print } from './ui.tsx'

/* The front door: the table before any work. A count of what is on it, one line to write, and five real floor
   plans to pick up. Once a line is written, the tools arrive as sheets laid on the table, each with its reason,
   and the questions they need are a ticket beside them. */

/** Which kind of scan stands for each starting point. The scan itself is taken from the feed at run time: a plan
    of a legible size in that starting point's city. No scan id is written here. */
const KIND: Record<string, Kind> = { wheelchair: 'apartment', fire: 'apartment', flood: 'home', office: 'office', manager: 'apartment' }
function starters(all: Building[]): (string | null)[] {
  const used = new Set<string>()
  return NEEDS.map((n) => {
    const kind = KIND[n.id] ?? 'apartment'
    for (const b of all) {
      if (b.metro !== n.city || (n.id === 'flood' && !b.splat)) continue
      const s = b.scans.find((x) => x.kind === kind && x.rooms >= 5 && x.rooms <= 12 && !used.has(x.sid))
      if (s) { used.add(s.sid); return s.sid }
    }
    return null
  })
}
const TILT = [-3.5, 2.5, -1.5, 4, -2.5], LIFT = [0, 30, 6, 38, 12]

function Starter({ need, sid, i, onPick }: { need: Need; sid: string | null; i: number; onPick: () => void }) {
  const [plan, setPlan] = useState<ScanPlan | null>(null)
  useEffect(() => { let on = true; if (sid) fetchPlan(sid).then((p) => on && setPlan(p), () => {}); return () => { on = false } }, [sid])
  return (
    <li style={{ ['--tilt' as string]: `${TILT[i % 5]}deg`, ['--lift' as string]: `${LIFT[i % 5]}px`, ['--i' as string]: i }}>
      <button className="mq-starter" onClick={onPick}>
        <span className="mq-tag"><b>{need.who}</b>{need.need}</span>
        <span className="mq-paper sheet" data-wait={!plan || undefined}>{plan && <Plan plan={plan} px={230} />}</span>
        <span className="on mq-dim">{need.runsOn}</span>
      </button>
    </li>
  )
}

export function Door() {
  const doc = useWorkspace((s) => s.doc)
  const { all, state, reload } = useMapModel()
  const [text, setText] = useState('')
  const sids = useMemo(() => (all.length ? starters(all) : NEEDS.map(() => null)), [all])
  const facts = useMemo(() => ({ scans: all.reduce((n, b) => n + b.count, 0), drone: all.filter((b) => b.splat).length }), [all])
  // the count runs up once, when the feed lands
  const [count, setCount] = useState(0)
  useEffect(() => { if (all.length) setCount(all.length) }, [all.length])
  // When the work begins, go to the table where it shows, after a moment: long enough to see the sheets that were
  // laid out and why. The server can compose and start in one turn, with no question to stop on.
  // Only for a brief written in this visit: a saved workspace that loads with its plan already made stays put.
  const planned = useRef(doc.plan.length), wrote = useRef(false)
  const begin = (sentence: string, needId?: string) => { wrote.current = true; void compose(sentence, needId) }
  useEffect(() => {
    const begun = wrote.current && !planned.current && doc.plan.length > 0
    planned.current = doc.plan.length
    if (!begun) return
    const t = setTimeout(() => { if (currentRoute().path === '/') navigate('/map', {}, { keep: true }) }, 2800)
    return () => clearTimeout(t)
  }, [doc.plan.length])

  const open = doc.questions.filter((q) => q.answer == null)
  if (doc.brief) {
    return (
      <main className="mq-door mq-mat is-composing">
        <Print onHome={() => navigate('/')}><span>Laying out the tools</span></Print>
        <section className="mq-said" aria-labelledby="said-h">
          <span className="mq-caps">Your brief</span>
          <h1 id="said-h" className="mq-paper">{doc.brief.text}</h1>
          {!!doc.brief.limits?.length && <div className="limits"><span className="mq-caps">What the tools here cannot do</span>{doc.brief.limits.map((l) => <p key={l}>{l}</p>)}</div>}
        </section>
        <section className="mq-laid" aria-labelledby="laid-h">
          <h2 id="laid-h" className="mq-caps">{doc.tools.length ? `${doc.tools.length} ${doc.tools.length === 1 ? 'tool' : 'tools'} for this` : 'Choosing the tools'}</h2>
          <ol aria-live="polite">
            {doc.tools.map((t, i) => (
              <li key={t.id} className="mq-paper" style={{ ['--tilt' as string]: `${[-1.2, 0.9, -0.5, 1.4][i % 4]}deg` }}>
                <span className="mq-num n">{i + 1}</span>
                <h3>{t.title}</h3>
                <p className="why">{t.reason}</p>
                {t.summary && <p className="mq-dim">{t.summary}</p>}
              </li>
            ))}
            {!doc.tools.length && <li className="is-wait" aria-hidden="true" />}
          </ol>
        </section>
        {(doc.tools.length > 0 || doc.questions.length > 0) && <section className="mq-ticket mq-paper" aria-labelledby="ticket-h">
          <h2 id="ticket-h" className="mq-caps">{doc.plan.length ? (doc.plan.some((s) => s.status !== 'done') ? 'The agent has started' : 'The agent has finished') : doc.questions.length ? 'Before the work starts' : 'Ready when you are'}</h2>
          {doc.questions.map((q) => <QuestionForm key={q.id} q={q} />)}
          {doc.plan.length > 0 ? <><p>{(doc.plan.find((s) => s.status === 'active') ?? doc.plan.at(-1)!).label}</p><button className="mq-btn is-tape" onClick={() => navigate('/map', {}, { keep: true })}>{doc.plan.some((s) => s.status !== 'done') ? 'Watch it on the table' : 'See it on the table'}</button></> : (
            <div className="go">
              <button className="mq-btn is-tape" disabled={open.length > 0 || !doc.tools.length} onClick={() => void investigate()}>{open.length ? `${open.length} left to answer` : 'Start the investigation'}</button>
              {open.length > 0 && <button className="mq-link" onClick={() => void investigate()}>Use the suggested answers</button>}
            </div>
          )}
          <button className="mq-link" onClick={() => { startOver(); navigate('/', {}, { replace: true }) }}>Start over</button>
        </section>}
      </main>
    )
  }
  return (
    <main className="mq-door mq-mat">
      <Print onHome={() => navigate('/')}><span>Houston and Los Angeles</span></Print>
      <Big value={state === 'ready' ? count : null} digits={0}>
        {state === 'error' ? <>The building list did not load. <button className="mq-link" onClick={reload}>Try again</button></>
          : <>buildings on the table<br /><span className="mq-dim"><span className="mq-num">{facts.scans.toLocaleString('en-US')}</span> scans inside them · <span className="mq-num">{facts.drone}</span> with a drone capture</span></>}
      </Big>
      <form className="mq-ask" onSubmit={(e) => { e.preventDefault(); if (text.trim()) begin(text.trim()) }}>
        <label htmlFor="who" className="mq-caps">Who are you, and what do you need from a building?</label>
        <textarea id="who" className="mq-paper" rows={2} value={text} onChange={(e) => setText(e.target.value)} placeholder="I use a power wheelchair and I want a single-storey house near Clear Lake."
          onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); e.currentTarget.form?.requestSubmit() } }} />
        <button className="mq-btn is-tape" disabled={!text.trim()}>Begin</button>
      </form>
      <ul className="mq-starters">{NEEDS.map((n, i) => <Starter key={n.id} need={n} sid={sids[i]} i={i} onPick={() => begin(n.sentence, n.id)} />)}</ul>
      <p className="mq-foot mq-caps mq-dim">Five real floor plans from the scans. Pick one up, write your own line, or <button className="mq-link" onClick={() => navigate('/map')}>walk the table</button>.</p>
    </main>
  )
}
