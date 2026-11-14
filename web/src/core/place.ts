import { useEffect, useMemo } from 'react'
import { matches, readFilters, useBuildings, type Building } from './buildings.ts'
import { currentRoute, navigate, setQuery, useRoute } from './router.ts'
import { useWorkspace } from './store.ts'
import type { Doc, Status } from './types.ts'

/* Where the person is and what the map has to show, worked out once for every look: the buildings and filters from
   the URL, the selected building, the buildings the workspace has touched, and what tools drew in map coordinates. */

/** Overlays given in map coordinates: an outdoor path (a route with floor "geo") and pins with a {geo} anchor. */
export type GeoMarks = { paths: [number, number][][]; pins: { lon: number; lat: number; status: Status; label: string }[] }

export function geoMarks(overlays: Doc['overlays']): GeoMarks {
  return {
    paths: overlays.flatMap(({ overlay: o }) => (o.kind === 'route' && o.floor === 'geo' ? [o.points.map(([x, y]): [number, number] => [x, y])] : [])),
    pins: overlays.flatMap(({ overlay: o }) => (o.kind === 'pins' ? o.pins.flatMap((p) => ('geo' in p.anchor ? [{ lon: p.anchor.geo[0], lat: p.anchor.geo[1], status: p.status, label: p.label }] : [])) : [])),
  }
}

/** The building a point on the map belongs to: the nearest within about 200 m (a pool or a dock is not at the address). */
export function nearestBuilding(all: Building[], [lon, lat]: [number, number]): Building | undefined {
  const d = (b: Building) => Math.hypot((b.lon - lon) * Math.cos((lat * Math.PI) / 180), b.lat - lat)
  return all.reduce<Building | undefined>((best, b) => (d(b) < 0.002 && (!best || d(b) < d(best)) ? b : best), undefined)
}

/** Everything a city map needs. Loads the building list on first use. */
export function useMapModel() {
  const route = useRoute()
  const { all, state, load } = useBuildings()
  useEffect(load, [load])
  const doc = useWorkspace((s) => s.doc)
  const filters = useMemo(() => readFilters(route.q), [route.q])
  const shown = useMemo(() => all.filter((b) => matches(b, filters)), [all, filters])
  const selected = useMemo(() => all.find((b) => b.id === route.q.get('b')) ?? (route.sid ? all.find((b) => b.scans.some((x) => x.sid === route.sid)) : undefined) ?? null, [all, route.q, route.sid])
  const marks = useMemo(() => {
    const sids = new Set([...doc.panels.map((p) => p.sid), ...doc.shortlist.map((s) => s.sid)])
    return all.filter((b) => b.scans.some((s) => sids.has(s.sid)))
  }, [all, doc.panels, doc.shortlist])
  const geo = useMemo(() => geoMarks(doc.overlays), [doc.overlays])
  const cam = doc.camera
  return {
    /** Every building, and whether the list is 'loading', 'ready' or in 'error' (then call reload). */
    all, state, reload: load,
    /** The filters in the URL, and the buildings that pass them (the current city only). */
    filters, shown,
    /** The building in ?b, or the one the open scan belongs to. select(null) clears it. */
    selected, select: (b: Building | null) => setQuery({ b: b?.id }, false),
    /** Buildings the workspace has a panel or a shortlist entry for: where the agent has been. */
    marks,
    /** What tools drew in map coordinates. */
    geo,
    /** A map point the camera was told to look at, or null. Go there, close enough to read the marks. */
    look: cam && 'geo' in cam.anchor ? cam.anchor.geo : null,
  }
}

/* Where the camera is told to look, the place goes: the agent's moves only while "follow" is on. This is the
   product's behaviour, not a look's, so it runs here for every skin. A skin animates the change of place as it likes. */
useWorkspace.subscribe((s, before) => {
  const cam = s.doc.camera
  if (cam === before.doc.camera || !cam || (cam.by === 'agent' && !s.follow)) return
  const a = cam.anchor
  if (cam.stay) { setQuery({ f: cam.finding }); return } // look at it from here: the place does not change
  if ('geo' in a) {
    const near = nearestBuilding(useBuildings.getState().all, a.geo)
    navigate('/map', { b: near?.id, city: near?.metro ?? undefined }, { keep: true })
  } else if (currentRoute().sid !== a.sid) navigate(`/scan/${a.sid}`, { f: cam.finding }, { keep: true })
  else setQuery({ f: cam.finding })
})
