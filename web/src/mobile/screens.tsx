import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import { building, captureFile, locate, place, runTool, send, setUnit, shrink, usePhone, type Action, type Meta, type Outcome, type Place, type Points, type Reply, type Task } from './api.ts'
import { compassPoint, fmtLength, toMetres, type Fix } from './dsp.ts'
import { Camera, Field, OutcomeCard, Page, PointsEditor, Problem, Progress, ResultCard, RoomPick, Row, Seg, SensorGate, num, toolTitle } from './parts.tsx'
import { getFix, recorderType, useHeading, useSoundMeter, useTilt } from './sensors.ts'

/* The capture screens. Each one takes what its sensor or the camera gives, sends one capture, and shows what the
   server made of it. A screen opened from a task carries the task; opened from Tools it stands alone. */

type Props = { task?: Task; back: () => void }
const fail = (e: unknown) => toast.error(e instanceof Error ? e.message : 'That did not work.')
const useSid = () => usePhone((s) => s.sid)
// a selector must hand back the same object for the same state, or the store re-renders without end
const NONE: never[] = []
const useRooms = () => usePhone((s) => building(s)?.rooms ?? NONE)

/** Send a capture and keep its reply; `busy` is the upload fraction while it goes (null when idle). */
function useSend() {
  const [busy, setBusy] = useState<number | null>(null)
  const [reply, setReply] = useState<Reply | null>(null)
  const go = async (meta: Meta, file?: Blob | null) => {
    setBusy(0); setReply(null)
    try { const r = await send(meta, file, (f) => setBusy(f)); setReply(r); return r } catch (e) { fail(e); return null } finally { setBusy(null) }
  }
  return { busy, reply, go, clear: () => setReply(null) }
}
/** What the capture just sent settled; before one is sent, what an earlier visit to this task settled. */
function Sent({ reply, task }: { reply: Reply | null; task?: Task }) {
  if (!reply) return task?.outcome ? <OutcomeCard outcome={task.outcome} task={task} /> : null
  if (reply.outcome && task) return <OutcomeCard outcome={reply.outcome} task={task} />
  if (reply.problem) return <Problem text={reply.problem} />
  const r = reply.run ? reply.view.results.find((x) => x.run === reply.run) : null
  return r ? <ResultCard r={r} open /> : <p className="m-note">Saved. It is on the desktop now.</p>
}
function TaskHead({ task }: { task: Task }) {
  return (
    <section className="m-brief">
      <p>{task.how}</p>
      <dl className="m-kv">
        {task.scan_value != null && <div><dt>{task.kind === 'heading' ? 'Direct sun by the scan' : task.kind === 'floor_height' ? 'Flood result uses' : task.kind === 'width' ? 'Clear, by the scan' : 'Scan says'}</dt><dd className="num">{num(task.scan_value, task.unit)}</dd></div>}
        {task.threshold != null && task.unit === 'm' && <div><dt>{task.kind === 'step' ? 'Flat up to' : 'You need'}</dt><dd className="num">{num(task.threshold, task.unit)}</dd></div>}
      </dl>
      <p className="m-why">{task.why}{task.standard ? ` ${task.standard}.` : ''}</p>
    </section>
  )
}

