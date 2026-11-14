import { useState } from 'react'
import { NEEDS, compose, investigate, startOver, useBuildings, useCatalog, useToolCatalog, useWorkspace } from '../../../core/index.ts'
import { DataTable, Empty, Icon, RunState, Stats, ToolKey, type Col } from '../design/ui.tsx'
import { ago, int } from '../lib/format.ts'
import { openSeen, started, statusOf, useSeen, type Seen } from '../lib/pending.ts'
import { go, goInvestigation, goScan } from '../lib/place.ts'
import { QuestionForm, RunRow } from '../shell/RunPanel.tsx'

export const STATUS: Record<Seen['status'], { label: string; state: 'pending' | 'running' | 'done' }> = {
  setup: { label: 'Setting up', state: 'pending' }, working: { label: 'Working', state: 'running' }, waiting: { label: 'Needs an answer', state: 'pending' }, done: { label: 'Finished', state: 'done' },
}

/** A new brief: one sentence, or a starting point. */
function Composer() {
  const [text, setText] = useState('')
  const live = useCatalog((s) => s.live)
  const send = () => { if (text.trim()) void compose(text.trim()) }
  return (
    <section className="card" aria-labelledby="new-h">
      <header><h2 id="new-h">New investigation</h2><p className="grow">Say who you are and what you need from a building. The agent picks the tools and asks what it must.</p></header>
      <div className="body stack">
        <form className="newform" onSubmit={(e) => { e.preventDefault(); send() }}>
          <textarea className="field" rows={2} value={text} onChange={(e) => setText(e.target.value)} placeholder="I use a wheelchair and I am choosing a one-bedroom apartment in Houston" aria-label="Who you are and what you need"
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }} />
          <button className="btn solid" disabled={!text.trim()}>Compose<span className="kbd">Enter</span></button>
        </form>
        {live === false && <p className="note"><Icon name="info" size={13} /><span>The agent server is not answering. A starting point below plays back a recorded composition; only the step-free access investigation runs.</span></p>}
      </div>
      <div className="tmpl">
        <h3>Or start from a need</h3>
        <ul>
          {NEEDS.map((n) => (
            <li key={n.id}>
              <button type="button" onClick={() => void compose(n.sentence, n.id)}>
                <span className="grow"><b>{n.who}</b> <span className="dim">{n.need}</span></span>
                <span className="muted on">{n.runsOn}</span>
                <span className="muted">{n.tools.length} tools</span>
                <Icon name="go" size={12} />
              </button>
            </li>
          ))}
        </ul>
      </div>
    </section>
  )
}

/** The brief is in: the tools arrive with their reasons, then the questions, then Start. */
function Setup() {
  const doc = useWorkspace((s) => s.doc)
  const open = doc.questions.filter((q) => q.answer == null)
  const settled = doc.questions.length > 0 || doc.tools.length > 0
  return (
    <section className="card" aria-labelledby="setup-h">
      <header>
        <h2 id="setup-h">Setting up the investigation</h2>
        <span className="grow" />
        <button className="btn quiet" onClick={() => { startOver(); go('home') }}>Start over</button>
      </header>
      <div className="body stack">
        <p className="said">{doc.brief!.text}</p>
        {!!doc.brief!.limits?.length && <div className="note"><Icon name="info" size={13} /><div><b>What the tools here cannot do</b>{doc.brief!.limits.map((l) => <p key={l}>{l}</p>)}</div></div>}
      </div>
      <div className="setup-cols">
        <div>
          <h3>Tools for this <span className="count">{doc.tools.length || ''}</span></h3>
          <ul className="picked" aria-live="polite">
            {doc.tools.map((t) => <li key={t.id} className="arrive"><ToolKey id={t.id} title={t.title} /><span className="grow"><b>{t.title}</b><span className="why">{t.reason}</span></span><span className="muted">{t.by === 'agent' ? 'agent' : 'you'}</span></li>)}
            {!settled && <li><RunState state="running">Reading the brief and choosing tools</RunState></li>}
            {!settled && [72, 54, 63].map((w) => <li key={w}><span className="sk" style={{ width: `${w}%` }} /></li>)}
          </ul>
        </div>
        <div>
          <h3>Before the work starts <span className="count">{open.length ? `${open.length} open` : ''}</span></h3>
          {doc.questions.length === 0 ? <p className="muted">{settled ? 'No questions. The tools can run on their defaults.' : 'Questions appear here once the tools are chosen.'}</p> : <div className="stack">{doc.questions.map((q) => <QuestionForm key={q.id} q={q} />)}</div>}
        </div>
      </div>
      {settled && (
        <footer className="setup-go">
          <button className="btn solid" disabled={open.length > 0} onClick={() => void investigate()}>{open.length ? `${open.length} left to answer` : 'Start the investigation'}</button>
          {open.length > 0 && <button className="btn" onClick={() => void investigate()}>Use the defaults</button>}
          <span className="muted small">The agent searches, measures and ranks. Its plan and every run show in the agent panel and on the map.</span>
        </footer>
      )}
    </section>
  )
}

