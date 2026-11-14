import { useCallback, useState } from 'react'
import { toast } from 'sonner'
import { answer, brief, building, captureFile, choose, forget, usePhone, type Capture, type Question, type Task, type View } from './api.ts'
import { Field, ResultCard, Row, num, toolTitle } from './parts.tsx'
import { useDictation } from './sensors.ts'

/* The three tabs: what to do in this building, the instruments, and what came back. */

export type Tab = 'tasks' | 'tools' | 'results'
export type ToolId = 'where' | 'level' | 'sound' | 'window' | 'floor' | 'photo' | 'walk' | 'note'
export const TOOLS: { id: ToolId; title: string; sub: string; uses: string; needsScan?: boolean }[] = [
  { id: 'where', title: 'Where am I', sub: 'Open the scanned building you are standing in', uses: 'GPS' },
  { id: 'level', title: 'Slope check', sub: 'A ramp against 1:12, a threshold, a door frame', uses: 'Tilt' },
  { id: 'photo', title: 'Photo measure', sub: 'A width or height from a photo with a sheet of paper in it', uses: 'Camera' },
  { id: 'floor', title: 'Floor height', sub: 'Steps and fixes at the front door, for the flood result', uses: 'GPS, camera', needsScan: true },
  { id: 'window', title: 'Window check', sub: 'Which way a window faces, and its hours of sun', uses: 'Compass', needsScan: true },
  { id: 'sound', title: 'Noise level', sub: 'How loud each room is next to the others', uses: 'Microphone' },
  { id: 'walk', title: 'Walk-through', sub: 'Smoke alarms and hazards in a home with no scan', uses: 'Video' },
  { id: 'note', title: 'Note', sub: 'A photo, clip or voice note pinned to a room', uses: 'Camera, microphone' },
]
const KIND_WORD: Record<Task['kind'], string> = { width: 'Tape', step: 'Tape', slope: 'Level', alarm: 'Look', floor_height: 'Count, GPS', heading: 'Compass' }
/* Tasks are listed under what is being settled, so a row only has to say where. */
const GROUPS: [Task['kind'], string, RegExp | null][] = [['floor_height', 'Flood: floor height', null], ['width', 'Doorways: clear width', /^Measure the doorway, /], ['step', 'Steps and thresholds', /^Measure the step (at the doorway, )?/],
  ['slope', 'Ramps', null], ['alarm', 'Smoke alarms: ceilings to check', /^Photograph the ceiling in /], ['heading', 'Windows: which way they face', /^Point the phone out of the window in /]]
const short = (t: Task) => { const cut = GROUPS.find(([k]) => k === t.kind)?.[2]; const s = cut ? t.title.replace(cut, '') : t.title; return s.charAt(0).toUpperCase() + s.slice(1) }
const SAID = { confirmed: 'confirms', contradicted: 'contradicts', measured: 'measured' } as const

/** The brief, spoken or typed. Dictation is the browser's own; where it has none, the keyboard's microphone still works. */
export function Composer({ sid, placeholder, cta }: { sid: string | null; placeholder: string; cta: string }) {
  const [text, setText] = useState('')
  const [sending, setSending] = useState(false)
  const heard = useCallback((t: string) => setText(t), [])
  const d = useDictation(heard)
  const go = async () => {
    setSending(true)
    try { await brief(text.trim(), sid); setText(''); toast('Sent. The agent is working; results arrive here and on the desktop.') } catch (e) { toast.error((e as Error).message) } finally { setSending(false) }
  }
  return (
    <div className="m-composer">
      <Field label="What do you need to know about this building?" hint={d.error ?? (d.supported ? undefined : 'This browser has no dictation of its own. The microphone key on the keyboard works here.')}>
        <textarea className="m-input" rows={3} value={text} onChange={(e) => setText(e.target.value)} placeholder={placeholder} maxLength={1500} />
      </Field>
      <div className="m-inline">
        {d.supported && <button className="btn m-btn" aria-pressed={d.on} onClick={() => (d.on ? d.stop() : d.start())}>{d.on ? 'Listening. Tap to stop' : 'Speak it'}</button>}
        <button className="btn m-btn solid" disabled={text.trim().length < 4 || sending} onClick={() => void go()}>{cta}</button>
      </div>
    </div>
  )
}

