/* The "Maquette" look (direction C of the design studies): a model on a table. Everything this look draws lives in
   this folder: tokens, type, layout, components, motion. It reads and writes the product only through src/core
   (web/src/core/README.md). Its own rules are in README.md beside this file. */
import './tokens.css'
import './maquette.css'
import App from './App.tsx'

export const Root = App
