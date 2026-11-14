import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import { CITIES, NEEDS, captureImage, compose, fetchCaptures, investigate, orthoImage, startOver, useBuildings, useCatalog, useWorkspace, type Building, type Capture, type CityId, type Doc } from '../../../core/index.ts'
import { DataTable, Empty, Icon, RunState, Seg, St, ToolKey, type Col } from '../design/ui.tsx'
import { ago, clock, dur, int, plural } from '../lib/format.ts'
import { activity, homeBuildings, starterBuildings, type HomeBuilding, type HomeEvent } from '../lib/home.ts'
import { openSeen, started, statusOf, useSeen, type Seen } from '../lib/pending.ts'
import { go, goInvestigation, goScan } from '../lib/place.ts'
import { CityMap, useMap } from '../map/CityMap.tsx'
import { QuestionForm, openRun } from '../shell/RunPanel.tsx'
import { useIsPhone, useUi } from '../shell/store.ts'
import { useScheme } from '../shell/theme.ts'

export const STATUS: Record<Seen['status'], { label: string; state: 'pending' | 'running' | 'done' }> = {
  setup: { label: 'Setting up', state: 'pending' }, working: { label: 'Working', state: 'running' }, waiting: { label: 'Needs an answer', state: 'pending' }, done: { label: 'Finished', state: 'done' },
}

/** A building's aerial photo: the 70 m patch the server keeps on disk, the same one Explore shows. One small image
    per card, never a 3D view. A picture that does not load leaves a building's mark in its place. */
function Aerial({ lat, lon }: { lat: number; lon: number }) {
  const [gone, setGone] = useState(false)
  return <span className="aerial">{gone ? <Icon name="building" size={16} /> : <img src={orthoImage(lat, lon, 70, 256)} alt="" loading="lazy" width={256} height={256} onError={() => setGone(true)} />}</span>
}

/** A new brief: one sentence, or one of five needs to start from. Keyboard: C comes here from anywhere on the page,
    Down from an empty field walks the needs, Enter composes, Escape gives the keys back to the page. */
