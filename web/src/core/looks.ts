/* The looks ("skins") the app can wear, chosen by the first path segment: /sheet/map, /a/map, /b/scan/<sid>.
   The rest of the URL is the place, and it means the same thing in every look. Pure, so it runs under `node --test`. */
export const LOOKS = [
  { id: 'sheet', name: 'Sheet' }, { id: 'a', name: 'Overflight' }, { id: 'b', name: 'Broadsheet' }, { id: 'c', name: 'Maquette' },
  { id: 'app', name: 'App' },
] as const
export type LookId = (typeof LOOKS)[number]['id']
export const DEFAULT_LOOK: LookId = 'app'

/** `/a/scan/x` is look `a` at place `/scan/x`. A path with no look (an old link) has look null. */
export function splitPath(pathname: string): { look: LookId | null; place: string } {
  const [, first, rest] = pathname.match(/^\/([^/]*)(\/.*)?$/) ?? []
  const look = LOOKS.find((l) => l.id === first)?.id ?? null
  return look ? { look, place: rest && rest !== '/' ? rest : '/' } : { look: null, place: pathname || '/' }
}
/** The URL of a place in a look. The front door of a look is `/<look>`. */
export const pathIn = (look: LookId, place: string) => `/${look}${place === '/' ? '' : place}`

/** The token of a read-only link, when the place is one: `/shared/<token>`, with anything after it. */
export const sharedToken = (place: string): string | null => place.match(/^\/shared\/([A-Za-z0-9_-]{8,})(?:\/|$)/)?.[1] ?? null

/** A path segment as text. A link with a broken escape (`%E0%A4%A`) is read as it stands: it must open the app at
    "not found", not throw before anything is drawn. */
export const decodeSegment = (s: string): string => { try { return decodeURIComponent(s) } catch { return s } }
/** The scan a place names (`/scan/<sid>`), or null. */
export const scanIn = (place: string): string | null => { const m = place.match(/^\/scan\/([^/]+)/); return m ? decodeSegment(m[1]) : null }
