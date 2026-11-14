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

const TILES = 'https://tiles.openfreemap.org/planet'
const GLYPHS = 'https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf'

/** Exponential zoom ramp for line widths. */
const w = (...stops: number[]) => ['interpolate', ['exponential', 1.6], ['zoom'], ...stops] as never

/**
 * Our own basemap over OpenFreeMap's OpenMapTiles vector tiles (no API key). Drawn like a survey sheet:
 * roads as ink lines of three weights, water as a flat wash with a shoreline, names set small and tracked,
 * water names in italic as on a printed topographic map.
 */
export function mapStyle(p: MapPalette): StyleSpecification {
  const road = (id: string, classes: string[], color: string, width: unknown, minzoom: number, opacity = 1) => ({
    id, type: 'line' as const, source: 'omt', 'source-layer': 'transportation', minzoom,
    filter: ['all', ['in', ['get', 'class'], ['literal', classes]], ['!=', ['get', 'brunnel'], 'tunnel']] as never,
    layout: { 'line-cap': 'round' as const, 'line-join': 'round' as const },
    paint: { 'line-color': color, 'line-width': width as never, 'line-opacity': opacity },
  })
  return {
    version: 8,
    glyphs: GLYPHS,
    sources: { omt: { type: 'vector', url: TILES, attribution: '© OpenStreetMap · OpenFreeMap' } },
    layers: [
      { id: 'ground', type: 'background', paint: { 'background-color': p.ground } },
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
      { id: 'road-name', type: 'symbol', source: 'omt', 'source-layer': 'transportation_name', minzoom: 14,
        layout: { 'symbol-placement': 'line', 'text-field': ['get', 'name'], 'text-font': ['Noto Sans Regular'],
          'text-size': 10, 'text-letter-spacing': 0.04 },
        paint: { 'text-color': p.labelMuted, 'text-halo-color': p.halo, 'text-halo-width': 1.2 } },
      { id: 'water-name', type: 'symbol', source: 'omt', 'source-layer': 'water_name', minzoom: 9,
        layout: { 'text-field': ['get', 'name'], 'text-font': ['Noto Sans Italic'], 'text-size': 11, 'text-letter-spacing': 0.08 },
        paint: { 'text-color': p.waterLine, 'text-halo-color': p.halo, 'text-halo-width': 1 } },
      { id: 'place-small', type: 'symbol', source: 'omt', 'source-layer': 'place', minzoom: 10,
        filter: ['in', ['get', 'class'], ['literal', ['suburb', 'neighbourhood', 'quarter', 'village']]],
        layout: { 'text-field': ['get', 'name'], 'text-font': ['Noto Sans Regular'], 'text-size': 10,
          'text-transform': 'uppercase', 'text-letter-spacing': 0.14, 'text-max-width': 7 },
        paint: { 'text-color': p.labelMuted, 'text-halo-color': p.halo, 'text-halo-width': 1.4 } },
      { id: 'place', type: 'symbol', source: 'omt', 'source-layer': 'place',
        filter: ['in', ['get', 'class'], ['literal', ['city', 'town']]],
        layout: { 'text-field': ['get', 'name'], 'text-font': ['Noto Sans Bold'],
          'text-size': ['interpolate', ['linear'], ['zoom'], 6, 11, 12, 15],
          'text-transform': 'uppercase', 'text-letter-spacing': 0.18, 'text-max-width': 8 },
        paint: { 'text-color': p.label, 'text-halo-color': p.halo, 'text-halo-width': 1.6 } },
    ],
  }
}
