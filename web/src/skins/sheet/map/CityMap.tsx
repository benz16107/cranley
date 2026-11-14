import { useEffect, useRef, type RefObject } from 'react'
import { create } from 'zustand'
import { MapLibreOverlay } from '@deck.gl/maplibre'
import { ContourLayer, PathLayer, ScatterplotLayer, TextLayer } from 'deck.gl'
import { Map as MapLibre } from '../../../core/maplibre.ts'
import { mapStyle } from '../../../core/basemap.ts'
import { CITIES, type Building, type CityId } from '../../../core/buildings.ts'
import { tokenCss, tokenRgba } from '../design/ui.tsx'

/** The live map and a counter that ticks when the view moves, for the furniture drawn around it. */
export const useMap = create<{ map: MapLibre | null; tick: number; hover: Building | null }>(() => ({ map: null, tick: 0, hover: null }))

const palette = () => ({
  ground: tokenCss('--paper'), water: tokenCss('--map-water'), waterLine: tokenCss('--map-water-line'), green: tokenCss('--map-green'),
  road: tokenCss('--map-road'), roadMajor: tokenCss('--map-road-major'), rail: tokenCss('--map-road'), building: tokenCss('--map-building'),
  label: tokenCss('--ink'), labelMuted: tokenCss('--ink-3'), halo: tokenCss('--paper'),
})
const reduced = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches

export type GeoMarks = { paths: [number, number][][]; pins: { lon: number; lat: number; status: 'pass' | 'warn' | 'fail' | 'unknown' }[] }
const NO_GEO: GeoMarks = { paths: [], pins: [] }

type Props = {
  buildings: Building[]
  selected: Building | null
  marks: { lon: number; lat: number }[] // places the agent has put on the map
  /** Overlays given in map coordinates (a path outside a building, pins on a roof or a pool), drawn where they are. */
  geo?: GeoMarks
  /** A point the camera was told to look at: the map goes there, close enough to read the marks. */
  look?: [number, number] | null
  city: CityId
  scheme: 'light' | 'dark'
  inset: boolean
  frame: RefObject<HTMLElement | null> // the free part of the stage; the view centres inside it
  onSelect: (b: Building | null) => void
}

