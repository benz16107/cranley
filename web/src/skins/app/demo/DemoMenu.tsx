import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { Icon, Menu, MenuBtn } from '../design/ui.tsx'
import { FLOWS, next, pause, play, stop, useDemo } from './player.ts'
import './demo.css'

/** The top bar's Demo menu: one item per flow, and while one plays, a caption bar at the foot of the window. */
export function DemoMenu() {
  const flow = useDemo((s) => s.flow), i = useDemo((s) => s.i)
  return (
    <>
      <MenuBtn align="end" trigger={
        <button type="button" className="btn quiet demo-btn" aria-label={flow ? `Demo: ${flow.title}, step ${i + 1} of ${flow.steps.length}` : 'Demo flows'}>
          <Icon name="play" size={13} /><span>Demo</span>{flow && <span className="num muted">{i + 1}/{flow.steps.length}</span>}
        </button>}>
        <div className="mh">Play a demo flow</div>
        {FLOWS.map((f) => (
          <Menu.Item key={f.id} onClick={() => void play(f)} className="demo-item">
            <span className="grow"><span>{f.title}</span><small className="muted">{f.track} · {f.steps.length} steps</small></span>
          </Menu.Item>
        ))}
        {flow && <Menu.Item onClick={stop}><Icon name="close" />Stop the flow</Menu.Item>}
      </MenuBtn>
      {flow && createPortal(<Captions />, document.body)}
    </>
  )
}

function Captions() {
  const s = useDemo()
  const [, tick] = useState(0)
  useEffect(() => { const t = setInterval(() => tick((n) => n + 1), 500); return () => clearInterval(t) }, [])
  if (!s.flow) return null
  const secs = Math.max(0, Math.round(((s.paused ? s.pausedFor : Date.now()) - s.started) / 1000))
  return (
    <div className="demo-cap" role="status" aria-live="polite">
      <div className="demo-say">
        <p>{s.say}</p>
        {s.note && <p className="demo-note">{s.note}</p>}
      </div>
      <div className="demo-ctl">
        <span className="num muted" title="Time since the flow started">{Math.floor(secs / 60)}:{String(secs % 60).padStart(2, '0')}</span>
        <span className="num muted">{s.done ? 'done' : `${s.i + 1}/${s.flow.steps.length}`}</span>
        {s.popup && <button type="button" className="btn sm solid" onClick={() => { window.open(s.popup!, 'threshold-second', 'popup,width=960,height=720'); useDemo.setState({ popup: null }) }}>Open the second window</button>}
        {!s.done && <button type="button" className="btn sm" onClick={() => pause(!s.paused)}>{s.paused ? 'Resume' : 'Pause'}</button>}
        {!s.done && <button type="button" className="btn sm quiet" onClick={next} title="Leave this step's caption now">Next</button>}
        <button type="button" className="btn sm quiet" onClick={stop} aria-label="Stop the demo flow"><Icon name="close" size={12} /></button>
      </div>
    </div>
  )
}
