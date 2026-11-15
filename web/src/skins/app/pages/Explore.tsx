import { useEffect, useMemo, useState } from 'react'
import { Popover } from '@base-ui/react/popover'
import {
  BASE_VIEWS, CITIES, KINDS, ROOMS_MAX, fetchLayers, fetchMeasureFields, navigate, orthoImage, searchMeasures, setQuery, useMapModel, useRoute, useWorkspace, userOp,
  type BaseView, type Building as BuildingRow, type CityId, type Kind, type MapLayer, type MeasureField, type MeasureHit,
} from '../../../core/index.ts'
import { DataTable, Empty, Icon, IconBtn, Menu, MenuBtn, RunState, Seg, SourceChip, useColumns, type Col } from '../design/ui.tsx'
import { int, num, plural } from '../lib/format.ts'
import { goScan } from '../lib/place.ts'
import { Legend, MapNav, MapTools, SunBar, WeatherChip, sunInstant, sunNow, type SunAt } from '../explore/Controls.tsx'
import { useHandoff } from '../explore/useHandoff.ts'
import { WorldMap, useWorld } from '../explore/WorldMap.tsx'
import '../explore/explore.css'
import { Building } from './Building.tsx'
import { useScheme } from '../shell/theme.ts'
import { useIsPhone } from '../shell/store.ts'
import { Edge, Fill, Pane, Split } from '../design/split.tsx'

const KIND_LABEL: Record<Kind, string> = { home: 'House', apartment: 'Apartment', amenity: 'Shared room', office: 'Office', other: 'Other' }
type View = 'map' | 'split' | 'table'
/** Criteria in the address bar: `app_m=floors==1;bath_route_door>=0.81`. */
const readWhere = (q: URLSearchParams) => (q.get('app_m') ?? '').split(';').filter(Boolean)
const PRESETS: { label: string; where: string[] }[] = [
  { label: 'A wheelchair reaches a bathroom from the entrance', where: ['wheelchair_bath==1'] },
  { label: 'One floor, bathroom through 0.81 m doors', where: ['floors==1', 'bath_route_door>=0.81'] },
  { label: 'Room for a piano: 3 m living-room wall, 2.9 m ceiling, 0.85 m entrance', where: ['living_wall>=3', 'ceiling_median>=2.9', 'entrance_width>=0.85'] },
]
const parse = (c: string) => { const m = c.match(/^([a-z_]+)(>=|<=|==|>|<)(.+)$/); return m ? { field: m[1], op: m[2], value: m[3] } : null }

