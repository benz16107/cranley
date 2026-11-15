import type { ComponentType } from 'react'
import type { LookId, SwitcherPlace } from '../core/index.ts'

/* One entry per look, keyed by its URL prefix (core/looks.ts names them). Each is loaded on its own, so only the
   chosen look's code and CSS reach the page: a look may style `body`, `:root` and plain element names freely.
   A look's index.tsx exports `Root`, and may export `switcher` to say where the look switcher's tab sits. */
export type Skin = { Root: ComponentType; switcher?: SwitcherPlace; /** awaited before the first render, if given */ ready?: () => Promise<unknown> | undefined }
export const SKINS: Record<LookId, () => Promise<Skin>> = {
  sheet: () => import('./sheet/index.tsx'),
  a: () => import('./overflight/index.tsx'),
  b: () => import('./broadsheet/index.tsx'),
  c: () => import('./maquette/index.tsx'),
  app: () => import('./app/index.tsx'),
}

/* Started beside the look's own import when the address already names a page that loads on its own, so its code does
   not wait for the look to load and run first. */
export const PRELOAD: Partial<Record<LookId, (place: string) => void>> = {
  // a building opens inside Explore's map on a wide screen; on a phone (the look's 760 px) it is the Building page alone
  app: (place) => {
    if (/^\/map(\/|$)/.test(place) || (/^\/scan\//.test(place) && !matchMedia('(max-width: 760px)').matches)) void import('./app/pages/Explore.tsx')
  },
}
