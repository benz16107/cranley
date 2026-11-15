import { useEffect, useRef } from 'react'
import { create } from 'zustand'
import { MapLibreOverlay } from '@deck.gl/maplibre'
import { PathLayer, ScatterplotLayer, TextLayer } from 'deck.gl'
import {
  CITIES, MapLibre, SCENE_FOV, SLOT, fetchLayerTile, layerCityUrl, loadCityMesh, mapStyle, sunPosition,
  type BaseView, type Building, type CityId, type CityMesh, type GeoMarks, type LayerCollection, type MapLayer,
} from '../../../core/index.ts'
import { tokenCss, tokenRgba } from '../design/ui.tsx'

/* The one map of the explorer: the base views, the data layers, the scanned buildings, and Vexcel's 3D city mesh
   in the same canvas once the view is close. It stays mounted while a building is open in front of it, so zooming
   back out of the building lands on the same map. */

type Tip = { x: number; y: number; title: string; detail: string; layer: string }
/** The live map and what the controls round it read: the camera, the building or feature under the pointer, and
    how far along the 3D city is. */
export const useWorld = create<{
  map: MapLibre | null; mesh: CityMesh | null; tick: number; hover: Building | null; tip: Tip | null
  zoom: number; pitch: number; bearing: number
  city3d: { status: CityMesh['status']; progress: number; capture: string }
}>(() => ({ map: null, mesh: null, tick: 0, hover: null, tip: null, zoom: 10, pitch: 0, bearing: 0, city3d: { status: 'idle', progress: 1, capture: '' } }))

/** Map zoom at which the aerial photo has fully replaced the drawn map, and from which the 3D city is asked for. */
export const CLOSE_Z = 16.4
const MESH_Z = 16.2
/** Zooming in past this on a scanned building opens it. */
const ENTER_Z = 18.5
const NO_GEO: GeoMarks = { paths: [], pins: [] }
const EMPTY: LayerCollection = { type: 'FeatureCollection', features: [] }
const reduced = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches

const palette = () => ({
  ground: tokenCss('--paper'), water: tokenCss('--map-water'), waterLine: tokenCss('--map-water-line'), green: tokenCss('--map-green'),
  road: tokenCss('--map-road'), roadMajor: tokenCss('--map-road-major'), rail: tokenCss('--map-road'), building: tokenCss('--map-building'),
  label: tokenCss('--ink'), labelMuted: tokenCss('--ink-3'), halo: tokenCss('--paper'),
})
/** The token each data layer is drawn in: the hue of the tool family it belongs with. Also its swatch in the layer list.
    A layer that is not here (one a source module added later) brings its own in the catalogue, or is drawn neutral. */
export const hueOf = (l: MapLayer) => LAYER_HUE[l.id] ?? (/^--[a-z0-9-]+$/.test(l.hue) ? l.hue : '--ink-2')
const LAYER_HUE: Record<string, string> = {
  scans: '--ink', records: '--tool-5', drone: '--tool-6', mesh3d: '--accent', fema: '--tool-2', harvey: '--ramp-5', fire_stations: '--tool-3',
  hydrants: '--tool-3', hospitals: '--tool-5', schools: '--tool-6', parcels: '--ink-2', transit: '--tool-1', ev: '--tool-4', radar: '--tool-2',
}

/** The map style for a base view with the chosen data layers spliced in over the 3D city and under the names. A pure
    function of what is shown, so every change is one `setStyle` and the map works out the difference. */
