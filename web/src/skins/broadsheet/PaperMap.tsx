import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { MapLibreOverlay } from '@deck.gl/maplibre'
import { PathLayer, ScatterplotLayer } from 'deck.gl'
import { CITIES, MapLibre, Marker, mapStyle, orthoImage, type Building, type CityId, type GeoMarks, type MapPalette } from '../../core/index.ts'
import { G, reduced, useFree } from './parts.tsx'

/* The city as a printed map: paper ground, ink roads, every scanned building a dot of ink. What the agent has read
   is numbered in the order the page lists it, the building it is reading now is ringed in pencil, and what tools drew
   in map coordinates (a path, a pin on a roof) is drawn where it is, on the aerial photograph when the page looks there. */

const PAPER: MapPalette = {
  ground: '#f2eee4', water: '#d5dfde', waterLine: '#6f8a97', green: '#e4e6d2', road: 'rgba(23,20,15,0.22)', roadMajor: 'rgba(23,20,15,0.55)',
  rail: 'rgba(23,20,15,0.22)', building: '#e3dccb', label: '#17140f', labelMuted: '#453f35', halo: '#f2eee4',
}
const INK: [number, number, number] = [23, 20, 15], PENCIL: [number, number, number] = [29, 63, 216]

export type Numbered = { b: Building; n: number; best?: boolean }
type Props = {
  city: CityId; buildings: Building[]; selected: Building | null; numbered: Numbered[]; now: Building | null
  hits: { lon: number; lat: number }[]; geo: GeoMarks; look: [number, number] | null; aerial: boolean; open: boolean
  onSelect: (b: Building | null) => void
}

function Pin({ map, lon, lat, anchor = 'center', dx = 0, children }: { map: MapLibre; lon: number; lat: number; anchor?: 'center' | 'left'; dx?: number; children: ReactNode }) {
  const [host] = useState(() => document.createElement('div'))
  useEffect(() => { const mk = new Marker({ element: host, anchor, offset: [dx, 0] }).setLngLat([lon, lat]).addTo(map); return () => { mk.remove() } }, [map, host, lon, lat, anchor, dx])
  return createPortal(children, host)
}

