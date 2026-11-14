import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { DEFAULT_LOOK, pathIn, splitPath } from './core/looks.ts'
import { mountSwitcher } from './core/switcher.ts'
import { SKINS } from './skins/registry.ts'

const root = createRoot(document.getElementById('root')!)
// /study/* is the design studies (web/src/studies), loaded only there.
if (location.pathname.startsWith('/study')) void import('./studies/index.tsx').then(({ Studies }) => root.render(<Studies />))
else {
  // The first path segment is the look. A link without one (/, /map, /scan/<sid>) opens in the default look.
  const { look, place } = splitPath(location.pathname)
  if (!look) history.replaceState(null, '', pathIn(DEFAULT_LOOK, place) + location.search)
  void SKINS[look ?? DEFAULT_LOOK]().then(({ Root }) => root.render(<StrictMode><Root /></StrictMode>))
  mountSwitcher()
}