function styleFor(base: BaseView, city: CityId, layers: MapLayer[], on: string[], grid: Map<string, LayerCollection>) {
  const style = mapStyle(palette(), { base, closeUp: CLOSE_Z })
  const sources: Record<string, unknown> = {}, drawn: unknown[] = []
  const paper = tokenCss('--pane')
  for (const L of layers) {
    if (!on.includes(L.id) || !L.available || L.scope === 'client') continue
    const hue = tokenCss(hueOf(L)), id = `L-${L.id}`
    const top = L.maxzoom < 24 ? { maxzoom: L.maxzoom } : {}
    if (L.scope === 'tiles') {
      sources[id] = { type: 'raster', tiles: [L.tiles], tileSize: 256, maxzoom: L.tile_maxzoom, attribution: L.attribution || L.source }
      drawn.push({ id, type: 'raster', source: id, minzoom: L.minzoom, ...top, paint: { 'raster-opacity': 0.72, 'raster-fade-duration': 200 } })
      continue
    }
    // a whole-city file, a grid of tiles the map fills in as it looks, or both (the city file far out, the grid close in)
    const far = L.scope === 'city' || L.coarse, near = L.scope === 'grid', split = L.grid_z + 0.5
    if (far) sources[id] = { type: 'geojson', data: layerCityUrl(L.id, city) }
    if (near) sources[`${id}-grid`] = { type: 'geojson', data: grid.get(L.id) ?? EMPTY }
    for (const [src, zooms] of [...(far ? [[id, near ? { minzoom: L.minzoom, maxzoom: split } : { minzoom: L.minzoom, ...top }] as const] : []), ...(near ? [[`${id}-grid`, { minzoom: far ? split : L.minzoom, ...top }] as const] : [])]) {
      if (L.shape === 'area') {
        const dashed = L.id === 'mesh3d'
        const byLevel = ['case', ['has', 'level'], ['match', ['get', 'level'], ...[0, 1, 2, 3, 4].flatMap((n) => [n, tokenCss(`--ramp-${n + 1}`)]), tokenCss('--ramp-6')], hue]
        if (!dashed) drawn.push({ id: `${src}-fill`, type: 'fill', source: src, ...zooms, paint: { 'fill-color': byLevel, 'fill-opacity': ['case', ['has', 'level'], 0.62, ['boolean', ['get', 'floodway'], false], 0.42, 0.22] } })
        drawn.push({ id: `${src}-line`, type: 'line', source: src, ...zooms, paint: { 'line-color': hue, 'line-width': dashed ? 1.4 : 0.8, 'line-opacity': 0.9, ...(dashed ? { 'line-dasharray': [3, 2] } : {}) } })
      } else if (L.shape === 'line') {
        // lines that only show over the photo (parcels) are light with a dark edge, which reads on roofs and on lawns;
        // lines seen from further out are drawn in their hue on a paper edge
        const photo = L.minzoom >= CLOSE_Z - 1
        drawn.push({ id: `${src}-case`, type: 'line', source: src, ...zooms, paint: { 'line-color': photo ? 'rgba(10,16,24,0.55)' : paper, 'line-width': photo ? 2.2 : 3 } })
        drawn.push({ id: `${src}-line`, type: 'line', source: src, ...zooms, paint: { 'line-color': photo ? 'rgba(255,255,255,0.92)' : hue, 'line-width': photo ? 0.9 : 1.6 } })
      } else {
        const big = ['case', ['any', ['boolean', ['get', 'rail'], false], ['boolean', ['get', 'fast'], false]], 1.5, 1]
        const size = L.id === 'hydrants' || L.id === 'transit' ? 2.6 : 4
        drawn.push({ id: `${src}-dot`, type: 'circle', source: src, ...zooms, paint: {
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 9, ['*', size * 0.55, big], 14, ['*', size, big], 18, ['*', size * 1.5, big]],
          'circle-color': L.id === 'harvey' ? ['interpolate', ['linear'], ['coalesce', ['get', 'depth_m'], 0], 0, tokenCss('--ramp-2'), 1, tokenCss('--ramp-4'), 2.5, tokenCss('--ramp-6')] : hue,
          'circle-stroke-color': paper, 'circle-stroke-width': 1, 'circle-opacity': 0.95,
        } })
      }
    }
  }
  // Over the 3D city, not under it: close in the mesh covers the whole ground, and a layer under it could not be seen.
  // They lie flat over the mesh as the building marks do (CityMesh clears its depth when it has drawn).
  const at = style.layers.findIndex((l) => l.id === SLOT.marks)
  return { ...style, sources: { ...style.sources, ...sources }, layers: [...style.layers.slice(0, at), ...drawn, ...style.layers.slice(at)] } as typeof style
}
const dataLayerIds = (map: MapLibre) => map.getStyle().layers.filter((l) => l.id.startsWith('L-') && l.type !== 'raster').map((l) => l.id)

