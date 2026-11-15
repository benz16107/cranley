import { create } from 'zustand'

export type Kind = 'home' | 'apartment' | 'amenity' | 'office' | 'other'
export type CityId = 'hou' | 'la'
export type Scan = { sid: string; name: string; rooms: number; panos: number; kind: Kind }
export type Building = {
  id: string; lon: number; lat: number; address: string; city: string; metro: CityId | null
  scans: Scan[]; count: number; splat: boolean; defurnished: boolean; kinds: Kind[]; rooms: number
}

export const CITIES: Record<CityId, { name: string; center: [number, number]; zoom: number; coord: string }> = {
  hou: { name: 'Houston', center: [-95.42, 29.76], zoom: 10.3, coord: '29.76 N · 95.37 W' },
  la: { name: 'Los Angeles', center: [-118.33, 34.05], zoom: 10.3, coord: '34.05 N · 118.24 W' },
}
export const KINDS: { id: Kind; label: string }[] = [
  { id: 'apartment', label: 'Apartments' }, { id: 'home', label: 'Houses' }, { id: 'office', label: 'Offices' },
  { id: 'amenity', label: 'Shared rooms' }, { id: 'other', label: 'Other' },
]

/** The index has no building type, so the kind is read from the scan's name and its market segment.
    A guess, and the filter says so. */
export function kindOf(name: string, segment: string): Kind {
  if (segment === 'residential') return 'home'
  if (/\b(studio|\d\s?br|\d\s?bed|bedroom|\d\s?x\s?\d)\b/i.test(name)) return 'apartment'
  if (/pool|fitness|gym|lobby|club|courtyard|lounge|laundry|leasing|resident|amenit|business c|dog|roof|theat|game|mail|spa\b|cabana|grill|play/i.test(name)) return 'amenity'
  if (/suite|floor|office|\bsf\b|sq\.? ?ft|rsf|tower|plaza/i.test(name)) return 'office'
  return 'other'
}
const metroOf = (lon: number, lat: number): CityId | null =>
  lon > -119.6 && lon < -117 && lat > 33 && lat < 35 ? 'la' : lon > -96.6 && lon < -94 && lat > 28.8 && lat < 31 ? 'hou' : null

/** The server's kind per scan (GET /api/buildings), folded into the five the filter offers. */
const KIND: Record<string, Kind> = { apartment_unit: 'apartment', house: 'home', amenity: 'amenity', office: 'office' }

/** One feature per building: scans that share a CoStar property, else an address. `scans` rows are compact:
    [sid, name, kind, rooms, panos]. */
type Row = [sid: string, name: string, kind: string | null, rooms: number | null, panos: number | null]
type Feature = { geometry: { coordinates: [number, number] }; properties: { id?: string; address: string | null; city: string | null; segment: string; count: number; splat: boolean; defurnished: boolean; scans: Row[] } }
export function toBuildings(features: Feature[]): Building[] {
  return features.map(({ geometry: { coordinates: [lon, lat] }, properties: p }) => {
    const scans = p.scans.map(([sid, name, kind, rooms, panos]) => ({ sid, name: name ?? sid, rooms: rooms ?? 0, panos: panos ?? 0, kind: (kind && KIND[kind]) || (kind ? 'other' : kindOf(name ?? '', p.segment)) }))
    return { id: p.id ?? `${lon},${lat}`, lon, lat, address: p.address || 'Address not recorded', city: p.city ?? '', metro: metroOf(lon, lat), scans,
      count: p.count, splat: p.splat, defurnished: p.defurnished, kinds: [...new Set(scans.map((s) => s.kind))], rooms: Math.max(0, ...scans.map((s) => s.rooms)) }
  })
}

export type Filters = { city: CityId; kinds: Kind[]; drone: boolean; empty: boolean; rooms: [number, number]; q: string }
export const ROOMS_MAX = 30
export function readFilters(q: URLSearchParams): Filters {
  const [lo, hi] = (q.get('rooms') ?? '').split('-').map(Number)
  return {
    city: q.get('city') === 'la' ? 'la' : 'hou',
    kinds: (q.get('kind') ?? '').split(',').filter((k): k is Kind => KINDS.some((x) => x.id === k)),
    drone: q.get('drone') === '1', empty: q.get('empty') === '1',
    rooms: [lo > 0 ? lo : 0, hi > 0 && hi < ROOMS_MAX ? hi : ROOMS_MAX], q: q.get('q') ?? '',
  }
}
export function matches(b: Building, f: Filters): boolean {
  if (b.metro !== f.city) return false
  if (f.kinds.length && !b.kinds.some((k) => f.kinds.includes(k))) return false
  if (f.drone && !b.splat) return false
  if (f.empty && !b.defurnished) return false
  if (b.rooms < f.rooms[0] || (f.rooms[1] < ROOMS_MAX && b.rooms > f.rooms[1])) return false
  return true
}
/** Address search across both cities: every word must appear in the address or a scan name. */
export function search(all: Building[], q: string, limit = 8): Building[] {
  const words = q.toLowerCase().split(/\s+/).filter(Boolean)
  if (!words.length) return []
  const out: Building[] = []
  for (const b of all) {
    const hay = (b.address + ' ' + b.scans.map((s) => s.name).join(' ')).toLowerCase()
    if (words.every((w) => hay.includes(w))) { out.push(b); if (out.length >= limit) break }
  }
  return out
}

type Store = { all: Building[]; state: 'loading' | 'ready' | 'error'; load: () => void }
let inFlight = false // the shell and Home's ask both call load() on the first render: one request, not two
export const useBuildings = create<Store>((set, get) => ({
  all: [], state: 'loading',
  load: () => {
    if (get().all.length || inFlight) return
    inFlight = true
    set({ state: 'loading' })
    fetch('/api/buildings').then((r) => { if (!r.ok) throw new Error(String(r.status)); return r.json() })
      .then((g) => set({ all: toBuildings(g.features), state: 'ready' }), () => set({ state: 'error' }))
      .finally(() => { inFlight = false })
  },
}))
