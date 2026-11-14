import { useEffect, useMemo, useRef, useState } from 'react'
import { Slider } from '@base-ui/react/slider'
import {
  CITIES, KINDS, ROOMS_MAX, fetchMeasureFields, navigate, search, searchMeasures, setQuery, useMapModel, useRoute, useWorkspace, userOp,
  type Building, type Doc, type Kind, type MeasureField, type MeasureHit,
} from '../../core/index.ts'
import { Desk, OpenQuestions, Plan } from './Desk.tsx'
import { Fig, Mark, Stat } from './parts.tsx'
import { PaperMap, type Numbered } from './PaperMap.tsx'
import { Story } from './Story.tsx'
import { useStories } from './stories.tsx'
import { headSize, plural, word } from './words.ts'

/* The city page. The map is figure 1; the column is the page being written about the city: what is selected, where
   the agent has been, and the two ways to find a building (by address, by what is measured inside it). */

const KIND_LABEL: Record<Kind, string> = { home: 'House', apartment: 'Apartment', amenity: 'Shared room', office: 'Office', other: 'Other' }
const verdictOf = (p: Doc['panels'][number]) => p.blocks.find((b) => b.type === 'VerdictHeader')

/** Buildings the agent has read, in the order of its latest ranking when it made one. */
function useNumbered(marks: Building[]): Numbered[] {
  const panels = useWorkspace((s) => s.doc.panels)
  return useMemo(() => {
    const table = panels.flatMap((p) => p.blocks).findLast((b) => b.type === 'RankedTable')
    const ranked = table?.type === 'RankedTable' ? table.rows.flatMap((r) => (r.anchor && 'sid' in r.anchor ? [r.anchor.sid] : [])) : []
    const order = (b: Building) => { const i = ranked.findIndex((sid) => b.scans.some((s) => s.sid === sid)); return i < 0 ? 1e6 : i }
    const read = marks.filter((b) => panels.some((p) => b.scans.some((s) => s.sid === p.sid)))
    return read.sort((x, y) => order(x) - order(y)).map((b, i) => ({ b, n: i + 1, best: i === 0 && order(b) === 0 }))
  }, [panels, marks])
}
/** The building the agent is reading now. A run names its scan at the end of its label, which is all a look is given. */
function useNow(all: Building[]): { b: Building | null; label: string | null } {
  const runs = useWorkspace((s) => s.doc.runs)
  return useMemo(() => {
    const r = runs.findLast((x) => x.status === 'running')
    if (!r) return { b: null, label: null }
    const tail = r.label.split(' · ').at(-1)!
    return { b: all.find((b) => b.address.split(',')[0] === tail || b.scans.some((s) => s.name === tail || s.sid === tail)) ?? null, label: r.label }
  }, [runs, all])
}

