import { useEffect, useMemo, useState } from 'react'
import { CITIES, KINDS, navigate, searchMeasures, useBuildings, useWorkspace, type CityId, type Kind } from '../../../core/index.ts'
import { PanelView } from '../blocks/blocks.tsx'
import { Empty, Icon, RunState, SourceChip } from '../design/ui.tsx'
import { int } from '../lib/format.ts'
import { facts, type FloodLevel } from '../lib/pending.ts'
import { familyOf } from '../lib/tools.ts'
import { startTool } from '../shell/StartTool.tsx'

/* City-level questions. The counts come from the server: search by measurement returns how many scans it looked at,
   how many could be answered, and how many match. Nothing is totalled here except rows of the building list. */
const CITY_IDS = Object.keys(CITIES) as CityId[]
const QUESTIONS: { label: string; where: string[] }[] = [
  { label: 'A wheelchair reaches a bathroom from the entrance', where: ['wheelchair_bath==1'] },
  { label: 'Step-free way to a bathroom', where: ['step_free_bath==1'] },
  { label: 'Bedroom and bathroom on the entrance floor', where: ['bed_bath_entry_floor==1'] },
  { label: 'One floor', where: ['floors==1'] },
  { label: 'Main entrance at least 0.815 m clear', where: ['entrance_width>=0.815'] },
  { label: 'Bathroom turning circle of 1.525 m', where: ['bath_turn>=1.525'] },
  { label: 'No step at any doorway', where: ['level_changes==0'] },
]
type Count = { pool: number; answerable: number; matches: number }
const asked = new Map<string, Count | 'error'>() // one request per question and city per visit
let queue: Promise<unknown> = Promise.resolve() // one at a time: the server is shared

function useCount(where: string[], city: CityId) {
  const key = `${city}|${where.join(';')}`
  const [, tick] = useState(0)
  useEffect(() => {
    if (asked.has(key)) return
    let on = true
    queue = queue.then(() => (asked.has(key) ? null : searchMeasures(where, { city: CITIES[city].name, limit: 1 }).then((r) => asked.set(key, { pool: r.pool, answerable: r.answerable, matches: r.matches }), () => asked.set(key, 'error')))).then(() => on && tick((n) => n + 1))
    return () => { on = false }
  }, [key]) // eslint-disable-line react-hooks/exhaustive-deps
  return asked.get(key)
}
function CountCell({ where, city }: { where: string[]; city: CityId }) {
  const c = useCount(where, city)
  if (!c) return <td className="barcell"><span className="sk" style={{ width: '60%' }} /></td>
  if (c === 'error') return <td className="muted">did not answer</td>
  return <td className="barcell" title={`${int(c.matches)} of the ${int(c.answerable)} scans that can be answered, out of ${int(c.pool)} in ${CITIES[city].name}`}><i style={{ width: `calc(${c.answerable ? (c.matches / c.answerable) * 100 : 0}% - 12px)` }} /><span><b>{int(c.matches)}</b> <span className="muted">of {int(c.answerable)}</span></span></td>
}

function Inventory() {
  const all = useBuildings((s) => s.all), state = useBuildings((s) => s.state)
  const rows = useMemo(() => {
    const per = (c: CityId) => {
      const list = all.filter((b) => b.metro === c), scans = list.flatMap((b) => b.scans)
      return { addresses: list.length, scans: scans.length, kind: Object.fromEntries(KINDS.map((k) => [k.id, scans.filter((s) => s.kind === k.id).length])) as Record<Kind, number>, drone: list.filter((b) => b.splat).length, empty: list.filter((b) => b.defurnished).length }
    }
    return Object.fromEntries(CITY_IDS.map((c) => [c, per(c)])) as Record<CityId, ReturnType<typeof per>>
  }, [all])
  const line = (label: string, get: (c: CityId) => number, of: (c: CityId) => number, strong = false) => (
    <tr key={label}><td className={strong ? 'strong' : undefined}>{label}</td>{CITY_IDS.map((c) => <td key={c} className="barcell">{!strong && <i style={{ width: `calc(${of(c) ? (get(c) / of(c)) * 100 : 0}% - 12px)` }} />}<span className={strong ? 'strong' : undefined}>{int(get(c))}</span></td>)}</tr>
  )
  return (
    <section className="card">
      <header><h2>What has been scanned</h2><p className="grow">Counted from the scan index. A bar is the share of that city’s scans (or addresses).</p><SourceChip source={{ layer: 'matterport', method: 'lookup', confidence: 'medium', note: 'The kind of space is read from each scan’s name and market segment, so treat the split as a guess.' }} /></header>
      {state === 'error' ? <Empty icon="warn" title="The building list did not load" /> : (
        <table className="tbl">
          <thead><tr><th scope="col">Scans by kind</th>{CITY_IDS.map((c) => <th key={c} scope="col" style={{ width: '30%' }}>{CITIES[c].name}</th>)}</tr></thead>
          <tbody>
            {line('All scans', (c) => rows[c].scans, () => 0, true)}
            {KINDS.map((k) => line(k.label, (c) => rows[c].kind[k.id], (c) => rows[c].scans))}
            {line('Addresses', (c) => rows[c].addresses, () => 0, true)}
            {line('Addresses with a drone capture', (c) => rows[c].drone, (c) => rows[c].addresses)}
            {line('Addresses with empty-room photos', (c) => rows[c].empty, (c) => rows[c].addresses)}
          </tbody>
        </table>
      )}
    </section>
  )
}

