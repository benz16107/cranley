import { useEffect, useMemo, useState } from 'react'
import { captureImage, fetchCaptures, type Capture, type Doc } from '../../../core/index.ts'
import { Icon, RunState, ToolKey } from '../design/ui.tsx'
import { ago, clock, dur } from '../lib/format.ts'
import { activity, type HomeEvent } from '../lib/home.ts'
import { openRun } from '../shell/RunPanel.tsx'
import { useUi } from '../shell/store.ts'

const NONE: Capture[] = []
const CAPTURE: Record<Capture['kind'], string> = { photo: 'Photo', video: 'Video', audio: 'Voice note', reading: 'Reading' }
/** One feed for everything that is happening or just did: runs, failed ones in red, a question that holds the work
    up, and what a paired phone sent. */
export function Activity({ doc }: { doc: Doc }) {
  // what the phone sent, kept with the workspace it belongs to so another workspace never shows it
  const [got, setGot] = useState<{ ws: string; list: Capture[] }>({ ws: '', list: NONE })
  const live = doc.id.startsWith('ws_'), captures = got.ws === doc.id ? got.list : NONE
  // Read again a moment after the workspace changes (a paired phone's capture is one of its writes), and every 20 s
  // while the page is in view, because a tab that did not do the pairing is not told about the phone's writes.
  useEffect(() => {
    if (!live) return
    let on = true
    const ws = doc.id
    const read = () => { if (document.visibilityState === 'visible') fetchCaptures(ws).then((list) => on && setGot({ ws, list }), () => {}) }
    const soon = setTimeout(read, 300), every = setInterval(read, 20_000)
    return () => { on = false; clearTimeout(soon); clearInterval(every) }
  }, [doc, live])
  const rows = useMemo(() => activity(doc, captures, 9), [doc, captures])
  const title = (tool: string, label: string) => doc.tools.find((t) => t.id === tool)?.title ?? label.split(' · ')[0]
  const where = (label: string) => (label.includes(' · ') ? label.split(' · ').slice(1).join(' · ') : '')
  const agent = () => useUi.getState().setRun(true)
  const row = (e: HomeEvent) => {
    if (e.kind === 'working') return (
      <button type="button" onClick={agent}><i className="ring" /><span className="grow"><span className="t"><b>{e.run ? title(e.run.tool, e.run.label) : 'The agent'}</b>{e.run && where(e.run.label) && <span className="muted"> · {where(e.run.label)}</span>}</span><span className="s">{e.text}</span></span><span className="w rs" data-state="running">Working</span></button>
    )
    if (e.kind === 'ask') return (
      <button type="button" onClick={agent}><Icon name="help" size={14} /><span className="grow"><span className="t"><b>{e.open === 1 ? 'One question' : `${e.open} questions`} before the work can go on</b></span><span className="s">Answer in the agent panel.</span></span><span className="w rs" data-state="ask">Answer</span></button>
    )
    if (e.kind === 'run') { const r = e.run, timed = r.at != null; return (
      <button type="button" onClick={() => openRun(r)} disabled={!r.sid && !doc.panels.some((p) => p.run === r.id)}>
        <ToolKey id={r.tool} title={title(r.tool, r.label)} />
        <span className="grow"><span className="t"><b>{title(r.tool, r.label)}</b>{where(r.label) && <span className="muted"> · {where(r.label)}</span>}</span>{r.summary && <span className="s">{r.summary}</span>}</span>
        {r.status === 'failed' ? <span className="w"><RunState state="failed" /></span> : <span className="w muted">{timed ? ago(e.at) : dur(r.ms)}</span>}
      </button>
    ) }
    const c = e.capture
    return (
      <div className="cap">
        <span className="k"><Icon name={c.kind === 'photo' || c.kind === 'video' ? 'camera' : 'site'} size={14} /></span>
        <span className="grow"><span className="t"><b>{CAPTURE[c.kind]} from the phone</b></span><span className="s">{c.note || (c.task ? 'Answers an on-site check' : c.tool ? c.tool.replace(/_/g, ' ') : 'A note')}</span></span>
        {c.kind === 'photo' && c.file && <img src={captureImage(c.id)} alt="" loading="lazy" width={40} height={30} />}
        <span className="w muted" title={clock(e.at)}>{ago(e.at)}</span>
      </div>
    )
  }
  if (rows.length === 0) return <p className="h-none">Nothing has run yet. Runs, failures, questions and what a paired phone sends are listed here as they happen.</p>
  return <ul className="h-feed" aria-live="polite">{rows.map((e) => <li key={e.id} data-kind={e.kind} data-failed={(e.kind === 'run' && e.run.status === 'failed') || undefined}>{row(e)}</li>)}</ul>
}
