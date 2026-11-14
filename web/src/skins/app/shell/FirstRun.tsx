import { useEffect, useMemo, useRef, useState } from 'react'
import { Dialog } from '@base-ui/react/dialog'
import { compose, fetchPlan, investigate, photorealReady, useBuildings, useCatalog, useWorkspace } from '../../../core/index.ts'
import { Icon, Mark, St } from '../design/ui.tsx'
import { FIRST_RUN_KEY, guide, onSite, pickScan, type GuideStep } from '../lib/firstrun.ts'
import { started, useSeen } from '../lib/pending.ts'
import { go, goInvestigation, goScan, usePlace } from '../lib/place.ts'
import { Composer } from '../pages/Home.tsx'
import { useUi } from './store.ts'

/* The guided first run. It asks one thing (who you are and what you need), then stands aside: the real workspace is
   on the page while the agent composes it, and a small card says which step is happening. It opens the first
   building the agent measures and ends when that building has results. It is shown once per browser, can be left at
   any moment, and Settings starts it again. */

const CAP = 100_000 // if nothing useful has arrived by then, the guide says so and steps back
const DWELL = 6_000 // the building is on the page at least this long before the guide ends: its results are seen arriving
const SAY: Partial<Record<GuideStep['id'], string>> = {
  tools: 'Each tool arrives on the page with the reason it was picked.',
  answers: 'The agent asked what it needs to know. The usual values are taken for now; you can change them later.',
  plan: 'The agent is deciding where to look first.',
  building: 'It is searching the scanned buildings for ones that fit your brief.',
  findings: 'This is one of the buildings it picked. Its tools are about to measure it.',
}
const done = () => { try { return localStorage.getItem(FIRST_RUN_KEY) != null } catch { return true } }
const mark = () => { try { localStorage.setItem(FIRST_RUN_KEY, '1') } catch { /* asked again next visit */ } }
const close = () => useUi.setState({ first: null })