function Questions({ qs }: { qs: Question[] }) {
  const [vals, setVals] = useState<Record<string, string>>({})
  const give = async (q: Question, raw: string | boolean) => {
    const t = q.input.type
    const value = typeof raw === 'boolean' ? raw : t === 'number' ? Number(raw) : t === 'integer' ? Math.round(Number(raw)) : raw
    if (typeof value === 'number' && !Number.isFinite(value)) { toast.error('Type a number.'); return }
    try {
      await answer(q.id, value)
      if (!usePhone.getState().view?.questions.length) await brief(null) // the last answer: the agent carries on
    } catch (e) { toast.error((e as Error).message) }
  }
  return (
    <section className="m-group">
      <h2 className="label">The agent needs {qs.length === 1 ? 'one answer' : `${qs.length} answers`}</h2>
      {qs.map((q) => (
        <div key={q.id} className="m-q">
          <p>{q.text}</p>
          {q.input.type === 'boolean' ? <div className="m-inline"><button className="btn m-btn" onClick={() => void give(q, true)}>Yes</button><button className="btn m-btn" onClick={() => void give(q, false)}>No</button></div>
            : q.input.enum ? <div className="m-inline wrap">{q.input.enum.map((o) => <button key={o} className="btn m-btn" onClick={() => void give(q, o)}>{o}</button>)}</div>
            : <div className="m-inline"><input className="m-input num" inputMode={q.input.type === 'string' ? 'text' : 'decimal'} aria-label={q.text} placeholder={q.input['x-unit'] ?? ''} value={vals[q.id] ?? ''} onChange={(e) => setVals({ ...vals, [q.id]: e.target.value })} />
              <button className="btn m-btn solid" disabled={!vals[q.id]} onClick={() => void give(q, vals[q.id].replace(',', '.'))}>Answer</button></div>}
        </div>
      ))}
      <p className="m-hint">The work starts when the last one is answered.</p>
    </section>
  )
}

function TaskRow({ t, open }: { t: Task; open: (t: Task) => void }) {
  const o = t.outcome
  return <Row status={o ? o.status : 'unknown'} done={t.status === 'done'} title={short(t)} onClick={() => open(t)}
    sub={o ? `${SAID[o.verdict]}${o.value != null ? `, ${num(o.value, t.unit)}` : ''}`
      : t.kind === 'width' && t.threshold != null ? `${t.scan_value != null ? `Scan says ${num(t.scan_value, 'm')}` : 'The scan has no usable width'}, you need ${num(t.threshold, 'm')}` : t.why}
    right={o ? 'Redo' : KIND_WORD[t.kind]} />
}

export function Tasks({ view, sid, open, openTool }: { view: View; sid: string | null; open: (t: Task) => void; openTool: (id: ToolId) => void }) {
  const mine = view.tasks.filter((t) => t.sid === sid)
  const todo = mine.filter((t) => t.status === 'open'), done = mine.filter((t) => t.status === 'done')
  const working = view.busy ? view.plan.find((p) => p.status === 'in_progress')?.text ?? view.results.find((r) => r.status === 'running')?.step ?? 'The agent is working' : null
  if (!sid) return (
    <>
      <section className="m-group">
        <h2 className="label">Start at a building</h2>
        <Row title="Find where I am" sub="Opens the scanned building you are standing in" right="GPS" onClick={() => openTool('where')} />
        <Row title="My home was never scanned" sub="Record a walk-through for a quick safety census" right="Video" onClick={() => openTool('walk')} />
      </section>
      <p className="m-hint">Or open a building on the desktop and tap Phone there: scanning its code brings that workspace here, and everything you capture shows up on it as you go.</p>
      {view.questions.length > 0 ? <Questions qs={view.questions} /> : <Composer sid={null} placeholder="I use a wheelchair and I am looking at a one-bedroom in Houston" cta="Ask" />}
      {working && <p className="m-note m-working" aria-busy="true"><b>Working</b><span>{working}</span></p>}
    </>
  )
  return (
    <>
      {working && <p className="m-note m-working" aria-busy="true"><b>Working</b><span>{working}</span></p>}
      {view.questions.length > 0 && <Questions qs={view.questions} />}
      {GROUPS.map(([kind, label]) => { const g = todo.filter((t) => t.kind === kind); return g.length > 0 && <section key={kind} className="m-group"><h2 className="label">{label} · <span className="num">{g.length}</span></h2>{g.map((t) => <TaskRow key={t.id} t={t} open={open} />)}</section> })}
      {done.length > 0 && <section className="m-group"><h2 className="label">Done · <span className="num">{done.length}</span></h2>{done.map((t) => <TaskRow key={t.id} t={t} open={open} />)}</section>}
      {mine.length === 0 && !view.busy && (
        <section className="m-empty">
          <h2>Nothing to check on site yet</h2>
          <p>Tasks come from what the tools could not settle from the scan: a door's clear width, a possible step, a smoke alarm not seen, the floor's height for a flood, which way a window faces. Ask below, or run door widths, step-free route, the smoke alarm census, flood rehearsal or daylight on the desktop.</p>
        </section>
      )}
      {view.questions.length === 0 && <Composer sid={sid} placeholder="Can a wheelchair get to the bathroom here?" cta={mine.length ? 'Ask for more' : 'Ask'} />}
    </>
  )
}