function Find({ all }: { all: Building[] }) {
  const { filters } = useMapModel()
  const [q, setQ] = useState('')
  const input = useRef<HTMLInputElement>(null)
  const hits = useMemo(() => search(all, q, 6), [all, q])
  useEffect(() => {
    const key = (e: KeyboardEvent) => { if (e.key === '/' && !/input|textarea|select/i.test((e.target as HTMLElement).tagName)) { e.preventDefault(); input.current?.focus() } }
    window.addEventListener('keydown', key)
    return () => window.removeEventListener('keydown', key)
  }, [])
  const toggle = (k: Kind) => setQuery({ kind: (filters.kinds.includes(k) ? filters.kinds.filter((x) => x !== k) : [...filters.kinds, k]).join(',') })
  const active = filters.kinds.length + +filters.drone + +filters.empty + +(filters.rooms[0] > 0 || filters.rooms[1] < ROOMS_MAX)
  return (
    <section className="sec" aria-labelledby="find-h">
      <header><h2 id="find-h">Find a building</h2>{active > 0 && <button className="link" onClick={() => setQuery({ kind: null, drone: null, empty: null, rooms: null })}>Clear filters</button>}</header>
      <input ref={input} className="field" style={{ marginTop: '0.5rem' }} value={q} onChange={(e) => setQ(e.target.value)} placeholder="An address or a unit type, in either city" aria-label="Find an address in either city" autoComplete="off" spellCheck={false}
        onKeyDown={(e) => { if (e.key === 'Enter' && hits[0]) { navigate('/map', { city: hits[0].metro ?? undefined, b: hits[0].id }, { keep: true }); setQ('') } if (e.key === 'Escape') setQ('') }} />
      {q && (
        <ul className="scans" aria-label="Addresses found">
          {hits.length === 0 && <li><p className="empty">No address matches “{q}”. Try a street name or a unit type such as “2BR”.</p></li>}
          {hits.map((b) => (
            <li key={b.id}><button className="open" onClick={() => { navigate('/map', { city: b.metro ?? undefined, b: b.id }, { keep: true }); setQ('') }}><b>{b.address}</b><span>{b.metro ? CITIES[b.metro].name : ''} · {b.count} {plural(b.count, 'scan')}</span></button></li>
          ))}
        </ul>
      )}
      <div className="filters" role="group" aria-label="Filter the buildings" title="The kind of space is read from the scan's name, so it is a guess">
        {KINDS.map((k) => <button key={k.id} aria-pressed={filters.kinds.includes(k.id)} onClick={() => toggle(k.id)}>{k.label}</button>)}
        <i className="sep" />
        <button aria-pressed={filters.drone} onClick={() => setQuery({ drone: filters.drone ? null : '1' })}>Drone capture</button>
        <button aria-pressed={filters.empty} onClick={() => setQuery({ empty: filters.empty ? null : '1' })}>Empty-room view</button>
      </div>
      <div className="control" style={{ borderBottom: 0, paddingBottom: 0 }}>
        <span style={{ font: '500 1.0625rem/1 var(--sans)' }}>Rooms in the largest scan</span>
        <span className="n">{filters.rooms[0]} to {filters.rooms[1] >= ROOMS_MAX ? `${ROOMS_MAX}+` : filters.rooms[1]}</span>
        <Slider.Root className="sliderroot" value={filters.rooms} min={0} max={ROOMS_MAX} minStepsBetweenValues={1}
          onValueChange={(v) => { const [lo, hi] = v as number[]; setQuery({ rooms: lo === 0 && hi === ROOMS_MAX ? null : `${lo}-${hi === ROOMS_MAX ? '' : hi}` }) }}>
          <Slider.Control className="slider"><Slider.Track className="track"><Slider.Indicator className="range" />
            <Slider.Thumb className="thumb" index={0} getAriaLabel={() => 'Fewest rooms'} /><Slider.Thumb className="thumb" index={1} getAriaLabel={() => 'Most rooms'} />
          </Slider.Track></Slider.Control>
        </Slider.Root>
      </div>
    </section>
  )
}

type Found = { pool: number; answerable: number; matches: number; rows: MeasureHit[] }
const OPS = ['>=', '<=', '=='] as const
/** Search by what is measured inside: criteria are built from the server's own list of measures. */
function Measure({ city, found, setFound }: { city: string; found: Found | null; setFound: (f: Found | null) => void }) {
  const [fields, setFields] = useState<Record<string, MeasureField> | null>(null)
  const [crit, setCrit] = useState<string[]>([])
  const [field, setField] = useState('bath_route_door'), [op, setOp] = useState<(typeof OPS)[number]>('>='), [value, setValue] = useState('0.815')
  const [state, setState] = useState<'idle' | 'busy' | string>('idle')
  useEffect(() => { fetchMeasureFields().then(setFields, () => setFields({})) }, [])
  const run = (where: string[]) => {
    setCrit(where)
    if (!where.length) { setFound(null); setState('idle'); return }
    setState('busy')
    searchMeasures(where, { city, limit: 12 }).then((r) => { setFound(r); setState('idle') }, (e: Error) => { setFound(null); setState(e.message) })
  }
  const f = fields?.[field], flag = f?.kind === 'flag'
  const label = (w: string) => { const [, k, o, v] = w.match(/^(\w+)(>=|<=|==)(.*)$/) ?? []; const m = fields?.[k]; return m ? `${m.label} ${o === '==' ? 'is' : o === '>=' ? 'at least' : 'at most'} ${v}${m.unit ? ` ${m.unit}` : ''}` : w }
  return (
    <section className="sec" aria-labelledby="measure-h">
      <h2 id="measure-h">Search by what is measured inside</h2>
      {fields && !Object.keys(fields).length ? <p className="empty">The measures did not load. The facts database may not be running.</p> : (
        <form className="measure" onSubmit={(e) => { e.preventDefault(); const v = flag ? '1' : value.trim(); if (v && Number.isFinite(+v)) run([...crit.filter((c) => !c.startsWith(field + op)), `${field}${flag ? '==' : op}${v}`]) }}>
          <select className="field" value={field} onChange={(e) => setField(e.target.value)} aria-label="Measure">
            {Object.entries(fields ?? {}).filter(([, m]) => m.kind !== 'text').map(([k, m]) => <option key={k} value={k}>{m.label}{m.unit ? ` (${m.unit})` : ''}</option>)}
          </select>
          {!flag && <select className="field" style={{ minWidth: '6.5rem' }} value={op} onChange={(e) => setOp(e.target.value as typeof op)} aria-label="Comparison"><option value=">=">at least</option><option value="<=">at most</option><option value="==">exactly</option></select>}
          {!flag && <input className="field n" style={{ width: '5.5rem', fontFamily: 'var(--mono)' }} inputMode="decimal" value={value} onChange={(e) => setValue(e.target.value)} aria-label="Value" />}
          <button className="btn">Add</button>
        </form>
      )}
      {f?.description && <p className="fig" style={{ marginTop: '0.5rem' }}>{f.description}.</p>}
      {crit.length > 0 && <div className="crit" aria-label="Criteria. Press one to remove it.">{crit.map((c) => <button key={c} onClick={() => run(crit.filter((x) => x !== c))} title="Remove">{label(c)} ×</button>)}</div>}
      {state === 'busy' && <div className="writing"><i className="unset" /><i className="unset" /></div>}
      {state !== 'busy' && state !== 'idle' && <p className="empty" role="alert">{state}</p>}
      {found && state === 'idle' && (
        <>
          <p className="fig" style={{ margin: '0.875rem 0 0.25rem' }}>{found.matches.toLocaleString('en-US')} of {found.answerable.toLocaleString('en-US')} homes where this was measured match ({found.pool.toLocaleString('en-US')} searched). Scan geometry, medium confidence. The first {found.rows.length} are ringed on the map.</p>
          <ol className="hits">
            {found.rows.map((r, i) => (
              <li key={r.sid}><button onClick={() => navigate(`/scan/${r.sid}`, {}, { keep: true })}><span className="rank">{i + 1}</span><span><b>{r.name}</b><small>{r.why.join(' · ')}</small></span></button></li>
            ))}
          </ol>
        </>
      )}
    </section>
  )
}

