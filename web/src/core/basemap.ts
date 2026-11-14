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

/** What the ground is drawn from. Every one becomes the aerial photo up close (see `closeUp`). */
export type BaseView = 'streets' | 'aerial' | 'terrain' | 'plain'
export const BASE_VIEWS: { id: BaseView; label: string; hint: string }[] = [
  { id: 'streets', label: 'Streets', hint: 'Roads, water and place names' },
  { id: 'aerial', label: 'Aerial', hint: 'Aerial photos at every zoom' },
  { id: 'terrain', label: 'Terrain', hint: 'Streets over shaded relief' },
  { id: 'plain', label: 'Plain', hint: 'A quiet ground for reading data layers' },
]
export interface MapStyleOptions {
  base?: BaseView
  /** Zoom at which the aerial photo has faded in under every base, so the map runs on into the 3D city. Missing: never. */
  closeUp?: number
}
/** Ids of empty layers that mark where a look inserts its own: data under `SLOT.data`, 3D under `SLOT.solid`, marks under `SLOT.marks`. */
export const SLOT = { data: 'slot-data', solid: 'slot-3d', marks: 'slot-marks' } as const
export const MAP_CREDIT: Record<BaseView | 'close', string> = {
  streets: '© OpenStreetMap · OpenFreeMap', plain: '© OpenStreetMap · OpenFreeMap',
  terrain: '© OpenStreetMap · OpenFreeMap · relief: Mapzen terrain tiles (USGS 3DEP, SRTM)',
  aerial: 'Aerial: USGS National Map (NAIP) · © OpenStreetMap', close: 'Aerial: © Vexcel Imaging',
}

const TILES = 'https://tiles.openfreemap.org/planet'
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
  const base = o.base ?? 'streets', photo = base === 'aerial', plain = base === 'plain', near = o.closeUp
  // on a photo, names are white on a dark plate; elsewhere ink on paper
  const label = photo ? '#ffffff' : p.label, labelMuted = photo ? 'rgba(255,255,255,0.86)' : p.labelMuted, halo = photo ? 'rgba(10,16,24,0.72)' : p.halo
  const fadeIn = near == null ? 0 : (['interpolate', ['linear'], ['zoom'], near - 1, 0, near, 1] as never)
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
    sources: {
      omt: { type: 'vector', url: TILES, attribution: '© OpenStreetMap · OpenFreeMap' },
      ...(photo || near != null ? {
        usgs: { type: 'raster', tiles: [USGS], tileSize: 256, maxzoom: 16, attribution: 'USGS National Map' },
        ortho: { type: 'raster', tiles: [ORTHO], tileSize: 256, minzoom: 14, maxzoom: 21, attribution: '© Vexcel Imaging' },
      } : {}),
      ...(base === 'terrain' ? { relief: { type: 'raster-dem', tiles: [RELIEF], tileSize: 256, maxzoom: 15, encoding: 'terrarium', attribution: 'Mapzen terrain tiles' } } : {}),
    },
    layers: ([
      { id: 'ground', type: 'background', paint: { 'background-color': p.ground } },
      ...(base === 'terrain' ? [{ id: 'relief', type: 'hillshade' as const, source: 'relief',
        paint: { 'hillshade-exaggeration': 0.55, 'hillshade-shadow-color': p.roadMajor, 'hillshade-highlight-color': p.halo, 'hillshade-accent-color': p.road } }] : []),
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
      road('road-mid', ['secondary', 'tertiary'], p.road, w(9, 0.3, 16, 3), 9),
      road('road-main', ['primary', 'trunk'], p.roadMajor, w(7, 0.4, 16, 4.5), 7),
      road('road-motorway', ['motorway'], p.roadMajor, w(5, 0.6, 16, 6), 5),
      { id: 'rail', type: 'line', source: 'omt', 'source-layer': 'transportation', minzoom: 11,
        filter: ['==', ['get', 'class'], 'rail'], paint: { 'line-color': p.rail, 'line-width': 0.8, 'line-dasharray': [4, 3] } },
      { id: 'building', type: 'fill', source: 'omt', 'source-layer': 'building', minzoom: 14,
        paint: { 'fill-color': p.building, 'fill-opacity': ['interpolate', ['linear'], ['zoom'], 14, 0, 15, 1] } },
      { id: 'building-line', type: 'line', source: 'omt', 'source-layer': 'building', minzoom: 15,
        paint: { 'line-color': p.road, 'line-width': 0.5, 'line-opacity': 0.6 } },
      ...(photo || near != null ? [
        { id: 'photo-far', type: 'raster' as const, source: 'usgs', ...(photo ? {} : { minzoom: near! - 1 }), paint: { 'raster-opacity': photo ? 1 : fadeIn, 'raster-fade-duration': 150 } },
        { id: 'photo', type: 'raster' as const, source: 'ortho', minzoom: photo ? 14 : Math.max(14, near! - 1), paint: { 'raster-opacity': photo ? 1 : fadeIn, 'raster-fade-duration': 150 } },
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
      // a photo carries its own ground; a plain ground keeps water, the main roads and the names of places
      photo ? ['green', 'wood', 'water', 'shore', 'stream', 'road-minor', 'road-mid', 'rail', 'building', 'building-line']
        : plain ? ['green', 'wood', 'stream', 'road-minor', 'road-mid', 'rail', 'building', 'building-line', 'road-name', 'place-small'] : [])),
  }
}
