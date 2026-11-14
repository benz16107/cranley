import { decodeSegment, navigate, useRoute } from '../../../core/index.ts'

/* The pages of this look. `/`, `/map` and `/scan/<sid>` are core's places and mean the same in every look. The rest
   are places only this look has: core's router reports them as `/`, so they are read from the address here.
   Stand-in for `Route.place` (core-requests.md, App 2). */
export type Page = 'home' | 'explore' | 'building' | 'investigations' | 'investigation' | 'buildings' | 'insights' | 'tools' | 'settings'
const OWN = ['investigations', 'buildings', 'insights', 'tools', 'settings'] as const
export type Place = { page: Page; id: string | null; sid: string | null; q: URLSearchParams }

export function usePlace(): Place {
  const r = useRoute() // re-renders on every change of address
  if (r.path === '/scan') return { page: 'building', id: null, sid: r.sid, q: r.q }
  if (r.path === '/map') return { page: 'explore', id: null, sid: null, q: r.q }
  const [, , seg, id] = window.location.pathname.split('/')
  // a read-only link (/shared/<token>) opens on the investigation it shares; the server names that document "shared"
  if (seg === 'shared' && id) return { page: 'investigation', id: 'shared', sid: null, q: r.q }
  const own = OWN.find((p) => p === seg)
  if (!own) return { page: 'home', id: null, sid: null, q: r.q }
  return { page: own === 'investigations' && id ? 'investigation' : own, id: id ? decodeSegment(id) : null, sid: null, q: r.q }
}

const PATH: Record<Exclude<Page, 'building' | 'investigation'>, string> = { home: '/', explore: '/map', investigations: '/investigations', buildings: '/buildings', insights: '/insights', tools: '/tools', settings: '/settings' }
/** Go to a page. Explore keeps its filters; the others start clean. */
export const go = (page: keyof typeof PATH, params?: Record<string, string | null | undefined>) => navigate(PATH[page], params, { keep: page === 'explore' && window.location.pathname.endsWith('/map') })
export const goScan = (sid: string, params?: Record<string, string | null | undefined>) => navigate(`/scan/${sid}`, params)
export const goInvestigation = (id: string) => navigate(`/investigations/${encodeURIComponent(id)}`)
