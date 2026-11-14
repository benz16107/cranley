/* The looks ("skins") the app can wear, chosen by the first path segment: /sheet/map, /a/map, /b/scan/<sid>.
   The rest of the URL is the place, and it means the same thing in every look. Pure, so it runs under `node --test`. */
export const LOOKS = [
  { id: 'sheet', name: 'Sheet' }, { id: 'a', name: 'Overflight' }, { id: 'b', name: 'Broadsheet' }, { id: 'c', name: 'Maquette' },
] as const
export type LookId = (typeof LOOKS)[number]['id']
export const DEFAULT_LOOK: LookId = 'sheet'

/** `/a/scan/x` is look `a` at place `/scan/x`. A path with no look (an old link) has look null. */
export function splitPath(pathname: string): { look: LookId | null; place: string } {
  const [, first, rest] = pathname.match(/^\/([^/]*)(\/.*)?$/) ?? []
  const look = LOOKS.find((l) => l.id === first)?.id ?? null
  return look ? { look, place: rest && rest !== '/' ? rest : '/' } : { look: null, place: pathname || '/' }
}
/** The URL of a place in a look. The front door of a look is `/<look>`. */
export const pathIn = (look: LookId, place: string) => `/${look}${place === '/' ? '' : place}`