export function Home() {
  const doc = useWorkspace((s) => s.doc)
  const seen = useSeen((s) => s.all)
  const count = useBuildings((s) => s.all.length)
  const tools = useToolCatalog()
  const composing = !!doc.brief && doc.plan.length === 0 && doc.panels.length === 0
  const list = Object.values(seen).sort((a, b) => b.last - a.last)
  const cols: Col<Seen>[] = [
    { id: 'brief', label: 'Investigation', fixed: true, cell: (s) => <span className="strong">{s.brief || 'Untitled investigation'}</span> },
    { id: 'status', label: 'Status', width: 140, cell: (s) => <RunState state={STATUS[s.status].state}>{STATUS[s.status].label}</RunState> },
    { id: 'runs', label: 'Runs', num: true, width: 60, cell: (s) => int(s.runs) },
    { id: 'findings', label: 'Findings', num: true, width: 76, cell: (s) => int(s.findings) },
    { id: 'last', label: 'Last change', width: 120, cell: (s) => <span className="dim">{ago(s.last)}</span> },
  ]
  const recentRuns = doc.runs.slice(-6).reverse()
  return (
    <div className="page">
      <div className="inner">
        {composing ? <Setup /> : (
          <>
            {started(doc) && (
              <section className="card current">
                <header>
                  <RunState state={STATUS[statusOf(doc)].state}>{STATUS[statusOf(doc)].label}</RunState>
                  <h2 className="grow trunc">{doc.brief?.text ?? 'Untitled investigation'}</h2>
                  <button className="btn" onClick={() => goInvestigation(doc.id)}>Open<Icon name="go" size={12} /></button>
                </header>
              </section>
            )}
            <Composer />
          </>
        )}
        <Stats items={[
          { label: 'Scanned addresses', value: count ? int(count) : <span className="sk" style={{ width: 48 }} /> },
          { label: 'Investigations here', value: int(list.length) },
          { label: 'Saved buildings', value: int(doc.shortlist.length) },
          { label: 'Tools', value: tools.length ? int(tools.length) : <span className="sk" style={{ width: 24 }} /> },
        ]} />
        <div className="home-cols">
          <section className="card">
            <header><h2 className="grow">Recent investigations</h2><button className="btn sm quiet" onClick={() => go('investigations')}>All<Icon name="go" size={11} /></button></header>
            <DataTable label="Recent investigations" noun="investigation" cols={cols} rows={list.slice(0, 6)} rowKey={(s) => s.id} onRow={(s) => (s.id === doc.id ? goInvestigation(s.id) : openSeen(s.id))}
              empty={<Empty icon="runs" title="No investigations yet">Describe a need above. Each investigation you start is listed here.</Empty>} />
          </section>
          <section className="card">
            <header><h2 className="grow">Saved buildings</h2><button className="btn sm quiet" onClick={() => go('buildings')}>All<Icon name="go" size={11} /></button></header>
            {doc.shortlist.length === 0 ? <Empty icon="keep" title="Nothing kept yet" action={<button className="btn" onClick={() => go('explore')}>Explore the map</button>}>Keep a scan from its page and it stays here.</Empty> : (
              <ul className="rows flush">
                {doc.shortlist.slice(0, 6).map((s) => <li key={s.sid}><button type="button" onClick={() => goScan(s.sid)}><Icon name="building" /><span className="grow"><span className="trunc">{s.name}</span><span className="s">{s.address.split(',')[0]}</span></span><Icon name="go" size={12} /></button></li>)}
              </ul>
            )}
          </section>
        </div>
        {recentRuns.length > 0 && (
          <section className="card">
            <header><h2 className="grow">Latest runs</h2><button className="btn sm quiet" onClick={() => goInvestigation(doc.id)}>All {doc.runs.length}<Icon name="go" size={11} /></button></header>
            <ul className="runlist">{recentRuns.map((r) => <RunRow key={r.id} r={r} />)}</ul>
          </section>
        )}
      </div>
    </div>
  )
}
