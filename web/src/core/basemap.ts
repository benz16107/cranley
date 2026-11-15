import type { StyleSpecification } from 'maplibre-gl'

/** Colours the basemap needs. The app fills this from the design tokens (see mapPalette in CityMap). */
export type MapPalette = {
  ground: string
  water: string
  waterLine: string
  green: string
  road: string
  roadMajor: string
  rail: string
  building: string
  label: string
  labelMuted: string
  halo: string
}

/** What the ground is drawn from. Every one becomes the aerial photo up close (see `closeUp`).
    `aerial` and `terrain` are photos from the whole Earth down: Sentinel-2 far out, USGS aerial photos over the
    United States from zoom 12, Vexcel's orthophoto in the two cities from zoom 14. `dark` is the drawn map; the look
    passes it a dark palette. */
export type BaseView = 'aerial' | 'streets' | 'terrain' | 'dark'
export const BASE_VIEWS: { id: BaseView; label: string; hint: string }[] = [
  { id: 'aerial', label: 'Satellite', hint: 'Satellite and aerial photos at every zoom' },
  { id: 'streets', label: 'Streets', hint: 'Roads, water and place names' },
  { id: 'terrain', label: 'Terrain', hint: 'Photos with shaded relief, main roads and names' },
  { id: 'dark', label: 'Dark', hint: 'A dark ground for reading data layers' },
]
export interface MapStyleOptions {
  base?: BaseView
  /** Draw the Earth as a globe when zoomed out (MapLibre goes over to the flat map by itself as the view closes in). */
  globe?: boolean
  /** Zoom at which the aerial photo has faded in under every base, so the map runs on into the 3D city. Missing: never. */
  closeUp?: number
}
/** Ids of empty layers that mark where a look inserts its own: data under `SLOT.data`, 3D under `SLOT.solid`, marks under `SLOT.marks`. */
export const SLOT = { data: 'slot-data', solid: 'slot-3d', marks: 'slot-marks' } as const
const SAT_CREDIT = 'Sentinel-2 cloudless, s2maps.eu, by EOX IT Services GmbH (contains modified Copernicus Sentinel data 2016 and 2017), CC BY 4.0 · USGS National Map (NAIP)'
export const MAP_CREDIT: Record<BaseView | 'close', string> = {
  streets: '© OpenStreetMap · OpenFreeMap', dark: '© OpenStreetMap · OpenFreeMap',
  terrain: `${SAT_CREDIT} · relief: Mapzen terrain tiles (USGS 3DEP, SRTM) · © OpenStreetMap`,
  aerial: `${SAT_CREDIT} · © OpenStreetMap`, close: 'Aerial: © Vexcel Imaging',
}

const TILES = 'https://tiles.openfreemap.org/planet'
// Sentinel-2 cloudless 2016 is the one EOX mosaic under CC BY 4.0 (the later years are non-commercial). No key.
const S2 = 'https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless_3857/default/g/{z}/{y}/{x}.jpg'
const US: [number, number, number, number] = [-125, 24, -66.5, 49.5] // the USGS service holds photos of the United States only
const USGS = 'https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/tile/{z}/{y}/{x}'
const RELIEF = 'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png'
const ORTHO = '/api/layers/ortho/{z}/{x}/{y}.jpg' // Vexcel's orthophoto through our server, which holds the key and the cache
const GLYPHS = 'https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf'

/** Exponential zoom ramp for line widths. */
const w = (...stops: number[]) => ['interpolate', ['exponential', 1.6], ['zoom'], ...stops] as never

/**
 * Our own basemap over OpenFreeMap's OpenMapTiles vector tiles (no API key). Drawn like a survey sheet:
 * roads as ink lines of three weights, water as a flat wash with a shoreline, names set small and tracked,
 * water names in italic as on a printed topographic map.
 */
