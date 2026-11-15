import { useCallback, useEffect, useState } from 'react'
import { Toaster } from 'sonner'
import '../skins/sheet/design/base.css'
import './mobile.css'
import { boot, refresh, usePhone, type Task } from './api.ts'
import { Header, Hero, Privacy, Results, Tasks, Tools, type Tab, type ToolId } from './home.tsx'
import { Ico } from './parts.tsx'
import { Alarm, FloorHeight, Level, Measure, Note, PhotoMeasure, Sound, Walkthrough, Where, Window } from './screens.tsx'

/* The phone companion, at /m. A person standing in the building closes what the scan left open: each task or
   instrument sends one capture, and the result lands in the same workspace the desktop is showing.
   Screens are history entries, so the phone's own back gesture closes a capture screen. */

type Screen = { at: 'home' } | { at: 'task'; id: string } | { at: 'tool'; id: ToolId }
const TABS: [Tab, string, 'runs' | 'ruler' | 'chart'][] = [['tasks', 'Tasks', 'runs'], ['tools', 'Tools', 'ruler'], ['results', 'Results', 'chart']]

export function Mobile() {
  const view = usePhone((s) => s.view), state = usePhone((s) => s.state), sid = usePhone((s) => s.sid)
  usePhone((s) => s.unit) // lengths everywhere are redrawn when the person changes unit
  const [screen, setScreen] = useState<Screen>(() => (history.state?.screen as Screen) ?? { at: 'home' })
  const [tab, setTab] = useState<Tab>('tasks')
  const [privacy, setPrivacy] = useState(false)
  // data-nav: a screen opened by a tap slides in; one restored by a reload does not
  const go = useCallback((s: Screen) => { document.documentElement.setAttribute('data-nav', ''); history.pushState({ screen: s }, ''); setScreen(s); scrollTo(0, 0) }, [])
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
    // the bar is laid out under the field while typing; bring it above the keyboard once that has risen
    // the action is laid out under the field while typing. Once the keyboard has risen, bring it above the keyboard:
    // the keyboard shrinks the visual viewport, not the page, so the page is scrolled by what the keyboard covers
    const lift = () => {
      const vv = window.visualViewport, bar = document.activeElement?.closest('.m-composer')?.querySelector('.m-inline') ?? document.querySelector('.m-actions')
      if (!vv || !bar || !typing()) return
      const over = bar.getBoundingClientRect().bottom + 12 - (vv.offsetTop + vv.height)
      if (over > 0) scrollBy({ top: over, behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' })
    }
    const sync = () => { const kb = typing(); root.toggleAttribute('data-kb', kb); if (kb) setTimeout(lift, 350) }
    // the bar moves back late, so a tap on Save lands first (Chrome focuses the button on touch-down, before the click)
    const off = () => { clearTimeout(t); t = window.setTimeout(sync, 500) }
    const on = () => { if (typing()) { clearTimeout(t); sync() } else off() }
    document.addEventListener('focusin', on); document.addEventListener('focusout', off); window.visualViewport?.addEventListener('resize', lift)
    return () => { document.removeEventListener('focusin', on); document.removeEventListener('focusout', off); window.visualViewport?.removeEventListener('resize', lift); clearTimeout(t) }
  }, [])
  const busy = view?.busy
  useEffect(() => { // while the agent or a slow tool works, read often; otherwise now and then, for what the desktop adds
    const t = setInterval(() => { if (document.visibilityState === 'visible') void refresh() }, busy ? 2500 : 8000)
    return () => clearInterval(t)
  }, [busy])

  const task = screen.at === 'task' ? view?.tasks.find((t) => t.id === screen.id) : undefined
  const openTask = (t: Task) => go({ at: 'task', id: t.id })
  let body
  if (screen.at === 'task' && task) body = task.kind === 'alarm' ? <Alarm task={task} back={back} /> : task.kind === 'slope' ? <Level task={task} back={back} />
    : task.kind === 'heading' ? <Window task={task} back={back} /> : task.kind === 'floor_height' ? <FloorHeight task={task} back={back} /> : <Measure task={task} back={back} />
  else if (screen.at === 'tool') body = { where: <Where back={back} />, level: <Level back={back} />, sound: <Sound back={back} />, window: <Window back={back} />, floor: <FloorHeight back={back} />,
    photo: <PhotoMeasure back={back} />, walk: <Walkthrough back={back} />, note: <Note back={back} /> }[screen.id]
  else {
    const empty: NonNullable<typeof view> = { brief: null, summary: null, buildings: [], questions: [], tasks: [], captures: [], results: [], busy: false, plan: [], seq: 0 }
    const v = view ?? empty
    const todo = v.tasks.filter((t) => t.sid === sid && t.status === 'open').length
    body = (
      <div className="m-home">
        <Header onPrivacy={() => setPrivacy(true)} />
        <main className="m-body">
          <Hero tab={tab} />
          {state === 'loading' && !view ? <div aria-busy="true" aria-label="Loading the workspace" className="m-list">{[0, 1, 2, 3].map((i) => <div key={i} className="m-row skeleton" />)}</div>
            : <>
              {state === 'expired' && <p className="m-note warn" role="alert">That phone link has expired. Scan a new code on the desktop, or carry on with this phone alone.</p>}
              {state === 'offline' && <div className="m-note warn" role="alert"><p>The server is not answering. This phone has to be on the same network as it.</p><button className="btn m-btn" onClick={() => void refresh()}>Try again</button></div>}
              {tab === 'tasks' && <Tasks view={v} sid={sid} open={openTask} openTool={(id) => go({ at: 'tool', id })} />}
              {tab === 'tools' && <Tools sid={sid} open={(id) => go({ at: 'tool', id })} />}
              {tab === 'results' && <Results view={v} />}
            </>}
        </main>
        <nav className="m-tabs" aria-label="Sections">
          {TABS.map(([id, label, icon]) => <button key={id} aria-current={tab === id ? 'page' : undefined} onClick={() => { setTab(id); scrollTo(0, 0) }}><span className="m-tab-ico"><Ico name={icon} size={24} />{id === 'tasks' && todo > 0 && <span className="num" aria-label={`${todo} to do`}>{todo}</span>}</span>{label}</button>)}
        </nav>
      </div>
    )
  }
  // toasts sit under the top bar, so Back stays in reach while one shows
  return <>{body}<Privacy open={privacy} onOpenChange={setPrivacy} /><Toaster position="top-center" visibleToasts={2} offset={{ top: 'calc(env(safe-area-inset-top) + 52px)' }} mobileOffset={{ top: 'calc(env(safe-area-inset-top) + 52px)' }} toastOptions={{ unstyled: true, className: 'm-toast' }} /></>
}
