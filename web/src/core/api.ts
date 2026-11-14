import type { ScanPlan } from './types.ts'

const plans = new Map<string, Promise<ScanPlan>>()
/** One request per scan per session. The server caches on disk; this keeps the shared keys quiet. */
export function fetchPlan(sid: string): Promise<ScanPlan> {
  let p = plans.get(sid)
  if (!p) {
    p = fetch(`/api/scan/${encodeURIComponent(sid)}/plan`).then((r) => {
      if (!r.ok) throw new Error(r.status === 404 ? 'This scan is not in the index.' : `The plan did not load (${r.status}).`)
      return r.json()
    })
    p.catch(() => plans.delete(sid))
    plans.set(sid, p)
  }
  return p
}
export const panoFace = (sid: string, pano: string, face = 1) => `/api/scan/${sid}/pano/${pano}/${face}.jpg?res=2k`

/* ---------- the rest of the data API (docs/ARCHITECTURE.md, Contract 2), as thin clients ----------
   Image helpers return a URL for an <img>; the others fetch JSON and reject with a sentence a person can read. */
async function getJson<T>(path: string): Promise<T> {
  const r = await fetch(path)
  if (!r.ok) throw new Error(r.status === 404 ? 'Nothing there.' : r.status === 503 ? 'That part of the server is not ready.' : `The server answered ${r.status}.`)
  return r.json()
}
const qs = (o: Record<string, string | number | boolean | null | undefined>) =>
  Object.entries(o).filter(([, v]) => v != null && v !== '').map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`).join('&')

/** A whole panorama as one 2:1 image. `view: 'defurnished'` is the empty-room version where the scan has one. */
export const panoEquirect = (sid: string, pano: string, w = 2048, view: 'furnished' | 'defurnished' = 'furnished') => `/api/scan/${sid}/pano/${pano}/equirect.jpg?w=${w}&view=${view}`
/** Matterport's own floor plan picture of one floor. */
export const floorplanImage = (sid: string, floor: string, flags = 'photogramy') => `/api/scan/${sid}/floorplan/${floor}.jpg?flags=${flags}`
/** A north-up aerial photo patch, `size_m` metres across, centred on a point. */
export const orthoImage = (lat: number, lon: number, size_m = 60, px = 1024) => `/api/aerial/ortho?${qs({ lat, lon, size_m, px })}`

export type ScanRow = { sid: string; name: string; kind: string; segment: string; address: string | null; city: string | null; lat: number | null; lon: number | null;
  splat: boolean; defurnished: boolean; drone_photos: number | null; panos: number | null; rooms: number | null; floors: number | null; costar_property_id: number | null }
/** Index rows for scans: free text, an address, a city, a kind ('house', 'apartment_unit', 'office', …). */
export const fetchScans = (filter: { q?: string; address?: string; city?: string; kind?: string; splat?: boolean; defurnished?: boolean; limit?: number; offset?: number } = {}) =>
  getJson<{ total: number; offset: number; scans: ScanRow[] }>(`/api/scans?${qs(filter)}`)
/** The CoStar or listing record for a scan, with its `claims` list. Rejects when the scan has none. */
export const fetchRecord = (sid: string) => getJson<Record<string, unknown>>(`/api/scan/${sid}/record`)
/** Drone photos of a scan's building, with position and gimbal angles; each `name` loads from droneImage. */
export const fetchDrone = (sid: string, n = 60) => getJson<Record<string, unknown>>(`/api/scan/${sid}/drone?n=${n}`)
export const droneImage = (sid: string, name: string) => `/api/scan/${sid}/drone/${encodeURIComponent(name)}`

export type MeasureField = { label: string; unit: string; kind: string; description: string }
export type MeasureHit = { sid: string; name: string; kind: string; city: string; address: string | null; lat: number | null; lon: number | null; score: number; why: string[]; values: Record<string, number | string | null> }
/** The measures a home can be searched by (door widths on the way to the bathroom, turning space, floors, …). */
export const fetchMeasureFields = () => getJson<Record<string, MeasureField>>('/api/search/measures/fields')
/** Homes by what is measured inside them. Each criterion is `<measure><op><value>`, for example `floors==1`. */
export const searchMeasures = (where: string[], filter: { city?: string; kind?: string; sort?: string; limit?: number } = {}) =>
  getJson<{ pool: number; answerable: number; matches: number; rows: MeasureHit[] }>(`/api/search/measures?${[...where.map((w) => `where=${encodeURIComponent(w)}`), qs(filter)].filter(Boolean).join('&')}`)
