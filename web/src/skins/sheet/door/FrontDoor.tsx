import { useState } from 'react'
import NumberFlow from '@number-flow/react'
import { NEEDS, TOOLS } from '../../../core/index.ts'
import { compose, investigate, startOver } from '../../../core/index.ts'
import { useWorkspace } from '../../../core/index.ts'
import { ToolKey } from '../design/ui.tsx'
import { navigate } from '../../../core/index.ts'
import { QuestionForm } from '../shell/Case.tsx'

/* The front door, set as the cover sheet of a drawing set: say who you are in a sentence, or pick a starting
   point from the index. Then the composition happens in view: tools arrive with their reasons, the questions
   those tools need are asked inline, and the investigation starts. */
export function FrontDoor({ count }: { count: number | null }) {
  const doc = useWorkspace((s) => s.doc)
  const [text, setText] = useState('')
  const composing = !!doc.brief
  const open = doc.questions.filter((q) => q.answer == null)
  const settled = composing && doc.questions.length > 0

  return (
    <section className="pane door scroll" aria-labelledby="door-h">
      <header className="sheethead"><span className="label">Cover sheet</span><span className="label num">{composing ? 'Composing' : 'Sheet 00'}</span></header>
      {!composing ? (
        <>
          <h1 id="door-h">Say who you are and what you need from a building.</h1>
          <p className="lede">
            {count == null ? <span className="skeleton count" /> : <b className="num"><NumberFlow value={count} /></b>} addresses in Houston and Los Angeles have been scanned inside.
            An agent picks the measuring tools for your question, runs them on those scans, and shows its work on the map and in the building.
          </p>
          <form className="say" onSubmit={(e) => { e.preventDefault(); if (text.trim()) void compose(text.trim()) }}>
            <label htmlFor="who" className="label">In one sentence</label>
            <div className="row">
              <input id="who" className="field" value={text} onChange={(e) => setText(e.target.value)} placeholder="I use a wheelchair and I am choosing an apartment" autoComplete="off" />
              <button className="btn solid" disabled={!text.trim()}>Compose</button>
            </div>
          </form>
          <h2 className="label idx">Or start from one of these</h2>
          <ol className="needs">
            {NEEDS.map((n, i) => (
              <li key={n.id}>
                <button onClick={() => void compose(n.sentence, n.id)}>
                  <span className="num n">{String(i + 1).padStart(2, '0')}</span>
                  <span className="who"><b>{n.who}</b> {n.need}</span>
                  <span className="codes" aria-hidden="true">{n.tools.map(([id]) => <ToolKey key={id} id={id} title={TOOLS[id].title} code={TOOLS[id].code} />)}</span>
                  <span className="on muted">{n.runsOn}</span>
                </button>
              </li>
            ))}
          </ol>
          <button className="link explore" onClick={() => navigate('/map')}>Skip this and look at the map</button>
        </>
      ) : (
        <>
          <h1 id="door-h" className="said">“{doc.brief!.text}”</h1>
          <h2 className="label idx">Tools for this</h2>
          <ol className="picked" aria-live="polite">
            {doc.tools.map((t) => (
              <li key={t.id} className="arrive">
                <ToolKey id={t.id} title={t.title} code={t.code} />
                <span><b>{t.title}</b><span className="why">{t.reason}</span></span>
              </li>
            ))}
            {!settled && <li className="pending"><span className="skeleton" /></li>}
          </ol>
          {settled && (
            <div className="arrive">
              <h2 className="label idx">Before the work starts</h2>
              <div className="asks">{doc.questions.map((q) => <QuestionForm key={q.id} q={q} />)}</div>
              <div className="row go">
                <button className="btn solid" disabled={open.length > 0} onClick={() => void investigate()}>{open.length ? `${open.length} left to answer` : 'Start the investigation'}</button>
                <button className="link" onClick={() => void investigate()}>Use the defaults</button>
                <button className="link" onClick={() => { startOver(); navigate('/', {}, { replace: true }) }}>Start over</button>
              </div>
            </div>
          )}
        </>
      )}
    </section>
  )
}