/** The tiles of zoom `z` that cover the view, nearest the middle first, at most `cap`. */
function tilesIn(map: MapLibre, z: number, cap = 16): [number, number][] {
  const b = map.getBounds(), n = 2 ** z, c = map.getCenter()
  const tx = (lon: number) => Math.floor(((lon + 180) / 360) * n), ty = (lat: number) => Math.floor(((1 - Math.asinh(Math.tan((lat * Math.PI) / 180)) / Math.PI) / 2) * n)
  const out: [number, number][] = []
  for (let x = tx(b.getWest()); x <= tx(b.getEast()); x++) for (let y = ty(b.getNorth()); y <= ty(b.getSouth()); y++) out.push([x, y])
  const cx = tx(c.lng), cy = ty(c.lat)
  return out.sort((p, q) => Math.hypot(p[0] - cx, p[1] - cy) - Math.hypot(q[0] - cx, q[1] - cy)).slice(0, cap)
}
const metres = (a: { lng: number; lat: number }, b: Building) => Math.hypot((b.lat - a.lat) * 110574, (b.lon - a.lng) * 111320 * Math.cos((a.lat * Math.PI) / 180))

type Props = {
  buildings: Building[]
  selected: Building | null
  marks: { lon: number; lat: number }[]
  geo?: GeoMarks
  look?: [number, number] | null
  city: CityId
  scheme: 'light' | 'dark'
  base: BaseView
  layers: MapLayer[]
  /** Ids of the layers that are on. */
  on: string[]
  /** The instant shadows are cast for, or null for no sun. */
  sun: Date | null
  /** A hand-off is under way or a building is open: the explorer chooses the 3D patch and the camera, not the map. */
  held?: boolean
  /** The building's scene is in front of the map: nothing is marked on it. */
  covered?: boolean
  onSelect: (b: Building | null) => void
  /** The person has zoomed right in on a scanned building. */
  onNear?: (b: Building) => void
}