function Composer({ first }: { first: boolean }) {
  const [text, setText] = useState('')
  const live = useCatalog((s) => s.live)
  const phone = useIsPhone()
  const field = useRef<HTMLTextAreaElement>(null), needs = useRef<HTMLUListElement>(null)
  const send = () => { if (text.trim()) void compose(text.trim()) }
  // On a first visit starting is the one thing to do, so the field has the focus. With work open it does not: the
  // single-key shortcuts (G E, the agent panel) must keep working on arrival. Not on a phone: it raises the keyboard.
  useEffect(() => { if (first && !phone && !document.querySelector('[role="dialog"]')) field.current?.focus({ preventScroll: true }) }, [first, phone])
  useEffect(() => {
    const key = (e: KeyboardEvent | globalThis.KeyboardEvent) => {
      const t = e.target as HTMLElement
      if (e.key.toLowerCase() !== 'c' || e.metaKey || e.ctrlKey || e.altKey || /^(input|textarea|select)$/i.test(t.tagName) || t.isContentEditable || document.querySelector('[role="dialog"], [role="menu"]')) return
      e.preventDefault(); field.current?.focus()
    }
    window.addEventListener('keydown', key)
    return () => window.removeEventListener('keydown', key)
  }, [])
  const walk = (e: KeyboardEvent, i: number) => {
    const all = [...(needs.current?.querySelectorAll('button') ?? [])]
    if (e.key === 'ArrowDown' && all[i + 1]) { e.preventDefault(); all[i + 1].focus() }
    else if (e.key === 'ArrowUp' || e.key === 'Escape') { e.preventDefault(); (e.key === 'ArrowUp' && all[i - 1] ? all[i - 1] : field.current)?.focus() }
  }
  return (
    <section className="h-sec h-new" aria-labelledby="new-h">
      <header><h2 id="new-h">New investigation</h2><p className="grow">Say who you are and what you need from a building. The agent picks the tools and asks what it must.</p></header>
      <form className="h-field" onSubmit={(e) => { e.preventDefault(); send() }}>
        <textarea ref={field} className="field" rows={2} value={text} onChange={(e) => setText(e.target.value)} placeholder="I use a wheelchair and I am choosing a one-bedroom apartment in Houston" aria-label="Who you are and what you need" aria-keyshortcuts="C"
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() }
            else if (e.key === 'ArrowDown' && !text) { e.preventDefault(); needs.current?.querySelector('button')?.focus() }
            else if (e.key === 'Escape') e.currentTarget.blur()
          }} />
        <div>
          <span className="hint" aria-hidden="true"><span className="kbd">C</span> to write here, <span className="kbd">↓</span> for a need below</span>
          <span className="grow" />
          <button className="btn solid" disabled={!text.trim()}>Compose<span className="kbd">Enter</span></button>
        </div>
      </form>
      {live === false && <p className="note"><Icon name="info" size={13} /><span>The agent server is not answering. A need below plays back a recorded composition; only the step-free access investigation runs.</span></p>}
      <ul className="h-needs" ref={needs} aria-label="Or start from a need">
        {NEEDS.map((n, i) => (
          <li key={n.id}>
            <button type="button" onClick={() => void compose(n.sentence, n.id)} onKeyDown={(e) => walk(e, i)} title={n.sentence}>
              <span className="t"><b>{n.who}</b> {n.need}</span>
              <span className="s">{n.runsOn}</span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}

/** The brief is in: the tools arrive with their reasons, then the questions, then Start. */
function Setup() {
  const doc = useWorkspace((s) => s.doc)
  const open = doc.questions.filter((q) => q.answer == null)
  const settled = doc.questions.length > 0 || doc.tools.length > 0
  return (
    <section className="card" aria-labelledby="setup-h">
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
            {doc.tools.map((t) => <li key={t.id} className="arrive"><ToolKey id={t.id} title={t.title} /><span className="grow"><b>{t.title}</b><span className="why">{t.reason}</span></span><span className="muted">{t.by === 'agent' ? 'agent' : 'you'}</span></li>)}
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

/** The open investigation: what it is, how far it has got, and the two ways back into it. */
function Continue({ doc }: { doc: Doc }) {
  const status = statusOf(doc), open = doc.questions.filter((q) => q.answer == null).length
  const failed = doc.runs.filter((r) => r.status === 'failed').length, done = doc.plan.filter((s) => s.status === 'done').length
  const facts = [doc.plan.length ? `${done} of ${doc.plan.length} steps` : null, plural(doc.runs.length, 'run'), plural(doc.findings.length, 'finding'), doc.shortlist.length ? `${int(doc.shortlist.length)} kept` : null].filter(Boolean)
  return (
    <section className="h-sec h-open" aria-labelledby="cont-h">
      <header><h2 id="cont-h">Continue</h2></header>
      <div className="h-cont">
        <button type="button" className="main" onClick={() => goInvestigation(doc.id)}>
          <span className="t">{doc.brief?.text ?? 'Tools run by hand, with no brief'}</span>
          <span className="f"><RunState state={STATUS[status].state}>{STATUS[status].label}</RunState><span className="muted">{facts.join(' · ')}</span>{failed > 0 && <span className="st" data-status="fail">{failed} failed</span>}</span>
        </button>
        {open > 0 && <button type="button" className="btn" onClick={() => useUi.getState().setRun(true)}>Answer {open === 1 ? 'the question' : `${open} questions`}</button>}
        <button type="button" className="btn" onClick={() => goInvestigation(doc.id)}>Open<Icon name="go" size={12} /></button>
      </div>
    </section>
  )
}

/** Buildings to open, each with its aerial photo. With work open: the kept ones and the ones it has results on. On a
    first visit: real scanned houses to start from, so the page shows what the product holds before anything is typed. */
function BuildingGrid({ items, first, loading }: { items: HomeBuilding[]; first: boolean; loading: boolean }) {
  // a starter is named by its address, so its second line is the city
  const street = (b: HomeBuilding) => { const [line, city] = b.address.split(',').map((x) => x.trim()); return !first && line && line !== b.name ? line : city ?? '' }
  return (
    <section className="h-sec" aria-labelledby="bld-h">
      <header>
        <h2 id="bld-h">{first ? 'Start from a building' : 'Buildings'}</h2>
        <p className="grow">{first ? 'Scanned addresses that also have a drone capture.' : 'Kept, and measured in this investigation.'}</p>
        <span className="muted small">Aerial photos: Vexcel</span>
        <button type="button" className="btn sm quiet" onClick={() => go(first ? 'explore' : 'buildings')}>{first ? 'All on the map' : 'All kept'}<Icon name="go" size={11} /></button>
      </header>
      <ul className="h-blds" aria-busy={loading || undefined}>
        {loading && [0, 1, 2, 3].map((i) => <li key={i} className="skel"><span className="aerial sk" /><span className="sk" style={{ width: '70%' }} /><span className="sk" style={{ width: '45%' }} /></li>)}
        {items.map((b) => (
          <li key={b.sid}>
            <button type="button" onClick={() => goScan(b.sid)}>
              <Aerial lat={b.lat} lon={b.lon} />
              <span className="n trunc">{b.name}</span>
              <span className="a trunc">{street(b)}</span>
              {!first && <span className="s">
                {b.worst && <St status={b.worst} />}
                {b.results > 0 && <span className="muted">{plural(b.results, 'result')}</span>}
                {b.kept && <span className="muted"><Icon name="keep" size={11} />Kept</span>}
              </span>}
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}

/** Where the data is: every scanned address in one city on the Explore map's own component, at a size that fits a
    column. A dot opens that address in Explore. The wheel is the page's, so it does not zoom this map. */
function Addresses({ doc }: { doc: Doc }) {
  const all = useBuildings((s) => s.all), state = useBuildings((s) => s.state)
  const scheme = useScheme()
  const mine = useMemo(() => { const sids = new Set([...doc.shortlist.map((s) => s.sid), ...doc.panels.map((p) => p.sid)]); return all.filter((b) => b.scans.some((s) => sids.has(s.sid))) }, [all, doc.shortlist, doc.panels])
  // the city of the work in hand, once the building list says where that is, until the person picks one
  const [picked, setCity] = useState<CityId | null>(null)
  const city = picked ?? mine[0]?.metro ?? 'hou'
  const here = useMemo(() => all.filter((b) => b.metro === city), [all, city])
  const marks = useMemo(() => mine.map((b) => ({ lon: b.lon, lat: b.lat })), [mine])
  const map = useMap((s) => s.map)
  // On a touch screen a finger on the map scrolls the page too: the map stays still there and its dots still open Explore.
  useEffect(() => {
    if (!map) return
    map.scrollZoom.disable()
    if (matchMedia('(pointer: coarse)').matches) { map.dragPan.disable(); map.touchZoomRotate.disable() }
  }, [map])
  return (
    <section className="h-sec h-map" aria-labelledby="map-h">
      <header><h2 id="map-h">Scanned addresses</h2><span className="grow" /><Seg label="City" value={city} onChange={setCity} options={(Object.keys(CITIES) as CityId[]).map((c) => ({ id: c, label: CITIES[c].name }))} /></header>
      <div className="box">
        {state === 'error' ? <Empty icon="warn" title="The building list did not load" /> : <CityMap buildings={here} selected={null} marks={marks} city={city} scheme={scheme} onSelect={(b: Building | null) => b && go('explore', { city, b: b.id })} />}
        <span className="credit">© OpenStreetMap · OpenFreeMap</span>
      </div>
      <footer>
        <span className="muted">{state === 'loading' ? <span className="sk" style={{ width: 180 }} /> : `${int(here.length)} addresses, ${int(here.reduce((n, b) => n + b.count, 0))} scans in ${CITIES[city].name}`}</span>
        <span className="grow" />
        <button type="button" className="btn sm quiet" onClick={() => go('explore', { city })}>Open Explore<Icon name="go" size={11} /></button>
      </footer>
    </section>
  )
}

const NONE: Capture[] = []
const CAPTURE: Record<Capture['kind'], string> = { photo: 'Photo', video: 'Video', audio: 'Voice note', reading: 'Reading' }
/** One feed for everything that is happening or just did: runs, failed ones in red, a question that holds the work
    up, and what a paired phone sent. */
function Activity({ doc }: { doc: Doc }) {
  // what the phone sent, kept with the workspace it belongs to so another workspace never shows it
  const [got, setGot] = useState<{ ws: string; list: Capture[] }>({ ws: '', list: NONE })
  const live = doc.id.startsWith('ws_'), captures = got.ws === doc.id ? got.list : NONE
  // Read again a moment after the workspace changes (a paired phone's capture is one of its writes), and every 20 s
  // while the page is in view, because a tab that did not do the pairing is not told about the phone's writes.
  useEffect(() => {
    if (!live) return
    let on = true
    const ws = doc.id
    const read = () => { if (document.visibilityState === 'visible') fetchCaptures(ws).then((list) => on && setGot({ ws, list }), () => {}) }
    const soon = setTimeout(read, 300), every = setInterval(read, 20_000)
    return () => { on = false; clearTimeout(soon); clearInterval(every) }
  }, [doc, live])
  const rows = useMemo(() => activity(doc, captures, 9), [doc, captures])
  const title = (tool: string, label: string) => doc.tools.find((t) => t.id === tool)?.title ?? label.split(' · ')[0]
  const where = (label: string) => (label.includes(' · ') ? label.split(' · ').slice(1).join(' · ') : '')
  const agent = () => useUi.getState().setRun(true)
  const row = (e: HomeEvent) => {
    if (e.kind === 'working') return (
      <button type="button" onClick={agent}><i className="ring" /><span className="grow"><span className="t"><b>{e.run ? title(e.run.tool, e.run.label) : 'The agent'}</b>{e.run && where(e.run.label) && <span className="muted"> · {where(e.run.label)}</span>}</span><span className="s">{e.text}</span></span><span className="w rs" data-state="running">Working</span></button>
    )
    if (e.kind === 'ask') return (
      <button type="button" onClick={agent}><Icon name="help" size={14} /><span className="grow"><span className="t"><b>{e.open === 1 ? 'One question' : `${e.open} questions`} before the work can go on</b></span><span className="s">Answer in the agent panel.</span></span><span className="w rs" data-state="ask">Answer</span></button>
    )
    if (e.kind === 'run') { const r = e.run, timed = r.at != null; return (
      <button type="button" onClick={() => openRun(r)} disabled={!r.sid && !doc.panels.some((p) => p.run === r.id)}>
        <ToolKey id={r.tool} title={title(r.tool, r.label)} />
        <span className="grow"><span className="t"><b>{title(r.tool, r.label)}</b>{where(r.label) && <span className="muted"> · {where(r.label)}</span>}</span>{r.summary && <span className="s">{r.summary}</span>}</span>
        {r.status === 'failed' ? <span className="w"><RunState state="failed" /></span> : <span className="w muted">{timed ? ago(e.at) : dur(r.ms)}</span>}
      </button>
    ) }
    const c = e.capture
    return (
      <div className="cap">
        <span className="k"><Icon name={c.kind === 'photo' || c.kind === 'video' ? 'camera' : 'site'} size={14} /></span>
        <span className="grow"><span className="t"><b>{CAPTURE[c.kind]} from the phone</b></span><span className="s">{c.note || (c.task ? 'Answers an on-site check' : c.tool ? c.tool.replace(/_/g, ' ') : 'A note')}</span></span>
        {c.kind === 'photo' && c.file && <img src={captureImage(c.id)} alt="" loading="lazy" width={40} height={30} />}
        <span className="w muted" title={clock(e.at)}>{ago(e.at)}</span>
      </div>
    )
  }
  return (
    <section className="h-sec" aria-labelledby="act-h">
      <header><h2 id="act-h">Activity</h2><span className="grow" />{doc.runs.length > 0 && <button type="button" className="btn sm quiet" onClick={() => goInvestigation(doc.id)}>All {int(doc.runs.length)} runs<Icon name="go" size={11} /></button>}</header>
      {rows.length === 0 ? <p className="h-none">Nothing has run yet. Runs, failures, questions and what a paired phone sends are listed here as they happen.</p>
        : <ul className="h-feed" aria-live="polite">{rows.map((e) => <li key={e.id} data-kind={e.kind} data-failed={(e.kind === 'run' && e.run.status === 'failed') || undefined}>{row(e)}</li>)}</ul>}
    </section>
  )
}

export function Home() {
  const doc = useWorkspace((s) => s.doc)
  const seen = useSeen((s) => s.all)
  const all = useBuildings((s) => s.all), listState = useBuildings((s) => s.state)
  const composing = !!doc.brief && doc.plan.length === 0 && doc.panels.length === 0
  const working = started(doc)
  const mine = useMemo(() => homeBuildings(doc, all), [doc, all])
  const first = mine.length === 0
  // whole rows of four: one building alone on a second row would take a third of the screen
  const items = useMemo(() => (first ? starterBuildings(all, 8) : mine.slice(0, mine.length >= 8 ? 8 : 4)), [first, mine, all])
  const where = useMemo(() => { const by = new Map<string, Building>(); for (const b of all) for (const s of b.scans) by.set(s.sid, b); return by }, [all])
  const others = Object.values(seen).filter((s) => s.id !== doc.id).sort((a, b) => b.last - a.last)
  const cols: Col<Seen>[] = [
    { id: 'brief', label: 'Investigation', fixed: true, cell: (s) => <span className="strong">{s.brief || 'Tools run by hand'}</span> },
    ...(others.some((s) => s.sids?.some((sid) => where.has(sid))) ? [{ id: 'where', label: 'Buildings', width: 100, cell: (s) => <span className="minis">{(s.sids ?? []).flatMap((sid) => { const b = where.get(sid); return b ? [<Aerial key={sid} lat={b.lat} lon={b.lon} />] : [] })}</span> } satisfies Col<Seen>] : []),
    { id: 'status', label: 'Status', width: 140, cell: (s) => <RunState state={STATUS[s.status].state}>{STATUS[s.status].label}</RunState> },
    { id: 'runs', label: 'Runs', num: true, width: 60, cell: (s) => int(s.runs) },
    { id: 'findings', label: 'Findings', num: true, width: 76, cell: (s) => int(s.findings) },
    { id: 'last', label: 'Last change', width: 120, cell: (s) => <span className="dim">{ago(s.last)}</span> },
  ]
  return (
    <div className="page home">
      <div className="inner">
        <div className="h-main">
          {composing ? <Setup /> : <Composer first={!working && Object.keys(seen).length === 0} />}
          {working && !composing && <Continue doc={doc} />}
          <BuildingGrid items={items} first={first} loading={listState === 'loading' && items.length === 0} />
          {others.length > 0 && (
            <section className="h-sec h-other" aria-labelledby="rec-h">
              <header><h2 id="rec-h">{working ? 'Other investigations' : 'Recent investigations'}</h2><p className="grow">Kept in this browser. Opening one loads the page again.</p><button type="button" className="btn sm quiet" onClick={() => go('investigations')}>All<Icon name="go" size={11} /></button></header>
              <div className="card"><DataTable label="Recent investigations" noun="investigation" cols={cols} rows={others.slice(0, 5)} rowKey={(s) => s.id} onRow={(s) => openSeen(s.id)} /></div>
            </section>
          )}
        </div>
        <aside className="h-rail" aria-label="The data and what is happening">
          <Addresses doc={doc} />
          <Activity doc={doc} />
        </aside>
      </div>
    </div>
  )
}
