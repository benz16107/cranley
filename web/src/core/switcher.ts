import { LOOKS, pathIn, splitPath, DEFAULT_LOOK, type LookId } from './looks.ts'

/* The look switcher: a small tab at the edge of the screen that opens the same place in another look. Where it sits
   is each look's choice (`export const switcher = 'top-right'` beside `Root` in the look's index.tsx). It lives in a shadow
   root, so no look's CSS reaches it and its CSS reaches no look. Changing look loads the page again on purpose:
   that is what keeps one look's global styles out of another. The place is in the URL and the workspace is on the
   server (its id in this browser), so the new look opens on the same moment. Alt+L steps to the next look. */
const here = () => splitPath(location.pathname)
const hrefIn = (look: LookId) => pathIn(look, here().place) + location.search

/** Where the tab sits. The default is the bottom centre. */
export type SwitcherPlace = 'bottom' | 'top' | 'bottom-left' | 'bottom-right' | 'top-left' | 'top-right'
const PLACES: Record<SwitcherPlace, string> = {
  bottom: 'left: 50%; bottom: 0; translate: -50% 0;', top: 'left: 50%; top: 0; translate: -50% 0;',
  'bottom-left': 'left: 12px; bottom: 0;', 'bottom-right': 'right: 12px; bottom: 0;', 'top-left': 'left: 12px; top: 0;', 'top-right': 'right: 12px; top: 0;',
}

export function mountSwitcher(place: SwitcherPlace = 'bottom') {
  if (!(place in PLACES)) place = 'bottom'
  const top = place.startsWith('top')
  const host = document.createElement('div')
  host.setAttribute('data-look-switcher', '')
  const root = host.attachShadow({ mode: 'open' })
  const current = here().look ?? DEFAULT_LOOK
  root.innerHTML = `<style>
    :host { all: initial; position: fixed; ${PLACES[place]} z-index: 2147483000; }
    nav { display: flex; gap: 2px; padding: 2px 6px; font: 500 10.5px/14px ui-monospace, 'SF Mono', Menlo, monospace; letter-spacing: 0.04em;
      background: rgb(22 24 28 / 0.82); color: #fff; border-radius: ${top ? '0 0 5px 5px' : '5px 5px 0 0'}; opacity: 0.5; transition: opacity 120ms ease; }
    nav:hover, nav:focus-within { opacity: 1; }
    a { color: inherit; text-decoration: none; padding: 0 5px; border-radius: 3px; display: none; }
    a[aria-current], nav:hover a, nav:focus-within a { display: block; }
    a[aria-current] { font-weight: 700; }
    nav:hover a[aria-current], nav:focus-within a[aria-current] { background: #fff; color: #16181c; }
    a:focus-visible { outline: 2px solid #8fb5ff; outline-offset: 1px; }
    @media (hover: hover) { a:not([aria-current]):hover { background: rgb(255 255 255 / 0.2); } }
    @media print { :host { display: none; } }
  </style><nav aria-label="Look">${LOOKS.map((l) => `<a data-look="${l.id}" href="/${l.id}"${l.id === current ? ' aria-current="page"' : ''} title="Open this place in the ${l.name} look">${l.name}</a>`).join('')}</nav>`
  const go = (look: LookId) => location.assign(hrefIn(look))
  // the place changes without a page load, so the link is worked out when it is used
  root.querySelectorAll<HTMLAnchorElement>('a').forEach((a) => {
    const look = a.dataset.look as LookId
    a.addEventListener('pointerenter', () => { a.href = hrefIn(look) })
    a.addEventListener('focus', () => { a.href = hrefIn(look) })
    a.addEventListener('click', (e) => { if (e.metaKey || e.ctrlKey || e.shiftKey) { a.href = hrefIn(look); return } e.preventDefault(); go(look) })
  })
  window.addEventListener('keydown', (e) => {
    if (!e.altKey || e.ctrlKey || e.metaKey || e.key.toLowerCase() !== 'l') return
    e.preventDefault()
    go(LOOKS[(LOOKS.findIndex((l) => l.id === current) + 1) % LOOKS.length].id)
  })
  document.body.append(host)
}
