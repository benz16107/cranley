import type { ComponentType } from 'react'
import type { LookId, SwitcherPlace } from '../core/index.ts'

/* One entry per look, keyed by its URL prefix (core/looks.ts names them). Each is loaded on its own, so only the
   chosen look's code and CSS reach the page: a look may style `body`, `:root` and plain element names freely.
   A look's index.tsx exports `Root`, and may export `switcher` to say where the look switcher's tab sits. */
export type Skin = { Root: ComponentType; switcher?: SwitcherPlace }
export const SKINS: Record<LookId, () => Promise<Skin>> = {
  sheet: () => import('./sheet/index.tsx'),
  a: () => import('./overflight/index.tsx'),
  b: () => import('./broadsheet/index.tsx'),
  c: () => import('./maquette/index.tsx'),
}
