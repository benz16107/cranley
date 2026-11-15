import { useCallback, useState } from 'react'
import { toast } from 'sonner'
import { Drawer } from 'vaul'
import { answer, brief, building, captureFile, choose, forget, usePhone, type Building, type Capture, type Question, type Task, type View } from './api.ts'
import { Field, Group, Ico, ResultCard, Row, buzz, num, toolTitle } from './parts.tsx'
import { useDictation } from './sensors.ts'

/* The three tabs: what to do in this building, the instruments, and what came back. */

export type Tab = 'tasks' | 'tools' | 'results'
export type ToolId = 'where' | 'level' | 'sound' | 'window' | 'floor' | 'photo' | 'walk' | 'note'
export const TOOLS: { id: ToolId; title: string; sub: string; needsScan?: boolean }[] = [
  { id: 'where', title: 'Where am I', sub: 'Open the scanned building you are in' },
  { id: 'level', title: 'Slope check', sub: 'A ramp, a threshold or a door frame' },
  { id: 'photo', title: 'Photo measure', sub: 'A width or height from one photo' },
  { id: 'floor', title: 'Floor height', sub: 'Steps at the front door, for the flood result', needsScan: true },
  { id: 'window', title: 'Window check', sub: 'Which way a window faces', needsScan: true },
  { id: 'sound', title: 'Noise level', sub: 'How loud one room is next to another' },
  { id: 'walk', title: 'Walk-through', sub: 'Smoke alarms in a home with no scan' },
  { id: 'note', title: 'Note', sub: 'A photo, clip or voice note' },
]
/* Tasks are listed under what is being settled, so a row only has to say where. */
const GROUPS: [Task['kind'], string, RegExp | null][] = [['floor_height', 'Flood: floor height', null], ['width', 'Doorways: clear width', /^Measure the doorway, /], ['step', 'Steps and thresholds', /^Measure the step:? (at the doorway, )?/],
  ['slope', 'Ramps', /^Check the slope:? (of the ramp )?/], ['alarm', 'Smoke alarms: ceilings to check', /^Photograph the ceiling in /], ['heading', 'Windows: which way they face', /^Point the phone out of the window in /]]
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
    try { await brief(text.trim(), sid); setText(''); buzz(); toast('Sent. Results show up here and on the desktop.') } catch (e) { buzz('error'); toast.error((e as Error).message) } finally { setSending(false) }
  }
  return (
    <div className="m-composer">
      <Field label="What do you need to know about this building?" hint={d.error ?? (d.supported ? undefined : 'To dictate, use the microphone key on the keyboard.')}>
        <textarea className="m-input" rows={3} value={text} onChange={(e) => setText(e.target.value)} placeholder={placeholder} maxLength={1500} />
      </Field>
      <div className="m-inline">
        {d.supported && <button className="btn m-btn" aria-pressed={d.on} onClick={() => (d.on ? d.stop() : d.start())}>{d.on ? 'Stop listening' : 'Speak it'}</button>}
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
    <Group title={`The agent needs ${qs.length === 1 ? 'one answer' : `${qs.length} answers`}`} pad foot="The work starts when the last one is answered.">
      {qs.map((q) => (
        <div key={q.id} className="m-q">
          <p>{q.text}</p>
          {q.input.type === 'boolean' ? <div className="m-inline"><button className="btn m-btn" onClick={() => void give(q, true)}>Yes</button><button className="btn m-btn" onClick={() => void give(q, false)}>No</button></div>
            : q.input.enum ? <div className="m-inline wrap">{q.input.enum.map((o) => <button key={o} className="btn m-btn" onClick={() => void give(q, o)}>{o}</button>)}</div>
            : <div className="m-inline"><input className="m-input num" inputMode={q.input.type === 'string' ? 'text' : 'decimal'} aria-label={q.text} placeholder={q.input['x-unit'] ?? ''} value={vals[q.id] ?? ''} onChange={(e) => setVals({ ...vals, [q.id]: e.target.value })} />
              <button className="btn m-btn solid" disabled={!vals[q.id]} onClick={() => void give(q, vals[q.id].replace(',', '.'))}>Answer</button></div>}
        </div>
      ))}
    </Group>
  )
}

