// Direction C, "Maquette". The product is a model on a cutting mat. The city is a table of blocks, a building is a
// white card model cut open, and every finding is a tag tied to the thing it measures. Tools are sheets laid over the model.
import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { ColumnLayer } from 'deck.gl'
import { BuildingScene } from '../../scene/BuildingScene.tsx'
import { FloorPlan } from '../../scene/FloorPlan.tsx'
import type { MapPalette } from '../../map/style.ts'
import type { View } from '../../scene/types.ts'
import { fetchPlan } from '../../lib/api.ts'
import type { ScanPlan } from '../../workspace/types.ts'
import { Scale } from '../Scale.tsx'
import { StudyMap, type Pin } from '../StudyMap.tsx'
import { BRIEF, FOCUS, NONE, PREFS, STARTERS, STEPS, doorOf, lookAtDoor, m2, rank, sceneOverlays, scenePlan, useAudit, useAudits, useCity, type Audit, type Place } from '../data.ts'
import type { Moment } from '../index.tsx'
import './c.css'

const MAT: MapPalette = {
  ground: '#1f5c4a', water: '#174a3c', waterLine: 'rgba(234,241,226,0.5)', green: '#236450', road: 'rgba(234,241,226,0.2)', roadMajor: 'rgba(234,241,226,0.62)',
  rail: 'rgba(234,241,226,0.2)', building: '#2a6b57', label: 'rgba(234,241,226,0.9)', labelMuted: 'rgba(234,241,226,0.6)', halo: '#1f5c4a',
}
const CUT: View = { mode: 'dollhouse', cut: 1.3 }
const READ = 6

export default function C({ moment }: { moment: Moment }) {
  return <div className="study study-c" data-moment={moment}>{moment === 'door' ? <Table /> : moment === 'city' ? <CityTable /> : <Model />}</div>
}
const Print = ({ place, note }: { place: string; note?: string }) => <header className="mq-print"><b>Threshold</b><span>{place}</span>{note && <span className="mq-print-r">{note}</span>}</header>
const Big = ({ value, unit, children }: { value: ReactNode; unit?: string; children: ReactNode }) => (
  <div className="mq-big"><div className="mq-big-n">{value}{unit && <small>{unit}</small>}</div><p>{children}</p></div>
)
/* Tools are sheets laid over the model; the one in use is on top. */
const Sheets = ({ on }: { on?: boolean }) => (
  <div className="mq-sheets">
    <span className="mq-strip">{BRIEF}</span>
    <button className="mq-sheet" aria-pressed={!!on}><i className="glyph" data-s={on ? 'fail' : 'unknown'} />Step-free access</button>
    <button className="mq-sheet mq-sheet-add">Lay another tool on the model</button>
  </div>
)

/* (a) The front door: the table seen from above, with five real plans on it to pick up. */
function Table() {
  const city = useCity()
  const [plans, setPlans] = useState<(ScanPlan | null)[]>([])
  useEffect(() => { void Promise.all(STARTERS.map(([, , sid]) => fetchPlan(sid).catch(() => null))).then(setPlans) }, [])
  return (
    <>
      <Print place="Houston and Los Angeles" />
      {city && <Big value={city.all.length.toLocaleString('en-US')}>buildings on the table<br />{city.scans.toLocaleString('en-US')} scans · {city.all.filter((p) => p.splat).length} with a drone capture</Big>}
      <label className="mq-ask"><span>Who are you, and what do you need from a building?</span><span className="mq-typed">{BRIEF}<i className="mq-caret" /></span><button>Begin</button></label>
      <ul className="mq-plans">
        {STARTERS.map(([who, need], i) => (
          <li key={who} style={{ ['--tilt' as string]: `${[-4, 3, -2, 5, -3][i]}deg`, ['--lift' as string]: `${[0, 34, 8, 40, 14][i]}px` }}>
            <button className="mq-paper th-scene" aria-label={`${who} ${need}`}>{plans[i] && <FloorPlan plan={scenePlan(plans[i]!)} compact />}</button>
            <span className="mq-tag"><b>{who}</b>{need}</span>
          </li>
        ))}
      </ul>
      <p className="mq-foot">Five real floor plans from the scans. Pick one up, or write your own line.</p>
    </>
  )
}

