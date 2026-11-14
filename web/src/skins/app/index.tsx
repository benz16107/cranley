/* The "App" look: Sheet's materials with a product's structure. A sidebar, a top bar and a page for each kind of
   work (home, map, building, investigations, saved buildings, insights, tools, settings), with the agent as a panel
   beside any of them. Everything it draws is in this folder; it reads and writes the product only through src/core. */
import './design/base.css'
import './shell/shell.css'
import './blocks/blocks.css'
import './map/map.css'
import './pages/pages.css'
import App from './App.tsx'

export const Root = App
