import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { MapLibreOverlay } from '@deck.gl/maplibre'
import { ColumnLayer, PathLayer, ScatterplotLayer } from 'deck.gl'
import { Popover } from '@base-ui/react/popover'
import { Slider } from '@base-ui/react/slider'
import {
  CITIES, KINDS, MapLibre, Marker, ROOMS_MAX, fetchMeasureFields, mapStyle, navigate, orthoImage, search, searchMeasures, setQuery, useMapModel, useWorkspace, userOp,
  type Building, type CityId, type Kind, type MapPalette, type MeasureField, type MeasureHit, type Status,
} from '../../core/index.ts'
import { Photo } from './blocks.tsx'
import { block } from './state.ts'
import { fmt, reduced, street } from './lib.ts'
import { Big, Glyph, Icon, Print, Src } from './ui.tsx'

/* The city as a table of white blocks. Block height is the number of scans at the address. Where the agent has
   been there is a tag on a string; the building it is reading has a strip of tape; a path it drew outdoors is tape
   on the table. The mat's colours are repeated here from tokens.css because a canvas cannot read a CSS variable. */
const MAT: MapPalette = {
  ground: '#2c3532', water: '#242c29', waterLine: 'rgba(233,236,228,0.34)', green: '#343f3b', road: 'rgba(233,236,228,0.15)', roadMajor: 'rgba(233,236,228,0.46)',
  rail: 'rgba(233,236,228,0.15)', building: '#39443f', label: 'rgba(233,236,228,0.9)', labelMuted: 'rgba(233,236,228,0.6)', halo: '#2c3532',
}
const CARD: [number, number, number] = [246, 244, 236], TAPE: [number, number, number] = [255, 212, 58]
const STATUS_RGB: Record<Status, [number, number, number]> = { pass: [26, 127, 80], warn: [208, 138, 12], fail: [196, 40, 28], unknown: [150, 158, 152] }
const WIDE = -0.5 // a pitched view shows less ground than a flat one at the same zoom
/** The open part of the table: clear of what is printed at the left and the stack at the right; with an address
    card out, clear of that too, so the block it describes stands above it. */
const pad = (card: boolean) => (window.innerWidth > 760 ? { left: 470, right: document.querySelector('.mq-sheets .mq-sheet') ? 440 : 240, top: 40, bottom: card ? 400 : 0 } : { left: 0, right: 0, top: 300, bottom: card ? 300 : 110 })
const KIND_LABEL: Record<Kind, string> = { home: 'House', apartment: 'Apartment', amenity: 'Shared room', office: 'Office', other: 'Other' }

/* ---------- a thing tied to a place on the table: a tag on its string ---------- */
function Pinned({ map, at, children }: { map: MapLibre; at: [number, number]; children: ReactNode }) {
  const [host] = useState(() => document.createElement('div'))
  useEffect(() => { const m = new Marker({ element: host, anchor: 'bottom' }).setLngLat(at).addTo(map); return () => { m.remove() } }, [map, host, at[0], at[1]]) // eslint-disable-line react-hooks/exhaustive-deps
  return createPortal(children, host)
}
type Tag = { key: string; at: [number, number]; h: number; body: ReactNode; kind?: 'now' | 'hit' | 'pin'; onClick?: () => void; label: string }