export function Tools({ sid, open }: { sid: string | null; open: (id: ToolId) => void }) {
  return (
    <section className="m-group">
      <h2 className="label">Instruments</h2>
      {TOOLS.map((t) => <Row key={t.id} title={t.title} sub={t.needsScan && !sid ? `${t.sub}. Needs a building first.` : t.sub} right={t.uses} onClick={() => open(t.id)} />)}
    </section>
  )
}

function CaptureRow({ c }: { c: Capture }) {
  const when = new Date(c.at * 1000).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
  const what = c.task ? 'For a task' : c.tool ? toolTitle(c.tool) : c.note || 'Note'
  return (
    <div className="m-cap">
      {c.kind === 'photo' ? <img src={captureFile(c.id)} alt="" loading="lazy" width={56} height={42} /> : <span className="m-cap-kind hatch">{c.kind === 'reading' ? 'reading' : c.kind}</span>}
      <span className="m-row-text"><b>{what}</b><span>{c.kind}, {when}</span></span>
    </div>
  )
}

export function Results({ view }: { view: View }) {
  const phone = view.results.filter((r) => r.phone), other = view.results.filter((r) => !r.phone)
  if (!view.results.length && !view.captures.length) return <section className="m-empty"><h2>Nothing back yet</h2><p>Results of the instruments and of on-site checks land here, and on the desktop at the same moment.</p></section>
  return (
    <>
      {phone.length > 0 && <section className="m-group"><h2 className="label">From this phone</h2>{phone.map((r) => <ResultCard key={r.run} r={r} />)}</section>}
      {other.length > 0 && <section className="m-group"><h2 className="label">From the scan and the aerial survey</h2>{other.map((r) => <ResultCard key={r.run} r={r} />)}</section>}
      {view.captures.length > 0 && <section className="m-group"><h2 className="label">Captures · <span className="num">{view.captures.length}</span></h2>{view.captures.map((c) => <CaptureRow key={c.id} c={c} />)}</section>}
    </>
  )
}

export function Header({ onPrivacy }: { onPrivacy: () => void }) {
  const view = usePhone((s) => s.view), sid = usePhone((s) => s.sid), paired = usePhone((s) => s.paired), b = usePhone(building)
  return (
    <header className="m-head">
      <div className="m-head-line">
        <b className="m-word">Threshold</b>
        <span className="m-link" data-on={paired || undefined}>{paired ? 'Linked to the desktop' : view ? 'This phone only' : 'Not started'}</span>
        <button className="link" onClick={onPrivacy}>What is sent</button>
      </div>
      {view && view.buildings.length > 1 ? (
        <select className="m-input m-building" aria-label="Building" value={sid ?? ''} onChange={(e) => choose(e.target.value)}>
          {view.buildings.map((x) => <option key={x.sid} value={x.sid}>{x.name}{x.address ? `, ${x.address}` : ''}</option>)}
        </select>
      ) : b ? <p className="m-building"><b>{b.name}</b>{b.address && <span> {b.address.startsWith(b.name) ? b.address.slice(b.name.length).replace(/^,\s*/, '') : b.address}</span>}{!b.walls && <span className="m-flag"> no wall graph</span>}</p> : null}
    </header>
  )
}

export function Privacy({ back }: { back: () => void }) {
  return (
    <div className="m-page">
      <header className="m-top"><button className="m-back" onClick={back} aria-label="Back"><svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><path d="M11 3 5 9l6 6" /></svg></button><div className="m-title"><h1>What this phone sends</h1></div></header>
      <main className="m-body m-prose">
        <p>Threshold is a HackPrinceton Fall 2026 project. This page sends only what you capture, when you tap:</p>
        <ul>
          <li><b>Photos, videos and voice notes</b> you take here. Photos are shrunk on the phone first. Photos and video frames you send for measuring or for the walk-through are read by an AI vision model (Anthropic's Claude).</li>
          <li><b>One location fix</b> when you tap a button that says it uses GPS. The page never tracks you in the background.</li>
          <li><b>Sensor readings</b> you record: tilt, compass heading, and a sound level. The sound level is worked out on the phone; no audio leaves it unless you record a voice note.</li>
          <li><b>What you type or dictate</b> as a brief or a note, and the name of your browser with each capture. Dictation is done by your browser, which on most phones sends the audio to Apple or Google.</li>
        </ul>
        <p>Captures are stored on the project's own server with the workspace they belong to, and are deleted with the rest of the event's data when the event ends. There are no accounts and no advertising. Anyone holding the phone link can add captures to that workspace for eight hours; it cannot read or change anything else.</p>
        <p>To remove this phone's link now: <button className="link" onClick={() => { forget(); back() }}>forget this workspace</button>.</p>
        <p className="m-hint">Questions go to whoever gave you the link.</p>
      </main>
    </div>
  )
}