export function WorldMap(props: Props) {
  const { buildings, selected, marks, geo = NO_GEO, look = null, city, scheme, base, layers, on, sun, covered = false } = props
  const el = useRef<HTMLDivElement>(null)
  const overlay = useRef<MapLibreOverlay | null>(null)
  const grid = useRef(new Map<string, LayerCollection>())
  const live = useRef({ ...props, geo, fonts: false })
  live.current = { ...live.current, ...props, geo }
  const onKey = on.join(',')

  const draw = () => {
    const map = useWorld.getState().map
    if (!map || !overlay.current) return
    const { buildings: data, selected: sel, marks: agentMarks, geo: marksGeo, fonts, on: shown, covered: behind } = live.current
    const hover = useWorld.getState().hover
    const z = map.getZoom()
    const ink = tokenRgba('--ink'), paper = tokenRgba('--paper'), accent = tokenRgba('--accent')
    const far = Math.max(0, Math.min(1, (12.4 - z) / 1.2)) // 1 at city scale, 0 once single buildings read
    const px = (b: Building) => 2.2 + Math.sqrt(b.count) * 1.5
    const grow = Math.max(0.75, Math.min(2.6, 1 + (z - 12) * 0.32))
    const top = { beforeId: SLOT.marks, parameters: { depthCompare: 'always', depthWriteEnabled: false } } as object // under the names, never behind the 3D city
    const ring = (id: string, rows: Building[], token: string, gap: number) => new ScatterplotLayer<Building>({
      id, data: rows, getPosition: (b) => [b.lon, b.lat], ...top, radiusUnits: 'pixels', getRadius: (b) => px(b) * grow + gap, filled: false, stroked: true,
      getLineColor: tokenRgba(token), lineWidthUnits: 'pixels', getLineWidth: 1.4, updateTriggers: { getRadius: grow },
    })
    overlay.current.setProps({
      layers: behind ? [] : [
        shown.includes('scans') && new ScatterplotLayer<Building>({
          id: 'buildings', data, getPosition: (b) => [b.lon, b.lat], ...top,
          radiusUnits: 'pixels', getRadius: px, radiusScale: grow * (1 - 0.34 * far), radiusMinPixels: 1.3,
          getFillColor: ink, stroked: true, getLineColor: paper, lineWidthUnits: 'pixels', getLineWidth: z > CLOSE_Z ? 1.6 : 1,
          opacity: 1 - far * 0.42, pickable: true,
          onHover: ({ object }) => { if ((object ?? null) !== useWorld.getState().hover) { useWorld.setState({ hover: object ?? null }); draw() } },
          onClick: ({ object }) => live.current.onSelect(object ?? null),
        }),
        shown.includes('scans') && fonts && z >= 12.6 && new TextLayer<Building>({
          id: 'counts', data: data.filter((b) => b.count > 1), getPosition: (b) => [b.lon, b.lat], getText: (b) => String(b.count), ...top,
          getSize: 9.5, sizeScale: Math.min(1.5, grow * 0.72), getColor: paper, fontFamily: '"Martian Mono Variable"', fontWeight: 600,
          characterSet: '0123456789', getTextAnchor: 'middle', getAlignmentBaseline: 'center',
        }),
        shown.includes('records') && ring('records', data.filter((b) => b.id.startsWith('p')), '--tool-5', 3),
        shown.includes('drone') && ring('drone', data.filter((b) => b.splat), '--tool-6', 5.5),
        new ScatterplotLayer<{ lon: number; lat: number }>({
          id: 'marks', data: agentMarks, getPosition: (m) => [m.lon, m.lat], ...top, radiusUnits: 'pixels', getRadius: 11, filled: false,
          stroked: true, getLineColor: accent, lineWidthUnits: 'pixels', getLineWidth: 1.5,
        }),
        new PathLayer<[number, number][]>({
          id: 'geo-paths', data: marksGeo.paths, getPath: (d) => d, ...top, widthUnits: 'pixels', getWidth: 3, getColor: accent, capRounded: true, jointRounded: true,
        }),
        new ScatterplotLayer<GeoMarks['pins'][number]>({
          id: 'geo-pins', data: marksGeo.pins, getPosition: (d) => [d.lon, d.lat], ...top, radiusUnits: 'pixels', getRadius: 6,
          getFillColor: (d) => tokenRgba(`--${d.status}`), stroked: true, getLineColor: paper, lineWidthUnits: 'pixels', getLineWidth: 1.5,
        }),
        new ScatterplotLayer<Building>({
          id: 'ring', data: [hover, sel].filter((b): b is Building => !!b), getPosition: (b) => [b.lon, b.lat], ...top,
          radiusUnits: 'pixels', getRadius: (b) => px(b) * grow + (b === sel ? 5 : 3.5), filled: false, stroked: true,
          getLineColor: accent, lineWidthUnits: 'pixels', getLineWidth: (b) => (b === sel ? 2.2 : 1.4),
          updateTriggers: { getRadius: [sel?.id, grow], getLineWidth: sel?.id },
        }),
      ],
    })
  }

  /** Fill the grid layers that are on for where the map looks now. */
  const loadGrid = () => {
    const map = useWorld.getState().map
    if (!map) return
    const { layers: all, on: shown } = live.current, z = map.getZoom()
    for (const L of all) {
      if (L.scope !== 'grid' || !L.available || !shown.includes(L.id) || z < (L.coarse ? L.grid_z + 0.2 : L.minzoom)) continue
      const want = tilesIn(map, L.grid_z), key = want.map((t) => t.join('_')).join(',')
      if ((grid.current.get(L.id) as { key?: string } | undefined)?.key === key) continue
      void Promise.all(want.map(([x, y]) => fetchLayerTile(L.id, L.grid_z, x, y).catch(() => null))).then((parts) => {
        const fc = Object.assign({ type: 'FeatureCollection' as const, features: parts.flatMap((p) => p?.features ?? []) }, { key })
        grid.current.set(L.id, fc)
        ;(useWorld.getState().map?.getSource(`L-${L.id}-grid`) as { setData?: (d: unknown) => void } | undefined)?.setData?.(fc)
      })
    }
  }

  // Create the map once.
  useEffect(() => {
    const start = live.current.selected
    const map = new MapLibre({
      container: el.current!, style: styleFor(base, city, layers, on, grid.current), attributionControl: false,
      center: start ? [start.lon, start.lat] : CITIES[city].center, zoom: start ? 15 : CITIES[city].zoom, minZoom: 3, maxZoom: 21.4, maxPitch: 80,
    })
    map.setVerticalFieldOfView(SCENE_FOV) // the building scene's lens, so the two cameras can be laid on each other
    let mesh: CityMesh | null = null, gone = false
    overlay.current = new MapLibreOverlay({ interleaved: true, layers: [], getCursor: ({ isHovering }) => (isHovering ? 'pointer' : 'grab') })
    map.addControl(overlay.current as never)
    const ensure = () => { try { if (mesh && map.isStyleLoaded() && !map.getLayer(mesh.id)) map.addLayer(mesh, SLOT.solid) } catch { /* the style is still changing: the next event tries again */ } }
    let raf = 0, tipRaf = 0
    const onMove = () => { cancelAnimationFrame(raf); raf = requestAnimationFrame(() => { useWorld.setState((s) => ({ tick: s.tick + 1, zoom: map.getZoom(), pitch: map.getPitch(), bearing: map.getBearing() })); draw() }) }
    // MapLibre's wheel zoom ends with no originalEvent, so "the person did this" is also: they touched the map a moment ago
    let input = 0, lastZ = map.getZoom()
    const touched = () => { input = performance.now() }
    for (const t of ['wheel', 'pointerdown', 'dblclick', 'keydown']) el.current!.addEventListener(t, touched, { passive: true, capture: true })
    const settle = (e?: { originalEvent?: unknown }) => {
      const z = map.getZoom(), c = map.getCenter(), now = live.current
      const closer = z > lastZ + 0.01; lastZ = z // zooming out past a building (on the way back from one) must not open it again
      mesh?.setShown(z >= MESH_Z - 0.2)
      if (!now.held && z >= MESH_Z) void mesh?.want({ lat: c.lat, lon: c.lng })
      mesh?.shadowsAt(c.lng, c.lat)
      loadGrid()
      if (!(e?.originalEvent || performance.now() - input < 1200) || !closer || now.held || z < ENTER_Z) return
      // the person zoomed right in: a scanned building at the middle of the view is the one they mean
      const near = now.buildings.map((b) => [metres(c, b), b] as const).sort((p, q) => p[0] - q[0])[0]
      if (near && near[0] < Math.max(35, 9000 / 2 ** (z - 12))) now.onNear?.(near[1])
    }
    map.on('move', onMove)
    map.on('moveend', settle)
    map.on('styledata', ensure); map.on('idle', ensure)
    map.on('mousemove', (e) => {
      cancelAnimationFrame(tipRaf)
      tipRaf = requestAnimationFrame(() => {
        if (live.current.covered || useWorld.getState().hover) { if (useWorld.getState().tip) useWorld.setState({ tip: null }); return }
        const ids = dataLayerIds(map), f = ids.length ? map.queryRenderedFeatures([[e.point.x - 3, e.point.y - 3], [e.point.x + 3, e.point.y + 3]], { layers: ids })[0] : undefined
        const L = f && live.current.layers.find((l) => f.layer.id.startsWith(`L-${l.id}`))
        const p = f?.properties as { name?: string; detail?: string } | undefined
        const tip = f && L && (p?.name || L.shape !== 'line') ? { x: e.point.x, y: e.point.y, title: p?.name || L.title, detail: p?.detail ?? '', layer: L.title } : null
        if (tip || useWorld.getState().tip) useWorld.setState({ tip })
      })
    })
    map.on('mouseout', () => useWorld.setState({ tip: null }))
    map.on('load', () => { useWorld.setState({ map, zoom: map.getZoom() }); ensure(); settle(); draw() })
    const host = el.current as unknown as { __map?: unknown; __mesh?: unknown }
    host.__map = map // check scripts find the map and the 3D city here, as they find the scene's engine
    // the 3D city arrives a moment after the map: it brings three.js, which the first paint of the page does not wait for
    void loadCityMesh().then((Mesh) => {
      if (gone) return
      const m = mesh = new Mesh()
      m.onChange = () => useWorld.setState({ city3d: { status: m.status, progress: m.progress, capture: (m.patch?.capture?.[0] ?? '').slice(0, 7).replace('/', '-') } })
      host.__mesh = m; useWorld.setState({ mesh: m })
      ensure(); if (map.loaded()) settle()
    })
    document.fonts.load('600 10px "Martian Mono Variable"').then(() => { live.current.fonts = true; draw() })
    const ro = new ResizeObserver(() => map.resize())
    ro.observe(el.current!)
    return () => { gone = true; ro.disconnect(); mesh?.dispose(); map.remove(); useWorld.setState({ map: null, mesh: null, hover: null, tip: null }) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const map = useWorld((s) => s.map), mesh = useWorld((s) => s.mesh)
  useEffect(draw, [buildings, selected, marks, geo, map, onKey, covered]) // eslint-disable-line react-hooks/exhaustive-deps

  // The style follows what is shown: the base view, the scheme's colours, the city's files, the layers that are on.
  const styleKey = `${base}|${scheme}|${city}|${onKey}|${layers.length}`, drawnStyle = useRef(styleKey)
  useEffect(() => {
    if (!map || drawnStyle.current === styleKey) return
    drawnStyle.current = styleKey
    for (const id of [...grid.current.keys()]) if (!on.includes(id)) grid.current.delete(id) // switched off: switching it on again asks afresh
    map.setStyle(styleFor(base, city, layers, on, grid.current))
    map.once('styledata', () => { draw(); loadGrid() })
  }, [styleKey, map]) // eslint-disable-line react-hooks/exhaustive-deps

  // The sun: where it stands over the middle of the map at the chosen instant; the 3D city casts the shadows.
  const sunKey = sun?.getTime() ?? null
  useEffect(() => {
    if (!map || !mesh) return
    const c = map.getCenter()
    mesh.setSun(sun ? sunPosition(sun, c.lat, c.lng) : null)
  }, [sunKey, map, mesh]) // eslint-disable-line react-hooks/exhaustive-deps

  // The city switch is the one long move: a flight between the two cities.
  const firstCity = useRef(true)
  useEffect(() => {
    if (!map) return
    if (firstCity.current) { firstCity.current = false; return }
    if (live.current.selected?.metro === city || live.current.held) return
    const { center, zoom } = CITIES[city]
    if (reduced()) map.jumpTo({ center, zoom, pitch: 0, bearing: 0 })
    else map.flyTo({ center, zoom, pitch: 0, bearing: 0, duration: 2400, curve: 1.25, essential: true })
  }, [city, map])

  // A point the camera was told to look at: go there, close enough to read the marks.
  const lookKey = look?.join(',')
  useEffect(() => {
    if (!map || !look || live.current.held) return
    const go = () => { map.resize(); const to = { center: look, zoom: 18.2 }; if (reduced()) map.jumpTo(to); else map.flyTo({ ...to, duration: 1400, essential: true }) }
    const t = setTimeout(go, 120) // after the page has laid the map out
    return () => clearTimeout(t)
  }, [lookKey, map]) // eslint-disable-line react-hooks/exhaustive-deps

  return <div ref={el} className="citymap" role="application" aria-label={`Map of scanned buildings in ${CITIES[city].name}. Scroll to zoom from the city down to a building; the table beside it lists the same buildings for the keyboard.`} />
}
