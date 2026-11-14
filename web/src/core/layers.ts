/* Clients for the map's data layers (server: threshold/api/layers.py) and for standing a scan in the world. A layer's
   title, source, caveat and the day our copy was fetched all come from the server's catalogue, so a look prints
   them and never writes them. */
import type { Site } from '../world/handoff.ts'

/** One row of the layer catalogue. `scope`: 'city' is one GeoJSON file per city; 'grid' is one per map tile at
    `grid_z` (plus a generalised whole-city file when `coarse`); 'tiles' is a raster the browser loads from `tiles`;
    'client' is drawn from what the page already has. */
export interface MapLayer {
  id: string; title: string; group: string
  shape: 'point' | 'line' | 'area' | 'raster' | 'readout'
  scope: 'city' | 'grid' | 'client' | 'tiles'
  source: string; source_url: string; confidence: 'high' | 'medium' | 'low'; note: string
  /** The licence the source names and the credit line it asks for ('' when it asks for none: credit `source`). */
  licence: string; attribution: string
  /** A design token for its colour ('' is the look's choice), and for an area coloured by value (each feature's
      `level`, 0 to 5, on the look's six-step ramp) what the levels mean. */
  hue: string; legend: { title: string; unit?: string; stops: [number, string][] } | null
  /** The date the source gives for its data, and the day our copy was fetched ('' when not fetched yet). */
  data_date: string; fetched: string
  /** The map zooms between which it is drawn, and for a raster the finest zoom its own tiles exist at. */
  available: boolean; grid_z: number; minzoom: number; maxzoom: number; tile_maxzoom: number; on: boolean; coarse: boolean; tiles: string
}
export interface Weather {
  time: string; timezone: string; utc_offset_s: number; sky: string
  temperature_c: number | null; feels_c: number | null; humidity_pct: number | null
  wind_kmh: number | null; gust_kmh: number | null; wind_from_deg: number | null; rain_mm: number | null; cloud_pct: number | null
  source: string
}
export type LayerCollection = { type: 'FeatureCollection'; features: GeoJSON.Feature[]; meta?: { fetched: string; count: number; truncated: boolean } }

async function get<T>(path: string): Promise<T> {
  const r = await fetch(path)
  if (!r.ok) throw new Error((await r.json().catch(() => null))?.detail ?? `The server answered ${r.status}.`)
  return r.json()
}
const catalogues = new Map<string, Promise<MapLayer[]>>()
/** Every layer for a city. One request per city per session; `again` asks afresh (a layer just fetched has its date now). */
export function fetchLayers(city: string, again = false): Promise<MapLayer[]> {
  let p = again ? undefined : catalogues.get(city)
  if (!p) { p = get<{ layers: MapLayer[] }>(`/api/layers?city=${city}`).then((x) => x.layers); p.catch(() => catalogues.delete(city)); catalogues.set(city, p) }
  return p
}
/** A 'city' layer's file (or a grid layer's generalised copy): give it to a GeoJSON map source as its data. */
export const layerCityUrl = (id: string, city: string) => `/api/layers/${encodeURIComponent(id)}/geojson?city=${city}`
const tiles = new Map<string, Promise<LayerCollection>>()
/** One tile of a 'grid' layer at the layer's own `grid_z`. Kept for the session. */
export function fetchLayerTile(id: string, z: number, x: number, y: number): Promise<LayerCollection> {
  const key = `${id}/${z}/${x}/${y}`
  let p = tiles.get(key)
  if (!p) { p = get<LayerCollection>(`/api/layers/${encodeURIComponent(id)}/tile/${z}/${x}/${y}`); p.catch(() => tiles.delete(key)); tiles.set(key, p) }
  return p
}
export const fetchWeather = (city: string) => get<Weather>(`/api/layers/weather?city=${city}`)
const sites = new Map<string, Promise<Site>>()
/** Where a scan stands in the world: its anchor and the turn and shift from its own frame to east and north. */
export function fetchSite(sid: string): Promise<Site> {
  let p = sites.get(sid)
  if (!p) { p = get<Site>(`/api/world/${encodeURIComponent(sid)}/site`); p.catch(() => sites.delete(sid)); sites.set(sid, p) }
  return p
}