export function FirstRun() {
  const phase = useUi((s) => s.first)
  const doc = useWorkspace((s) => s.doc)
  const all = useBuildings((s) => s.all)
  const place = usePlace()
  const [opened, setOpened] = useState<string | null>(null)
  const g = useMemo(() => guide(doc, opened), [doc, opened])
  const run = useRef(0)
  // While the guide shows one building the place does not follow the agent's camera. `held` is the setting to put back.
  const held = useRef<boolean | null>(null), following = useWorkspace((s) => s.follow)
  const release = (to?: boolean) => { if (held.current != null) { useWorkspace.getState().setFollow(to ?? held.current); held.current = null } }

  // A first visit: nothing kept in this browser, nothing open, not someone else's link, and the visit lands on Home.
  useEffect(() => {
    let fresh = true
    try { fresh = localStorage.getItem('threshold.workspace') == null } catch { /* a private window is a first visit */ }
    if (!done() && fresh && place.page === 'home' && !Object.keys(useSeen.getState().all).length && !useCatalog.getState().shared && !started(useWorkspace.getState().doc)) useUi.setState({ first: 'ask' })
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const start = (sentence: string, needId?: string) => {
    mark()
    const mine = ++run.current
    setOpened(null)
    if (held.current == null) held.current = useWorkspace.getState().follow
    useWorkspace.getState().setFollow(false)
    useUi.setState({ first: 'watch' })
    void (async () => {
      await compose(sentence, needId)
      // Composing has ended. With nothing to ask the server has gone on by itself; otherwise the answers on offer are
      // taken and the work starts, with nobody pressing Start. A question with no answer on offer waits for the person.
      const here = () => run.current === mine && useUi.getState().first === 'watch'
      if (here() && !guide(useWorkspace.getState().doc, null).ask) await investigate()
    })()
  }
  const skip = () => { mark(); close() }
  const end = () => useUi.setState({ first: 'end' })
  const leave = () => { release(); close() } // leaving mid-way: the app behaves as it always does from here

  // Open one building and stay on it: of the agent's picks, one that opens photoreal on its site (the warmed demo
  // scans); failing that one whose photoreal colour is made; failing that the first.
  // If the agent then measures others and passes that one over, the guide moves once to one it did measure.
  const moved = g.instead.length > 0
  const picks = g.candidates.slice(0, 6).join(' '), at = useRef(0)
  useEffect(() => {
    if (phase !== 'watch' || (opened && !moved) || !picks) return
    let on = true
    // The agent's tools land on its picks within a second or two of each other, so a pick with no run yet is given
    // a few seconds before the guide decides it was passed over; the scans to move to are read when that time is up.
    const wait = setTimeout(() => void (async () => {
      const sids = moved ? guide(useWorkspace.getState().doc, opened).instead.slice(0, 6) : picks.split(' ')
      if (!sids.length) return
      const baked = await Promise.all(sids.map(photorealReady))
      // a plan is read only for a scan whose colour is made: that scan is on disk already, so nothing new is fetched
      const sited = await Promise.all(sids.map((sid, i) => (baked[i] ? fetchPlan(sid).then(onSite, () => false) : false)))
      const sid = pickScan(sids, baked, sited)
      if (!on || !sid || useUi.getState().first !== 'watch') return
      at.current = Date.now(); setOpened(sid); goScan(sid)
    })(), moved ? 4000 : 0)
    return () => { on = false; clearTimeout(wait) }
  }, [phase, opened, moved, picks])
  useEffect(() => { if (phase !== 'watch' || !g.ready) return; const t = setTimeout(end, Math.max(0, at.current + DWELL - Date.now())); return () => clearTimeout(t) }, [phase, g.ready])
  // the limit does not run while a question waits for the person: that time is theirs
  useEffect(() => { if (phase !== 'watch' || g.ask) return; const t = setTimeout(end, CAP); return () => clearTimeout(t) }, [phase, g.ask])
  // the person answered the question that was holding the work up: carry on without their pressing Start
  const asked = useRef(false)
  useEffect(() => { if (phase === 'watch' && asked.current && !g.ask && !doc.plan.length) void investigate(); asked.current = g.ask }, [phase, g.ask]) // eslint-disable-line react-hooks/exhaustive-deps
  // the agent has finished: the place follows it again, as before, unless the person chose first
  useEffect(() => { if (phase !== 'watch' && phase !== 'ask' && !g.working) release() }, [phase, g.working]) // eslint-disable-line react-hooks/exhaustive-deps

  const name = useMemo(() => { for (const b of all) { const s = b.scans.find((x) => x.sid === opened); if (s) return s.name } return null }, [all, opened])
  const active = g.steps.find((s) => s.state === 'active' || s.state === 'ask')
  const onBuilding = !!opened && place.sid === opened

  return (
    <>
      <Dialog.Root open={phase === 'ask'} onOpenChange={(o) => { if (!o && useUi.getState().first === 'ask') skip() }}>
        <Dialog.Portal>
          <Dialog.Backdrop className="backdrop" />
          {/* the field takes the focus, except on a touch screen, where that would raise the keyboard over the needs */}
          <Dialog.Popup className="dialog firstrun" initialFocus={() => document.querySelector<HTMLElement>(window.matchMedia('(pointer: coarse)').matches ? '.firstrun .h-needs button' : '.firstrun textarea')}>
            <header>
              <Mark />
              <Dialog.Title render={<h2 />}>Who are you, and what do you need from a building?</Dialog.Title>
              <Dialog.Close render={<button type="button" className="btn sm quiet" />}>Skip</Dialog.Close>
            </header>
            <div className="body stack">
              <Dialog.Description render={<p className="dim" />}>One line, or one tap. The agent picks tools for you and tries them on a real scanned building while you watch. It takes about a minute.</Dialog.Description>
              <Composer bare first={false} onStart={start} />
              <p className="small muted">What you type is sent to the Threshold server and the language model it uses. <button type="button" className="link" onClick={() => { skip(); go('settings') }}>Privacy and terms</button></p>
            </div>
          </Dialog.Popup>
        </Dialog.Portal>
      </Dialog.Root>

      {(phase === 'watch' || phase === 'end') && (
        <section className="guide arrive" aria-label="First run guide">
          <header>
            <h2>{phase === 'watch' ? 'Setting up your workspace' : g.results ? 'Your first result' : 'Still working'}</h2>
            <button type="button" className="btn sm icon quiet" aria-label={phase === 'watch' ? 'Leave the guide' : 'Close'} onClick={leave}><Icon name="close" size={12} /></button>
          </header>
          {phase === 'watch' ? (
            <>
              <ol aria-live="polite">
                {g.steps.map((s) => (
                  <li key={s.id} data-state={s.state}>
                    {s.state === 'done' ? <Icon name="check" size={12} /> : s.state === 'active' ? <i className="ring" /> : s.state === 'ask' ? <Icon name="help" size={12} /> : <i className="dot" />}
                    <span>{s.id === 'building' && s.state === 'done' && name ? `${name} opened` : s.label}</span>
                  </li>
                ))}
              </ol>
              {active && <p className="say">{active.state === 'ask' ? 'Answer on the page. The work starts as soon as you do.' : SAY[active.id]}</p>}
            </>
          ) : (
            <>
              {g.verdict ? (
                <div className="verdict">
                  <p className="row"><St status={g.verdict.status} /><b className="trunc">{g.verdict.title}</b></p>
                  <p className="text">{g.verdict.text}</p>
                  <p className="muted small">{name ? `${name}. ` : ''}{g.working ? 'The agent is still measuring; more results are on their way.' : 'The agent has finished.'}</p>
                </div>
              ) : <p className="say">{g.working ? 'The agent has not finished its first building yet. Its plan and every run are in the agent panel.' : 'Nothing was measured this time. Ask again in other words, or run a tool by hand on a building from Explore.'}</p>}
              <dl className="where">
                {onBuilding && <div><dt>Results</dt><dd>Every check on this building, with its source</dd></div>}
                <div><dt><span className="kbd">]</span></dt><dd>The agent’s plan and each run</dd></div>
                <div><dt><span className="kbd">G</span><span className="kbd">E</span></dt><dd>Every scanned address on the map</dd></div>
              </dl>
              <footer>
                {g.working && !following
                  ? <><button type="button" className="btn solid" onClick={() => { release(true); close() }}>Follow the agent</button><button type="button" className="btn" onClick={close}>Stay here</button></>
                  : <button type="button" className="btn solid" onClick={leave}>Done</button>}
                {!onBuilding && started(doc) && <button type="button" className="btn quiet" onClick={() => { leave(); goInvestigation(doc.id) }}>Open the investigation</button>}
              </footer>
            </>
          )}
        </section>
      )}
    </>
  )
}
