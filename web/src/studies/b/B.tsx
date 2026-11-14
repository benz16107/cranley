// Direction B, "Broadsheet". The product is a page the agent writes about a building. The verdict is the headline,
// every highlighted number is tied to a numbered figure, and the model sits on the paper like a printed plate.
import { useMemo, type ReactNode } from 'react'
import { ScatterplotLayer } from 'deck.gl'
import { BuildingScene } from '../../scene/BuildingScene.tsx'
import type { MapPalette } from '../../map/style.ts'
import type { View } from '../../scene/types.ts'
import { StudyMap, type Pin } from '../StudyMap.tsx'
import { BRIEF, NONE, PREFS, STARTERS, doorOf, lookAtDoor, m2, rank, sceneOverlays, scenePlan, useAudit, useAudits, useCity, type Audit, type Place } from '../data.ts'
import type { Moment } from '../index.tsx'
import './b.css'

const PAPER: MapPalette = {
  ground: '#f2eee4', water: '#dbe3e2', waterLine: '#7f98a4', green: '#e7e8d7', road: 'rgba(23,20,15,0.2)', roadMajor: 'rgba(23,20,15,0.5)',
  rail: 'rgba(23,20,15,0.2)', building: '#e6e0d2', label: '#17140f', labelMuted: '#6a6358', halo: '#f2eee4',
}
const TOOLS = ['Step-free access', 'Flood', 'Fire', 'Office fit', 'Record and reality']
const CUT: View = { mode: 'dollhouse', cut: 1.3 }
const READ = 6
const WORDS = ['No', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine', 'Ten']
const word = (n: number) => WORDS[n] ?? String(n)
const today = new Date().toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })

export default function B({ moment }: { moment: Moment }) {
  return (
    <div className="study study-b" data-moment={moment}>
      {moment === 'door' ? <Door /> : moment === 'city' ? <CityPage /> : <BuildingPage />}
      <header className="bs-mast">
        <span className="bs-name">Threshold</span><span className="bs-date">{today}</span>
        <nav aria-label="Tools">{TOOLS.map((t, i) => <button key={t} aria-pressed={i === 0 && moment !== 'door'}>{t}</button>)}<button aria-label="Add a tool">+</button></nav>
      </header>
    </div>
  )
}
const Mark = ({ children }: { children: ReactNode }) => <mark className="bs-mark">{children}</mark>
const Fig = ({ n, children, className }: { n: number; children: ReactNode; className?: string }) => <figcaption className={`bs-fig ${className ?? ''}`}><b>Fig. {n}</b> {children}</figcaption>

/* (a) The front door: one fact, one line to write on, and a real house cut open on the page. */
function Door() {
  const city = useCity(), audit = useAudit(city?.focus.sid)
  return (
    <>
      <div className="stage bs-plate-right">{audit && <BuildingScene plan={scenePlan(audit.plan)} view={CUT} />}</div>
      <div className="bs-fade" />
      <main className="bs-col">
        <p className="bs-kicker">Houston and Los Angeles</p>
        <h1 className="bs-head bs-head-xl">{city ? <><Mark>{city.all.length.toLocaleString('en-US')}</Mark> buildings, measured from the inside.</> : ' '}</h1>
        <p className="bs-deck">Say who you are and what you need. An agent picks the measuring tools, runs them on the scans and shows its working.</p>
        <label className="bs-line"><span className="bs-label">In one sentence</span><span className="bs-typed">{BRIEF}<i className="bs-caret" /></span><button>Begin</button></label>
        <ol className="bs-index">{STARTERS.map(([who, need], i) => <li key={who}><span>{i + 1}</span><button><b>{who}</b> {need}</button></li>)}</ol>
      </main>
      {audit && <Fig n={1} className="bs-fig-stage">{city?.focus.street}, Houston, cut open at 1.3 m. Drawn from {audit.plan.walls.length} walls and {audit.doors} doorways in its scan.</Fig>}
    </>
  )
}

