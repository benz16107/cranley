/* The "Maquette" look (direction C of the design studies): a model on a table. Everything this look draws lives in
   this folder: tokens, type, layout, components, motion. It reads and writes the product only through src/core
   (web/src/core/README.md). Its own rules are in README.md beside this file. */
import './tokens.css'
import './maquette.css'
import type { SwitcherPlace } from '../../core/index.ts'
import App from './App.tsx'

export const Root = App
/** Under the stack, in the strip of table below the sheets: the bottom centre holds prints and the address card. */
export const switcher: SwitcherPlace = 'bottom-right'
