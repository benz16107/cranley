import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './skins/sheet/design/base.css'
import './skins/sheet/shell/shell.css'
import './skins/sheet/map/map.css'
import './skins/sheet/blocks/blocks.css'
import './skins/sheet/door/door.css'
import App from './skins/sheet/App.tsx'

const root = createRoot(document.getElementById('root')!)
// /study/* is the design studies (web/src/studies), loaded only there. Everything else is the shell.
if (location.pathname.startsWith('/study')) void import('./studies/index.tsx').then(({ Studies }) => root.render(<Studies />))
else root.render(<StrictMode><App /></StrictMode>)
