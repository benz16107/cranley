/* The "App" look: Sheet's materials with a product's structure. A sidebar, a top bar and a page for each kind of
   work (home, map, building, investigations, saved buildings, insights, tools, settings), with the agent as a panel
   beside any of them. Everything it draws is in this folder; it reads and writes the product only through src/core. */
import './design/base.css'
import './shell/shell.css'
import './blocks/blocks.css'
import './map/map.css'
import './pages/pages.css'
import type { SwitcherPlace } from '../../core/index.ts'
import App from './App.tsx'
import { loadExplore } from './shell/Shell.tsx'

export const Root = App
/* The look switcher's tab sits under the sidebar, where nothing is clicked: table footers and the agent panel's
   composer use the bottom centre and the bottom right. */
export const switcher: SwitcherPlace = 'bottom-left'
/* On a map or building address the first render waits for the map page's code (its download started beside this
   look's, from the registry's PRELOAD), so the page draws in the first render instead of after a Suspense fallback. */
export const ready = () => {
  const p = location.pathname // /app/map, /app/scan/<sid>; a building opens inside the map on a wide screen only (as in Shell)
  return /^\/[^/]+\/map(\/|$)/.test(p) || (/^\/[^/]+\/scan\//.test(p) && !matchMedia('(max-width: 760px)').matches) ? loadExplore() : undefined
}
