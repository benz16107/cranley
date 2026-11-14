import { useEffect, useRef, useState } from 'react'
import { Toaster, toast } from 'sonner'
import { Drawer } from 'vaul'
import { currentRoute, focusFinding, onNotice, setQuery, useRoute, useWorkspace } from '../../core/index.ts'
import { City } from './City.tsx'
import { Door } from './Door.tsx'
import { Model } from './Model.tsx'
import { Catalog, Sheets } from './Sheets.tsx'
import { Questions, Tray } from './Tray.tsx'
import { usePhone, useSheet } from './state.ts'

const SNAPS = ['108px', 0.56, 0.93]

export default function App() {
  const route = useRoute()
  const doc = useWorkspace((s) => s.doc), undo = useWorkspace((s) => s.undo)
  const phone = usePhone()
  const [menu, setMenu] = useState<false | 'all' | 'tools'>(false)
  const view = route.path === '/scan' && route.sid ? 'scan' : route.path === '/map' ? 'map' : 'door'
  const sheet = useSheet(view === 'scan' ? route.sid : null)

  // what core has to say outside the workspace is a slip of paper pushed in from the top edge
  useEffect(() => onNotice((n) => (n.kind === 'error' ? toast.error : toast)(n.title, { description: n.description })), [])

  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey, typing = /input|textarea|select/i.test((e.target as HTMLElement).tagName)
      if (mod && e.key.toLowerCase() === 'k') { e.preventDefault(); setMenu((m) => (m ? false : 'all')) }
      if (mod && e.key.toLowerCase() === 'z' && !typing) { e.preventDefault(); undo() }
      if (e.key === 'Escape' && !e.defaultPrevented && !document.querySelector('[data-open], [cmdk-root]') && currentRoute().path === '/map' && currentRoute().q.has('b')) setQuery({ b: null }, false)
    }
    window.addEventListener('keydown', key)
    return () => window.removeEventListener('keydown', key)
  }, [undo])

  // A link with ?f opens on that finding. Core keeps ?f in step with the camera but does not read it back on a
  // reload (core-requests.md, Maquette 3), so it is focused once, when the workspace has arrived.
  const restored = useRef(false)
  useEffect(() => {
    if (restored.current || !doc.findings.length) return
    restored.current = true
    const f = currentRoute().q.get('f'), found = f && doc.findings.find((x) => x.id === f)
    if (found && doc.camera?.finding !== f) focusFinding(found)
  }, [doc.findings.length]) // eslint-disable-line react-hooks/exhaustive-deps

  // the phone sheet rises when there is something new to read in it
  const [snap, setSnap] = useState<number | string | null>(SNAPS[0])
  useEffect(() => { if (doc.panels.length || doc.questions.some((q) => q.answer == null)) setSnap(SNAPS[1]) }, [doc.panels.length, doc.questions.length]) // eslint-disable-line react-hooks/exhaustive-deps

  const stack = <Sheets sid={view === 'scan' ? route.sid : null} sheet={sheet} onAdd={() => setMenu('tools')} />
  return (
    <div className="mq-app" data-view={view} data-sheet={sheet.active && !sheet.folded ? 'open' : undefined}>
      <a className="mq-skip" href="#mq-main">Skip to the table</a>
      <div id="mq-main" tabIndex={-1}>
        {view === 'door' ? <Door /> : view === 'map' ? <City /> : <Model sid={route.sid!} sheet={sheet} />}
      </div>
      {view !== 'door' && !phone && <>{stack}<div className="mq-near"><Questions /><Tray /></div></>}
      {view !== 'door' && phone && (
        <Drawer.Root open modal={false} dismissible={false} snapPoints={SNAPS} activeSnapPoint={snap} setActiveSnapPoint={setSnap}>
          <Drawer.Portal>
            <Drawer.Content className="mq-drawer" aria-label="Tools, results and the agent's work">
              <Drawer.Handle className="mq-grip" />
              <Drawer.Title className="sr">Tools, results and the agent's work</Drawer.Title>
              <div className="mq-drawer-body"><Questions /><Tray />{stack}</div>
            </Drawer.Content>
          </Drawer.Portal>
        </Drawer.Root>
      )}
      <Catalog mode={menu} onClose={() => setMenu(false)} />
      <Toaster position="top-center" offset={18} toastOptions={{ unstyled: true, classNames: { toast: 'mq-slip', title: 'mq-slip-t', description: 'mq-slip-d' } }} />
    </div>
  )
}