function Table({ shown, selected, tags, paths, pins, hits, city, look, onSelect }: {
  shown: Building[]; selected: Building | null; tags: Tag[]; paths: [number, number][][]; pins: { lon: number; lat: number; status: Status }[]; hits: MeasureHit[]
  city: CityId; look: [number, number] | null; onSelect: (b: Building | null) => void
}) {
  const el = useRef<HTMLDivElement>(null), overlay = useRef<MapLibreOverlay | null>(null)
  const [map, setMap] = useState<MapLibre | null>(null)
  const live = useRef({ shown, selected, paths, pins, hits, onSelect })
  live.current = { shown, selected, paths, pins, hits, onSelect }

  const draw = () => {
    const m = map, o = overlay.current
    if (!m || !o) return
    const { shown: data, selected: sel, paths: tape, pins: marks, hits: found } = live.current
    const z = m.getZoom(), mpp = (40075016.686 * Math.cos((m.getCenter().lat * Math.PI) / 180)) / (512 * 2 ** z)
    const r = Math.max(2.6, Math.min(11, 2.6 + (z - 9.5) * 1.5)) // a block stays a readable size from the whole city down to one street
    o.setProps({
      layers: [
        new ColumnLayer<Building>({
          id: 'blocks', data, getPosition: (b) => [b.lon, b.lat], diskResolution: 4, angle: 45, radius: r, radiusUnits: 'pixels', extruded: true,
          getElevation: (b) => 5 + Math.min(b.count, 32) * 1.9, elevationScale: mpp, // heights in screen pixels: one more scan, one more step
          getFillColor: (b) => (b.id === sel?.id ? TAPE : CARD), material: { ambient: 0.46, diffuse: 0.8, shininess: 0, specularColor: [0, 0, 0] }, // matte card: the faces differ by light alone
          pickable: true, autoHighlight: true, highlightColor: [...TAPE, 150], onClick: ({ object }) => live.current.onSelect(object ?? null),
          updateTriggers: { getFillColor: sel?.id },
        }),
        new PathLayer<[number, number][]>({ id: 'tape', data: tape, getPath: (d) => d, widthUnits: 'pixels', getWidth: 6, getColor: TAPE, capRounded: false, jointRounded: false }),
        new ScatterplotLayer<MeasureHit>({ id: 'hits', data: found.filter((h) => h.lon != null && h.lat != null), getPosition: (h) => [h.lon!, h.lat!], radiusUnits: 'pixels', getRadius: r + 5, filled: false, stroked: true, getLineColor: TAPE, lineWidthUnits: 'pixels', getLineWidth: 2 }),
        new ScatterplotLayer<{ lon: number; lat: number; status: Status }>({ id: 'pins', data: marks, getPosition: (d) => [d.lon, d.lat], radiusUnits: 'pixels', getRadius: 6, getFillColor: (d) => STATUS_RGB[d.status], stroked: true, getLineColor: CARD, lineWidthUnits: 'pixels', getLineWidth: 2 }),
      ],
    })
  }

  useEffect(() => {
    const start = live.current.selected
    const m = new MapLibre({
      container: el.current!, style: mapStyle(MAT), attributionControl: false, maxPitch: 68, minZoom: 3, maxZoom: 19,
      center: start ? [start.lon, start.lat] : CITIES[city].center, zoom: start ? 15.5 : CITIES[city].zoom + WIDE, pitch: 52, bearing: -22,
    })
    // the city sits in the open part of the table, clear of what is printed at the left and the stack at the right
    m.setPadding(pad(!!start))
    overlay.current = new MapLibreOverlay({ interleaved: false, layers: [], getCursor: ({ isHovering, isDragging }) => (isDragging ? 'grabbing' : isHovering ? 'pointer' : 'grab') })
    m.addControl(overlay.current as never)
    m.on('load', () => setMap(m))
    const ro = new ResizeObserver(() => m.resize())
    ro.observe(el.current!)
    return () => { ro.disconnect(); m.remove(); setMap(null) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  useEffect(() => { if (!map) return; draw(); map.on('zoom', draw); return () => { map.off('zoom', draw) } }, [map]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(draw, [shown, selected, paths, pins, hits]) // eslint-disable-line react-hooks/exhaustive-deps

  // Moves. Reduced motion jumps; otherwise the table turns under you, slow at both ends.
  const go = (to: { center: [number, number]; zoom: number }, ms: number) => { if (!map) return; const o = { ...to, padding: pad(!!live.current.selected) }; if (reduced()) map.jumpTo(o); else map.flyTo({ ...o, duration: ms, curve: 1.3, essential: true }) }
  const firstCity = useRef(true)
  useEffect(() => { if (!map) return; if (firstCity.current) { firstCity.current = false; return } if (live.current.selected?.metro !== city) go({ center: CITIES[city].center, zoom: CITIES[city].zoom + WIDE }, 2400) }, [city, map]) // eslint-disable-line react-hooks/exhaustive-deps
  const lookKey = look?.join(',')
  useEffect(() => { if (look) go({ center: look, zoom: 17.2 }, 1500) }, [lookKey, map]) // close enough to read the marks, far enough to keep the blocks around it // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!map || look) return
    if (!selected) { map.easeTo({ padding: pad(false), duration: reduced() ? 0 : 500 }); return }
    go({ center: [selected.lon, selected.lat], zoom: Math.max(map.getZoom(), 15.2) }, map.getZoom() < 13 ? 1500 : 700)
  }, [selected?.id, map]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div ref={el} className="mq-table" role="application" aria-label={`The ${CITIES[city].name} table: scanned buildings as blocks. Use the address field to choose one from the keyboard.`}>
      {map && tags.map((t) => (
        <Pinned key={t.key} map={map} at={t.at}>
          <button className="mq-pinned" data-kind={t.kind} style={{ ['--h' as string]: `${t.h}px` }} onClick={t.onClick} aria-label={t.label}>
            <span className={t.kind === 'now' ? 'mq-tag mq-tape' : 'mq-tag'}>{t.body}</span><i className="string" /><i className="foot" />
          </button>
        </Pinned>
      ))}
    </div>
  )
}

/* ---------- the label beside a block: the scans at one address ---------- */
function Address({ b, onClose }: { b: Building; onClose: () => void }) {
  const shortlist = useWorkspace((s) => s.doc.shortlist)
  const ref = useRef<HTMLElement>(null)
  useEffect(() => { const at = document.activeElement; if (!at || at === document.body || at.tagName === 'CANVAS') ref.current?.querySelector<HTMLElement>('.open')?.focus({ preventScroll: true }) }, [b.id])
  return (
    <section className="mq-address mq-paper" ref={ref} role="dialog" aria-label={`Scans at ${b.address}`} onKeyDown={(e) => e.key === 'Escape' && onClose()}>
      <header>
        <div><h2>{street(b.address)}</h2><p className="mq-dim">{[b.city || (b.metro ? CITIES[b.metro].name : ''), `${b.count} ${b.count === 1 ? 'scan' : 'scans'}`].filter(Boolean).join(' · ')}</p></div>
        <button className="mq-x" aria-label="Close" onClick={onClose}><Icon name="close" size={14} /></button>
      </header>
      <div className="body">
        <figure className="mq-pic"><Photo src={orthoImage(b.lat, b.lon, 90, 512)} alt="" /><figcaption className="mq-caps">From the air, 90 m across</figcaption></figure>
        <div className="has">
          {b.splat && <span className="mq-caps">Drone capture</span>}
          {b.defurnished && <span className="mq-caps">Empty-room view</span>}
          <Src source={{ layer: 'matterport', method: 'lookup', confidence: 'high', note: 'Room and scan counts come from the scan index. The kind of space is read from the scan name, so treat it as a guess.' }} />
        </div>
      </div>
      <ul>
        {b.scans.map((s) => {
          const kept = shortlist.some((x) => x.sid === s.sid)
          return (
            <li key={s.sid}>
              <button className="open" onClick={() => navigate(`/scan/${s.sid}`, { b: b.id }, { keep: true })}><b>{s.name}</b><small>{KIND_LABEL[s.kind]} · <span className="mq-num">{s.rooms}</span> {s.rooms === 1 ? 'room' : 'rooms'}</small></button>
              <button className="mq-x" aria-pressed={kept} aria-label={kept ? `Remove ${s.name} from the kept list` : `Keep ${s.name}`}
                onClick={() => userOp(kept ? { op: 'shortlist.remove', sid: s.sid } : { op: 'shortlist.add', item: { sid: s.sid, name: s.name, address: b.address } })}><Icon name={kept ? 'kept' : 'keep'} size={16} /></button>
            </li>
          )
        })}
      </ul>
    </section>
  )
}

/* ---------- find an address ---------- */
function Find({ all }: { all: Building[] }) {
  const [q, setQ] = useState(''), [open, setOpen] = useState(false), [at, setAt] = useState(0)
  const input = useRef<HTMLInputElement>(null)
  const hits = useMemo(() => search(all, q), [all, q])
  useEffect(() => {
    const key = (e: KeyboardEvent) => { if (e.key === '/' && !/input|textarea|select/i.test((e.target as HTMLElement).tagName)) { e.preventDefault(); input.current?.focus() } }
    window.addEventListener('keydown', key)
    return () => window.removeEventListener('keydown', key)
  }, [])
  const pick = (b: Building) => { navigate('/map', { city: b.metro ?? undefined, b: b.id }, { keep: true }); setOpen(false); setQ(''); input.current?.blur() }
  return (
    <div className="mq-find" role="combobox" aria-expanded={open && q.length > 0} aria-haspopup="listbox" aria-controls="mq-find-hits">
      <Icon name="search" size={14} />
      <input ref={input} value={q} placeholder="Find an address" aria-label="Find an address in either city" autoComplete="off" spellCheck={false}
        onChange={(e) => { setQ(e.target.value); setOpen(true); setAt(0) }} onFocus={() => setOpen(true)} onBlur={() => setTimeout(() => setOpen(false), 120)}
        onKeyDown={(e) => {
          if (e.key === 'ArrowDown') { e.preventDefault(); setAt((i) => Math.min(hits.length - 1, i + 1)) }
          if (e.key === 'ArrowUp') { e.preventDefault(); setAt((i) => Math.max(0, i - 1)) }
          if (e.key === 'Enter' && hits[at]) pick(hits[at])
          if (e.key === 'Escape') { setQ(''); input.current?.blur() }
        }} />
      {open && q && (
        <ul id="mq-find-hits" role="listbox" className="mq-paper">
          {!hits.length && <li className="none">No address matches “{q}”. Try a street name, or a unit type such as “2BR”.</li>}
          {hits.map((b, i) => (
            <li key={b.id} role="option" aria-selected={i === at} onMouseDown={(e) => { e.preventDefault(); pick(b) }} onMouseEnter={() => setAt(i)}>
              <b>{b.address}</b><small>{b.metro ? CITIES[b.metro].name : ''} · <span className="mq-num">{b.count}</span> {b.count === 1 ? 'scan' : 'scans'}</small>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

/* ---------- search by what is measured inside ---------- */
const OPS = ['>=', '<=', '=='] as const
function ByMeasure({ city, hits, onHits, all }: { city: CityId; hits: MeasureHit[]; onHits: (h: MeasureHit[]) => void; all: Building[] }) {
  const [fields, setFields] = useState<Record<string, MeasureField> | null>(null)
  const [where, setWhere] = useState<string[]>([]), [field, setField] = useState('narrowest_door'), [op, setOp] = useState<string>('>='), [val, setVal] = useState('')
  const [state, setState] = useState<{ say: string; busy?: boolean } | null>(null)
  const load = () => { if (!fields) fetchMeasureFields().then(setFields, (e: Error) => setState({ say: e.message })) }
  const run = (w: string[]) => {
    setWhere(w)
    if (!w.length) { onHits([]); setState(null); return }
    setState({ say: 'Searching the measurements', busy: true })
    searchMeasures(w, { city: CITIES[city].name, limit: 40 }).then(
      (r) => { onHits(r.rows); setState({ say: `${r.matches} of ${r.answerable} homes with these measurements match${r.matches > r.rows.length ? `; the first ${r.rows.length} are marked` : ''}.` }) },
      (e: Error) => { onHits([]); setState({ say: e.message }) })
  }
  const f = fields?.[field]
  return (
    <Popover.Root onOpenChange={(o) => o && load()}>
      <Popover.Trigger className="mq-toggle" aria-pressed={where.length > 0}>By measurement{where.length > 0 && <span className="mq-num"> {hits.length}</span>}</Popover.Trigger>
      <Popover.Portal><Popover.Positioner className="mq-popper" side="bottom" align="start" sideOffset={8}><Popover.Popup className="mq-pop mq-measure">
        <span className="mq-caps">Find homes by what is measured inside</span>
        <form className="mq-row" onSubmit={(e) => { e.preventDefault(); if (val.trim()) { run([...where, `${field}${op}${val.trim()}`]); setVal('') } }}>
          <select className="mq-field" value={field} onChange={(e) => setField(e.target.value)} aria-label="Measure" style={{ width: 190 }}>
            {fields ? Object.entries(fields).map(([k, x]) => <option key={k} value={k}>{x.label}</option>) : <option>Loading</option>}
          </select>
          <select className="mq-field mq-num" value={op} onChange={(e) => setOp(e.target.value)} aria-label="Comparison" style={{ width: 66 }}>{OPS.map((o) => <option key={o}>{o}</option>)}</select>
          <input className="mq-field mq-num" style={{ width: 84 }} inputMode={f?.kind === 'text' ? undefined : 'decimal'} value={val} onChange={(e) => setVal(e.target.value)} placeholder={f?.unit || 'value'} aria-label="Value" />
          <button className="mq-btn is-ink is-sm" disabled={!val.trim() || !fields}>Add</button>
        </form>
        {f && <p className="mq-dim">{f.description}</p>}
        {where.length > 0 && <div className="mq-row">{where.map((w) => <button key={w} className="mq-chip mq-num" aria-label={`Remove ${w}`} onClick={() => run(where.filter((x) => x !== w))}>{w} <Icon name="close" size={10} /></button>)}</div>}
        {state && <p role="status" data-busy={state.busy || undefined}>{state.say}</p>}
        {hits.length > 0 && (
          <ul className="mq-hits">
            {hits.map((h) => {
              const b = all.find((x) => x.scans.some((s) => s.sid === h.sid))
              return <li key={h.sid}><Popover.Close className="open" onClick={() => (b ? navigate('/map', { b: b.id }, { keep: true }) : navigate(`/scan/${h.sid}`, {}, { keep: true }))}><b>{h.name}</b><small>{[street(h.address), ...h.why].filter(Boolean).join(' · ')}</small></Popover.Close></li>
            })}
          </ul>
        )}
      </Popover.Popup></Popover.Positioner></Popover.Portal>
    </Popover.Root>
  )
}

export function City() {
  const m = useMapModel()
  const doc = useWorkspace((s) => s.doc)
  const [hits, setHits] = useState<MeasureHit[]>([])
  const { filters, shown, selected } = m
  useEffect(() => setHits([]), [filters.city])

  // What the agent has left on the table: a tag on every building it has a sheet for (the sheet's verdict and first
  // figure, as given), its rank where a table ranks it, tape on the one it is reading now.
  const tags = useMemo<Tag[]>(() => {
    const out: Tag[] = [], seen = new Set<string>()
    const ranked = doc.panels.flatMap((p) => p.blocks).findLast((b) => b.type === 'RankedTable')
    const rank = (b: Building) => (ranked?.type === 'RankedTable' ? ranked.rows.findIndex((r) => r.anchor && 'sid' in r.anchor && b.scans.some((s) => s.sid === (r.anchor as { sid: string }).sid)) : -1)
    const running = doc.runs.filter((r) => r.status === 'running')
    for (const r of running) { // a run's label ends with its scan's name
      const b = m.all.find((x) => x.scans.some((s) => r.label.endsWith(s.name)))
      if (!b || seen.has(b.id)) continue
      seen.add(b.id)
      out.push({ key: `now-${b.id}`, at: [b.lon, b.lat], h: 78, kind: 'now', label: `The agent is reading ${street(b.address)}`, body: <><i className="pulse" />reading<b>{street(b.address)}</b></>, onClick: () => m.select(b) })
    }
    m.marks.forEach((b, i) => {
      if (seen.has(b.id)) return
      seen.add(b.id)
      const p = doc.panels.findLast((x) => b.scans.some((s) => s.sid === x.sid)), v = block(p, 'VerdictHeader'), mt = block(p, 'MetricRow')?.metrics.find((x) => x.value != null), n = rank(b)
      out.push({
        key: `mark-${b.id}`, at: [b.lon, b.lat], h: n === 0 ? 92 : 30 + (i % 3) * 22, label: `${street(b.address)}${v ? `: ${v.text}` : ', kept'}`,
        body: <>{n >= 0 && <span className="rank">{n + 1}</span>}{v && <Glyph status={v.status} size={10} />}{mt ? <>{fmt(mt.value)} {mt.unit}</> : !p && 'kept'}{(n === 0 || b.id === selected?.id) && <b>{street(b.address)}</b>}</>,
        onClick: () => (p?.sid ? navigate(`/scan/${p.sid}`, { b: b.id, c_p: p.id }, { keep: true }) : m.select(b)),
      })
    })
    if (selected && !seen.has(selected.id)) out.push({ key: `sel-${selected.id}`, at: [selected.lon, selected.lat], h: 54, kind: 'now', label: street(selected.address), body: <b>{street(selected.address)}</b> })
    hits.slice(0, 10).forEach((h, i) => {
      const b = m.all.find((x) => x.scans.some((s) => s.sid === h.sid))
      if (h.lon == null || h.lat == null || (b && seen.has(b.id))) return
      if (b) seen.add(b.id)
      out.push({ key: `hit-${h.sid}`, at: [h.lon, h.lat], h: 26 + (i % 3) * 20, kind: 'hit', label: `${h.name}: ${h.why.join(', ')}`, body: <>{h.why[0] ?? h.name}</>, onClick: () => (b ? m.select(b) : navigate(`/scan/${h.sid}`, {}, { keep: true })) })
    })
    m.geo.pins.forEach((p, i) => out.push({ key: `pin-${i}`, at: [p.lon, p.lat], h: 30 + (i % 2) * 20, kind: 'pin', label: p.label, body: <><Glyph status={p.status} size={10} /><b>{p.label}</b></> }))
    return out
  }, [doc.panels, doc.runs, m.marks, m.all, m.geo.pins, selected, hits]) // eslint-disable-line react-hooks/exhaustive-deps

  const now = doc.plan.find((s) => s.status === 'active'), working = !!now || doc.runs.some((r) => r.status === 'running')
  const ran = doc.runs.filter((r) => !now || r.step === now.id), done = ran.filter((r) => r.status !== 'running').length
  const toggleKind = (k: Kind) => setQuery({ kind: (filters.kinds.includes(k) ? filters.kinds.filter((x) => x !== k) : [...filters.kinds, k]).join(',') })
  const rooms = filters.rooms[0] > 0 || filters.rooms[1] < ROOMS_MAX
  const active = filters.kinds.length + +filters.drone + +filters.empty + +rooms

  return (
    <main className="mq-city">
      <Table shown={shown} selected={selected} tags={tags} paths={m.geo.paths} pins={m.geo.pins} hits={hits} city={filters.city} look={m.look} onSelect={m.select} />
      <Print onHome={() => navigate('/')}>
        <div className="mq-cities" role="group" aria-label="City">
          {(Object.keys(CITIES) as CityId[]).map((id) => <button key={id} aria-pressed={filters.city === id} onClick={() => navigate('/map', { city: id, b: null }, { keep: true })}>{CITIES[id].name}</button>)}
        </div>
        <Find all={m.all} />
      </Print>
      <div className="mq-lead">
      {working && ran.length > 0
        ? <Big value={done} unit={`/${ran.length}`} digits={0}>{now?.label ?? 'Tools running'}<br /><span className="mq-dim">{ran.findLast((r) => r.status === 'running')?.label ?? 'read so far'}</span></Big>
        : <Big value={m.state === 'ready' ? shown.length : null} digits={0}>
            {m.state === 'error' ? <>The building list did not load. <button className="mq-link" onClick={m.reload}>Try again</button></> : <>{active ? 'buildings pass the filters' : 'buildings on the table'}<br /><span className="mq-dim">{CITIES[filters.city].name} · {CITIES[filters.city].coord}</span></>}
          </Big>}
      <div className="mq-filters" role="group" aria-label="Filter the buildings">
        <div title="Read from the scan name, so a guess">{KINDS.map((k) => <button key={k.id} className="mq-toggle" aria-pressed={filters.kinds.includes(k.id)} onClick={() => toggleKind(k.id)}>{k.label}</button>)}</div>
        <div>
          <button className="mq-toggle" aria-pressed={filters.drone} onClick={() => setQuery({ drone: filters.drone ? null : '1' })}>Drone capture</button>
          <button className="mq-toggle" aria-pressed={filters.empty} onClick={() => setQuery({ empty: filters.empty ? null : '1' })}>Empty-room view</button>
          <Popover.Root>
            <Popover.Trigger className="mq-toggle" aria-pressed={rooms}>Rooms <span className="mq-num">{filters.rooms[0]} to {filters.rooms[1] >= ROOMS_MAX ? `${ROOMS_MAX}+` : filters.rooms[1]}</span></Popover.Trigger>
            <Popover.Portal><Popover.Positioner className="mq-popper" side="bottom" align="start" sideOffset={8}><Popover.Popup className="mq-pop" style={{ width: 280 }}>
              <span className="mq-caps">Rooms in the largest scan at an address</span>
              <Slider.Root value={filters.rooms} min={0} max={ROOMS_MAX} minStepsBetweenValues={1}
                onValueChange={(v) => { const [lo, hi] = v as number[]; setQuery({ rooms: lo === 0 && hi === ROOMS_MAX ? null : `${lo}-${hi === ROOMS_MAX ? '' : hi}` }) }}>
                <Slider.Control className="mq-slider"><Slider.Track className="mq-track"><Slider.Indicator className="mq-range" />
                  <Slider.Thumb className="mq-thumb" index={0} getAriaLabel={() => 'Fewest rooms'} /><Slider.Thumb className="mq-thumb" index={1} getAriaLabel={() => 'Most rooms'} />
                </Slider.Track></Slider.Control>
              </Slider.Root>
              <div className="mq-row mq-num mq-dim" style={{ justifyContent: 'space-between' }}><span>0</span><span>{ROOMS_MAX}+</span></div>
            </Popover.Popup></Popover.Positioner></Popover.Portal>
          </Popover.Root>
          <ByMeasure city={filters.city} hits={hits} onHits={setHits} all={m.all} />
          {active > 0 && <button className="mq-link" onClick={() => setQuery({ kind: null, drone: null, empty: null, rooms: null })}>Clear</button>}
        </div>
      </div>
      </div>
      {selected && <Address b={selected} onClose={() => m.select(null)} />}
      <p className="mq-legend mq-caps mq-dim">Block height: scans at the address · © OpenStreetMap, OpenFreeMap</p>
    </main>
  )
}