/* ---------- search by measurement: field, operator, value ---------- */
function MeasureBuilder({ where, fields }: { where: string[]; fields: Record<string, MeasureField> | null }) {
  const [open, setOpen] = useState(false)
  const [rows, setRows] = useState<{ field: string; op: string; value: string }[]>([])
  useEffect(() => { if (open) setRows(where.map(parse).filter((x): x is NonNullable<typeof x> => !!x).concat(where.length ? [] : [{ field: 'bath_route_door', op: '>=', value: '0.81' }])) }, [open]) // eslint-disable-line react-hooks/exhaustive-deps
  const apply = (w: string[]) => { setQuery({ app_m: w.join(';') || null, b: null }, false); setOpen(false) }
  const ok = rows.length > 0 && rows.every((r) => r.field && r.value.trim() !== '' && Number.isFinite(+r.value))
  const set = (i: number, patch: Partial<(typeof rows)[number]>) => setRows(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)))
  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger className="chip" render={<button type="button" aria-pressed={where.length > 0} />}><Icon name="ruler" size={13} />{where.length ? `Measured: ${plural(where.length, 'criterion', 'criteria')}` : 'Search by measurement'}</Popover.Trigger>
      <Popover.Portal><Popover.Positioner sideOffset={6} align="start" style={{ zIndex: 60 }}><Popover.Popup className="pop builder">
        <h4>Find homes by what is measured inside them</h4>
        <p className="muted small">Every criterion must hold. Only scans whose walls and doors were measured can be answered.</p>
        {!fields ? <span className="sk" style={{ width: '70%', margin: '12px 0' }} /> : (
          <form className="stack" onSubmit={(e) => { e.preventDefault(); if (ok) apply(rows.map((r) => `${r.field}${r.op}${+r.value}`)) }}>
            <ul className="crit">
              {rows.map((r, i) => (
                <li key={i}>
                  <select className="field" value={r.field} onChange={(e) => set(i, { field: e.target.value, ...(fields[e.target.value]?.kind === 'flag' ? { op: '==', value: '1' } : {}) })} aria-label="Measure">
                    {Object.entries(fields).filter(([, f]) => f.kind !== 'text').map(([k, f]) => <option key={k} value={k}>{f.label}{f.unit ? ` (${f.unit})` : ''}</option>)}
                  </select>
                  <select className="field" value={r.op} onChange={(e) => set(i, { op: e.target.value })} aria-label="Comparison">
                    <option value=">=">at least</option><option value="<=">at most</option><option value="==">exactly</option>
                  </select>
                  <input className="field" inputMode="decimal" value={r.value} onChange={(e) => set(i, { value: e.target.value })} aria-label="Value" aria-invalid={r.value.trim() !== '' && !Number.isFinite(+r.value)} />
                  <IconBtn icon="close" label="Remove this criterion" className="btn icon quiet sm" size={12} onClick={() => setRows(rows.filter((_, j) => j !== i))} />
                </li>
              ))}
            </ul>
            {rows.some((r) => fields[r.field]?.description) && <p className="muted small">{rows.map((r) => fields[r.field]).filter((f) => f?.description).map((f) => `${f.label}: ${f.description.toLowerCase()}`).join('. ')}.</p>}
            <div className="row">
              <button type="button" className="btn sm" onClick={() => setRows([...rows, { field: 'floors', op: '==', value: '1' }])}><Icon name="plus" size={12} />Add a criterion</button>
              <span className="grow" />
              {where.length > 0 && <button type="button" className="btn sm quiet" onClick={() => apply([])}>Clear</button>}
              <button className="btn sm solid" disabled={!ok}>Search</button>
            </div>
          </form>
        )}
        <div className="presets">
          <span className="muted small">Or start from a question</span>
          {PRESETS.map((p) => <button key={p.label} type="button" onClick={() => apply(p.where)}>{p.label}</button>)}
        </div>
      </Popover.Popup></Popover.Positioner></Popover.Portal>
    </Popover.Root>
  )
}

function RoomsFilter({ rooms }: { rooms: [number, number] }) {
  const on = rooms[0] > 0 || rooms[1] < ROOMS_MAX
  const [lo, setLo] = useState(''), [hi, setHi] = useState('')
  return (
    <Popover.Root onOpenChange={(o) => { if (o) { setLo(rooms[0] ? String(rooms[0]) : ''); setHi(rooms[1] < ROOMS_MAX ? String(rooms[1]) : '') } }}>
      <Popover.Trigger className="chip" render={<button type="button" aria-pressed={on} />}>{on ? `Rooms: ${rooms[0] || 'any'} to ${rooms[1] < ROOMS_MAX ? rooms[1] : 'any'}` : 'Rooms'}<Icon name="down" size={10} /></Popover.Trigger>
      <Popover.Portal><Popover.Positioner sideOffset={6} align="start" style={{ zIndex: 60 }}><Popover.Popup className="pop">
        <form className="stack" onSubmit={(e) => { e.preventDefault(); const a = Math.max(0, Math.round(+lo) || 0), b = Math.round(+hi) || 0; setQuery({ rooms: a || b ? `${a}-${b && b >= a ? b : ROOMS_MAX}` : null }) }}>
          <h4>Rooms in the largest scan</h4>
          <div className="row"><label className="fld"><span>At least</span><input className="field" inputMode="numeric" value={lo} onChange={(e) => setLo(e.target.value)} style={{ width: 84 }} /></label><label className="fld"><span>At most</span><input className="field" inputMode="numeric" value={hi} onChange={(e) => setHi(e.target.value)} style={{ width: 84 }} /></label></div>
          <div className="row"><Popover.Close className="btn sm solid" type="submit">Apply</Popover.Close>{on && <Popover.Close className="btn sm quiet" type="button" onClick={() => setQuery({ rooms: null })}>Clear</Popover.Close>}</div>
        </form>
      </Popover.Popup></Popover.Positioner></Popover.Portal>
    </Popover.Root>
  )
}