function TaskRow({ t, open }: { t: Task; open: (t: Task) => void }) {
  const o = t.outcome
  return <Row status={o ? o.status : 'unknown'} done={t.status === 'done'} title={short(t)} onClick={() => open(t)}
    sub={o ? `${SAID[o.verdict]}${o.value != null ? `, ${num(o.value, t.unit)}` : ''}`
      : t.kind === 'width' && t.threshold != null ? `${t.scan_value != null ? `Scan ${num(t.scan_value, 'm')}` : 'No width from the scan'}, need ${num(t.threshold, 'm')}` : t.why} />
}
const Working = ({ text }: { text: string }) => <p className="m-working" aria-busy="true"><i aria-hidden="true" /><span>{text}</span></p>

export function Tasks({ view, sid, open, openTool }: { view: View; sid: string | null; open: (t: Task) => void; openTool: (id: ToolId) => void }) {
  const mine = view.tasks.filter((t) => t.sid === sid)
  const todo = mine.filter((t) => t.status === 'open'), done = mine.filter((t) => t.status === 'done')
  const working = view.busy ? view.plan.find((p) => p.status === 'in_progress')?.text ?? view.results.find((r) => r.status === 'running')?.step ?? 'The agent is working' : null
  if (!sid) return (
    <>
      <Group title="Start at a building" foot="Or choose Continue on a phone on the desktop and scan its code. What you capture then shows up there as you go.">
        <Row title="Find where I am" sub="Opens the scanned building you are in" onClick={() => openTool('where')} />
        <Row title="My home was never scanned" sub="Record a walk-through for a quick safety census" onClick={() => openTool('walk')} />
      </Group>
      {working && <Working text={working} />}
      {view.questions.length > 0 ? <Questions qs={view.questions} /> : <Composer sid={null} placeholder="I use a wheelchair and I am looking at a one-bedroom in Houston" cta="Ask" />}
    </>
  )
  return (
    <>
      {working && <Working text={working} />}
      {view.questions.length > 0 && <Questions qs={view.questions} />}
      {GROUPS.map(([kind, label]) => { const g = todo.filter((t) => t.kind === kind); return g.length > 0 && <Group key={kind} title={label} count={g.length}>{g.map((t) => <TaskRow key={t.id} t={t} open={open} />)}</Group> })}
      {done.length > 0 && <Group title="Done" count={done.length}>{done.map((t) => <TaskRow key={t.id} t={t} open={open} />)}</Group>}
      {mine.length === 0 && !view.busy && (
        <section className="m-empty">
          <h2>Nothing to check on site yet</h2>
          <p>A task appears when a tool cannot settle something from the scan, like a door's clear width or a smoke alarm it did not see. Ask below, or run a tool on the desktop.</p>
        </section>
      )}
      {view.questions.length === 0 && <Composer sid={sid} placeholder="Can a wheelchair get to the bathroom here?" cta={mine.length ? 'Ask for more' : 'Ask'} />}
    </>
  )
}

