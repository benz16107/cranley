import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './design/base.css'
import './shell/shell.css'
import './map/map.css'
import './workspace/blocks.css'
import './door/door.css'
import App from './App.tsx'

const root = createRoot(document.getElementById('root')!)
// /study/* is the design studies (web/src/studies), loaded only there. Everything else is the shell.
if (location.pathname.startsWith('/study')) void import('./studies/index.tsx').then(({ Studies }) => root.render(<Studies />))
else root.render(<StrictMode><App /></StrictMode>)
