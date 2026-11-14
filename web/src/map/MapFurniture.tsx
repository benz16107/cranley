import { useEffect, useMemo, useRef, useState, type RefObject } from 'react'
import NumberFlow from '@number-flow/react'
import { Popover } from '@base-ui/react/popover'
import { Slider } from '@base-ui/react/slider'
import { toast } from 'sonner'
import { useMap } from './CityMap.tsx'
import { CITIES, KINDS, ROOMS_MAX, search, type Building, type CityId, type Filters, type Kind } from './buildings.ts'
import { Icon, SourceChip } from '../design/ui.tsx'
import { navigate, setQuery } from '../lib/router.ts'
import { useWorkspace, userOp } from '../workspace/store.ts'

/* ---------- the neatline: a frame with coordinate ticks, as on a printed map sheet ---------- */
const STEPS = [60, 30, 20, 10, 5, 2, 1, 0.5, 0.25, 1 / 12] // arc minutes
function ticksBetween(a: number, b: number): { at: number; step: number }[] {
  const span = Math.abs(b - a) * 60
  const step = STEPS.find((s) => span / s >= 2.5) ?? STEPS.at(-1)!
  const out = []
  for (let m = Math.ceil((Math.min(a, b) * 60) / step) * step; m <= Math.max(a, b) * 60; m += step) out.push({ at: m / 60, step })
  return out.slice(0, 12)
}
function dms(deg: number, step: number, axis: 'lat' | 'lon') {
  const a = Math.abs(deg) + 1e-9
  const d = Math.floor(a), m = Math.floor((a - d) * 60), s = Math.round(((a - d) * 60 - m) * 60)
  const hemi = axis === 'lat' ? (deg >= 0 ? 'N' : 'S') : deg >= 0 ? 'E' : 'W'
  return `${d}°${String(m).padStart(2, '0')}'${step < 1 ? String(s).padStart(2, '0') + '"' : ''} ${hemi}`
}

export function Neatline({ frame }: { frame: RefObject<HTMLDivElement | null> }) {
  const map = useMap((s) => s.map)
  useMap((s) => s.tick)
  const f = frame.current?.getBoundingClientRect()
  const c = map?.getContainer().getBoundingClientRect()
  let top: { x: number; text: string }[] = [], left: { y: number; text: string }[] = []
  if (map && f && c && f.width > 200) {
    const nw = map.unproject([f.left - c.left, f.top - c.top]), se = map.unproject([f.right - c.left, f.bottom - c.top])
    top = ticksBetween(nw.lng, se.lng).map(({ at, step }) => ({ x: map.project([at, nw.lat]).x + c.left - f.left, text: dms(at, step, 'lon') }))
      .filter((t) => t.x > 50 && t.x < f.width - 50)
    left = ticksBetween(se.lat, nw.lat).map(({ at, step }) => ({ y: map.project([nw.lng, at]).y + c.top - f.top, text: dms(at, step, 'lat') }))
      .filter((t) => t.y > 50 && t.y < f.height - 50)
  }
  return (
    <div className="neat" ref={frame} aria-hidden="true">
      {top.map((t) => <span key={t.text} className="tick t num" style={{ translate: `${t.x}px 0` }}>{t.text}</span>)}
      {left.map((t) => <span key={t.text} className="tick l num" style={{ translate: `0 ${t.y}px` }}>{t.text}</span>)}
    </div>
  )
}

