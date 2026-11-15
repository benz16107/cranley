import { useState } from 'react'
import { Dialog } from '@base-ui/react/dialog'
import { Switch } from '@base-ui/react/switch'
import { Tabs } from '@base-ui/react/tabs'
import { answerPref, compose, focusFinding, investigate, useCatalog, useWorkspace, userOp, type Pref, type Question, type Run } from '../../../core/index.ts'
import { PanelView } from '../blocks/blocks.tsx'
import { Empty, Icon, IconBtn, RunState, StatusGlyph, ToolKey } from '../design/ui.tsx'
import { Sheet } from '../design/split.tsx'
import { sheetFocus } from '../lib/split.ts'
import { askHere } from '../lib/pending.ts'
import { goScan } from '../lib/place.ts'
import { newInvestigation } from './Sidebar.tsx'
import { useUi } from './store.ts'
import { ApprovalCard, ApproveAll, isApproval, Lanes } from './AgentLive.tsx'
import { Because, KnowsButton, Marks, useFirst } from './Knows.tsx'

// a mark on a check or a kind of check has no value to print: its sentence says it
const prefText = (p: Pick<Pref, 'value' | 'unit'>) => (typeof p.value === 'boolean' ? (p.value ? 'yes' : 'no') : typeof p.value === 'object' ? '' : `${p.value}${p.unit ? ' ' + p.unit : ''}`)

/* ---------- a question a tool needs answered: choice, number or text, with the value on offer ---------- */
export function QuestionForm({ q }: { q: Question }) {
  const [n, setN] = useState(q.hint != null && q.kind !== 'choice' ? String(q.hint) : '')
  const begun = useWorkspace((s) => s.doc.plan.length > 0)
  const answer = (a: string | number) => {
    userOp({ op: 'question.answer', id: q.id, answer: a })
    if (begun && q.pref) userOp(answerPref(q, a)) // answered after the work began: it counts at once
  }
  const done = q.answer != null
  return (
    <fieldset className="question" data-done={done || undefined}>
      <legend>{q.text}</legend>
      {q.kind === 'choice' && (
        <div className="row wrap">
          {q.options?.map((o) => <button key={o} type="button" className="chip" aria-pressed={q.answer === o} onClick={() => answer(o)}>{o}{q.answer == null && q.hint === o && <span className="muted">suggested</span>}</button>)}
        </div>
      )}
      {q.kind !== 'choice' && (
        <form className="row" onSubmit={(e) => { e.preventDefault(); if (q.kind === 'number' ? n !== '' && Number.isFinite(+n) : n.trim()) answer(q.kind === 'number' ? +n : n.trim()) }}>
          <input className="field" inputMode={q.kind === 'number' ? 'decimal' : undefined} value={done && !n ? String(q.answer) : n} onChange={(e) => setN(e.target.value)} aria-label={q.text} style={q.kind === 'number' ? { width: 96 } : undefined} />
          {q.unit && <span className="muted">{q.unit}</span>}
          <button className="btn" disabled={!n.trim()}>{done ? 'Change' : 'Set'}</button>
          {!done && q.hint != null && <span className="muted">offered: {String(q.hint)}</span>}
        </form>
      )}
    </fieldset>
  )
}

/** Open a run's result: over the page when it has a panel, else its building. */
export function openRun(r: Run) {
  const p = useWorkspace.getState().doc.panels.find((x) => x.run === r.id)
  if (p) useUi.setState({ panel: p.id }); else if (r.sid) goScan(r.sid)
}
export function RunRow({ r }: { r: Run }) {
  const doc = useWorkspace((s) => s.doc)
  const title = doc.tools.find((t) => t.id === r.tool)?.title ?? r.label.split(' · ')[0]
  const where = r.label.includes(' · ') ? r.label.split(' · ').slice(1).join(' · ') : ''
  const has = doc.panels.some((p) => p.run === r.id) || !!r.sid
  return (
    <li className="runrow" data-status={r.status}>
      <button type="button" disabled={!has} onClick={() => openRun(r)} title={has ? 'Open this result' : undefined}>
        <ToolKey id={r.tool} title={title} />
        <span className="grow"><span className="t trunc"><b>{title}</b>{where && <span className="muted"> · {where}</span>}</span>{r.summary && <span className="s">{r.summary}</span>}</span>
        {r.status === 'running' ? <RunState state="running">{''}</RunState> : r.status === 'failed' && <RunState state="failed" />}
      </button>
    </li>
  )
}