/* ---------- the scans at one address ---------- */
function BuildingDetail({ b, onClose }: { b: BuildingRow; onClose: () => void }) {
  const shortlist = useWorkspace((s) => s.doc.shortlist), panels = useWorkspace((s) => s.doc.panels)
  return (
    <section className="bdetail" aria-label={`Scans at ${b.address}`}>
      <header>
        <img src={orthoImage(b.lat, b.lon, 70, 256)} alt="" width={64} height={64} loading="lazy" onError={(e) => { e.currentTarget.style.visibility = 'hidden' }} />
        <div className="grow">
          <h3 className="trunc">{b.address.split(',')[0]}</h3>
          <p className="muted trunc">{[b.city || (b.metro ? CITIES[b.metro].name : ''), plural(b.count, 'scan')].filter(Boolean).join(' · ')}</p>
          <div className="row wrap">
            {b.splat && <span className="chip">Drone capture</span>}{b.defurnished && <span className="chip">Empty-room photos</span>}
            <SourceChip source={{ layer: 'matterport', method: 'lookup', confidence: 'medium', note: 'Counts come from the scan index. The kind of space is read from the scan name, so treat it as a guess.' }} />
          </div>
        </div>
        <IconBtn icon="close" label="Close" kbd="Esc" onClick={onClose} />
      </header>
      <ul className="scans scroll">
        {b.scans.map((s) => {
          const kept = shortlist.some((x) => x.sid === s.sid), n = panels.filter((p) => p.sid === s.sid).length
          return (
            <li key={s.sid}>
              <button type="button" className="open" onClick={() => goScan(s.sid, { b: b.id })}>
                <span className="grow trunc">{s.name}</span>
                {n > 0 && <span className="chip">{plural(n, 'result')}</span>}
                <span className="muted">{KIND_LABEL[s.kind]} · {plural(s.rooms, 'room')}</span>
                <Icon name="go" size={12} />
              </button>
              <IconBtn icon="keep" label={kept ? `Stop keeping ${s.name}` : `Keep ${s.name}`} aria-pressed={kept} className="btn icon quiet sm"
                onClick={() => userOp(kept ? { op: 'shortlist.remove', sid: s.sid } : { op: 'shortlist.add', item: { sid: s.sid, name: s.name, address: b.address } })} />
            </li>
          )
        })}
      </ul>
    </section>
  )
}

function HoverTip() {
  const map = useWorld((s) => s.map), hover = useWorld((s) => s.hover), tip = useWorld((s) => s.tip)
  useWorld((s) => s.tick)
  if (map && hover) { const p = map.project([hover.lon, hover.lat]); return <div className="tip hovertip" style={{ translate: `${p.x}px ${p.y}px` }}>{hover.address.split(',')[0]} · {plural(hover.count, 'scan')}</div> }
  if (!tip) return null
  // a feature of a data layer: its name, its detail, and which layer it is
  return <div className="tip hovertip" style={{ translate: `${tip.x}px ${tip.y}px` }}>{tip.title}{tip.detail && ` · ${tip.detail}`}{tip.title !== tip.layer && <span className="of"> {tip.layer}</span>}</div>
}

/** The layers that are on, as the address bar holds them: missing is the catalogue's own defaults, `none` is none. */
const readLayers = (q: URLSearchParams) => { const v = q.get('app_l'); return v == null ? null : v === 'none' ? [] : v.split(',').filter(Boolean) }