export function Tools({ sid, open }: { sid: string | null; open: (id: ToolId) => void }) {
  return (
    <Group title="Instruments">
      {TOOLS.map((t) => <Row key={t.id} title={t.title} sub={t.needsScan && !sid ? `${t.sub}. Needs a building first.` : t.sub} onClick={() => open(t.id)} />)}
    </Group>
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
  if (!view.results.length && !view.captures.length) return <section className="m-empty"><h2>Nothing back yet</h2><p>Results from this phone and from the desktop appear here.</p></section>
  return (
    <>
      {phone.length > 0 && <section className="m-group"><h2 className="m-group-h">From this phone</h2>{phone.map((r) => <ResultCard key={r.run} r={r} />)}</section>}
      {other.length > 0 && <section className="m-group"><h2 className="m-group-h">From the scan and the aerial survey</h2>{other.map((r) => <ResultCard key={r.run} r={r} />)}</section>}
      {view.captures.length > 0 && <Group title="Captures" count={view.captures.length}>{view.captures.map((c) => <CaptureRow key={c.id} c={c} />)}</Group>}
    </>
  )
}

/** The address without the part the name already says (names are often the address plus the unit). */
const rest = (b: Building) => (b.address?.startsWith(b.name) ? b.address.slice(b.name.length).replace(/^,\s*/, '') : b.address ?? '')

const TITLE: Record<Tab, string> = { tasks: 'Tasks', tools: 'Tools', results: 'Results' }

/** The slim bar that stays: the name, whether the desktop is linked, and what this phone sends. */
export function Header({ onPrivacy }: { onPrivacy: () => void }) {
  const view = usePhone((s) => s.view), paired = usePhone((s) => s.paired), offline = usePhone((s) => s.state === 'offline')
  return (
    <header className="m-head">
      <b className="m-word">Cranley</b>
      {(offline || view) && <span className="m-link" data-on={(paired && !offline) || undefined} data-off={offline || undefined}>{offline ? 'Offline' : paired ? 'Linked to the desktop' : 'This phone only'}</span>}
      <button className="m-icon" onClick={onPrivacy} aria-label="What is sent"><Ico name="info" /></button>
    </header>
  )
}

/** The tab's large title, and the building it is about. */
export function Hero({ tab }: { tab: Tab }) {
  const view = usePhone((s) => s.view), sid = usePhone((s) => s.sid), b = usePhone(building)
  return (
    <div className="m-title">
      <h1>{TITLE[tab]}</h1>
      {view && view.buildings.length > 1 ? (
        <select className="m-building" aria-label="Building" value={sid ?? ''} onChange={(e) => choose(e.target.value)}>
          {view.buildings.map((x) => <option key={x.sid} value={x.sid}>{x.name}{rest(x) && `, ${rest(x)}`}</option>)}
        </select>
      ) : b ? <p className="m-building">{b.name}{rest(b) && `, ${rest(b)}`}{!b.walls && <span className="m-flag"> · no wall graph</span>}</p> : null}
    </div>
  )
}

/** What the phone sends, as a sheet over whatever the person was doing. */
export function Privacy({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  return (
    <Drawer.Root open={open} onOpenChange={onOpenChange}>
      <Drawer.Portal>
        <Drawer.Overlay className="m-scrim" />
        <Drawer.Content className="m-sheet" aria-describedby={undefined}>
          <Drawer.Handle className="m-grip" />
          <header><Drawer.Title>What this phone sends</Drawer.Title><Drawer.Close className="m-done">Done</Drawer.Close></header>
          <div className="m-prose">
            <p>Cranley is a HackPrinceton Fall 2026 project. This page sends only what you capture, when you tap:</p>
            <ul>
              <li><b>Photos, videos and voice notes</b> you take here. Photos are shrunk on the phone first. Photos and video frames you send for measuring or for the walk-through are read by an AI vision model (Anthropic's Claude).</li>
              <li><b>One location fix</b> when you tap a button that says it uses GPS. The page never tracks you in the background.</li>
              <li><b>Sensor readings</b> you record: tilt, compass heading, and a sound level. The sound level is worked out on the phone; no audio leaves it unless you record a voice note.</li>
              <li><b>What you type or dictate</b> as a brief or a note, and the name of your browser with each capture. Dictation is done by your browser, which on most phones sends the audio to Apple or Google.</li>
            </ul>
            <p>Captures are stored on the project's own server with the workspace they belong to, and are deleted with the rest of the event's data when the event ends. There are no accounts and no advertising. Anyone holding the phone link can add captures to that workspace for eight hours; it cannot read or change anything else.</p>
            <p>Questions go to whoever gave you the link.</p>
            <button className="btn m-btn" onClick={() => { forget(); onOpenChange(false) }}>Forget this workspace</button>
          </div>
        </Drawer.Content>
      </Drawer.Portal>
    </Drawer.Root>
  )
}