const REFS = [['letter', 'Letter sheet'], ['a4', 'A4 sheet'], ['door', 'The door'], ['card', 'Bank card']] as const
type Ref = (typeof REFS)[number][0]
const REF_HELP: Record<Ref, string> = {
  letter: 'Tape a sheet of letter paper in the middle of what you are measuring and stand square on to it. Good to about 2 in (5 cm) on a doorway once the points are right: enough to tell 30 in from 36, not 31 from 32.',
  a4: 'Tape a sheet of A4 in the middle of what you are measuring and stand square on to it. Good to about 5 cm on a doorway once the points are right.',
  door: 'The door leaf itself is the reference: 80 in tall, and you give its width. The most exact of these, for anything in the door\'s own plane.',
  card: 'A bank card is only large enough for small things close up: a step, a threshold. Fill the frame with it.',
}
/** A photo with a reference in it, its points shown for correction, measured by the server. */
function PhotoMeasurePane({ meta, what, onReply, task }: { meta: Omit<Meta, 'kind'>; what?: string; onReply?: (r: Reply) => void; task?: Task }) {
  const [ref, setRef] = useState<Ref>('letter')
  const [doorIn, setDoorIn] = useState('30')
  const [photo, setPhoto] = useState<string | null>(null)
  const [pts, setPts] = useState<Points | null>(null)
  const [moved, setMoved] = useState(false)
  const s = useSend()
  const values = () => ({ reference: ref, ...(what ? { what } : {}), ...(ref === 'door' ? { door_width_m: (Number(doorIn) || 30) * 0.0254 } : {}) })
  const took = async (f: File) => {
    const r = await s.go({ ...meta, kind: 'photo', values: values() }, await shrink(f))
    if (!r) return
    setPhoto(r.capture.id); setPts(r.points ?? r.outcome?.points ?? null); setMoved(false); onReply?.(r)
  }
  const remeasure = async () => {
    const r = await s.go({ ...meta, kind: 'reading', values: { ...values(), photo, points: pts } })
    if (r) { setMoved(false); onReply?.(r) }
  }
  const place0 = () => { setPts({ corners: [[0.4, 0.4], [0.6, 0.4], [0.6, 0.55], [0.4, 0.55]], a: [0.2, 0.5], b: [0.8, 0.5] }); setMoved(true) }
  return (
    <>
      <Seg label="Reference in the photo" options={REFS} value={ref} onChange={setRef} />
      <p className="m-hint">{REF_HELP[ref]}</p>
      {ref === 'door' && <Field label="Door leaf width, inches"><input className="m-input num" inputMode="decimal" value={doorIn} onChange={(e) => setDoorIn(e.target.value)} /></Field>}
      {photo && pts && <PointsEditor src={captureFile(photo)} points={pts} onChange={(p) => { setPts(p); setMoved(true) }} />}
      {photo && !pts && <img className="m-photo" src={captureFile(photo)} alt="Your photo" />}
      {s.busy != null && <Progress value={s.busy < 1 ? s.busy : null} label={s.busy < 1 ? 'Sending the photo' : 'Finding the reference and measuring'} />}
      <Sent reply={s.reply} task={task} />
      <div className="m-inline">
        <Camera label={photo ? 'Retake' : 'Take the photo'} onFile={took} quiet={!!photo} />
        {photo && !pts && <button className="btn m-btn" onClick={place0}>Place the points by hand</button>}
        {photo && pts && moved && <button className="btn m-btn solid" disabled={s.busy != null} onClick={remeasure}>Measure with these points</button>}
      </div>
      {photo && pts && <p className="m-hint">Squares are the reference's corners, A and B the two ends. Drag any that are off, then measure again.</p>}
    </>
  )
}

/** Width of a doorway or height of a step: a tape measure typed in, or a photo with a reference. */
export function Measure({ task, back }: Props & { task: Task }) {
  const [mode, setMode] = useState<'tape' | 'photo'>('tape')
  const unit = usePhone((st) => st.unit)
  const [text, setText] = useState('')
  const s = useSend()
  const m = toMetres(text, unit)
  const plausible = m != null && (task.kind === 'step' ? m <= 0.6 : m >= 0.3 && m <= 3)
  return (
    <Page title={task.title} sub={`From ${task.tools.map(toolTitle).join(', ')}`} onBack={back}
      actions={mode === 'tape' && <button className="btn m-btn solid wide" disabled={!plausible || s.busy != null} onClick={() => void s.go({ kind: 'reading', task: task.id, scan: task.sid, opening: task.opening, values: { value_m: m } })}>Save {m != null ? fmtLength(m, unit) : 'the measurement'}</button>}>
      <TaskHead task={task} />
      <Seg label="How to measure" options={[['tape', 'Tape measure'], ['photo', 'Photo']] as const} value={mode} onChange={setMode} />
      {mode === 'tape' ? (
        <>
          <div className="m-inline">
            <Field label={task.kind === 'step' ? 'Height' : 'Clear width'}><input className="m-input num big" inputMode="decimal" autoComplete="off" placeholder={unit === 'in' ? '32.5' : '82.5'} value={text} onChange={(e) => setText(e.target.value)} aria-invalid={!!text && !plausible} /></Field>
            <Seg label="Unit" options={[['in', 'in'], ['cm', 'cm']] as const} value={unit} onChange={(u) => { setUnit(u); setText('') }} />
          </div>
          {text && !plausible && <p className="m-hint warn">{m == null ? 'Type a number.' : 'That is outside what a doorway or a step can be. Check the unit.'}</p>}
          {s.busy != null && <Progress value={null} label="Saving" />}
          <Sent reply={s.reply} task={task} />
        </>
      ) : <PhotoMeasurePane meta={{ task: task.id, scan: task.sid, opening: task.opening }} task={task} />}
    </Page>
  )
}

/** Any length from a photo, outside a task. */
export function PhotoMeasure({ back }: Props) {
  const sid = useSid(), rooms = useRooms()
  const [room, setRoom] = useState<string | null>(null)
  const [what, setWhat] = useState('the clear width of the doorway')
  return (
    <Page title="Photo measure" sub="A width or a height from one photo" onBack={back}>
      <Field label="What to measure" hint="Say it as you would to a person holding the tape."><input className="m-input" value={what} onChange={(e) => setWhat(e.target.value)} maxLength={180} /></Field>
      {rooms.length > 0 && <RoomPick rooms={rooms} value={room} onChange={setRoom} />}
      <PhotoMeasurePane meta={{ tool: 'photo_measure', scan: sid, room }} what={what} />
    </Page>
  )
}

/** Is there a smoke alarm? The person's word settles it; a photo is the proof, and can settle "there is one". */
export function Alarm({ task, back }: Props & { task: Task }) {
  const s = useSend()
  const base = { task: task.id, scan: task.sid, room: task.room }
  const [photo, setPhoto] = useState<Blob | null>(null)
  const say = (answer: 'present' | 'absent') => void s.go({ ...base, kind: photo ? 'photo' : 'reading', values: { answer } }, photo)
  return (
    <Page title={task.title} sub="Smoke alarm census" onBack={back}
      actions={<><button className="btn m-btn wide" disabled={s.busy != null} onClick={() => say('absent')}>No alarm here</button><button className="btn m-btn solid wide" disabled={s.busy != null} onClick={() => say('present')}>There is one</button></>}>
      <TaskHead task={task} />
      <div className="m-inline">
        <Camera label={photo ? 'Retake the ceiling' : 'Photograph the ceiling'} quiet onFile={async (f) => { const b = await shrink(f); setPhoto(b); toast('Photo ready. Now say what you see, or send it alone.') }} />
        {photo && <button className="btn m-btn" disabled={s.busy != null} onClick={() => void s.go({ ...base, kind: 'photo' }, photo)}>Let the photo decide</button>}
      </div>
      {photo && <p className="m-hint">Your answer goes with the photo as its proof. A photo alone only counts when an alarm is plainly in it.</p>}
      {s.busy != null && <Progress value={s.busy < 1 ? s.busy : null} label={s.busy < 1 ? 'Sending' : 'Reading the photo'} />}
      <Sent reply={s.reply} task={task} />
    </Page>
  )
}

const LEVEL_MODES = [['ramp', 'Ramp'], ['threshold', 'Threshold'], ['plumb', 'Door frame']] as const
type LevelMode = (typeof LEVEL_MODES)[number][0]
const LEVEL_HOW: Record<LevelMode, [string, string]> = {
  ramp: ['Lay the phone on the ramp, on its back, top edge pointing up the slope.', 'Turn it end for end, top edge pointing down the slope, on the same spot.'],
  threshold: ['Lay the phone on the sloped face of the threshold, top edge pointing up it.', 'Turn it end for end on the same spot.'],
  plumb: ['Hold the phone upright, one long edge flat against the door frame, screen facing you.', 'Turn it over so the other long edge is against the same spot.'],
}
/** The phone as a level. Two readings end for end cancel the sensor's offset and the camera bump. */
export function Level({ task, back }: Props) {
  const sid = useSid()
  const t = useTilt(), s = useSend()
  const [mode, setMode] = useState<LevelMode>('ramp')
  const [first, setFirst] = useState<{ long: number; short: number; spread: number } | null>(null)
  const [reading, setReading] = useState(false)
  const axis = (v: { long: number; short: number }) => (mode === 'plumb' ? v.short : v.long)
  const read = async () => {
    setReading(true)
    const r = await t.sample(2000)
    setReading(false)
    if (!r) { toast.error('No readings came from the tilt sensor. Keep the screen on and try again.'); return }
    if (r.spread > 1.5) { toast.error('The phone moved. Let it lie still for two seconds.'); return }
    // held up, not lying on the surface: two such readings cancel end for end and would pass as level (a steep bevel is 27°)
    const off = Math.max(Math.abs(r.long), Math.abs(r.short))
    if (mode !== 'plumb' && off > 45) { toast.error(`The phone is ${off.toFixed(0)}° from flat. Lay it on its back on the surface, then read.`); return }
    if (!first) { setFirst(r); return }
    await submit(first, r)
  }
  const submit = (a: { long: number; short: number; spread: number }, b: { long: number; short: number; spread: number } | null) => s.go({
    kind: 'reading', ...(task ? { task: task.id } : { tool: 'slope_check' }), scan: task?.sid ?? sid, opening: task?.opening,
    tilt: { pitch_deg: a.long, roll_deg: a.short },
    values: { mode, reading_deg: +axis(a).toFixed(3), spread_deg: +Math.max(a.spread, b?.spread ?? 0).toFixed(3), ...(b ? { flipped_deg: +axis(b).toFixed(3) } : {}),
      ...(mode === 'ramp' ? { cross_deg: +a.short.toFixed(3), ...(b ? { cross_flipped_deg: +b.short.toFixed(3) } : {}) } : {}) } }).then(() => setFirst(null))
  const live = t.now ? axis(t.now) : null
  return (
    <Page title={task?.title ?? 'Slope check'} sub="The phone as a level" onBack={back}
      actions={t.state === 'on' && <>
        {first && <button className="btn m-btn" disabled={reading || s.busy != null} onClick={() => void submit(first, null)}>Use one reading</button>}
        <button className="btn m-btn solid wide" disabled={reading || s.busy != null} onClick={() => void read()}>{reading ? 'Hold still' : first ? 'Read the second way' : 'Read'}</button></>}>
      {task && <TaskHead task={task} />}
      {!task && <Seg label="What is being read" options={LEVEL_MODES} value={mode} onChange={(m) => { setMode(m); setFirst(null) }} />}
      <ol className="m-steps">
        <li aria-current={!first || undefined} data-done={!!first || undefined}><span>{LEVEL_HOW[mode][0]}{first && <b className="num"> Read {Math.abs(axis(first)).toFixed(1)}°.</b>}</span></li>
        <li aria-current={!!first || undefined}><span>{LEVEL_HOW[mode][1]}</span></li>
      </ol>
      <SensorGate state={t.state} allow={() => void t.allow()} name="tilt sensor" fallback="Use a spirit level and a tape instead: rise over run is the slope." />
      {t.state === 'on' && live != null && (
        <div className="m-meter" aria-live="off">
          <div className="m-bubble"><i style={{ translate: `${Math.max(-46, Math.min(46, live * 4.6))}% 0` }} /></div>
          <dl className="m-kv"><div><dt>Tilt now</dt><dd className="num">{Math.abs(live).toFixed(1)}°</dd></div><div><dt>As a slope</dt><dd className="num">{(Math.tan(Math.abs(live) * Math.PI / 180) * 100).toFixed(1)} %</dd></div>
            {mode === 'ramp' && <div><dt>Limit</dt><dd className="num">8.33 % (1:12)</dd></div>}</dl>
        </div>
      )}
      {s.busy != null && <Progress value={null} label="Working it out" />}
      <Sent reply={s.reply} task={task} />
    </Page>
  )
}

const SECONDS = 15
/** An A-weighted level per room. One fixed interval each, so rooms compare. */
export function Sound({ back }: Props) {
  const sid = useSid(), rooms = useRooms()
  const meter = useSoundMeter(), s = useSend()
  const [room, setRoom] = useState<string | null>(null)
  const [label, setLabel] = useState('')
  const [left, setLeft] = useState<number | null>(null)
  const captures = usePhone((st) => st.view?.captures ?? NONE)
  const taken = captures.filter((c) => c.tool === 'noise_level' && c.scan === (sid ?? undefined))
  const timer = useRef<ReturnType<typeof setInterval> | undefined>(undefined)
  useEffect(() => () => clearInterval(timer.current), [])
  const start = async () => {
    try { await meter.start() } catch (e) { fail(e); return }
    setLeft(SECONDS)
    timer.current = setInterval(() => setLeft((n) => {
      if (n == null || n > 1) return n == null ? n : n - 1
      clearInterval(timer.current)
      const r = meter.stop()
      // a muted, busy or simulated microphone sends exact zeros; no real room reads under 5 dBA
      if (r && r.lmax_dba < 5) toast.error('The microphone sent only silence, so nothing was measured. Check that no other app is using it, then try again.')
      else if (r) void s.go({ kind: 'reading', tool: 'noise_level', scan: sid, room, values: { ...r, ...(room ? { room } : { label: label.trim() || 'This room' }) } })
      return null
    }), 1000)
  }
  const named = (id: string | undefined) => rooms.find((r) => r.id === id)?.label
  return (
    <Page title="Noise level" sub="Uncalibrated: compare rooms, do not quote the number" onBack={back}
      actions={<button className="btn m-btn solid wide" disabled={left != null || s.busy != null} onClick={() => void start()}>{left != null ? `Listening, ${left} s left` : `Measure ${SECONDS} seconds here`}</button>}>
      <p className="m-hint">Stand in the middle of the room, hold the phone away from you, and stay quiet. The level is good to about 10 dB; the difference between two rooms measured this way is good to about 3.</p>
      {rooms.length > 0 ? <RoomPick rooms={rooms} value={room} onChange={setRoom} /> : <Field label="Where"><input className="m-input" value={label} onChange={(e) => setLabel(e.target.value)} placeholder="Front bedroom" maxLength={60} /></Field>}
      {left != null && <div className="m-meter"><div className="m-level"><i style={{ scale: `${Math.max(0.02, Math.min(1, ((meter.live ?? 20) - 20) / 70))} 1` }} /></div><dl className="m-kv"><div><dt>Now</dt><dd className="num">{meter.live != null ? `${meter.live.toFixed(0)} dBA` : 'settling'}</dd></div></dl></div>}
      {s.busy != null && <Progress value={null} label="Saving" />}
      <Sent reply={s.reply} />
      {taken.length > 0 && <section><h2 className="label">Measured this visit</h2>{taken.map((c) => { const v = (c.values ?? {}) as { leq_dba?: number; label?: string }
        return <Row key={c.id} title={named(c.room) ?? v.label ?? 'A room'} right={v.leq_dba != null ? `${v.leq_dba.toFixed(0)} dBA` : ''} /> })}</section>}
    </Page>
  )
}

const DIRS = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'] as const
/** Which way a window faces, from the compass, or picked by hand where the phone has none. */
export function Window({ task, back }: Props) {
  const sid = useSid(), rooms = useRooms()
  const h = useHeading(), s = useSend()
  const [room, setRoom] = useState<string | null>(task?.room ?? null)
  const [reading, setReading] = useState(false)
  const base = { ...(task ? { task: task.id } : { tool: 'window_check' }), scan: task?.sid ?? sid, room }
  const record = async () => {
    setReading(true)
    const r = await h.sample(2000)
    setReading(false)
    if (!r) { toast.error('No heading came from the compass.'); return }
    if (r.spread > 12) { toast.error('The compass was swinging. Step away from metal and hold still.'); return }
    const fix = await getFix(2500).catch(() => null)
    await s.go({ ...base, kind: 'reading', fix, heading_deg: +r.heading.toFixed(1), heading_accuracy_deg: Math.max(h.now?.accuracy ?? 0, +r.spread.toFixed(1)) || null, values: {} })
  }
  const byHand = (i: number) => void s.go({ ...base, kind: 'reading', heading_deg: i * 45, heading_accuracy_deg: 22.5, values: { magnetic: false } })
  const ok = room != null && (task != null || sid != null)
  return (
    <Page title={task?.title ?? 'Window check'} sub="Which way the window faces" onBack={back}
      actions={h.state === 'on' && <button className="btn m-btn solid wide" disabled={!ok || reading || s.busy != null} onClick={() => void record()}>{reading ? 'Hold still' : 'Record this direction'}</button>}>
      {task ? <TaskHead task={task} /> : <p className="m-hint">Stand at the window. Hold the phone flat, like a tray, with its top edge pointing straight out through the glass.</p>}
      {!task && (rooms.length > 0 ? <RoomPick rooms={rooms} value={room} onChange={setRoom} /> : <Problem text="Pick a building first: a window check compares with a scan's rooms." />)}
      {!task && rooms.length > 0 && room == null && <p className="m-hint">Pick the room the window is in first.</p>}
      <SensorGate state={h.state} allow={() => void h.allow()} name="compass" fallback="Pick the direction the window faces below; a map on your phone will tell you." />
      {h.state === 'on' && h.now && (
        <div className="m-meter"><div className="m-dial" aria-hidden="true"><i style={{ rotate: `${-h.now.heading}deg` }}>N</i></div>
          <dl className="m-kv"><div><dt>Top edge points</dt><dd className="num">{Math.round(h.now.heading) % 360}° {compassPoint(h.now.heading)}</dd></div>{h.now.accuracy != null && <div><dt>Phone says, give or take</dt><dd className="num">{h.now.accuracy.toFixed(0)}°</dd></div>}</dl>
          {!h.now.flat && <p className="m-hint warn">Hold it flat, like a tray.</p>}</div>
      )}
      {(h.state === 'missing' || h.state === 'denied') && <div className="m-compass" role="group" aria-label="Direction the window faces">{DIRS.map((d, i) => <button key={d} className="btn m-btn" disabled={!ok || s.busy != null} onClick={() => byHand(i)}>{d}</button>)}</div>}
      {s.busy != null && <Progress value={null} label="Comparing with the scan" />}
      <Sent reply={s.reply} task={task} />
    </Page>
  )
}

function FixRow({ label, fix, onTake, busy }: { label: string; fix: Fix | null; onTake: () => void; busy: boolean }) {
  return (
    <div className="m-fix">
      <div><b>{label}</b>{fix ? <span className="num">± {fix.accuracy_m?.toFixed(0) ?? '?'} m{fix.altitude_m != null ? `, altitude ${fix.altitude_m.toFixed(1)} m ± ${fix.altitude_accuracy_m?.toFixed(0) ?? '?'}` : ', no altitude from this phone'}</span> : <span>Not taken</span>}</div>
      <button className="btn m-btn" disabled={busy} onClick={onTake}>{busy ? 'Fixing' : fix ? 'Again' : 'Take a fix'}</button>
    </div>
  )
}
/** The flood tool's weak number. Steps counted at the door do most of the work; the fixes add the ground's slope. */
export function FloorHeight({ task, back }: Props) {
  const sid = useSid(), s = useSend()
  const [steps, setSteps] = useState<number | null>(null)
  const [riser, setRiser] = useState('')
  const unit = usePhone((st) => st.unit)
  const [door, setDoor] = useState<Fix | null>(null)
  const [street, setStreet] = useState<Fix | null>(null)
  const [fixing, setFixing] = useState<'door' | 'street' | null>(null)
  const [photo, setPhoto] = useState<Blob | null>(null)
  const take = async (which: 'door' | 'street') => {
    setFixing(which)
    try { const f = await getFix(8000); if (which === 'door') setDoor(f); else setStreet(f) } catch (e) { fail(e) } finally { setFixing(null) }
  }
  const riserM = toMetres(riser, unit)
  const scan = task?.sid ?? sid
  const go = () => void s.go({ kind: photo ? 'photo' : 'reading', ...(task ? { task: task.id } : { tool: 'floor_height' }), scan, fix: door,
    values: { ...(steps != null ? { steps } : {}), ...(riserM ? { riser_m: riserM } : {}), ...(door ? { door } : {}), ...(street ? { street } : {}) } }, photo)
  return (
    <Page title={task ? 'Floor height at the front door' : 'Floor height'} sub="Narrows the flood result" onBack={back}
      actions={<button className="btn m-btn solid wide" disabled={!scan || (steps == null && !(door && street)) || s.busy != null} onClick={go}>Work out the floor height</button>}>
      {task ? <TaskHead task={task} /> : <p className="m-hint">How far the floor sits above the ground outside decides how much water comes in. Count the steps at the front door; the rest helps.</p>}
      {!scan && <Problem text="Pick a building first: this narrows a scan's flood result." />}
      <section className="m-group">
        <h2 className="label">1. Steps up to the door</h2>
        <div className="m-stepper"><button className="btn m-btn" aria-label="One fewer" disabled={!steps} onClick={() => setSteps((n) => Math.max(0, (n ?? 0) - 1))}>−</button>
          <output className="num">{steps == null ? 'count them' : steps === 0 ? 'none, level with the ground' : `${steps} step${steps > 1 ? 's' : ''}`}</output>
          <button className="btn m-btn" aria-label="One more" disabled={steps === 12} onClick={() => setSteps((n) => (n == null ? 0 : n + 1))}>+</button></div>
        {!!steps && <div className="m-inline"><Field label="One step's height, if you measure it" hint="Without it a typical 7 in step is assumed, with a wider error."><input className="m-input num" inputMode="decimal" value={riser} onChange={(e) => setRiser(e.target.value)} placeholder={unit === 'in' ? '7' : '18'} /></Field><Seg label="Unit" options={[['in', 'in'], ['cm', 'cm']] as const} value={unit} onChange={setUnit} /></div>}
      </section>
      <section className="m-group">
        <h2 className="label">2. Where the ground slopes (optional)</h2>
        <FixRow label="At the front door" fix={door} busy={fixing === 'door'} onTake={() => void take('door')} />
        <FixRow label="At the street or yard edge" fix={street} busy={fixing === 'street'} onTake={() => void take('street')} />
        <p className="m-hint">The two fixes read the ground's rise from the aerial elevation model. GPS altitude itself is good to metres and is shown, not relied on.</p>
      </section>
      <section className="m-group">
        <h2 className="label">3. The threshold (optional)</h2>
        <Camera label={photo ? 'Retake the threshold' : 'Photograph the threshold and steps'} quiet onFile={async (f) => setPhoto(await shrink(f))} />
        {photo && <p className="m-hint">Photo ready. It goes with the result as evidence.</p>}
      </section>
      {s.busy != null && <Progress value={s.busy < 1 && photo ? s.busy : null} label="Running the flood before and after" />}
      <Sent reply={s.reply} task={task} />
    </Page>
  )
}

const MAX_CLIP = 45
/** A short video walking through a home with no scan. Recorded here where the browser can, else by the camera app. */
export function Walkthrough({ back }: Props) {
  const s = useSend()
  const type = recorderType('video')
  const [rec, setRec] = useState<{ stop: () => void } | null>(null)
  const [secs, setSecs] = useState(0)
  const preview = useRef<HTMLVideoElement>(null)
  const upload = async (blob: Blob) => { const fix = await getFix(2500).catch(() => null); await s.go({ kind: 'video', tool: 'walkthrough', fix, values: {} }, blob) }
  const start = async () => {
    let stream: MediaStream
    try { stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' }, width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false }) }
    catch (e) { toast.error((e as Error).name === 'NotAllowedError' ? 'The camera is switched off for this page. Use "Record or choose a video" below.' : 'No camera answered.'); return }
    if (preview.current) { preview.current.srcObject = stream; void preview.current.play().catch(() => {}) }
    const chunks: Blob[] = [], r = new MediaRecorder(stream, { mimeType: type!, videoBitsPerSecond: 2_500_000 })
    r.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data) }
    const tick = setInterval(() => setSecs((n) => { if (n + 1 >= MAX_CLIP) r.stop(); return n + 1 }), 1000)
    r.onstop = () => { clearInterval(tick); stream.getTracks().forEach((t) => t.stop()); setRec(null); setSecs(0); if (!chunks.length) { toast.error('Nothing was recorded. Try again, or use "Record or choose a video".'); return } void upload(new Blob(chunks, { type: type!.split(';')[0] })) }
    r.start(1000)
    setRec({ stop: () => r.state !== 'inactive' && r.stop() })
  }
  useEffect(() => () => rec?.stop(), [rec])
  return (
    <Page title="Walk-through" sub="A safety census of a home with no scan" onBack={back}
      actions={type && s.busy == null && (rec ? <button className="btn m-btn solid wide" onClick={rec.stop}>Stop and send, {secs} of {MAX_CLIP} s</button> : <button className="btn m-btn solid wide" onClick={() => void start()}>Record</button>)}>
      <p className="m-hint">Walk slowly through each room for up to {MAX_CLIP} seconds. Tilt up to take in the ceiling in bedrooms and hallways: that is where smoke alarms are. Eight frames are read; a room the camera does not show is not counted.</p>
      {type && <video ref={preview} className="m-video" data-on={!!rec || undefined} muted playsInline />}
      {!rec && s.busy == null && <Camera label="Record or choose a video" video quiet onFile={(f) => void upload(f)} />}
      {s.busy != null && <Progress value={s.busy < 1 ? s.busy : null} label={s.busy < 1 ? `Sending the video, ${Math.round(s.busy * 100)}%` : 'Reading the frames. This takes about half a minute.'} />}
      <Sent reply={s.reply} />
    </Page>
  )
}

