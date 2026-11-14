import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './design/base.css'
import './shell/shell.css'
import './map/map.css'
import './workspace/blocks.css'
import './door/door.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>)
