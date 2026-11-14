/* The "Broadsheet" look (direction B of the design studies, web/src/studies/b): a page the agent writes about a
   building. Everything this look draws lives in this folder: tokens, type, layout, components, motion. It reads and
   writes the product only through src/core (web/src/core/README.md). */
import { useEffect, useState } from 'react'
import { Toaster, toast } from 'sonner'
import { currentRoute, onNotice, setQuery, useMapModel, useRoute, useWorkspace } from '../../core/index.ts'
import './bs.css'
import { BuildingPage } from './Building.tsx'
import { CityPage } from './City.tsx'
import { DoorPage } from './Door.tsx'
import { Index, Masthead, type Menu } from './Masthead.tsx'
import { useStories } from './stories.tsx'

export function Root() {
  const route = useRoute()
  const { all } = useMapModel()
  const { story, stories } = useStories()
  const undo = useWorkspace((s) => s.undo)
  const [menu, setMenu] = useState<Menu>(false)

  // what core has to tell the person arrives as a notice; on this page it is a stop-press slug under the masthead
  useEffect(() => onNotice((n) => (n.kind === 'error' ? toast.error : toast)(n.title, { description: n.description })), [])
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey, typing = /input|textarea|select/i.test((e.target as HTMLElement).tagName)
      if (mod && e.key.toLowerCase() === 'k') { e.preventDefault(); setMenu((m) => (m ? false : 'all')) }
      if (mod && e.key.toLowerCase() === 'z' && !typing) { e.preventDefault(); undo() }
      if (e.key === 'Escape' && !e.defaultPrevented && !document.querySelector('[data-open][role="dialog"], [cmdk-root]')) {
        const q = currentRoute().q
        if (q.get('b_o')) setQuery({ b_o: null }); else if (q.has('b') && currentRoute().path === '/map') setQuery({ b: null }, false)
      }
    }
    window.addEventListener('keydown', key)
    return () => window.removeEventListener('keydown', key)
  }, [undo])
  // a new place starts at the top of its page
  useEffect(() => { window.scrollTo({ top: 0 }) }, [route.path, route.sid])

  return (
    <>
      <Masthead story={story} stories={stories} onMenu={setMenu} />
      <main id="page" tabIndex={-1}>
        {route.path === '/scan' && route.sid ? <BuildingPage sid={route.sid} /> : route.path === '/map' ? <CityPage /> : <DoorPage />}
      </main>
      <Index open={menu} onClose={() => setMenu(false)} all={all} />
      <Toaster position="top-right" offset={{ top: 'calc(var(--top) + 0.75rem)', right: 'var(--gut)' }} toastOptions={{ unstyled: true, classNames: { toast: 'stoppress', title: 'stoppress-title', description: 'stoppress-desc' } }} />
    </>
  )
}
