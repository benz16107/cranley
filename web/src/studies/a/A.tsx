// Direction A, "Overflight". The product is one camera shot from the city down to a doorway. The picture always
// fills the screen, the agent speaks in subtitles, and a measurement is drawn in the photograph it was taken from.
import { useMemo, type ReactNode } from 'react'
import NumberFlow from '@number-flow/react'
import { PathLayer, ScatterplotLayer } from 'deck.gl'
import { BuildingScene } from '../../scene/BuildingScene.tsx'
import type { MapPalette } from '../../map/style.ts'
import type { View } from '../../scene/types.ts'
import { Scale } from '../Scale.tsx'
import { StudyMap, type Pin } from '../StudyMap.tsx'
import { BRIEF, FOCUS, NONE, PREFS, STARTERS, STEPS, doorOf, lookAtDoor, m2, rank, sceneOverlays, scenePlan, useAudit, useAudits, useCity, type Place } from '../data.ts'
import type { Moment } from '../index.tsx'
import './a.css'

const NIGHT: MapPalette = {
  ground: '#0d1114', water: '#03070b', waterLine: 'rgba(150,190,215,0.4)', green: '#0e1614', road: 'rgba(255,220,180,0.2)', roadMajor: 'rgba(255,214,170,0.62)',
  rail: 'rgba(255,220,180,0.10)', building: '#141a20', label: 'rgba(244,241,234,0.78)', labelMuted: 'rgba(244,241,234,0.42)', halo: '#0b0e11',
}
const SPLAT: View = { mode: 'splat' }
const READ = 6 // the moment shown on the city screen: this many houses read, the next one being read

export default function A({ moment }: { moment: Moment }) {
  return <div className="study study-a" data-moment={moment}>{moment === 'door' ? <Door /> : moment === 'city' ? <CityShot /> : <Doorway />}</div>
}

function Frame({ place, children }: { place?: string; children?: ReactNode }) {
  return (
    <>
      <div className="ov-scrim" />
      <header className="ov-top"><span className="ov-mark">Threshold</span>{place && <span className="ov-place">{place}</span>}</header>
      {children}
    </>
  )
}
const Voice = ({ children }: { children: ReactNode }) => <p className="ov-voice" aria-live="polite">{children}</p>
const Figure = ({ value, unit, children }: { value: ReactNode; unit?: string; children: ReactNode }) => (
  <div className="ov-figure"><div className="ov-figure-n">{value}{unit && <small>{unit}</small>}</div><div className="ov-caption">{children}</div></div>
)

const VIEWS = ['Drone', 'Cutaway', 'Plan', 'Inside']
function Dock({ step, view, children }: { step?: number; view?: string; children?: ReactNode }) {
  return (
    <div className="ov-dock">
      {children ?? <span className="ov-brief">{BRIEF}</span>}
      {!children && <>
        <span className="ov-tool"><i className="glyph" data-s="fail" />Step-free access</span>
        <button className="ov-add">Add a tool</button>
        {step != null && <span className="ov-step">Step {step} of {STEPS.length}</span>}
        {view && <span className="ov-views" role="group" aria-label="View">{VIEWS.map((v) => <button key={v} aria-pressed={v === view}>{v}</button>)}</span>}
      </>}
    </div>
  )
}

/* (a) The front door: a drone capture of a real house, the agent's first line, one field. */
function Door() {
  const city = useCity(), audit = useAudit(FOCUS)
  return (
    <>
      <div className="stage">{audit && <BuildingScene plan={scenePlan(audit.plan)} view={SPLAT} />}</div>
      <Frame place="Houston and Los Angeles">
        {city && <Figure value={city.all.length.toLocaleString('en-US')}>
          addresses scanned from the inside<br />{city.scans.toLocaleString('en-US')} scans · {city.all.filter((p) => p.splat).length} with a drone capture
        </Figure>}
        <Voice>Tell me who you are and what you need from a building.</Voice>
        <Dock>
          <label className="ov-field"><span className="ov-typed">{BRIEF}</span><i className="ov-caret" /></label>
          <button className="ov-go">Begin</button>
        </Dock>
        <ul className="ov-starters">{STARTERS.map(([who, need]) => <li key={who}><button><b>{who}</b> {need}</button></li>)}</ul>
        <p className="ov-credit">{city?.focus.street ?? 'A house'}, Houston · drag to orbit</p>
      </Frame>
    </>
  )
}