function Brief() {
  const doc = useWorkspace((s) => s.doc)
  const [editing, setEditing] = useState(false)
  const [text, setText] = useState('')
  const open = doc.questions.filter((q) => q.answer == null)
  if (!doc.brief && !open.length && !doc.plan.length && !doc.runs.length) {
    return <Empty icon="runs" title="No investigation open" action={<button className="btn solid" onClick={newInvestigation}>New investigation</button>}>Describe a need on Home and the agent picks the tools, asks what it must, and shows its work here.</Empty>
  }
  if (!doc.brief && !open.length) return null // tools run by hand, no brief: the runs below are the whole story
  return (
    <section className="rp-sec brief">
      {doc.brief && (
        <>
          <header><h3>Brief</h3>{!editing && <button className="btn sm quiet" onClick={() => { setText(doc.brief!.text); setEditing(true) }}>Edit</button>}</header>
          {editing ? (
            <form className="stack" onSubmit={(e) => { e.preventDefault(); setEditing(false); if (text.trim() && text !== doc.brief!.text) void compose(text.trim()) }}>
              <textarea className="field" rows={4} value={text} onChange={(e) => setText(e.target.value)} aria-label="Who you are and what you need" autoFocus />
              <div className="row"><button className="btn solid">Save and compose again</button><button type="button" className="btn quiet" onClick={() => setEditing(false)}>Cancel</button></div>
            </form>
          ) : <p className={doc.plan.length ? 'said clamp' : 'said'} title={doc.brief.text}>{doc.brief.text}</p>}
          {/* once the work is under way the limits fold away: the plan is what the panel is for */}
          {!editing && !!doc.brief.limits?.length && (
            <details className="limits" open={!doc.plan.length || undefined}>
              <summary><Icon name="right" size={11} />What the tools here cannot do<span className="count">{doc.brief.limits.length}</span></summary>
              {doc.brief.limits.map((l) => <p key={l}>{l}</p>)}
            </details>
          )}
        </>
      )}
      {open.length > 0 && !editing && (
        <div className="asks">
          <header><h3>{open.every(isApproval) ? (open.length === 1 ? 'The agent is waiting for your approval' : `The agent is waiting for ${open.length} approvals`) : open.length === 1 ? 'One question' : `${open.length} questions`} before the work can go on</h3></header>
          {/* several approvals at once are usually the same step on several buildings: one press answers them all */}
          {open.length > 1 && open.every(isApproval) && <ApproveAll open={open} />}
          {open.map((q) => (isApproval(q) ? <ApprovalCard key={q.id} q={q} /> : <QuestionForm key={q.id} q={q} />))}
        </div>
      )}
      {doc.brief && doc.questions.length > 0 && !doc.plan.length && !editing && (
        <div className="row">
          <button className="btn solid" disabled={open.length > 0} onClick={() => void investigate()}>{open.length ? `${open.length} left to answer` : 'Start the investigation'}</button>
          {open.length > 0 && open.every((q) => q.hint != null) && <button className="btn" onClick={() => void investigate()}>Use the defaults</button>}
        </div>
      )}
    </section>
  )
}

