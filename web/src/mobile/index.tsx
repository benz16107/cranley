import { useCallback, useEffect, useState } from 'react'
import { Toaster } from 'sonner'
import '../skins/sheet/design/base.css'
import './mobile.css'
import { boot, refresh, usePhone, type Task } from './api.ts'
import { Header, Privacy, Results, Tasks, Tools, type Tab, type ToolId } from './home.tsx'
import { Alarm, FloorHeight, Level, Measure, Note, PhotoMeasure, Sound, Walkthrough, Where, Window } from './screens.tsx'

/* The phone companion, at /m. A person standing in the building closes what the scan left open: each task or
   instrument sends one capture, and the result lands in the same workspace the desktop is showing.
   Screens are history entries, so the phone's own back gesture closes a capture screen. */

type Screen = { at: 'home' } | { at: 'task'; id: string } | { at: 'tool'; id: ToolId } | { at: 'privacy' }
const TABS: [Tab, string][] = [['tasks', 'Tasks'], ['tools', 'Tools'], ['results', 'Results']]

export function Mobile() {
  const view = usePhone((s) => s.view), state = usePhone((s) => s.state), sid = usePhone((s) => s.sid)
  usePhone((s) => s.unit) // lengths everywhere are redrawn when the person changes unit
  const [screen, setScreen] = useState<Screen>(() => (history.state?.screen as Screen) ?? { at: 'home' })
  const [tab, setTab] = useState<Tab>('tasks')
  const go = useCallback((s: Screen) => { history.pushState({ screen: s }, ''); setScreen(s); scrollTo(0, 0) }, [])
  const back = useCallback(() => (history.state?.screen ? history.back() : setScreen({ at: 'home' })), [])
  useEffect(() => {
    void boot()
    const pop = (e: PopStateEvent) => setScreen((e.state?.screen as Screen) ?? { at: 'home' })
    const seen = () => { if (document.visibilityState === 'visible') void refresh() }
    addEventListener('popstate', pop); document.addEventListener('visibilitychange', seen)
    return () => { removeEventListener('popstate', pop); document.removeEventListener('visibilitychange', seen) }
  }, [])
  useEffect(() => { // the keyboard and iOS's toolbar over it hide fixed bars: while typing, the action bar follows the field
    const root = document.documentElement
    let t = 0
    const typing = () => { const e = document.activeElement; return e instanceof HTMLTextAreaElement || (e instanceof HTMLInputElement && !['file', 'checkbox', 'radio', 'button', 'range'].includes(e.type)) }
    const on = () => { clearTimeout(t); root.toggleAttribute('data-kb', typing()) }
    const off = () => { clearTimeout(t); t = window.setTimeout(on, 300) } // late, so a tap on Save lands before the bar moves back
    document.addEventListener('focusin', on); document.addEventListener('focusout', off)
    return () => { document.removeEventListener('focusin', on); document.removeEventListener('focusout', off); clearTimeout(t) }
  }, [])
  const busy = view?.busy
  useEffect(() => { // while the agent or a slow tool works, read often; otherwise now and then, for what the desktop adds
    const t = setInterval(() => { if (document.visibilityState === 'visible') void refresh() }, busy ? 2500 : 8000)
    return () => clearInterval(t)
  }, [busy])

  const task = screen.at === 'task' ? view?.tasks.find((t) => t.id === screen.id) : undefined
  const openTask = (t: Task) => go({ at: 'task', id: t.id })
  let body
  if (screen.at === 'privacy') body = <Privacy back={back} />
  else if (screen.at === 'task' && task) body = task.kind === 'alarm' ? <Alarm task={task} back={back} /> : task.kind === 'slope' ? <Level task={task} back={back} />
    : task.kind === 'heading' ? <Window task={task} back={back} /> : task.kind === 'floor_height' ? <FloorHeight task={task} back={back} /> : <Measure task={task} back={back} />
  else if (screen.at === 'tool') body = { where: <Where back={back} />, level: <Level back={back} />, sound: <Sound back={back} />, window: <Window back={back} />, floor: <FloorHeight back={back} />,
    photo: <PhotoMeasure back={back} />, walk: <Walkthrough back={back} />, note: <Note back={back} /> }[screen.id]
  else {
    const empty: NonNullable<typeof view> = { brief: null, summary: null, buildings: [], questions: [], tasks: [], captures: [], results: [], busy: false, plan: [], seq: 0 }
    const v = view ?? empty
    const todo = v.tasks.filter((t) => t.sid === sid && t.status === 'open').length
    body = (
      <div className="m-home">
        <Header onPrivacy={() => go({ at: 'privacy' })} />
        <main className="m-body">
          {state === 'loading' && !view ? <div aria-busy="true" aria-label="Loading the workspace">{[0, 1, 2, 3].map((i) => <div key={i} className="m-row skeleton" style={{ height: 52 }} />)}</div>
            : <>
              {state === 'expired' && <p className="m-note warn" role="alert">That phone link has expired. Scan a new code from the desktop, or carry on with this phone alone.</p>}
              {state === 'offline' && <p className="m-note warn" role="alert">The server is not answering. This phone has to be on the same network as it. <button className="link" onClick={() => void refresh()}>Try again</button></p>}
              {tab === 'tasks' && <Tasks view={v} sid={sid} open={openTask} openTool={(id) => go({ at: 'tool', id })} />}
              {tab === 'tools' && <Tools sid={sid} open={(id) => go({ at: 'tool', id })} />}
              {tab === 'results' && <Results view={v} />}
            </>}
        </main>
        <nav className="m-tabs" aria-label="Sections">
          {TABS.map(([id, label]) => <button key={id} aria-current={tab === id ? 'page' : undefined} onClick={() => { setTab(id); scrollTo(0, 0) }}>{label}{id === 'tasks' && todo > 0 && <span className="num">{todo}</span>}</button>)}
        </nav>
      </div>
    )
  }
  return <>{body}<Toaster position="top-center" visibleToasts={2} toastOptions={{ unstyled: true, className: 'm-toast' }} /></>
}