/* (b) The city at night. Every light is a scanned address; the agent's path runs between the houses it has read. */
function CityShot() {
  const city = useCity()
  const cands = city?.candidates ?? NONE
  const audits = useAudits(useMemo(() => cands.map((c) => c.sid), [cands]))
  const read = cands.slice(0, READ).filter((c) => audits[c.sid]), current = cands[READ]
  const ranked = [...read].sort((x, y) => rank(audits[x.sid], audits[y.sid]))
  const best = ranked[0] && audits[ranked[0].sid]

  const layers = useMemo(() => !city ? [] : [
    new ScatterplotLayer<Place>({ id: 'lights', data: city.houston, getPosition: (p) => [p.lon, p.lat], radiusUnits: 'pixels', getRadius: (p) => 1.6 + Math.sqrt(p.scans) * 1.1,
      getFillColor: [255, 232, 196, 210], billboard: true }),
    new PathLayer<Place[]>({ id: 'path', data: [cands.slice(0, READ + 1)], getPath: (d) => d.map((p): [number, number] => [p.lon, p.lat]), getColor: [244, 241, 234, 190], widthUnits: 'pixels', getWidth: 1.5 }),
  ], [city, cands])

  const pins: Pin[] = cands.map((c, i) => {
    const a = audits[c.sid], state = i < READ && a ? 'read' : i === READ ? 'now' : 'wait'
    return { key: c.sid, lon: c.lon, lat: c.lat, node: (
      <div className="ov-pin" data-state={state} data-best={ranked[0]?.sid === c.sid || undefined}>
        {state === 'read' && <span className="ov-pin-n" data-s={a.traced ? a.worst?.status : 'unknown'}><i className="glyph" data-s={a.traced ? a.worst?.status : 'unknown'} />{a.traced && a.worst?.measured != null ? m2(a.worst.measured) : 'no route'}</span>}
        {state === 'now' && <span className="ov-pin-n">reading</span>}
        {(state === 'now' || ranked[0]?.sid === c.sid) && <span className="ov-pin-street">{c.street}</span>}
        <i className="ov-pin-stem" style={state === 'read' && ranked[0]?.sid !== c.sid ? { height: 30 + (i % 3) * 30 } : undefined} /><i className="ov-pin-foot" />
      </div>) }
  })

  return (
    <>
      {city && <StudyMap className="stage" palette={NIGHT} layers={layers} pins={pins} names={false}
        camera={{ center: [(city.focus.lon + cands.at(-1)!.lon) / 2 + 0.012, (city.focus.lat + cands.at(-1)!.lat) / 2 - 0.004], zoom: 12.5, pitch: 58, bearing: -48 }} />}
      <Frame place="Clear Lake, Houston">
        <Figure value={<NumberFlow value={read.length} />} unit={`/${cands.length}`}>houses read<br />{STEPS[2].toLowerCase()}</Figure>
        {ranked.length > 0 && <ol className="ov-rank">
          <li className="ov-rank-h">Closest to working</li>
          {ranked.map((c, i) => { const a = audits[c.sid]; return (
            <li key={c.sid} data-best={i === 0 || undefined}>
              <span className="ov-rank-i">{i + 1}</span><span className="ov-rank-s">{c.street}</span>
              <span className="ov-rank-v">{a.traced ? <>{a.under} to widen · {a.worst?.measured != null ? m2(a.worst.measured) : 'n/a'} m</> : 'route not traced'}</span>
            </li>) })}
          <li className="ov-rank-f">{cands.length - READ - 1} waiting · widths are scan geometry, medium confidence</li>
        </ol>}
        {best && current && <Voice>{read.length} read. None clears {PREFS.door} m at every doorway. {ranked[0].street} is closest, with {best.under} to widen.<br /><em>Reading {current.street}.</em></Voice>}
        <Dock step={3} />
        <p className="ov-credit">Each light is a scanned address · © OpenStreetMap, OpenFreeMap</p>
      </Frame>
    </>
  )
}

/* (c) The result: stand at the doorway that fails, with its width drawn across it. */
function Doorway() {
  const city = useCity(), audit = useAudit(FOCUS)
  const hit = audit && doorOf(audit.result, audit.worst)
  const view = useMemo(() => (audit && hit ? lookAtDoor(audit.plan, hit.opening) : null), [audit, hit?.opening]) // eslint-disable-line react-hooks/exhaustive-deps
  const overlays = useMemo(() => (audit ? sceneOverlays(audit.result) : []), [audit])
  if (!audit) return <Frame />
  const w = audit.worst!, short = (w.threshold ?? 0) - (w.measured ?? 0), under = audit.result.metrics.find((m) => m.id === 'under')
  const doors = audit.result.checks.filter((c) => c.measured != null && c.id !== 'turning')
  return (
    <>
      <div className="stage">{view && <BuildingScene plan={scenePlan(audit.plan)} overlays={overlays} view={view} />}</div>
      <Frame place={`${city?.focus.street ?? ''}, Houston · inside`}>
        <Figure value={<NumberFlow value={w.measured ?? 0} format={{ minimumFractionDigits: 2, maximumFractionDigits: 2 }} />} unit="m">
          {hit?.finding?.title ?? w.rule}<br />{m2(short)} m short of the {w.threshold} m you need
          <span className="ov-source">Scan geometry · {hit?.finding?.source.confidence} confidence</span>
          <Scale doors={doors} limit={PREFS.door} />
        </Figure>
        <svg className="ov-leader" aria-hidden="true"><line x1="520" y1="236" x2="50%" y2="53%" /><circle cx="50%" cy="53%" r="5" /></svg>
        <div className="ov-verdict"><i className="glyph" data-s={audit.result.verdict.status} />{under?.value} {under?.unit} doorways under your limit</div>
        <Voice>{audit.result.verdict.text} <em>This is the narrowest.</em></Voice>
        <Dock view="Inside" />
      </Frame>
    </>
  )
}