export function CityMap({ buildings, selected, marks, geo = NO_GEO, look = null, city, scheme, inset, frame, onSelect }: Props) {
  const el = useRef<HTMLDivElement>(null)
  const overlay = useRef<MapLibreOverlay | null>(null)
  const live = useRef({ buildings, selected, marks, geo, onSelect, fonts: false })
  live.current = { ...live.current, buildings, selected, marks, geo, onSelect }

  const draw = () => {
    const map = useMap.getState().map
    if (!map || !overlay.current) return
    const { buildings: data, selected: sel, marks: agentMarks, geo: marksGeo, fonts } = live.current
    const hover = useMap.getState().hover
    const z = map.getZoom()
    const ink = tokenRgba('--ink'), paper = tokenRgba('--paper'), accent = tokenRgba('--accent')
    const ramp = [1, 2, 3, 4, 5, 6].map((i) => tokenRgba(`--ramp-${i}`))
    const far = Math.max(0, Math.min(1, (12.4 - z) / 1.2)) // 1 at city scale, 0 once single buildings read
    const px = (b: Building) => 2.2 + Math.sqrt(b.count) * 1.5
    const grow = Math.max(0.75, Math.min(2.6, 1 + (z - 12) * 0.32))
    const band = (lo: number, hi: number, i: number) => ({ threshold: [lo, hi] as [number, number], color: [...ramp[i].slice(0, 3), 120 * far] as [number, number, number, number], zIndex: i })
    const under = { beforeId: 'road-name' } as object // interleaved: draw beneath the map's labels
    const line = (t: number, i: number) => ({ threshold: t, color: [...accent.slice(0, 3), 190 * far] as [number, number, number, number], strokeWidth: i ? 1 : 1.4, zIndex: 10 + i })

    overlay.current.setProps({
      layers: [
        // Density drawn as relief, the way a survey sheet draws height: read the dense districts before any dot.
        far > 0 && new ContourLayer<Building>({
          id: 'density', data, getPosition: (b: Building) => [b.lon, b.lat], cellSize: 640, gpuAggregation: false, ...under,
          contours: [band(2, 4, 0), band(4, 8, 1), band(8, 14, 2), band(14, 1e6, 3), line(2, 0), line(4, 1), line(8, 2), line(14, 3)],
          updateTriggers: { getPosition: data.length },
        } as never),
        new ScatterplotLayer<Building>({
          id: 'buildings', data, getPosition: (b) => [b.lon, b.lat], ...under,
          radiusUnits: 'pixels', getRadius: px, radiusScale: grow, radiusMinPixels: 1.6,
          getFillColor: ink, stroked: true, getLineColor: paper, lineWidthUnits: 'pixels', getLineWidth: 1,
          opacity: 1 - far * 0.35, pickable: true,
          onHover: ({ object }) => { if ((object ?? null) !== useMap.getState().hover) { useMap.setState({ hover: object ?? null }); draw() } },
          onClick: ({ object }) => live.current.onSelect(object ?? null),
        }),
        fonts && z >= 12.6 && new TextLayer<Building>({
          id: 'counts', data: data.filter((b) => b.count > 1), getPosition: (b) => [b.lon, b.lat], getText: (b) => String(b.count),
          getSize: 9.5, sizeScale: Math.min(1.5, grow * 0.72), getColor: paper, fontFamily: '"Martian Mono Variable"', fontWeight: 600,
          characterSet: '0123456789', getTextAnchor: 'middle', getAlignmentBaseline: 'center',
        }),
        new ScatterplotLayer<{ lon: number; lat: number }>({
          id: 'marks', data: agentMarks, getPosition: (m) => [m.lon, m.lat], radiusUnits: 'pixels', getRadius: 11, filled: false,
          stroked: true, getLineColor: accent, lineWidthUnits: 'pixels', getLineWidth: 1.5,
        }),
        new PathLayer<[number, number][]>({
          id: 'geo-paths', data: marksGeo.paths, getPath: (d) => d, widthUnits: 'pixels', getWidth: 3, getColor: accent, capRounded: true, jointRounded: true,
        }),
        new ScatterplotLayer<GeoMarks['pins'][number]>({
          id: 'geo-pins', data: marksGeo.pins, getPosition: (d) => [d.lon, d.lat], radiusUnits: 'pixels', getRadius: 6,
          getFillColor: (d) => tokenRgba(`--${d.status}`), stroked: true, getLineColor: paper, lineWidthUnits: 'pixels', getLineWidth: 1.5,
        }),
        new ScatterplotLayer<Building>({
          id: 'ring', data: [hover, sel].filter((b): b is Building => !!b), getPosition: (b) => [b.lon, b.lat],
          radiusUnits: 'pixels', getRadius: (b) => px(b) * grow + (b === sel ? 5 : 3.5), filled: false, stroked: true,
          getLineColor: accent, lineWidthUnits: 'pixels', getLineWidth: (b) => (b === sel ? 2.2 : 1.4),
          updateTriggers: { getRadius: [sel?.id, grow], getLineWidth: sel?.id },
        }),
      ],
    })
  }

  // Create the map once.
  useEffect(() => {
    const start = live.current.selected
    const map = new MapLibre({
      container: el.current!, style: mapStyle(palette()), attributionControl: false, dragRotate: false, pitchWithRotate: false,
      center: start ? [start.lon, start.lat] : CITIES[city].center, zoom: start ? 15 : CITIES[city].zoom, minZoom: 3, maxZoom: 19,
    })
    map.touchZoomRotate.disableRotation()
    overlay.current = new MapLibreOverlay({ interleaved: true, layers: [], getCursor: ({ isHovering }) => (isHovering ? 'pointer' : 'grab') })
    map.addControl(overlay.current as never)
    let raf = 0
    const onMove = () => { cancelAnimationFrame(raf); raf = requestAnimationFrame(() => { useMap.setState((s) => ({ tick: s.tick + 1 })); draw() }) }
    map.on('move', onMove)
    map.on('load', () => { useMap.setState({ map }); draw() })
    document.fonts.load('600 10px "Martian Mono Variable"').then(() => { live.current.fonts = true; draw() })
    const ro = new ResizeObserver(() => map.resize())
    ro.observe(el.current!)
    return () => { ro.disconnect(); map.remove(); useMap.setState({ map: null, hover: null }) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const map = useMap((s) => s.map)
  useEffect(draw, [buildings, selected, marks, geo, map]) // eslint-disable-line react-hooks/exhaustive-deps

  // The basemap is redrawn from the tokens when the scheme changes.
  const firstScheme = useRef(scheme)
  useEffect(() => {
    if (!map || firstScheme.current === scheme) return
    firstScheme.current = scheme
    map.setStyle(mapStyle(palette()))
    map.once('styledata', draw)
  }, [scheme, map]) // eslint-disable-line react-hooks/exhaustive-deps

  // Keep the view centred in the free part of the stage, not under the panes.
  useEffect(() => {
    if (!map) return
    const pad = () => {
      if (map.isMoving()) { map.once('moveend', pad); return } // setting padding would cut a flight short
      const f = frame.current?.getBoundingClientRect(), c = el.current!.getBoundingClientRect()
      map.setPadding(inset || !f ? { top: 0, right: 0, bottom: 0, left: 0 }
        : { top: Math.max(0, f.top - c.top), left: Math.max(0, f.left - c.left), right: Math.max(0, c.right - f.right), bottom: Math.max(0, c.bottom - f.bottom) })
    }
    pad()
    const ro = new ResizeObserver(pad)
    if (frame.current) ro.observe(frame.current)
    return () => ro.disconnect()
  }, [map, inset, frame])

  // The city switch is the one long move: a flight between the two sheets.
  const firstCity = useRef(true)
  useEffect(() => {
    if (!map) return
    if (firstCity.current) { firstCity.current = false; return }
    if (live.current.selected?.metro === city) return
    const { center, zoom } = CITIES[city]
    if (reduced()) map.jumpTo({ center, zoom })
    else map.flyTo({ center, zoom, duration: 2400, curve: 1.25, essential: true })
  }, [city, map])

  // A point the camera was told to look at wins over the selected building: go there, close enough to read the marks.
  const lookKey = look?.join(',')
  useEffect(() => {
    if (!map || !look || inset) return
    const go = () => { map.resize(); const to = { center: look, zoom: 18.5 }; if (reduced()) map.jumpTo(to); else map.flyTo({ ...to, duration: 1400, essential: true }) }
    const t = setTimeout(go, 120) // after the key plan has grown back into the full map
    return () => clearTimeout(t)
  }, [lookKey, map, inset]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!map || !selected || (look && !inset)) return
    const z = map.getZoom()
    const inView = map.getBounds().contains([selected.lon, selected.lat])
    const to = { center: [selected.lon, selected.lat] as [number, number], zoom: inset ? 15.5 : Math.max(z, 14.5) }
    if (inset || reduced()) map.jumpTo(to)
    else if (z < 12.5 || !inView) map.flyTo({ ...to, duration: 1400, essential: true })
  }, [selected, map, inset, lookKey]) // eslint-disable-line react-hooks/exhaustive-deps

  return <div ref={el} className="citymap" role="application" aria-label={`Map of scanned buildings in ${CITIES[city].name}. Use the search field or the list of buildings in view to choose one from the keyboard.`} />
}
