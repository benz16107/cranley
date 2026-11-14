import { useSyncExternalStore } from 'react'

/* Routing without a library: the URL is the state of the view, so every view is a link.
   /                     the front door
   /map?city&kind&…&b    the city map, its filters and the selected address
   /scan/:sid?f&demo     one scan in the building view, the focused finding, a fixture to replay */
export type Route = { path: string; sid: string | null; q: URLSearchParams }

const listeners = new Set<() => void>()
let cached: Route | null = null
function read(): Route {
  const { pathname, search } = window.location
  const key = pathname + search
  if (cached && (cached as Route & { key?: string }).key === key) return cached
  const m = pathname.match(/^\/scan\/([^/]+)/)
  cached = Object.assign({ path: m ? '/scan' : pathname === '/map' ? '/map' : '/', sid: m ? decodeURIComponent(m[1]) : null, q: new URLSearchParams(search) }, { key })
  return cached
}
const emit = () => listeners.forEach((l) => l())
window.addEventListener('popstate', emit)

export function navigate(path: string, params?: Record<string, string | null | undefined>, opts?: { replace?: boolean; keep?: boolean }) {
  const q = new URLSearchParams(opts?.keep ? window.location.search : '')
  for (const [k, v] of Object.entries(params ?? {})) if (v == null || v === '') q.delete(k); else q.set(k, v)
  const url = path + (q.size ? '?' + q : '')
  if (url === window.location.pathname + window.location.search) return
  window.history[opts?.replace ? 'replaceState' : 'pushState'](null, '', url)
  emit()
}
/** Change query parameters on the current path. Filters replace the history entry; selections push one. */
export const setQuery = (params: Record<string, string | null | undefined>, replace = true) =>
  navigate(window.location.pathname, params, { replace, keep: true })

export const useRoute = () => useSyncExternalStore((l) => (listeners.add(l), () => listeners.delete(l)), read)
export const currentRoute = read