/* ---------- the title block: what is in view, at what scale ---------- */
const NICE = [20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000, 50000, 100000, 200000, 500000, 1000000]
export function TitleBlock({ buildings, city, frame }: { buildings: Building[]; city: CityId; frame: RefObject<HTMLElement | null> }) {
  const map = useMap((s) => s.map)
  const tick = useMap((s) => s.tick)
  const [open, setOpen] = useState(false)
  const inView = useMemo(() => {
    const f = frame.current?.getBoundingClientRect(), c = map?.getContainer().getBoundingClientRect()
    if (!map || !f || !c) return []
    const nw = map.unproject([f.left - c.left, f.top - c.top]), se = map.unproject([f.right - c.left, f.bottom - c.top])
    return buildings.filter((b) => b.lon >= nw.lng && b.lon <= se.lng && b.lat >= se.lat && b.lat <= nw.lat)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, tick, buildings])
  if (!map) return null
  const z = map.getZoom()
  const mpp = (40075016.686 * Math.cos((map.getCenter().lat * Math.PI) / 180)) / (512 * 2 ** z)
  const len = NICE.findLast((n) => n / mpp <= 112) ?? NICE[0]
  return (
    <div className="pane titleblock">
      <Popover.Root open={open} onOpenChange={setOpen}>
        <Popover.Trigger className="cell" aria-label={`${inView.length} buildings in view. Open the list.`}>
          <span className="label">In view</span>
          <span className="num big"><NumberFlow value={inView.length} /> <small>buildings</small></span>
        </Popover.Trigger>
        <Popover.Portal>
          <Popover.Positioner side="top" align="start" sideOffset={8}>
            <Popover.Popup className="pop listpop">
              <BuildingList items={inView.slice(0, 60)} onPick={() => setOpen(false)} empty="No scanned building in view. Zoom out or clear a filter." />
              {inView.length > 60 && <p className="muted" style={{ padding: '8px 4px 0' }}>Showing the first 60. Zoom in to narrow it.</p>}
            </Popover.Popup>
          </Popover.Positioner>
        </Popover.Portal>
      </Popover.Root>
      <div className="cell">
        <span className="label">Scale</span>
        <span className="scalebar"><i style={{ width: len / mpp }} /><span className="num">{len >= 1000 ? `${len / 1000} km` : `${len} m`}</span></span>
      </div>
      <div className="cell">
        <span className="label">Sheet</span>
        <span className="num big">{city.toUpperCase()} · {z.toFixed(1)}</span>
      </div>
      <div className="cell tools">
        <button className="btn icon quiet" aria-label="Zoom in" onClick={() => map.zoomIn()}><Icon name="plus" /></button>
        <button className="btn icon quiet" aria-label="Zoom out" onClick={() => map.zoomOut()}><span className="minus" /></button>
      </div>
    </div>
  )
}

export function BuildingList({ items, onPick, empty }: { items: Building[]; onPick?: () => void; empty: string }) {
  if (!items.length) return <p className="muted" style={{ padding: 4 }}>{empty}</p>
  return (
    <ul className="blist scroll">
      {items.map((b) => (
        <li key={b.id}>
          <button onClick={() => { navigate('/map', { city: b.metro ?? undefined, b: b.id }, { keep: true }); onPick?.() }}>
            <span>{b.address}</span><span className="num muted">{b.count > 1 ? `${b.count} scans` : b.scans[0]?.name.slice(0, 22)}</span>
          </button>
        </li>
      ))}
    </ul>
  )
}

/* ---------- the callout: the scans at one address ---------- */
const KIND_LABEL: Record<Kind, string> = { home: 'House', apartment: 'Apartment', amenity: 'Shared room', office: 'Office', other: 'Other' }

