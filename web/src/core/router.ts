import { useSyncExternalStore } from 'react'
import { DEFAULT_LOOK, pathIn, splitPath } from './looks.ts'

/* Routing without a library: the URL is the state of the view, so every view is a link.
   The first path segment is the look (see looks.ts); the rest is the place, the same in every look:
   /                     the front door
   /map?city&kind&…&b    the city map, its filters and the selected address
   /scan/:sid?f&v&p&demo one scan in the building view: the focused finding, the scene mode and panorama position,
                         a fixture to replay
   Code names places only (`navigate('/map')`); the look in the address bar is kept. */
export type Route = { path: string; sid: string | null; q: URLSearchParams }

const listeners = new Set<() => void>()
let cached: Route | null = null
function read(): Route {
  const { pathname, search } = window.location
  const key = pathname + search
  if (cached && (cached as Route & { key?: string }).key === key) return cached
  const { place } = splitPath(pathname)
  const m = place.match(/^\/scan\/([^/]+)/)
  cached = Object.assign({ path: m ? '/scan' : place === '/map' ? '/map' : '/', sid: m ? decodeURIComponent(m[1]) : null, q: new URLSearchParams(search) }, { key })
  return cached
}
const emit = () => listeners.forEach((l) => l())
window.addEventListener('popstate', emit)

export function navigate(path: string, params?: Record<string, string | null | undefined>, opts?: { replace?: boolean; keep?: boolean }) {
  const q = new URLSearchParams(opts?.keep ? window.location.search : '')
  for (const [k, v] of Object.entries(params ?? {})) if (v == null || v === '') q.delete(k); else q.set(k, v)
  const url = pathIn(splitPath(window.location.pathname).look ?? DEFAULT_LOOK, path) + (q.size ? '?' + q : '')
  if (url === window.location.pathname + window.location.search) return
  window.history[opts?.replace ? 'replaceState' : 'pushState'](null, '', url)
  emit()
}
/** Change query parameters on the current path. Filters replace the history entry; selections push one. */
export const setQuery = (params: Record<string, string | null | undefined>, replace = true) =>
  navigate(splitPath(window.location.pathname).place, params, { replace, keep: true })

export const useRoute = () => useSyncExternalStore((l) => (listeners.add(l), () => listeners.delete(l)), read)
export const currentRoute = read