function Flood() {
  const [rows, setRows] = useState<FloodLevel[] | null | 'error'>(null)
  useEffect(() => { facts.fetchFloodWet?.().then(setRows, () => setRows('error')) }, [])
  return (
    <section className="card">
      <header><h2>Flood exposure</h2><p className="grow">Rooms and houses wet at three water depths, across the Houston houses in the flood series.</p></header>
      {!facts.fetchFloodWet ? <div className="body"><p className="note"><Icon name="info" size={13} /><span>Not connected yet. The flood series is in the facts database, and this page will chart it once the app can read it.</span></p></div>
        : rows === 'error' ? <Empty icon="warn" title="The facts database did not answer" />
        : !rows ? <div className="body"><span className="sk" style={{ width: '50%' }} /></div> : (
          <table className="tbl">
            <thead><tr><th scope="col">Water above the lowest floor</th><th scope="col" style={{ width: '32%' }}>Rooms wet</th><th scope="col" style={{ width: '32%' }}>Houses wet</th></tr></thead>
            <tbody>{rows.map((r) => <tr key={r.level_m}><td><span className="num">{r.level_m}</span> m</td><td className="barcell"><i style={{ width: `calc(${(Number(r.rooms_wet) / Number(r.rooms)) * 100}% - 12px)` }} /><span><b>{int(Number(r.rooms_wet))}</b> <span className="muted">of {int(Number(r.rooms))}</span></span></td><td className="barcell"><i style={{ width: `calc(${(r.houses_wet / r.houses) * 100}% - 12px)` }} /><span><b>{int(r.houses_wet)}</b> <span className="muted">of {int(r.houses)}</span></span></td></tr>)}</tbody>
          </table>
        )}
    </section>
  )
}

function Census() {
  const doc = useWorkspace((s) => s.doc)
  const panels = doc.panels.filter((p) => familyOf(p.tool) === 'database')
  const working = doc.runs.filter((r) => r.status === 'running' && familyOf(r.tool) === 'database')
  return (
    <section className="card">
      <header>
        <h2>Rollups from the facts database</h2><p className="grow">Listed against measured area by property type, accessible homes by zip code, typical door widths by city.</p>
        <button className="btn sm" onClick={() => startTool({ id: 'facts_query', form: true })}>Ask in SQL</button>
        <button className="btn sm" onClick={() => startTool({ id: 'city_census', form: true })}><Icon name="play" size={11} />Run a rollup</button>
      </header>
      {working.length > 0 && <div className="body stack">{working.map((r) => <RunState key={r.id} state="running">{r.label}{r.summary ? `: ${r.summary}` : ''}</RunState>)}</div>}
      {panels.length === 0 && working.length === 0 && <Empty icon="database" title="No rollup in this investigation yet" action={<button className="btn" onClick={() => startTool({ id: 'city_census', form: true })}>Run a rollup</button>}>A rollup counts one measured fact across every scanned building, by zip code, city or property type. Its result is kept here.</Empty>}
      {panels.map((p) => <PanelView key={p.id} panel={p} folded={panels.length > 1} />)}
    </section>
  )
}

export function Insights() {
  return (
    <div className="page"><div className="inner">
      <section className="card">
        <header><h2>Measured access</h2><p className="grow">How many scanned homes meet each condition. A bar is the share of the homes that could be answered.</p><SourceChip source={{ layer: 'matterport', method: 'geometry', confidence: 'medium', note: 'From each scan’s wall outline and doorways. A scan with no wall outline cannot be answered and is not in the denominator.' }} /></header>
        <table className="tbl">
          <thead><tr><th scope="col">Condition</th>{CITY_IDS.map((c) => <th key={c} scope="col" style={{ width: '26%' }}>{CITIES[c].name}</th>)}<th style={{ width: 132 }} /></tr></thead>
          <tbody>
            {QUESTIONS.map((q) => (
              <tr key={q.label}>
                <td>{q.label}</td>
                {CITY_IDS.map((c) => <CountCell key={c} where={q.where} city={c} />)}
                <td className="r"><button className="btn sm quiet" onClick={() => navigate('/map', { app_m: q.where.join(';'), app_view: 'split' })}>See them<Icon name="go" size={11} /></button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      <Inventory />
      <Flood />
      <Census />
    </div></div>
  )
}