function Plan() {
  const plan = useWorkspace((s) => s.doc.plan), runs = useWorkspace((s) => s.doc.runs)
  const [all, setAll] = useState<Record<string, boolean>>({})
  const byHand = runs.filter((r) => !r.step), earlier = runs.filter((r) => r.step && !plan.some((s) => s.id === r.step))
  if (!plan.length && !runs.length) return <p className="rp-none">No plan yet. It appears when the investigation starts.</p>
  const done = plan.filter((s) => s.status === 'done').length
  return (
    <div className="plan">
      {plan.length > 0 && <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={plan.length} aria-valuenow={done} aria-label={`${done} of ${plan.length} steps done`}><i style={{ scale: `${done / plan.length} 1` }} /></div>}
      <ol>
        {plan.map((s, i) => {
          const mine = runs.filter((r) => r.step === s.id), shown = all[s.id] || s.status === 'active' ? mine : mine.slice(-2)
          return (
            <li key={s.id} className="step" data-status={s.status} aria-current={s.status === 'active' ? 'step' : undefined}>
              <div className="sh"><span className="n">{i + 1}</span><span className="grow">{s.label}</span><RunState state={s.status}>{''}</RunState></div>
              {mine.length > 0 && (
                <ul className="runs">
                  {mine.length > shown.length && <li><button className="more" onClick={() => setAll({ ...all, [s.id]: true })}>{mine.length - shown.length} earlier runs</button></li>}
                  {shown.map((r) => <RunRow key={r.id} r={r} />)}
                </ul>
              )}
            </li>
          )
        })}
        {[['Earlier turns', earlier] as const, ['Run by you', byHand] as const].map(([label, list]) => list.length > 0 && (
          <li key={label} className="step" data-status="done">
            <div className="sh"><span className="n" /><span className="grow">{label}</span><span className="count">{list.length}</span></div>
            <ul className="runs">
              {list.length > 4 && !all[label] && <li><button className="more" onClick={() => setAll({ ...all, [label]: true })}>{list.length - 4} earlier runs</button></li>}
              {(all[label] ? list : list.slice(-4)).map((r) => <RunRow key={r.id} r={r} />)}
            </ul>
          </li>
        ))}
      </ol>
    </div>
  )
}

function Findings() {
  const doc = useWorkspace((s) => s.doc)
  const order = { fail: 0, warn: 1, unknown: 2, pass: 3 } as const
  const first = useFirst() // kinds the person marked useful lead, within each status
  const items = [...doc.findings].sort((a, b) => order[a.status] - order[b.status] || +first.has(b.id) - +first.has(a.id))
  if (!items.length) return <p className="rp-none">Nothing checked yet. Each check links to its place in the building.</p>
  return (
    <ul className="flist">
      {items.slice(0, 80).map((f) => (
        <li key={f.id} data-first={first.has(f.id) || undefined} title={first.has(f.id) ? `Listed first: ${first.get(f.id)}` : undefined}>
          <button type="button" disabled={!f.anchor} aria-current={doc.camera?.finding === f.id || undefined} onClick={() => focusFinding(f)} title={f.anchor ? 'Show this in the building' : 'This check has no place to show'}>
            <StatusGlyph status={f.status} />
            <span className="grow"><span className="t">{f.title}</span>{f.detail && <span className="s">{f.detail}</span>}</span>
            {f.anchor && <Icon name="target" size={13} />}
          </button>
          <Marks id={f.id} title={f.title} />
        </li>
      ))}
      {items.length > 80 && <li className="rp-none">Showing 80 of {items.length}. The investigation page lists all of them.</li>}
    </ul>
  )
}

export function Learned() {
  const prefs = useWorkspace((s) => s.doc.prefs)
  if (!prefs.length) return <p className="rp-none">Nothing learned yet. An answer or a changed setting is kept here, with where it came from, and can be undone.</p>
  return (
    <ul className="learned">
      {prefs.map((p) => (
        <li key={p.key}>
          <span className="grow">{p.label}{prefText(p) && <b> {prefText(p)}</b>}<small>{p.from}{p.prev != null && ` (was ${prefText({ value: p.prev, unit: p.unit })})`}</small></span>
          <button className="btn sm" aria-label={`Undo: ${p.label}`} onClick={() => userOp({ op: 'pref.set', key: p.key, label: p.label, value: p.prev ?? null, unit: p.unit, from: p.prev != null ? 'You undid a change' : undefined })}>Undo</button>
        </li>
      ))}
    </ul>
  )
}