export function PaperMap({ city, buildings, selected, numbered, now, hits, geo, look, aerial, open, onSelect }: Props) {
  const el = useRef<HTMLDivElement>(null), overlay = useRef<MapLibreOverlay | null>(null)
  const [map, setMap] = useState<MapLibre | null>(null)
  const [hover, setHover] = useState<{ b: Building; x: number; y: number } | null>(null)
  const [far, setFar] = useState(true) // from far off a mark on the map is its glyph; close in, it is named
  const select = useRef(onSelect); select.current = onSelect
  const padded = useRef(false)

  useEffect(() => {
    const m = new MapLibre({
      container: el.current!, style: mapStyle(PAPER), attributionControl: false, dragRotate: false, pitchWithRotate: false, minZoom: 3, maxZoom: 19,
      center: selected ? [selected.lon, selected.lat] : CITIES[city].center, zoom: selected ? 15 : CITIES[city].zoom,
    })
    m.touchZoomRotate.disableRotation()
    overlay.current = new MapLibreOverlay({ interleaved: false, layers: [], getCursor: ({ isHovering }) => (isHovering ? 'pointer' : 'grab') })
    m.addControl(overlay.current as never)
    m.on('load', () => setMap(m))
    m.on('zoomend', () => setFar(m.getZoom() < 15))
    const ro = new ResizeObserver(() => m.resize())
    ro.observe(el.current!)
    return () => { ro.disconnect(); m.remove(); setMap(null) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const quiet = numbered.length > 0 || hits.length > 0 // the page is about a few buildings: the rest step back
  const layers = useMemo(() => [
    new ScatterplotLayer<Building>({
      id: 'buildings', data: buildings, getPosition: (b) => [b.lon, b.lat], radiusUnits: 'pixels', getRadius: (b) => 2.4 + Math.sqrt(b.count) * 1.1, radiusMinPixels: 2,
      getFillColor: [...INK, quiet ? 90 : 190], pickable: true, updateTriggers: { getFillColor: quiet },
      onHover: ({ object, x, y }) => setHover(object ? { b: object, x, y } : null),
      onClick: ({ object }) => select.current(object ?? null),
    }),
    new ScatterplotLayer<{ lon: number; lat: number }>({ id: 'hits', data: hits, getPosition: (h) => [h.lon, h.lat], radiusUnits: 'pixels', getRadius: 9, filled: false, stroked: true, getLineColor: PENCIL, lineWidthUnits: 'pixels', getLineWidth: 3 }),
    new PathLayer<[number, number][]>({ id: 'paths', data: geo.paths, getPath: (d) => d, widthUnits: 'pixels', getWidth: 5, getColor: PENCIL, capRounded: true, jointRounded: true }),
  ], [buildings, hits, geo.paths, quiet])
  useEffect(() => { overlay.current?.setProps({ layers }) }, [layers, map])

  // The middle of the map is the middle of what the column and the caption leave free.
  const free = useFree(open)
  useEffect(() => {
    if (!map) return
    if (reduced() || !padded.current) map.setPadding(free); else map.easeTo({ padding: free, duration: 560 })
    padded.current = true
  }, [map, free])

  // The city switch is the one long move: a flight between the two editions.
  const firstCity = useRef(true)
  useEffect(() => {
    if (!map) return
    if (firstCity.current) { firstCity.current = false; return }
    if (selected?.metro === city) return
    const { center, zoom } = CITIES[city]
    if (reduced()) map.jumpTo({ center, zoom }); else map.flyTo({ center, zoom, duration: 2400, curve: 1.25, essential: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [city, map])

  // The map goes where the work is: it frames the buildings the page lists (read, being read, found by a search),
  // inside the part of the stage the column leaves free.
  const fitKey = [...numbered.map((x) => x.b.id), now?.id, hits.map((h) => h.lon).join()].join('|')
  useEffect(() => {
    if (!map || look || selected) return
    const pts = [...numbered.map((x) => [x.b.lon, x.b.lat]), ...(now ? [[now.lon, now.lat]] : []), ...hits.map((h) => [h.lon, h.lat])]
    if (!pts.length) return
    const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1])
    const rem = parseFloat(getComputedStyle(document.documentElement).fontSize)
    // (fitBounds adds its padding to the map's own, which already keeps the column and the caption clear)
    map.fitBounds([[Math.min(...xs), Math.min(...ys)], [Math.max(...xs), Math.max(...ys)]], { padding: { left: free.left ? 9 * rem : 3 * rem, right: 4 * rem, top: 5 * rem, bottom: 3 * rem }, maxZoom: 14, duration: reduced() ? 0 : 1400, essential: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fitKey, map, free])

  const lookKey = look?.join(',')
  useEffect(() => {
    if (!map) return
    const to = look ? { center: look, zoom: 18.2 } : selected && (map.getZoom() < 12.5 || !map.getBounds().contains([selected.lon, selected.lat])) ? { center: [selected.lon, selected.lat] as [number, number], zoom: Math.max(map.getZoom(), 14.5) } : null
    if (!to) return
    if (reduced()) map.jumpTo(to); else map.flyTo({ ...to, duration: 1400, essential: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lookKey, selected?.id, map])

  // The aerial photograph, laid under the marks where the page is looking.
  const at = look ?? (aerial && selected ? ([selected.lon, selected.lat] as [number, number]) : null), atKey = at?.join(',')
  useEffect(() => {
    if (!map || !at) return
    const [lon, lat] = at, size = 180, dLat = size / 2 / 111320, dLon = dLat / Math.cos((lat * Math.PI) / 180)
    map.addSource('aerial', { type: 'image', url: orthoImage(lat, lon, size, 1024), coordinates: [[lon - dLon, lat + dLat], [lon + dLon, lat + dLat], [lon + dLon, lat - dLat], [lon - dLon, lat - dLat]] })
    map.addLayer({ id: 'aerial', type: 'raster', source: 'aerial', paint: { 'raster-fade-duration': 240 } }, 'road-minor')
    return () => { if (map.getLayer('aerial')) map.removeLayer('aerial'); if (map.getSource('aerial')) map.removeSource('aerial') }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, atKey])

  const marked = new Set(numbered.map((x) => x.b.id))
  return (
    <div ref={el} className="citymap" data-far={far || undefined} role="application" aria-label={`Map of scanned buildings in ${CITIES[city].name}. The page beside it lists them: use its search and lists from the keyboard.`}>
      {map && numbered.slice(0, 40).map(({ b, n, best }) => <Pin key={b.id} map={map} lon={b.lon} lat={b.lat}><button className="pin" data-best={best || undefined} aria-label={`${n}: ${b.address}`} onClick={() => onSelect(b)}>{n}</button></Pin>)}
      {map && selected && !marked.has(selected.id) && <Pin map={map} lon={selected.lon} lat={selected.lat}><span className="pin" data-kind="selected" /></Pin>}
      {map && now && <Pin map={map} lon={now.lon} lat={now.lat}><span className="pin" data-kind="now" style={{ position: 'relative' }} /></Pin>}
      {map && geo.pins.slice(0, 30).map((p, i) => <Pin key={i} map={map} lon={p.lon} lat={p.lat} anchor="left" dx={10}><span className="geopin" data-s={p.status} title={p.label}><G s={p.status} /><span>{p.label}</span></span></Pin>)}
      {hover && <span className="maptip" style={{ left: hover.x, top: hover.y }}>{hover.b.address.split(',')[0]} · {hover.b.count} {hover.b.count === 1 ? 'scan' : 'scans'}</span>}
    </div>
  )
}
