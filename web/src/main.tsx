import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { DEFAULT_LOOK, pathIn, splitPath } from './core/looks.ts'
import { mountSwitcher } from './core/switcher.ts'
import { SKINS } from './skins/registry.ts'
import type { SwitcherPlace } from './core/switcher.ts'

// "Continue on phone": a tab beside the look switcher, loaded on its own so no look pays for it.
const phoneLink = (place?: SwitcherPlace) => void import('./mobile/desk.ts').then((m) => m.mountPhoneLink(place))

const root = createRoot(document.getElementById('root')!)
// /study/* is the design studies (web/src/studies), loaded only there.
if (location.pathname.startsWith('/study')) void import('./studies/index.tsx').then(({ Studies }) => root.render(<Studies />))
// /m is the phone companion (web/src/mobile): its own small app, no look and no switcher.
else if (/^\/m(\/|$)/.test(location.pathname)) void import('./mobile/index.tsx').then(({ Mobile }) => root.render(<StrictMode><Mobile /></StrictMode>))
else {
  // The first path segment is the look. A link without one (/, /map, /scan/<sid>) opens in the default look.
  const { look, place } = splitPath(location.pathname)
  if (!look) history.replaceState(null, '', pathIn(DEFAULT_LOOK, place) + location.search)
  // the look says where the switcher's tab sits; if a look fails to load, the tab is still there to leave by
  void SKINS[look ?? DEFAULT_LOOK]().then(({ Root, switcher }) => { root.render(<StrictMode><Root /></StrictMode>); mountSwitcher(switcher); phoneLink(switcher) }, (e) => { console.error(e); mountSwitcher() })
}