export function Explore({ sid = null }: { sid?: string | null }) {
  const m = useMapModel()
  const { q } = useRoute()
  const scheme = useScheme()
  const phone = useIsPhone()
  const doc = useWorkspace((s) => s.doc)
  const f = m.filters
  // A building is open in this view: the map hands over to its scene in the same rectangle, and back.
  const inside = !!sid && !phone
  const city = inside && m.selected?.metro ? m.selected.metro : f.city
  const view = (phone ? (q.get('app_view') === 'table' ? 'table' : 'map') : inside ? 'split' : (q.get('app_view') as View) || 'split') as View
  const [text, setText] = useState('')

  // The ground the map is drawn on and the layers over it. Chosen here, kept in the address bar for a link, and
  // held in state so they outlast a visit to a building (whose own links do not carry them).
  const [base, setBaseOnly] = useState<BaseView>(() => BASE_VIEWS.find((b) => b.id === q.get('app_base'))?.id ?? 'streets')
  const [picked, setPicked] = useState<string[] | null>(() => readLayers(q))
  const [layers, setLayers] = useState<MapLayer[]>([])
  useEffect(() => { let on = true; fetchLayers(city).then((l) => on && setLayers(l), () => on && setLayers([])); return () => { on = false } }, [city])
  const on = useMemo(() => picked ?? (layers.length ? layers.filter((l) => l.on).map((l) => l.id) : ['scans']), [picked, layers])
  const setBase = (b: BaseView) => { setBaseOnly(b); setQuery({ app_base: b === 'streets' ? null : b }) }
  const toggle = (id: string) => {
    const next = on.includes(id) ? on.filter((x) => x !== id) : [...on, id]
    setPicked(next); setQuery({ app_l: next.join(',') || 'none' })
    if (!on.includes(id)) setTimeout(() => fetchLayers(city, true).then(setLayers, () => {}), 4000) // a layer fetched for the first time has its date now
  }
  const [sunAt, setSunAt] = useState<SunAt>(() => sunNow(city))
  const sunOn = on.includes('sun'), sunKey = `${sunOn}|${sunAt.date}|${sunAt.minutes}|${city}`
  const sun = useMemo(() => (sunOn ? sunInstant(sunAt, city) : null), [sunKey]) // eslint-disable-line react-hooks/exhaustive-deps

  // search by measurement: the criteria are in the address bar, the answer comes from the server
  const where = useMemo(() => readWhere(q), [q]), key = where.join(';')
  const [fields, setFields] = useState<Record<string, MeasureField> | null>(null)
  useEffect(() => { fetchMeasureFields().then(setFields, () => setFields({})) }, [])
  const [found, setFound] = useState<{ key: string; state: 'loading' | 'ready' | 'error'; pool?: number; answerable?: number; matches?: number; rows: MeasureHit[]; error?: string }>({ key: '', state: 'ready', rows: [] })
  useEffect(() => {
    if (!key) { setFound({ key: '', state: 'ready', rows: [] }); return }
    let on = true
    const id = `${key}@${city}`
    setFound((x) => ({ ...x, key: id, state: 'loading' }))
    searchMeasures(where, { city: CITIES[city].name, limit: 300 }).then((r) => on && setFound({ key: id, state: 'ready', ...r }), (e: Error) => on && setFound({ key: id, state: 'error', rows: [], error: e.message }))
    return () => { on = false }
  }, [key, city]) // eslint-disable-line react-hooks/exhaustive-deps
  const measured = key !== ''

  const marks = useMemo(() => new Set(m.marks.map((b) => b.id)), [m.marks])
  const bySid = useMemo(() => { const x = new Map<string, BuildingRow>(); for (const b of m.all) for (const s of b.scans) x.set(s.sid, b); return x }, [m.all])
  const hitBuildings = useMemo(() => [...new Set(found.rows.map((r) => bySid.get(r.sid)).filter((b): b is BuildingRow => !!b))], [found.rows, bySid])
  const rows = useMemo(() => { const t = text.trim().toLowerCase(); return t ? m.shown.filter((b) => (b.address + ' ' + b.scans.map((s) => s.name).join(' ')).toLowerCase().includes(t)) : m.shown }, [m.shown, text])
  const shown = useMemo(() => (inside ? m.all.filter((b) => b.metro === city) : measured ? hitBuildings : m.shown), [inside, m.all, city, measured, hitBuildings, m.shown])

  // ---- the hand-off: a building opens inside the map's own rectangle, and zooming back out returns to the map
  const [stage, setStage] = useState<HTMLElement | null>(null), [headEl, setHead] = useState<HTMLElement | null>(null)
  const [sceneEl, setScene] = useState<HTMLElement | null>(null), [sideEl, setSide] = useState<HTMLElement | null>(null)
  const kept = { app_base: base === 'streets' ? null : base, app_l: picked ? picked.join(',') || 'none' : null }
  const back = () => navigate('/map', { city, b: m.selected?.id, ...kept })
  const hand = useHandoff(inside ? sid : null, stage, back)
  const phase = hand.phase, covered = phase === 'ready'
  /** Open a scan of this building here. On a phone the building is a page of its own. */
  const enter = (b: BuildingRow, scan = b.scans[0]?.sid) => { if (scan) goScan(scan, { b: b.id, city: b.metro ?? city, ...kept }) }
  const select = (b: BuildingRow | null) => (phone || !b ? m.select(b) : enter(b))
  const host = useMemo(() => (headEl && sceneEl && sideEl ? { head: headEl, stage: sceneEl, side: sideEl, hold: hand.hold, ...hand.host } : null), [headEl, sceneEl, sideEl, hand.host, hand.hold])
  // once the scene has faded in the map under it is not drawn at all, so the browser has one 3D picture to put on screen, not two
  const [under, setUnder] = useState(false)
  useEffect(() => { if (!covered) { setUnder(false); return } const t = setTimeout(() => setUnder(true), 600); return () => clearTimeout(t) }, [covered])

  const cols = useMemo<Col<BuildingRow>[]>(() => [
    { id: 'address', label: 'Address', fixed: true, sort: (b) => b.address, cell: (b) => <><span className="strong">{b.address.split(',')[0]}</span>{marks.has(b.id) && <span className="chip visited" title="The open investigation has results or kept scans here">In this investigation</span>}</> },
    { id: 'kind', label: 'Kind', width: '28%', sort: (b) => b.kinds[0], cell: (b) => <span className="dim">{b.kinds.map((k) => KIND_LABEL[k]).join(', ')}</span> },
    { id: 'scans', label: 'Scans', num: true, width: 62, sort: (b) => b.count, cell: (b) => int(b.count) },
    { id: 'rooms', label: 'Rooms', num: true, width: 62, sort: (b) => b.rooms, cell: (b) => (b.rooms ? int(b.rooms) : <span className="muted">–</span>) },
    { id: 'drone', label: 'Drone', width: 62, sort: (b) => (b.splat ? 0 : 1), cell: (b) => (b.splat ? <Icon name="check" size={13} /> : <span className="muted">–</span>) },
    { id: 'empty', label: 'Empty rooms', width: 96, off: true, sort: (b) => (b.defurnished ? 0 : 1), cell: (b) => (b.defurnished ? <Icon name="check" size={13} /> : <span className="muted">–</span>) },
    { id: 'city', label: 'City', width: 110, off: true, sort: (b) => b.city, cell: (b) => <span className="dim">{b.city}</span> },
  ], [marks])
  const table = useColumns('explore', cols)

  const crit = where.map(parse).filter((x): x is NonNullable<ReturnType<typeof parse>> => !!x)
  const hitCols = useMemo<Col<MeasureHit>[]>(() => [
    { id: 'name', label: 'Scan', fixed: true, cell: (r) => <><span className="strong">{r.name}</span><span className="sub">{[(r.address ?? '').split(',')[0], r.kind.replace(/_/g, ' ')].filter(Boolean).join(' · ')}</span></> },
    ...crit.map((c): Col<MeasureHit> => ({ id: c.field, label: fields?.[c.field]?.label ?? c.field, num: true, width: crit.length > 2 ? 104 : 128, sort: (r) => (typeof r.values[c.field] === 'number' ? (r.values[c.field] as number) : null),
      cell: (r) => { const v = r.values[c.field]; return typeof v === 'number' ? <><span className="num">{num(v)}</span>{fields?.[c.field]?.unit && <span className="muted"> {fields[c.field].unit}</span>}</> : String(v ?? '–') } })),
  ], [key, fields]) // eslint-disable-line react-hooks/exhaustive-deps

  const setKinds = (k: Kind) => { const next = f.kinds.includes(k) ? f.kinds.filter((x) => x !== k) : [...f.kinds, k]; setQuery({ kind: next.join(',') || null }) }
  const active = f.kinds.length + Number(f.drone) + Number(f.empty) + Number(f.rooms[0] > 0 || f.rooms[1] < ROOMS_MAX) + Number(measured)

  const side = (
    <div className="ex-side">
      {phone && m.selected && <BuildingDetail b={m.selected} onClose={() => m.select(null)} />}
      <div className="bar thin">
        {measured ? (
          <p className="grow small">
            {found.state === 'loading' ? 'Searching the measured scans' : found.state === 'error' ? found.error
              : <><b>{int(found.matches ?? 0)}</b> of {int(found.answerable ?? 0)} scans that can be answered match, out of {int(found.pool ?? 0)} in {CITIES[city].name}. <SourceChip source={{ layer: 'matterport', method: 'geometry', confidence: 'medium', note: 'Measured from each scan’s wall outline and doorways. Scans with no wall outline cannot be answered and are left out.' }} /></>}
          </p>
        ) : (
          <label className="inset grow"><Icon name="search" size={13} /><input className="field" value={text} onChange={(e) => setText(e.target.value)} placeholder="Filter by address or scan name" aria-label="Filter the table by address or scan name" /></label>
        )}
        {!measured && table.chooser}
      </div>
      {measured ? (
        <DataTable label="Scans that match the measured criteria" noun="scan" cols={hitCols} rows={found.state === 'ready' && found.key === `${key}@${city}` ? found.rows : []} rowKey={(r) => r.sid} loading={found.state === 'loading'}
          onRow={(r) => { const b = bySid.get(r.sid); if (b && !phone) enter(b, r.sid); else goScan(r.sid, { b: b?.id }) }}
          empty={found.state === 'error' ? <Empty icon="warn" title="The search did not run">{found.error}</Empty> : <Empty icon="ruler" title="No scan matches">Loosen a criterion, or try the other city.</Empty>} />
      ) : (
        <DataTable label={`Scanned buildings in ${CITIES[city].name}`} noun="building" cols={table.shown} rows={rows} rowKey={(b) => b.id} loading={m.state === 'loading'} selected={m.selected?.id ?? null}
          onRow={(b) => (phone ? m.select(m.selected?.id === b.id ? null : b) : enter(b))} sortBy={{ col: 'scans', dir: -1 }}
          empty={m.state === 'error' ? <Empty icon="warn" title="The building list did not load" action={<button className="btn" onClick={m.reload}>Try again</button>}>Is the data server running?</Empty>
            : <Empty icon="filter" title="No building passes these filters" action={<button className="btn" onClick={() => { setText(''); navigate('/map', { city }) }}>Clear the filters</button>} />} />
      )}
    </div>
  )

  return (
    <div className="ex" data-view={view} data-phase={phase} data-under={under || undefined}>
      {/* a building's own header takes the filter bar's place while it is open */}
      <div className="ex-head" ref={setHead} hidden={!inside} />
      {!inside && <div className="bar">
        <Seg label="City" value={city} onChange={(c: CityId) => navigate('/map', { city: c, b: null }, { keep: true })} options={(Object.keys(CITIES) as CityId[]).map((c) => ({ id: c, label: CITIES[c].name }))} />
        <span className="sep" />
        <MenuBtn trigger={<button type="button" className="chip" aria-pressed={f.kinds.length > 0}>{f.kinds.length ? `Kind: ${f.kinds.map((k) => KINDS.find((x) => x.id === k)!.label).join(', ')}` : 'Kind'}<Icon name="down" size={10} /></button>}>
          <div className="mh">Kind of space, read from the scan’s name</div>
          {KINDS.map((k) => (
            <Menu.CheckboxItem key={k.id} checked={f.kinds.includes(k.id)} closeOnClick={false} onCheckedChange={() => setKinds(k.id)}>
              <span className="mi-check"><Menu.CheckboxItemIndicator><Icon name="check" size={12} /></Menu.CheckboxItemIndicator></span>{k.label}
            </Menu.CheckboxItem>
          ))}
        </MenuBtn>
        <button type="button" className="chip" aria-pressed={f.drone} onClick={() => setQuery({ drone: f.drone ? null : '1' })}>Drone capture</button>
        <button type="button" className="chip" aria-pressed={f.empty} onClick={() => setQuery({ empty: f.empty ? null : '1' })}>Empty-room photos</button>
        <RoomsFilter rooms={f.rooms} />
        <span className="sep" />
        <MeasureBuilder where={where} fields={fields} />
        {active > 0 && <button type="button" className="btn sm quiet" onClick={() => navigate('/map', { city, app_view: q.get('app_view'), ...kept })}>Clear {active === 1 ? 'the filter' : `${active} filters`}</button>}
        <span className="grow" />
        <Seg label="Layout" compact value={view} onChange={(v: View) => setQuery({ app_view: v === 'split' && !phone ? null : v })}
          options={phone ? [{ id: 'map', label: 'Map', icon: 'map' }, { id: 'table', label: 'Table', icon: 'table' }] : [{ id: 'map', label: 'Map', icon: 'map' }, { id: 'split', label: 'Split', icon: 'split' }, { id: 'table', label: 'Table', icon: 'table' }]} />
      </div>}
      <Split className="ex-body" off={phone}>
        {(phone || view !== 'table') && <Fill key="map" id="map" min={320}>
        <div className="ex-map" ref={setStage}>
          <WorldMap buildings={shown} selected={m.selected} marks={m.marks} geo={m.geo} look={m.look} city={city} scheme={scheme} base={base} layers={layers} on={on} sun={sun}
            held={phase !== 'map'} covered={covered} onSelect={select} onNear={(b) => phase === 'map' && !phone && enter(b)} />
          {/* the open building's scene and its toolbars: they fade in over the map when the two cameras agree */}
          <div className="ex-scene" ref={setScene} />
          {!covered && <>
            <HoverTip />
            <MapTools base={base} onBase={setBase} layers={layers} on={on} toggle={toggle} reset={() => { setPicked(null); setQuery({ app_l: null }) }} />
            {on.includes('weather') && <WeatherChip city={city} source={layers.find((l) => l.id === 'weather')} />}
            <MapNav />
            <div className="mapfoot">
              <Legend layers={layers} on={on} base={base} marks={m.marks.length} drawn={m.geo.paths.length > 0 || m.geo.pins.length > 0} />
              {sunOn && <SunBar city={city} value={sunAt} onChange={setSunAt} source={layers.find((l) => l.id === 'sun')} />}
            </div>
            {phone && view === 'map' && m.selected && <div className="ex-float"><BuildingDetail b={m.selected} onClose={() => m.select(null)} /></div>}
          </>}
          {phase === 'approach' && <p className="mapread opening" role="status"><RunState state="running">Opening {m.selected ? m.selected.address.split(',')[0] : 'the building'}</RunState></p>}
          {doc.runs.some((r) => r.status === 'running') && !covered && view === 'map' && <p className="mapread working" role="status">The agent is working</p>}
        </div>
        </Fill>}
        {!phone && view === 'split' && <Edge key="edge" of="list" label={inside ? 'Resize the inspector' : 'Resize the list'} />}
        {phone || view === 'split' ? <Pane key="list" id="list" size="44%" min={360} max="72%"><div className="ex-insp" ref={setSide} hidden={!inside} />{!inside && side}</Pane> : view === 'table' && <Fill key="list" id="table">{side}</Fill>}
      </Split>
      {inside && host && <Building key={sid} sid={sid!} host={host} />}
    </div>
  )
}