export function mapStyle(p: MapPalette, o: MapStyleOptions = {}): StyleSpecification {
  const base = o.base ?? 'streets', photo = base === 'aerial' || base === 'terrain', hybrid = base === 'terrain', near = o.closeUp
  // on a photo, names are white on a dark plate; elsewhere ink on paper
  const label = photo ? '#ffffff' : p.label, labelMuted = photo ? 'rgba(255,255,255,0.86)' : p.labelMuted, halo = photo ? 'rgba(10,16,24,0.72)' : p.halo
  const ramp = (from: number, to: number) => ['interpolate', ['linear'], ['zoom'], from, 0, to, 1] as never
  const fadeIn = near == null ? 0 : ramp(near - 1, near)
  const onPhoto = (alpha: number) => `rgba(255,255,255,${alpha})` // road lines over a photo
  const slot = (id: string) => ({ id, type: 'background' as const, layout: { visibility: 'none' as const } })
  const drawn = (ids: string[]) => (l: { id: string }) => !ids.includes(l.id)
  const road = (id: string, classes: string[], color: string, width: unknown, minzoom: number, opacity = 1) => ({
    id, type: 'line' as const, source: 'omt', 'source-layer': 'transportation', minzoom,
    filter: ['all', ['in', ['get', 'class'], ['literal', classes]], ['!=', ['get', 'brunnel'], 'tunnel']] as never,
    layout: { 'line-cap': 'round' as const, 'line-join': 'round' as const },
    paint: { 'line-color': color, 'line-width': width as never, 'line-opacity': opacity },
  })
  return {
    version: 8,
    glyphs: GLYPHS,
    ...(o.globe ? { projection: { type: 'globe' } } : {}),
    sources: {
      omt: { type: 'vector', url: TILES, attribution: '© OpenStreetMap · OpenFreeMap' },
      ...(photo ? {
        // the same mosaic twice: its first four levels are a few small tiles that cover the Earth, so there is a
        // picture under the view at once and at every zoom while the sharp tiles load over it
        'sat-low': { type: 'raster', tiles: [S2], tileSize: 256, maxzoom: 3, attribution: 'Sentinel-2 cloudless by EOX' },
        sat: { type: 'raster', tiles: [S2], tileSize: 256, maxzoom: 13, attribution: 'Sentinel-2 cloudless by EOX' },
      } : {}),
      ...(photo || near != null ? {
        usgs: { type: 'raster', tiles: [USGS], tileSize: 256, maxzoom: 16, bounds: US, attribution: 'USGS National Map' },
        ortho: { type: 'raster', tiles: [ORTHO], tileSize: 256, minzoom: 14, maxzoom: 21, attribution: '© Vexcel Imaging' },
      } : {}),
      ...(base === 'terrain' ? { relief: { type: 'raster-dem', tiles: [RELIEF], tileSize: 256, maxzoom: 15, encoding: 'terrarium', attribution: 'Mapzen terrain tiles' } } : {}),
    },
    layers: ([
      { id: 'ground', type: 'background', paint: { 'background-color': photo ? '#0b1a2b' : p.ground } }, // deep water, for the moment before the first photo
      { id: 'green', type: 'fill', source: 'omt', 'source-layer': 'park', paint: { 'fill-color': p.green } },
      { id: 'wood', type: 'fill', source: 'omt', 'source-layer': 'landcover',
        filter: ['in', ['get', 'class'], ['literal', ['wood', 'grass']]], paint: { 'fill-color': p.green, 'fill-opacity': 0.6 } },
      { id: 'water', type: 'fill', source: 'omt', 'source-layer': 'water',
        filter: ['!=', ['get', 'brunnel'], 'tunnel'], paint: { 'fill-color': p.water } },
      { id: 'shore', type: 'line', source: 'omt', 'source-layer': 'water',
        paint: { 'line-color': p.waterLine, 'line-width': 0.6 } },
      { id: 'stream', type: 'line', source: 'omt', 'source-layer': 'waterway',
        paint: { 'line-color': p.waterLine, 'line-width': w(8, 0.4, 14, 1.4) } },
      road('road-minor', ['minor', 'service', 'track'], p.road, w(12, 0.3, 16, 1.6), 12, 0.7),
      { id: 'rail', type: 'line', source: 'omt', 'source-layer': 'transportation', minzoom: 11,
        filter: ['==', ['get', 'class'], 'rail'], paint: { 'line-color': p.rail, 'line-width': 0.8, 'line-dasharray': [4, 3] } },
      { id: 'building', type: 'fill', source: 'omt', 'source-layer': 'building', minzoom: 14,
        paint: { 'fill-color': p.building, 'fill-opacity': ['interpolate', ['linear'], ['zoom'], 14, 0, 15, 1] } },
      { id: 'building-line', type: 'line', source: 'omt', 'source-layer': 'building', minzoom: 15,
        paint: { 'line-color': p.road, 'line-width': 0.5, 'line-opacity': 0.6 } },
      ...(hybrid ? [] : [
        road('road-mid', ['secondary', 'tertiary'], p.road, w(9, 0.3, 16, 3), 9),
        road('road-main', ['primary', 'trunk'], p.roadMajor, w(7, 0.4, 16, 4.5), 7),
        road('road-motorway', ['motorway'], p.roadMajor, w(5, 0.6, 16, 6), 5),
      ]),
      ...(photo ? [
        { id: 'photo-low', type: 'raster' as const, source: 'sat-low', paint: { 'raster-fade-duration': 0 } },
        { id: 'photo-world', type: 'raster' as const, source: 'sat', paint: { 'raster-fade-duration': 150 } },
      ] : []),
      // every layer here states its minzoom: a style change that drops one (setStyle's diff) leaves the old value in
      // place, which is how the photo once stayed hidden after switching to it from Streets
      ...(photo || near != null ? [
        { id: 'photo-far', type: 'raster' as const, source: 'usgs', minzoom: photo ? 12 : near! - 1, paint: { 'raster-opacity': photo ? ramp(12, 13) : fadeIn, 'raster-fade-duration': 150 } },
        { id: 'photo', type: 'raster' as const, source: 'ortho', minzoom: photo ? 14 : Math.max(14, near! - 1), paint: { 'raster-opacity': photo ? ramp(14, 15) : fadeIn, 'raster-fade-duration': 150 } },
      ] : []),
      ...(hybrid ? [
        { id: 'relief', type: 'hillshade' as const, source: 'relief',
          paint: { 'hillshade-exaggeration': 0.5, 'hillshade-shadow-color': 'rgba(0,0,0,0.55)', 'hillshade-highlight-color': 'rgba(255,255,255,0.18)', 'hillshade-accent-color': 'rgba(0,0,0,0.25)' } },
        road('road-mid', ['secondary', 'tertiary'], onPhoto(0.35), w(9, 0.3, 16, 2), 10),
        road('road-main', ['primary', 'trunk'], onPhoto(0.5), w(7, 0.4, 16, 3), 7),
        road('road-motorway', ['motorway'], onPhoto(0.6), w(5, 0.6, 16, 4), 5),
      ] : []),
      slot(SLOT.data), slot(SLOT.solid), slot(SLOT.marks),
      { id: 'road-name', type: 'symbol', source: 'omt', 'source-layer': 'transportation_name', minzoom: 14,
        layout: { 'symbol-placement': 'line', 'text-field': ['get', 'name'], 'text-font': ['Noto Sans Regular'],
          'text-size': 10, 'text-letter-spacing': 0.04 },
        paint: { 'text-color': labelMuted, 'text-halo-color': halo, 'text-halo-width': 1.2 } },
      { id: 'water-name', type: 'symbol', source: 'omt', 'source-layer': 'water_name', minzoom: 9,
        layout: { 'text-field': ['get', 'name'], 'text-font': ['Noto Sans Italic'], 'text-size': 11, 'text-letter-spacing': 0.08 },
        paint: { 'text-color': photo ? labelMuted : p.waterLine, 'text-halo-color': halo, 'text-halo-width': 1 } },
      { id: 'place-small', type: 'symbol', source: 'omt', 'source-layer': 'place', minzoom: 10,
        filter: ['in', ['get', 'class'], ['literal', ['suburb', 'neighbourhood', 'quarter', 'village']]],
        layout: { 'text-field': ['get', 'name'], 'text-font': ['Noto Sans Regular'], 'text-size': 10,
          'text-transform': 'uppercase', 'text-letter-spacing': 0.14, 'text-max-width': 7 },
        paint: { 'text-color': labelMuted, 'text-halo-color': halo, 'text-halo-width': 1.4 } },
      { id: 'town', type: 'symbol', source: 'omt', 'source-layer': 'place', minzoom: 8, filter: ['==', ['get', 'class'], 'town'],
        layout: { 'text-field': ['get', 'name'], 'text-font': ['Noto Sans Regular'], 'text-size': ['interpolate', ['linear'], ['zoom'], 8, 9.5, 13, 12],
          'text-transform': 'uppercase', 'text-letter-spacing': 0.16, 'text-max-width': 7 },
        paint: { 'text-color': labelMuted, 'text-halo-color': halo, 'text-halo-width': 1.4 } },
      { id: 'place', type: 'symbol', source: 'omt', 'source-layer': 'place', filter: ['==', ['get', 'class'], 'city'],
        layout: { 'text-field': ['get', 'name'], 'text-font': ['Noto Sans Bold'],
          'text-size': ['interpolate', ['linear'], ['zoom'], 6, 11, 12, 15],
          'text-transform': 'uppercase', 'text-letter-spacing': 0.18, 'text-max-width': 8 },
        paint: { 'text-color': label, 'text-halo-color': halo, 'text-halo-width': 1.6 } },
    ] as StyleSpecification['layers']).filter(drawn(
      // a photo carries its own ground: satellite keeps only names over it, terrain adds relief and the main roads (above)
      photo ? ['green', 'wood', 'water', 'shore', 'stream', 'road-minor', 'rail', 'building', 'building-line', ...(hybrid ? [] : ['road-mid', 'road-main', 'road-motorway'])] : [])),
  }
}