export function CityPage() {
  const route = useRoute()
  const m = useMapModel()
  const { stories } = useStories()
  // The city's story is one piece: the agent's notes lead, and its ranking and anything else about the city follow.
  const story = stories.findLast((p) => !p.blocks.some((b) => b.type === 'VerdictHeader') && p.blocks.some((b) => b.type === 'Note')) ?? stories.at(-1) ?? null
  const doc = useWorkspace((s) => s.doc)
  const [found, setFound] = useState<Found | null>(null)
  const numbered = useNumbered(m.marks), now = useNow(m.all)
  const open = route.q.get('b_o') === '1', aerial = route.q.get('b_v') === 'air'
  const city = CITIES[m.filters.city]
  const step = doc.plan.find((s) => s.status === 'active')?.label
  const working = !!step || doc.runs.some((r) => r.status === 'running')
  const hits = useMemo(() => (found?.rows ?? []).flatMap((r) => (r.lat != null && r.lon != null ? [{ lon: r.lon, lat: r.lat }] : [])), [found])
  const sel = m.selected, photo = !!m.look || (aerial && !!sel)

  const head = sel ? (
    <>
      <p className="kicker cap"><span>{city.name} edition</span>{sel.city && sel.city !== city.name && <span>{sel.city}</span>}<button className="link keep" onClick={() => m.select(null)}>Close</button></p>
      <h1 className="head" data-size={sel.address.split(',')[0].length > 22 ? 'm' : 'l'} key={sel.id}>{sel.address.split(',')[0]}</h1>
      <p className="deck"><b>{word(sel.count)}</b> {plural(sel.count, 'scan')} at this address{sel.splat ? ', with a drone capture' : ''}{sel.defurnished ? ', with an empty-room view' : ''}.</p>
    </>
  ) : working || (numbered.length && !found) ? (
    <>
      <p className="kicker cap"><span>{city.name} edition</span>{working && <span className="reading">The agent is at work</span>}</p>
      {numbered.length ? <h1 className="head" key={numbered.length}><Mark>{word(numbered.length)}</Mark> {plural(numbered.length, 'building')} read{working ? ' so far' : ''}.</h1>
        : <h1 className="head" data-size={headSize(step ?? '')} key={step}><span className="reading">{step ?? 'Starting the work'}</span></h1>}
      {now.label ? <p className="deck"><em>Reading {now.label} now.</em></p> : numbered.length > 0 && step && <p className="deck"><em>{step}.</em></p>}
    </>
  ) : found ? (
    <>
      <p className="kicker cap"><span>{city.name} edition</span><span>Search by measurement</span></p>
      <h1 className="head" key={found.matches}><Mark>{found.matches.toLocaleString('en-US')}</Mark> {plural(found.matches, 'home')} {found.matches === 1 ? 'matches' : 'match'} what you asked for.</h1>
    </>
  ) : (
    <>
      <p className="kicker cap"><span>{city.name} edition</span><span>{city.coord}</span></p>
      <h1 className="head">{m.state === 'ready' ? <><Mark>{m.shown.length.toLocaleString('en-US')}</Mark> scanned {plural(m.shown.length, 'building')} in {city.name}.</> : m.state === 'error' ? 'The building list did not load.' : <span className="reading">Reading the building list</span>}</h1>
      <p className="deck">Pick a dot on the map, find an address, or search by what is measured inside.</p>
    </>
  )

  return (
    <div className="page" data-open={open || undefined} data-plate={photo ? 'photo' : 'paper'}>
      <div className="col">
        <OpenQuestions />
        {story && !sel ? <Story key={`${story.id}:${story.run}`} panel={story} place={<span>{city.name} edition</span>} more={stories.filter((p) => p !== story)} /> : head}
        <Plan />
        {sel && (
          <section className="sec" aria-labelledby="scans-h">
            <h2 id="scans-h">At this address</h2>
            <ul className="scans">
              {sel.scans.map((s) => {
                const kept = doc.shortlist.some((x) => x.sid === s.sid)
                return (
                  <li key={s.sid}>
                    <button className="open" onClick={() => navigate(`/scan/${s.sid}`, { b: sel.id })}><b>{s.name}</b><span>{KIND_LABEL[s.kind]} · {s.rooms} {plural(s.rooms, 'room')} · {s.panos} scan {plural(s.panos, 'position')}</span></button>
                    <button className="link" aria-pressed={kept} aria-label={kept ? `Remove ${s.name} from the kept list` : `Keep ${s.name}`}
                      onClick={() => userOp(kept ? { op: 'shortlist.remove', sid: s.sid } : { op: 'shortlist.add', item: { sid: s.sid, name: s.name, address: sel.address } })}>{kept ? 'Kept' : 'Keep'}</button>
                  </li>
                )
              })}
            </ul>
            <p className="fig" style={{ marginTop: '0.5rem' }}>Room and scan counts come from the scan index. The kind of space is read from the scan’s name, so treat it as a guess.</p>
          </section>
        )}
        {numbered.length > 0 && (
          <section className="sec" aria-labelledby="been-h">
            <h2 id="been-h">Where the agent has been</h2>
            <ol className="hits">
              {numbered.map(({ b, n }) => (
                <li key={b.id}>
                  <button onClick={() => m.select(b)} aria-current={sel?.id === b.id || undefined}><span className="rank">{n}</span><span><b>{b.address.split(',')[0]}</b>
                    {doc.panels.filter((p) => b.scans.some((s) => s.sid === p.sid)).slice(0, 6).map((p) => { const v = verdictOf(p); return <small key={p.id}>{v?.type === 'VerdictHeader' ? <Stat s={v.status}>{p.title}</Stat> : p.title}{b.scans.length > 1 && p.scope ? `, ${p.scope}` : ''}</small> })}
                  </span></button>
                </li>
              ))}
            </ol>
          </section>
        )}
        <Find all={m.all} />
        <Measure city={city.name} found={found} setFound={setFound} />
        <Desk />
      </div>
      <div className="stage">
        <PaperMap city={m.filters.city} buildings={m.shown} selected={sel} numbered={numbered} now={now.b} hits={hits} geo={m.geo} look={m.look} aerial={aerial} open={open} onSelect={m.select} />
        {m.state === 'error' && <div className="state" role="alert" style={{ background: 'var(--paper)' }}><p>The building list did not load. Is the data server running?</p><button className="btn" onClick={m.reload}>Try again</button></div>}
      </div>
      <figure className="figbar">
        <Fig n={1}>{m.shown.length.toLocaleString('en-US')} scanned {plural(m.shown.length, 'building')} in {city.name}; each dot is an address.{numbered.length > 0 && ' Numbers follow the list on the page.'}{now.b && ' The pencil ring is the one being read.'} Map © OpenStreetMap, OpenFreeMap.</Fig>
        <div className="views">
          {sel && <button aria-pressed={aerial} onClick={() => setQuery({ b_v: aerial ? null : 'air' })}>Aerial photograph</button>}
          <button className="open" onClick={() => setQuery({ b_o: open ? null : '1' })}>{open ? 'Back to the page' : 'Open the map'}</button>
        </div>
      </figure>
    </div>
  )
}