/** The agent's panel: the brief, what it must be told, its plan with live runs, its findings, and one line to ask. */
export function RunPanel({ onClose }: { onClose: () => void }) {
  const doc = useWorkspace((s) => s.doc)
  const follow = useWorkspace((s) => s.follow), setFollow = useWorkspace((s) => s.setFollow)
  const canUndo = useWorkspace((s) => s.undoStack.length > 0), undo = useWorkspace((s) => s.undo)
  const [text, setText] = useState('')
  const [tab, setTab] = useState('plan')
  const shared = useCatalog((s) => !!s.shared)
  const active = doc.plan.find((s) => s.status === 'active'), running = doc.runs.filter((r) => r.status === 'running')
  const open = doc.questions.filter((q) => q.answer == null).length
  const send = () => { if (text.trim()) { void askHere(text.trim()); setText('') } }
  return (
    <aside className="run" aria-label="Agent">
      <header className="rp-head">
        <h2>Agent</h2>
        <span className="grow trunc">{active || running.length ? <RunState state="running">{active?.label ?? running[0].label}</RunState> : open ? <span className="rs" data-state="ask">{open} to answer</span> : doc.plan.length ? <RunState state="done">Finished</RunState> : <span className="muted">Idle</span>}</span>
        <KnowsButton />
        <IconBtn icon="close" label="Close the agent panel" kbd="]" onClick={onClose} />
      </header>
      <div className="rp-body scroll">
        <Brief />
        <Because />
        {(doc.plan.length > 0 || doc.runs.length > 0 || doc.findings.length > 0 || doc.prefs.length > 0) && (
          <Tabs.Root value={tab} onValueChange={(v) => setTab(String(v))}>
            <Tabs.List className="tabs">
              <Tabs.Tab value="plan">Plan{doc.runs.length > 0 && <span className="count">{doc.runs.length}</span>}</Tabs.Tab>
              <Tabs.Tab value="findings">Checks{doc.findings.length > 0 && <span className="count">{doc.findings.length}</span>}</Tabs.Tab>
              <Tabs.Tab value="learned">Learned{doc.prefs.length > 0 && <span className="count">{doc.prefs.length}</span>}</Tabs.Tab>
            </Tabs.List>
            <Tabs.Panel value="plan"><Lanes /><Plan /></Tabs.Panel>
            <Tabs.Panel value="findings"><Findings /></Tabs.Panel>
            <Tabs.Panel value="learned"><Learned /></Tabs.Panel>
          </Tabs.Root>
        )}
      </div>
      {shared ? <footer className="rp-foot"><p className="muted small">This is a read-only link. The plan, the runs and every finding can be opened; nothing can be asked or changed from here.</p></footer> : (
      <footer className="rp-foot">
        <form className="composer" onSubmit={(e) => { e.preventDefault(); send() }}>
          <textarea className="field" rows={2} value={text} onChange={(e) => setText(e.target.value)} placeholder="Ask the agent for a change or a check" aria-label="Ask the agent"
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }} />
          <button className="btn solid icon" disabled={!text.trim()} aria-label="Send"><Icon name="send" size={14} /></button>
        </form>
        <div className="row">
          <label className="follow"><Switch.Root className="switch" checked={follow} onCheckedChange={setFollow}><Switch.Thumb className="knob" /></Switch.Root><span>Follow the agent’s view</span></label>
          <span className="grow" />
          {canUndo && <button className="btn sm quiet" onClick={undo} title="Undo your last change (Ctrl Z)"><Icon name="undo" size={13} />Undo</button>}
        </div>
      </footer>
      )}
    </aside>
  )
}

/** One result, opened over the page from a run or a table row. */
export function PanelDrawer() {
  const id = useUi((s) => s.panel)
  const doc = useWorkspace((s) => s.doc)
  const panel = doc.panels.find((p) => p.id === id)
  const tool = panel && doc.tools.find((t) => t.id === panel.tool)
  return (
    <Dialog.Root open={!!panel} onOpenChange={(o) => !o && useUi.setState({ panel: null })}>
      <Dialog.Portal>
        <Dialog.Backdrop className="backdrop" />
        <Dialog.Popup className="drawerwrap" aria-label={panel?.title} initialFocus={sheetFocus}>
          {panel && (
            <Sheet>
              <header>
                <ToolKey id={panel.tool} title={tool?.title ?? panel.title} />
                <Dialog.Title render={<h2 className="trunc" />}><b>{panel.title}</b>{panel.scope && <span className="muted"> · {panel.scope}</span>}</Dialog.Title>
                {panel.sid && <button className="btn sm" onClick={() => { useUi.setState({ panel: null }); goScan(panel.sid!) }}>Open the building<Icon name="go" size={12} /></button>}
                <Dialog.Close render={<button className="btn icon quiet" aria-label="Close" />}><Icon name="close" /></Dialog.Close>
              </header>
              <div className="body"><Because run={panel.run} /><PanelView panel={panel} bare /></div>
            </Sheet>
          )}
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