/** The GPS fix against the scan index: open the building you are in, or use the aerial tools at this spot. */
export function Where({ back }: Props) {
  const [busy, setBusy] = useState(false)
  const [found, setFound] = useState<{ fix: Fix; here: Place[]; text: string | null; actions: Action[] } | null>(null)
  const results = usePhone((s) => s.view?.results ?? NONE)
  const find = async () => {
    setBusy(true)
    try { const fix = await getFix(6000); const r = await locate(fix); setFound({ fix, here: r.here, text: r.verdict?.text ?? null, actions: r.actions }) } catch (e) { fail(e) } finally { setBusy(false) }
  }
  const open = async (sid: string) => { try { await place(sid); toast('Opened. Its on-site checks are under Tasks.'); back() } catch (e) { fail(e) } }
  const aerial = async (a: Action) => { try { const r = await runTool(a.tool, a.inputs); toast(r.status === 'running' ? `${a.label}: running, the result will be under Results.` : r.error ?? `${a.label}: done.`) } catch (e) { fail(e) } }
  return (
    <Page title="Where am I" sub="Finds the scanned building you are in" onBack={back}
      actions={<button className="btn m-btn solid wide" disabled={busy} onClick={() => void find()}>{busy ? 'Getting a fix' : found ? 'Fix again' : 'Find where I am'}</button>}>
      {!found && !busy && <p className="m-hint">Uses this phone's location once, when you tap. Indoors a fix can be tens of metres off, so the list shows every scanned address in reach.</p>}
      {busy && <Progress value={null} label="Averaging fixes for a few seconds" />}
      {found && <>
        <p className="m-note">{found.text}<span className="num"> Fix ± {found.fix.accuracy_m?.toFixed(0) ?? '?'} m.</span></p>
        {found.here.map((b) => (
          <section key={`${b.lat},${b.lon}`} className="m-group">
            <h2 className="label">{b.address ?? 'No address'} · <span className="num">{b.distance_m < 1000 ? `${b.distance_m.toFixed(0)} m` : `${(b.distance_m / 1000).toFixed(1)} km`}</span></h2>
            {b.scans.slice(0, 8).map((sc) => <Row key={sc.sid} title={sc.name} sub={sc.kind?.replaceAll('_', ' ')} right="Open" onClick={() => void open(sc.sid)} />)}
            {b.scans.length > 8 && <p className="m-hint">{b.scans.length - 8} more scans at this address are on the desktop.</p>}
          </section>
        ))}
        {found.actions.length > 0 && <section className="m-group"><h2 className="label">Without a scan, from the aerial survey at this spot</h2>
          {found.actions.map((a) => <Row key={a.id} title={a.label} right="Run" onClick={() => void aerial(a)} />)}
          {results.filter((r) => found.actions.some((a) => a.tool === r.tool)).map((r) => <ResultCard key={r.run} r={r} />)}</section>}
      </>}
    </Page>
  )
}

const NOTE_KINDS = [['photo', 'Photo'], ['video', 'Video'], ['audio', 'Voice']] as const
/** Plain evidence: a photo, a clip or a spoken note pinned to a room. */
export function Note({ back }: Props) {
  const sid = useSid(), rooms = useRooms(), s = useSend()
  const [kind, setKind] = useState<(typeof NOTE_KINDS)[number][0]>('photo')
  const [room, setRoom] = useState<string | null>(null)
  const [text, setText] = useState('')
  const [rec, setRec] = useState<{ stop: () => void } | null>(null)
  const meta = async (): Promise<Omit<Meta, 'kind'>> => ({ scan: sid, room, note: text.trim() || undefined, fix: await getFix(2000).catch(() => null) })
  const voice = async () => {
    const type = recorderType('audio')
    if (!type) { toast.error('This browser cannot record sound in a page. Type the note instead.'); return }
    let stream: MediaStream
    try { stream = await navigator.mediaDevices.getUserMedia({ audio: true }) } catch { toast.error('The microphone is switched off for this page.'); return }
    const chunks: Blob[] = [], r = new MediaRecorder(stream, { mimeType: type })
    r.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data) }
    r.onstop = async () => { stream.getTracks().forEach((t) => t.stop()); setRec(null); if (!chunks.length) { toast.error('Nothing was recorded. Check that no other app is using the microphone.'); return } await s.go({ ...(await meta()), kind: 'audio' }, new Blob(chunks, { type: type.split(';')[0] })) }
    r.start(); setRec({ stop: () => r.stop() })
    setTimeout(() => r.state !== 'inactive' && r.stop(), 60_000)
  }
  return (
    <Page title="Note" sub="Evidence for the desktop, pinned to a room" onBack={back}
      actions={kind === 'audio' ? <button className="btn m-btn solid wide" disabled={s.busy != null} onClick={() => (rec ? rec.stop() : void voice())}>{rec ? 'Stop and send' : 'Record a voice note'}</button>
        : <Camera label={kind === 'photo' ? 'Take the photo' : 'Record the video'} video={kind === 'video'} onFile={async (f) => void s.go({ ...(await meta()), kind }, kind === 'photo' ? await shrink(f) : f)} />}>
      <Seg label="Kind of note" options={NOTE_KINDS} value={kind} onChange={setKind} />
      {rooms.length > 0 && <RoomPick rooms={rooms} value={room} onChange={setRoom} />}
      <Field label="What it shows"><textarea className="m-input" rows={3} value={text} onChange={(e) => setText(e.target.value)} maxLength={600} placeholder="Water stain under the window" /></Field>
      {kind === 'audio' && <p className="m-hint">The clip is kept as it is. Nothing here turns it into text.</p>}
      {s.busy != null && <Progress value={s.busy < 1 ? s.busy : null} label="Sending" />}
      <Sent reply={s.reply} />
    </Page>
  )
}

export type { Outcome }