/* (b) The city: the page is being written. Read houses are set in type; the rest are still ruled lines. */
function CityPage() {
  const city = useCity()
  const cands = city?.candidates ?? NONE
  const audits = useAudits(useMemo(() => cands.map((c) => c.sid), [cands]))
  const read = cands.slice(0, READ).filter((c) => audits[c.sid]), current = cands[READ]
  const ranked = [...read].sort((x, y) => rank(audits[x.sid], audits[y.sid]))
  const best = ranked[0] && audits[ranked[0].sid]
  const clear = read.filter((c) => audits[c.sid].traced && audits[c.sid].under === 0).length

  const layers = useMemo(() => !city ? [] : [
    new ScatterplotLayer<Place>({ id: 'all', data: city.houston, getPosition: (p) => [p.lon, p.lat], radiusUnits: 'pixels', getRadius: 2, getFillColor: [23, 20, 15, 120] }),
  ], [city])
  const pins: Pin[] = cands.map((c, i) => {
    const r = ranked.findIndex((x) => x.sid === c.sid), state = r >= 0 ? 'read' : i === READ ? 'now' : 'wait'
    return { key: c.sid, lon: c.lon, lat: c.lat, anchor: 'center', node: <span className="bs-pin" data-state={state} data-best={r === 0 || undefined}>{r >= 0 ? r + 1 : ''}</span> }
  })
  return (
    <>
      {city && <StudyMap className="stage" palette={PAPER} layers={layers} pins={pins} camera={{ center: [city.focus.lon - 0.052, city.focus.lat + 0.024], zoom: 11.75 }} />}
      <div className="bs-fade" />
      <main className="bs-col">
        <p className="bs-kicker">Clear Lake, Houston · step-free access</p>
        <h1 className="bs-head">{word(read.length)} houses read. {clear ? `${word(clear)} clear` : 'None clears'} <Mark>{PREFS.door}{'\u00a0'}m</Mark> at every door.</h1>
        {best && current && <p className="bs-deck">{ranked[0].street} is closest so far, with {best.under} doorways to widen. <em>Reading {current.street} now.</em></p>}
        <ol className="bs-table">
          {ranked.map((c, i) => { const a = audits[c.sid]; return (
            <li key={c.sid} data-best={i === 0 || undefined}>
              <span className="bs-rank">{i + 1}</span><span className="bs-street">{c.street}</span>
              <span className="bs-fix">{a.traced ? `${a.under} to widen` : 'route not traced'}</span>
              <span className="bs-width" data-s={a.traced ? a.worst?.status : 'unknown'}><i className="glyph" data-s={a.traced ? a.worst?.status : 'unknown'} />{a.traced && a.worst?.measured != null ? `${m2(a.worst.measured)} m` : 'not measured'}</span>
            </li>) })}
          {current && <li className="bs-reading"><span className="bs-rank">{ranked.length + 1}</span><span className="bs-street">{current.street}</span><span className="bs-fix">reading its floor plan</span><span className="bs-width" /></li>}
          {cands.slice(READ + 1).map((c) => <li key={c.sid} className="bs-unset" aria-label="Not read yet"><span /><span /><span /><span /></li>)}
        </ol>
      </main>
      <Fig n={1} className="bs-fig-stage">{cands.length} houses with a drone capture near Clear Lake, numbered in the order above. Narrowest doorway on the way in; scan geometry, medium confidence. Map © OpenStreetMap, OpenFreeMap.</Fig>
    </>
  )
}

/* (c) The building: the verdict as a headline, the model as figure 1, the two doorways as photographs. */
function BuildingPage() {
  const city = useCity(), audit = useAudit(city?.focus.sid)
  const overlays = useMemo(() => (audit ? sceneOverlays(audit.result) : []), [audit])
  if (!audit) return null
  const r = audit.result, w = audit.worst!, hit = doorOf(r, w), under = r.metrics.find((m) => m.id === 'under'), route = r.metrics.find((m) => m.id === 'route')
  const plates = r.checks.filter((c) => c.measured != null && c.status !== 'pass' && c.id !== 'turning').sort((x, y) => x.measured! - y.measured!).slice(0, 2)
  return (
    <>
      <div className="stage bs-plate-right"><BuildingScene plan={scenePlan(audit.plan)} overlays={overlays} view={CUT} /></div>
      <div className="bs-fade" />
      <main className="bs-col">
        <p className="bs-kicker">{city?.focus.street}, Houston · step-free access · <span data-s={r.verdict.status}><i className="glyph" data-s={r.verdict.status} /> does not pass</span></p>
        <h1 className="bs-head">{word(Number(under?.value ?? 0))} doorways on the way in are too narrow. The {hit.finding?.title.toLowerCase()} is <Mark>{m2(w.measured!)}{'\u00a0'}m</Mark>. You need {w.threshold}.</h1>
        <p className="bs-deck bs-by">{hit.finding?.source.note?.split(' Worked out')[0]} <span className="bs-label">Scan geometry · {hit.finding?.source.confidence} confidence</span></p>
        <div className="bs-plates">
          {plates.map((c, i) => <Plate key={c.id} n={i + 2} audit={audit} check={c} />)}
        </div>
      </main>
      <Fig n={1} className="bs-fig-stage">The way in, from the entrance to the bedroom, {route?.value != null ? m2(Number(route.value)) : ''} m. Doorways are marked by width against your {PREFS.door} m: square too narrow, triangle within 5 cm, circle wide enough.</Fig>
    </>
  )
}

function Plate({ n, audit, check }: { n: number; audit: Audit; check: Audit['result']['checks'][number] }) {
  const hit = doorOf(audit.result, check)
  const view = useMemo(() => lookAtDoor(audit.plan, hit.opening), [audit, hit.opening])
  const overlays = useMemo(() => sceneOverlays(audit.result).filter((o) => o.kind === 'rule'), [audit])
  return (
    <figure className="bs-plate">
      <div className="bs-photo">{view && <BuildingScene plan={scenePlan(audit.plan)} overlays={overlays} view={view} />}</div>
      <Fig n={n}>{hit.finding?.title}. <span data-s={check.status}><i className="glyph" data-s={check.status} /> {m2(check.measured!)} m</span>, {m2(check.threshold! - check.measured!)} m short.</Fig>
    </figure>
  )
}
