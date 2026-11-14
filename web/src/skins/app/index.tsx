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

export const Root = App
/* The look switcher's tab sits under the sidebar, where nothing is clicked: table footers and the agent panel's
   composer use the bottom centre and the bottom right. */
export const switcher: SwitcherPlace = 'bottom-left'
