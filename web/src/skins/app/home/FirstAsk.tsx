import { useRef, useState, type KeyboardEvent } from 'react'
import { NEEDS, useCatalog } from '../../../core/index.ts'
import { Icon } from '../design/ui.tsx'

/** The field and the five needs inside the first run's dialog (shell/FirstRun.tsx), which has its own heading and
    decides what starting does. One line, or one tap. Home's own entry is home/Ask.tsx. */
export function FirstAsk({ onStart }: { onStart: (sentence: string, needId?: string) => unknown }) {
  const [text, setText] = useState('')
  const live = useCatalog((s) => s.live)
  const field = useRef<HTMLTextAreaElement>(null), needs = useRef<HTMLUListElement>(null)
  const send = () => { if (text.trim()) void onStart(text.trim()) }
  const walk = (e: KeyboardEvent, i: number) => {
    const all = [...(needs.current?.querySelectorAll('button') ?? [])]
    if (e.key === 'ArrowDown' && all[i + 1]) { e.preventDefault(); all[i + 1].focus() }
    else if (e.key === 'ArrowUp' || e.key === 'Escape') { e.preventDefault(); (e.key === 'ArrowUp' && all[i - 1] ? all[i - 1] : field.current)?.focus() }
  }
  return (
    <section className="h-new">
      <form className="h-field" onSubmit={(e) => { e.preventDefault(); send() }}>
        <textarea ref={field} className="field" rows={2} value={text} onChange={(e) => setText(e.target.value)} placeholder="I use a wheelchair and I am choosing a one-bedroom apartment in Houston" aria-label="Who you are and what you need"
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() }
            else if (e.key === 'ArrowDown' && !text) { e.preventDefault(); needs.current?.querySelector('button')?.focus() }
            else if (e.key === 'Escape') e.currentTarget.blur()
          }} />
        <div>
          <span className="hint" aria-hidden="true"><span className="kbd">↓</span> for a need below</span>
          <span className="grow" />
          <button className="btn solid" disabled={!text.trim()}>Start<span className="kbd">Enter</span></button>
        </div>
      </form>
      {live === false && <p className="note"><Icon name="info" size={13} /><span>The agent server is not answering. A need below plays back a recorded composition; only the step-free access investigation runs.</span></p>}
      <ul className="h-needs" ref={needs} aria-label="Or start from a need">
        {NEEDS.map((n, i) => (
          <li key={n.id}>
            <button type="button" onClick={() => void onStart(n.sentence, n.id)} onKeyDown={(e) => walk(e, i)} title={n.sentence}>
              <span className="t"><b>{n.who}</b> {n.need}</span>
              <span className="s">{n.runsOn}</span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}
