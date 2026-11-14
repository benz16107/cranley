import type { ComponentType } from 'react'
import { LOOKS, type LookId, type SwitcherPlace } from '../core/index.ts'

/* One entry per look, keyed by its URL prefix (core/looks.ts names them). Each is loaded on its own, so only the
   chosen look's code and CSS reach the page: a look may style `body`, `:root` and plain element names freely.
   A look's index.tsx exports `Root`, and may export `switcher` to say where the look switcher's tab sits. */
export type Skin = { Root: ComponentType; switcher?: SwitcherPlace }
/* Stand-in: `app` belongs in LOOKS (core/looks.ts), which this workstream may not edit. This file loads before main.tsx
   reads the path, so adding it here makes /app a look. Delete these two lines when LOOKS lists it (core-requests.md, App 1). */
if (!LOOKS.some((l) => (l.id as string) === 'app')) (LOOKS as unknown as { id: string; name: string }[]).push({ id: 'app', name: 'App' })
export const SKINS: Record<LookId | 'app', () => Promise<Skin>> = {
  sheet: () => import('./sheet/index.tsx'),
  a: () => import('./overflight/index.tsx'),
  b: () => import('./broadsheet/index.tsx'),
  c: () => import('./maquette/index.tsx'),
  app: () => import('./app/index.tsx'),
}