export function BuildingCard({ b, onClose }: { b: Building; onClose: () => void }) {
  const shortlist = useWorkspace((s) => s.doc.shortlist)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => { ref.current?.querySelector<HTMLElement>('.scanrow')?.focus({ preventScroll: true }) }, [b.id])
  return (
    <div className="bcard" ref={ref} role="dialog" aria-label={`Scans at ${b.address}`} onKeyDown={(e) => e.key === 'Escape' && onClose()}>
      <header>
        <div>
          <h3>{b.address.split(',')[0]}</h3>
          <p className="muted">{[b.city || (b.metro ? CITIES[b.metro].name : ''), `${b.count} ${b.count === 1 ? 'scan' : 'scans'}`].filter(Boolean).join(' · ')}</p>
        </div>
        <button className="btn icon quiet" aria-label="Close" onClick={onClose}><Icon name="close" size={14} /></button>
      </header>
      <div className="has">
        {b.splat && <span className="chip">Drone capture</span>}
        {b.defurnished && <span className="chip">Empty-room view</span>}
        <SourceChip source={{ layer: 'matterport', method: 'lookup', confidence: 'high', note: 'Room and scan counts come from the scan index. The kind of space is read from the scan name, so treat it as a guess.' }} />
      </div>
      <ul className="scroll">
        {b.scans.map((s) => {
          const kept = shortlist.some((x) => x.sid === s.sid)
          return (
            <li key={s.sid}>
              <button className="scanrow" onClick={() => navigate(`/scan/${s.sid}`, { b: b.id })}>
                <span className="nm">{s.name}</span>
                <span className="meta"><span className="muted">{KIND_LABEL[s.kind]}</span><span className="num">{s.rooms} {s.rooms === 1 ? 'room' : 'rooms'}</span></span>
              </button>
              <button className="btn icon quiet keep" aria-pressed={kept} aria-label={kept ? `Remove ${s.name} from the shortlist` : `Add ${s.name} to the shortlist`}
                onClick={() => userOp(kept ? { op: 'shortlist.remove', sid: s.sid } : { op: 'shortlist.add', item: { sid: s.sid, name: s.name, address: b.address } })}>
                <Icon name="keep" size={15} />
              </button>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

/** Pins the card beside its building with a leader line, flipping sides to stay inside the frame. */
export function Callout({ b, frame, onClose }: { b: Building; frame: RefObject<HTMLElement | null>; onClose: () => void }) {
  const map = useMap((s) => s.map)
  useMap((s) => s.tick)
  const f = frame.current?.getBoundingClientRect(), c = map?.getContainer().getBoundingClientRect()
  if (!map || !f || !c) return null
  const p = map.project([b.lon, b.lat])
  const x = p.x + c.left - f.left, y = p.y + c.top - f.top
  const W = 284, LEAD = 34
  const right = x + LEAD + W < f.width - 8
  const left = right ? x + LEAD : Math.max(8, x - LEAD - W)
  const top = Math.max(8, Math.min(f.height - 250, y - 40))
  const hidden = x < -20 || y < -20 || x > f.width + 20 || y > f.height + 20
  return (
    <div className="callout" style={{ visibility: hidden ? 'hidden' : 'visible' }}>
      <svg className="leader" aria-hidden="true"><polyline points={`${x},${y} ${right ? left : left + W},${top + 22}`} /></svg>
      <div className="float" style={{ translate: `${left}px ${top}px`, width: W }}><BuildingCard b={b} onClose={onClose} /></div>
    </div>
  )
}

export function HoverTip({ frame }: { frame: RefObject<HTMLElement | null> }) {
  const map = useMap((s) => s.map), hover = useMap((s) => s.hover)
  useMap((s) => s.tick)
  const f = frame.current?.getBoundingClientRect(), c = map?.getContainer().getBoundingClientRect()
  if (!map || !hover || !f || !c) return null
  const p = map.project([hover.lon, hover.lat])
  return <div className="tip hovertip" style={{ translate: `${p.x + c.left - f.left}px ${p.y + c.top - f.top}px` }}>{hover.address.split(',')[0]}<span className="num"> · {hover.count}</span></div>
}

/* ---------- filters ---------- */
export function FilterBar({ filters, all, selected }: { filters: Filters; all: Building[]; selected: Building | null }) {
  const inCity = useMemo(() => all.filter((b) => b.metro === filters.city), [all, filters.city])
  const hist = useMemo(() => {
    const bins = Array<number>(ROOMS_MAX + 1).fill(0)
    for (const b of inCity) bins[Math.min(ROOMS_MAX, b.rooms)]++
    return bins
  }, [inCity])
  const peak = Math.max(1, ...hist)
  const toggleKind = (k: Kind) => {
    const next = filters.kinds.includes(k) ? filters.kinds.filter((x) => x !== k) : [...filters.kinds, k]
    setQuery({ kind: next.join(',') })
  }
  const active = filters.kinds.length + +filters.drone + +filters.empty + +(filters.rooms[0] > 0 || filters.rooms[1] < ROOMS_MAX)
  return (
    <div className="pane filterbar" role="group" aria-label="Filter the buildings">
      <span className="label lead"><Icon name="filter" size={13} /> Filter</span>
      <div className="grp" title="Read from the scan name, so a guess">
        {KINDS.map((k) => <button key={k.id} className="chip" aria-pressed={filters.kinds.includes(k.id)} onClick={() => toggleKind(k.id)}>{k.label}</button>)}
      </div>
      <div className="grp">
        <button className="chip" aria-pressed={filters.drone} onClick={() => setQuery({ drone: filters.drone ? null : '1' })}>Drone capture</button>
        <button className="chip" aria-pressed={filters.empty} onClick={() => setQuery({ empty: filters.empty ? null : '1' })}>Empty-room view</button>
      </div>
      <Popover.Root>
        <Popover.Trigger className="chip" aria-pressed={filters.rooms[0] > 0 || filters.rooms[1] < ROOMS_MAX}>
          Rooms <span className="num">{filters.rooms[0]}–{filters.rooms[1] >= ROOMS_MAX ? `${ROOMS_MAX}+` : filters.rooms[1]}</span>
        </Popover.Trigger>
        <Popover.Portal>
          <Popover.Positioner side="bottom" align="start" sideOffset={8}>
            <Popover.Popup className="pop roomspop">
              <span className="label">Rooms in the largest scan at an address</span>
              <div className="hist" aria-hidden="true">
                {hist.map((n, i) => <i key={i} data-in={i >= filters.rooms[0] && i <= filters.rooms[1]} style={{ height: `${Math.max(2, (n / peak) * 100)}%` }} />)}
              </div>
              <Slider.Root value={filters.rooms} min={0} max={ROOMS_MAX} minStepsBetweenValues={1}
                onValueChange={(v) => { const [lo, hi] = v as number[]; setQuery({ rooms: lo === 0 && hi === ROOMS_MAX ? null : `${lo}-${hi === ROOMS_MAX ? '' : hi}` }) }}>
                <Slider.Control className="slider">
                  <Slider.Track className="track"><Slider.Indicator className="range" />
                    <Slider.Thumb className="thumb" index={0} getAriaLabel={() => 'Fewest rooms'} />
                    <Slider.Thumb className="thumb" index={1} getAriaLabel={() => 'Most rooms'} />
                  </Slider.Track>
                </Slider.Control>
              </Slider.Root>
              <div className="ends num"><span>0</span><span>{ROOMS_MAX}+</span></div>
            </Popover.Popup>
          </Popover.Positioner>
        </Popover.Portal>
      </Popover.Root>
      {active > 0 && <button className="link" onClick={() => setQuery({ kind: null, drone: null, empty: null, rooms: null })}>Clear</button>}
      <div className="grp"><AerialToggle b={selected} /></div>
    </div>
  )
}

/* ---------- search by address ---------- */
export function AddressSearch({ all }: { all: Building[] }) {
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(false)
  const [at, setAt] = useState(0)
  const input = useRef<HTMLInputElement>(null)
  const hits = useMemo(() => search(all, q), [all, q])
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.key === '/' && !/input|textarea/i.test((e.target as HTMLElement).tagName)) { e.preventDefault(); input.current?.focus() }
    }
    window.addEventListener('keydown', key)
    return () => window.removeEventListener('keydown', key)
  }, [])
  const pick = (b: Building) => { navigate('/map', { city: b.metro ?? undefined, b: b.id }, { keep: true }); setOpen(false); setQ(''); input.current?.blur() }
  return (
    <div className="search" role="combobox" aria-expanded={open && q.length > 0} aria-haspopup="listbox" aria-controls="search-hits">
      <Icon name="search" size={14} />
      <input ref={input} value={q} placeholder="Find an address" aria-label="Find an address in either city" autoComplete="off" spellCheck={false}
        onChange={(e) => { setQ(e.target.value); setOpen(true); setAt(0) }} onFocus={() => setOpen(true)} onBlur={() => setTimeout(() => setOpen(false), 120)}
        onKeyDown={(e) => {
          if (e.key === 'ArrowDown') { e.preventDefault(); setAt((i) => Math.min(hits.length - 1, i + 1)) }
          if (e.key === 'ArrowUp') { e.preventDefault(); setAt((i) => Math.max(0, i - 1)) }
          if (e.key === 'Enter' && hits[at]) pick(hits[at])
          if (e.key === 'Escape') { setQ(''); input.current?.blur() }
        }} />
      <span className="kbd" aria-hidden="true">/</span>
      {open && q && (
        <ul id="search-hits" role="listbox" className="float hits">
          {hits.length === 0 && <li className="muted none">No address matches “{q}”. Try a street name or a unit type such as “2BR”.</li>}
          {hits.map((b, i) => (
            <li key={b.id} role="option" aria-selected={i === at} onMouseDown={(e) => { e.preventDefault(); pick(b) }} onMouseEnter={() => setAt(i)}>
              <span>{b.address}</span>
              <span className="num muted">{b.metro ? CITIES[b.metro].name : ''} · {b.count} {b.count === 1 ? 'scan' : 'scans'}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

/** The slot for the aerial photo layer (GET /api/aerial/ortho, perception workstream). Draws a square photo patch
    around the selected address once the route exists; until then it says so and stays off. */
export function AerialToggle({ b }: { b: Building | null }) {
  const map = useMap((s) => s.map)
  const [on, setOn] = useState(false)
  useEffect(() => {
    if (!map || !on || !b) return
    const size = 160, dLat = size / 2 / 111320, dLon = dLat / Math.cos((b.lat * Math.PI) / 180)
    let url = '', gone = false
    fetch(`/api/aerial/ortho?lat=${b.lat}&lon=${b.lon}&size_m=${size}&px=1024`).then((r) => { if (!r.ok) throw new Error(); return r.blob() }).then((blob) => {
      if (gone) return
      url = URL.createObjectURL(blob)
      map.addSource('aerial', { type: 'image', url, coordinates: [[b.lon - dLon, b.lat + dLat], [b.lon + dLon, b.lat + dLat], [b.lon + dLon, b.lat - dLat], [b.lon - dLon, b.lat - dLat]] })
      map.addLayer({ id: 'aerial', type: 'raster', source: 'aerial', paint: { 'raster-fade-duration': 200 } }, 'road-minor')
    }).catch(() => { toast('The aerial photo layer is not connected yet.', { description: 'It arrives with the aerial workstream.' }); setOn(false) })
    return () => { gone = true; if (map.getLayer('aerial')) map.removeLayer('aerial'); if (map.getSource('aerial')) map.removeSource('aerial'); if (url) URL.revokeObjectURL(url) }
  }, [map, on, b])
  return <button className="chip" aria-pressed={on} disabled={!b} title={b ? '' : 'Choose a building first'} onClick={() => setOn(!on)}><Icon name="layers" size={12} /> Aerial photo</button>
}