/* (b) The city as a table of blocks. Block height is the number of scans at the address. */
function CityTable() {
  const city = useCity()
  const cands = city?.candidates ?? NONE
  const audits = useAudits(useMemo(() => cands.map((c) => c.sid), [cands]))
  const read = cands.slice(0, READ).filter((c) => audits[c.sid]), current = cands[READ]
  const ranked = [...read].sort((x, y) => rank(audits[x.sid], audits[y.sid]))
  const best = ranked[0] && audits[ranked[0].sid]

  const layers = useMemo(() => !city ? [] : [
    new ColumnLayer<Place>({ id: 'blocks', data: city.houston, getPosition: (p) => [p.lon, p.lat], diskResolution: 4, angle: 45, radius: 46, extruded: true,
      getElevation: (p) => 30 + p.scans * 38, getFillColor: [240, 244, 232], material: { ambient: 0.72, diffuse: 0.5, shininess: 0, specularColor: [0, 0, 0] } }),
  ], [city])
  const pins: Pin[] = cands.map((c, i) => {
    const a = audits[c.sid], r = ranked.findIndex((x) => x.sid === c.sid), state = r >= 0 ? 'read' : i === READ ? 'now' : 'wait'
    return { key: c.sid, lon: c.lon, lat: c.lat, node: (
      <div className="mq-pin" data-state={state} data-best={r === 0 || undefined} style={{ ['--h' as string]: `${r === 0 ? 96 : 34 + (i % 3) * 30}px` }}>
        {state === 'read' && <span className="mq-tag"><i className="mq-tag-n">{r + 1}</i><i className="glyph" data-s={a.traced ? a.worst?.status : 'unknown'} />{a.traced && a.worst?.measured != null ? `${m2(a.worst.measured)} m` : 'no route'}{r === 0 && <b>{c.street}</b>}</span>}
        {state === 'now' && <span className="mq-tag mq-tag-now">reading<b>{c.street}</b></span>}
        <i className="mq-string" /><i className="mq-foot-dot" />
      </div>) }
  })
  return (
    <>
      {city && <StudyMap className="stage" palette={MAT} layers={layers} pins={pins} names={false}
        camera={{ center: [(city.focus.lon + cands.at(-1)!.lon) / 2 + 0.004, (city.focus.lat + cands.at(-1)!.lat) / 2 - 0.006], zoom: 12.7, pitch: 54, bearing: -30 }} />}
      <Print place="Clear Lake, Houston" note="Block height = scans at the address · © OpenStreetMap, OpenFreeMap" />
      <Big value={read.length} unit={`/${cands.length}`}>houses read<br />{STEPS[2].toLowerCase()}</Big>
      <Sheets on />
      {best && current && (
        <div className="mq-card">
          <p className="mq-card-k">Step 3 of {STEPS.length} · closest so far</p>
          <p className="mq-card-v">{ranked[0].street}</p>
          <p className="mq-card-t">{best.under} doorways to widen. None of the {read.length} read so far clears {PREFS.door} m at every doorway.</p>
          <p className="mq-card-k mq-card-s">Reading {current.street} · {cands.length - READ - 1} waiting</p>
        </div>
      )}
    </>
  )
}

/* (c) The building: a card model cut open on the mat, the way in laid through it in tape, the doorways tagged. */
function Model() {
  const city = useCity(), audit = useAudit(FOCUS)
  const overlays = useMemo(() => (audit ? sceneOverlays(audit.result) : []), [audit])
  if (!audit) return null
  const r = audit.result, w = audit.worst!, hit = doorOf(r, w), under = r.metrics.find((m) => m.id === 'under')
  const doors = r.checks.filter((c) => c.measured != null && c.id !== 'turning')
  const prints = doors.filter((c) => c.status !== 'pass').sort((x, y) => x.measured! - y.measured!).slice(0, 2)
  return (
    <>
      <div className="stage"><BuildingScene plan={scenePlan(audit.plan)} overlays={overlays} view={CUT} /></div>
      <Print place={`${city?.focus.street ?? ''}, Houston`} note="Mat grid 1 m, heavy lines 5 m" />
      <Big value={m2(w.measured!)} unit="m">{hit.finding?.title}<br />{m2(w.threshold! - w.measured!)} m short of the {w.threshold} m you need</Big>
      <Sheets on />
      <div className="mq-card">
        <p className="mq-card-k">Step-free access · scan geometry, {hit.finding?.source.confidence} confidence</p>
        <p className="mq-card-v"><i className="glyph" data-s={r.verdict.status} />{under?.value} {under?.unit} doorways under your limit</p>
        <Scale doors={doors} limit={PREFS.door} />
      </div>
      <div className="mq-photos">{prints.map((c, i) => <Photo key={c.id} audit={audit} check={c} i={i} />)}</div>
    </>
  )
}

function Photo({ audit, check, i }: { audit: Audit; check: Audit['result']['checks'][number]; i: number }) {
  const hit = doorOf(audit.result, check)
  const view = useMemo(() => lookAtDoor(audit.plan, hit.opening), [audit, hit.opening])
  const overlays = useMemo(() => sceneOverlays(audit.result).filter((o) => o.kind === 'rule'), [audit])
  return (
    <figure className="mq-photo" style={{ ['--tilt' as string]: `${i ? 3 : -4}deg` }}>
      <div>{view && <BuildingScene plan={scenePlan(audit.plan)} overlays={overlays} view={view} />}</div>
      <figcaption data-s={check.status}><i className="glyph" data-s={check.status} />{m2(check.measured!)} m<span>{hit.finding?.title.replace('Doorway to the ', '')} doorway</span></figcaption>
    </figure>
  )
}
