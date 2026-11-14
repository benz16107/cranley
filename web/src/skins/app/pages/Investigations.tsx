import { useMemo, useState } from 'react'
import { Tabs } from '@base-ui/react/tabs'
import { toast } from 'sonner'
import { DownloadReport } from '../report/DownloadReport.tsx'
import { focusFinding, investigate, shareWorkspace, useBuildings, useCatalog, useWorkspace, userOp, type Doc, type Run, type Status } from '../../../core/index.ts'
import { PanelView } from '../blocks/blocks.tsx'
import { DataTable, Empty, Icon, IconBtn, RunState, Seg, SourceChip, St, Stats, ToolKey, statusWord, type Col } from '../design/ui.tsx'
import { ago, clock, dur, int } from '../lib/format.ts'
import { forgetSeen, leaveShared, openSeen, statusOf, useSeen, type Seen } from '../lib/pending.ts'
import { goInvestigation, goScan } from '../lib/place.ts'
import { family } from '../lib/tools.ts'
import { Learned, QuestionForm, openRun } from '../shell/RunPanel.tsx'
import { newInvestigation } from '../shell/Sidebar.tsx'
import { useUi } from '../shell/store.ts'
import { STATUS } from './Home.tsx'

/* ---------- the list: investigations this browser has seen ---------- */
export function Investigations() {
  const seen = useSeen((s) => s.all), current = useWorkspace((s) => s.doc.id)
  const [text, setText] = useState(''), [only, setOnly] = useState<'all' | Seen['status']>('all')
  const all = useMemo(() => Object.values(seen).sort((a, b) => b.last - a.last), [seen])
  const rows = all.filter((s) => (only === 'all' || s.status === only) && (!text.trim() || s.brief.toLowerCase().includes(text.trim().toLowerCase())))
  const cols: Col<Seen>[] = [
    { id: 'brief', label: 'Investigation', fixed: true, sort: (s) => s.brief, cell: (s) => <><span className="strong">{s.brief || 'Untitled investigation'}</span>{s.id === current && <span className="chip visited">Open</span>}</> },
    { id: 'status', label: 'Status', width: 150, sort: (s) => s.status, cell: (s) => <RunState state={STATUS[s.status].state}>{STATUS[s.status].label}</RunState> },
    { id: 'steps', label: 'Steps', num: true, width: 76, sort: (s) => s.done, cell: (s) => (s.steps ? `${s.done} of ${s.steps}` : <span className="muted">–</span>) },
    { id: 'tools', label: 'Tools', num: true, width: 64, sort: (s) => s.tools, cell: (s) => int(s.tools) },
    { id: 'runs', label: 'Runs', num: true, width: 64, sort: (s) => s.runs, cell: (s) => int(s.runs) },
    { id: 'failed', label: 'Failed', num: true, width: 68, sort: (s) => s.failed, cell: (s) => (s.failed ? <span className="st" data-status="fail">{s.failed}</span> : <span className="muted">–</span>) },
    { id: 'findings', label: 'Findings', num: true, width: 80, sort: (s) => s.findings, cell: (s) => int(s.findings) },
    { id: 'kept', label: 'Kept', num: true, width: 60, sort: (s) => s.kept, cell: (s) => int(s.kept) },
    { id: 'first', label: 'First seen', width: 132, sort: (s) => s.first, cell: (s) => <span className="dim">{clock(s.first)}</span> },
    { id: 'last', label: 'Last change', width: 116, sort: (s) => s.last, cell: (s) => <span className="dim">{ago(s.last)}</span> },
    { id: 'x', label: '', width: 56, fixed: true, cell: (s) => (s.id === current ? null : <IconBtn icon="trash" label="Remove from this list" className="btn icon quiet sm" size={13} onClick={(e) => { e.stopPropagation(); forgetSeen(s.id) }} />) },
  ]
  return (
    <div className="listpage">
      <div className="bar">
        <label className="inset"><Icon name="search" size={13} /><input className="field" value={text} onChange={(e) => setText(e.target.value)} placeholder="Filter by brief" aria-label="Filter investigations by their brief" /></label>
        <Seg label="Status" value={only} onChange={setOnly} options={[{ id: 'all', label: `All ${all.length}` }, { id: 'working', label: 'Working' }, { id: 'waiting', label: 'Needs an answer' }, { id: 'done', label: 'Finished' }]} />
        <span className="grow" />
        <button className="btn solid" onClick={newInvestigation}><Icon name="plus" size={13} />New investigation</button>
      </div>
      <DataTable label="Investigations" noun="investigation" cols={cols} rows={rows} rowKey={(s) => s.id} sortBy={{ col: 'last', dir: -1 }} onRow={(s) => (s.id === current ? goInvestigation(s.id) : openSeen(s.id))}
        empty={all.length ? <Empty icon="filter" title="No investigation matches" /> : <Empty icon="runs" title="No investigations yet" action={<button className="btn solid" onClick={newInvestigation}>New investigation</button>}>An investigation is one brief, the tools picked for it, and every run and finding that followed.</Empty>}
        foot={<span className="grow" style={{ textAlign: 'right' }}>Listed from this browser. Work started elsewhere is not shown until the server lists past work.</span>} />
    </div>
  )
}

/* ---------- one investigation ---------- */
const scanName = (all: ReturnType<typeof useBuildings.getState>['all'], sid?: string) => { if (!sid) return ''; for (const b of all) { const s = b.scans.find((x) => x.sid === sid); if (s) return s.name } return sid }

function Runs({ doc }: { doc: Doc }) {
  const all = useBuildings((s) => s.all)
  const max = Math.max(1, ...doc.runs.map((r) => r.ms ?? 0))
  const stepNo = (r: Run) => { const i = doc.plan.findIndex((s) => s.id === r.step); return i < 0 ? null : i + 1 }
  const cols: Col<Run>[] = [
    { id: 'step', label: 'Step', width: 56, num: true, sort: (r) => stepNo(r) ?? 99, cell: (r) => stepNo(r) ?? <span className="muted">you</span> },
    { id: 'tool', label: 'Tool', fixed: true, width: '21%', sort: (r) => r.tool, cell: (r) => <span className="row"><ToolKey id={r.tool} title={r.label} /><span className="trunc">{doc.tools.find((t) => t.id === r.tool)?.title ?? r.label.split(' · ')[0]}</span></span> },
    { id: 'on', label: 'On', width: '19%', sort: (r) => scanName(all, r.sid), cell: (r) => <span className="dim">{r.sid ? scanName(all, r.sid) : r.place?.address ?? (r.place?.geo ? 'A point on the map' : '–')}</span> },
    { id: 'status', label: 'Status', width: 88, sort: (r) => r.status, cell: (r) => <RunState state={r.status} /> },
    { id: 'ms', label: 'Time', num: true, width: 128, sort: (r) => r.ms ?? null, cell: (r) => (r.ms == null ? <span className="muted">–</span> : <span className="durbar"><i style={{ width: `${Math.max(2, (r.ms / max) * 100)}%` }} /><span className="num">{dur(r.ms)}</span></span>) },
    { id: 'summary', label: 'Result', cell: (r) => <span className="dim" title={r.summary}>{r.summary ?? ''}</span> },
  ]
  return <DataTable label="Runs" noun="run" cols={cols} rows={doc.runs} rowKey={(r) => r.id} onRow={openRun}
    empty={<Empty icon="play" title="No runs yet">A run is one tool on one scan or place. They appear here as the agent works, or when you run a tool on a building.</Empty>} />
}

type F = Doc['findings'][number]
function Findings({ doc }: { doc: Doc }) {
  const all = useBuildings((s) => s.all)
  const [only, setOnly] = useState<'all' | Status>('all')
  const n = (s: Status) => doc.findings.filter((f) => f.status === s).length
  const order = { fail: 0, warn: 1, unknown: 2, pass: 3 } as const
  const rows = useMemo(() => doc.findings.filter((f) => only === 'all' || f.status === only).sort((a, b) => order[a.status] - order[b.status]), [doc.findings, only]) // eslint-disable-line react-hooks/exhaustive-deps
  const where = (f: F) => (f.anchor && 'sid' in f.anchor ? scanName(all, f.anchor.sid) : f.anchor ? 'On the map' : '')
  const cols: Col<F>[] = [
    { id: 'status', label: 'Status', width: 124, sort: (f) => order[f.status], cell: (f) => <St status={f.status} /> },
    { id: 'title', label: 'Check', fixed: true, sort: (f) => f.title, cell: (f) => <><span className="strong">{f.title}</span>{f.detail && <span className="sub">{f.detail}</span>}</> },
    { id: 'tool', label: 'Tool', width: '16%', sort: (f) => f.tool, cell: (f) => <span className="dim">{doc.tools.find((t) => t.id === f.tool)?.title ?? f.tool}</span> },
    { id: 'where', label: 'Where', width: '18%', sort: where, cell: (f) => <span className="dim">{where(f) || <span className="muted">no place</span>}</span> },
    { id: 'source', label: 'Where it comes from', width: 200, cell: (f) => <SourceChip source={f.source} /> },
  ]
  return (
    <>
      <div className="bar thin">
        <Seg label="Status" value={only} onChange={setOnly} options={[{ id: 'all', label: `All ${doc.findings.length}` }, ...(['fail', 'warn', 'unknown', 'pass'] as Status[]).map((s) => ({ id: s, label: `${statusWord(s)} ${n(s)}`, disabled: n(s) === 0 }))]} />
        <span className="grow" /><span className="muted small">A row opens the check in its building.</span>
      </div>
      <DataTable label="Checks" noun="check" cols={cols} rows={rows} rowKey={(f) => f.id} onRow={(f) => (f.anchor ? focusFinding(f) : toast('This check has no place to show.'))}
        empty={<Empty icon="target" title="Nothing checked yet">Each check carries its status, where it is, and where its number came from.</Empty>} />
    </>
  )
}

function ToolsTab({ doc }: { doc: Doc }) {
  type T = Doc['tools'][number]
  const cols: Col<T>[] = [
    { id: 'tool', label: 'Tool', fixed: true, width: '24%', cell: (t) => <span className="row"><ToolKey id={t.id} title={t.title} /><span className="strong trunc">{t.title}</span></span> },
    { id: 'family', label: 'Family', width: 150, cell: (t) => <span className="dim">{family(t.id).label}</span> },
    { id: 'why', label: 'Why it is here', cell: (t) => <span title={t.reason}>{t.reason || 'You added it.'}</span> },
    { id: 'by', label: 'Added by', width: 96, cell: (t) => <span className="dim">{t.by === 'agent' ? 'The agent' : 'You'}</span> },
    { id: 'runs', label: 'Runs', num: true, width: 60, cell: (t) => int(doc.runs.filter((r) => r.tool === t.id).length) },
    { id: 'x', label: '', width: 92, fixed: true, cell: (t) => <button className="btn sm" onClick={() => userOp({ op: 'tool.disable', id: t.id })}>Remove</button> },
  ]
  return (
    <>
      <div className="bar thin"><span className="grow muted small">The tools this investigation may use. The agent chose from the brief; you can add or remove any.</span><button className="btn sm" onClick={() => useUi.setState({ menu: 'tools' })}><Icon name="plus" size={12} />Add a tool</button></div>
      <DataTable label="Tools in this investigation" noun="tool" cols={cols} rows={doc.tools} rowKey={(t) => t.id} empty={<Empty icon="tool" title="No tools yet" action={<button className="btn" onClick={() => useUi.setState({ menu: 'tools' })}>Add a tool</button>} />} />
    </>
  )
}

function OverviewTab({ doc }: { doc: Doc }) {
  const open = doc.questions.filter((q) => q.answer == null)
  const notes = doc.panels.filter((p) => p.role && p.role !== 'tool')
  return (
    <div className="page"><div className="inner inv-over">
      {(!!doc.brief?.limits?.length || doc.questions.length > 0) && <section className="card">
        <header><h3 className="grow">{doc.questions.some((q) => q.answer == null) ? 'Before the work starts' : 'Before you rely on this'}</h3></header>
        <div className="body stack">
          {!!doc.brief?.limits?.length && <div className="note"><Icon name="info" size={13} /><div><b>What the tools here cannot do</b>{doc.brief.limits.map((l) => <p key={l}>{l}</p>)}</div></div>}
          {doc.questions.length > 0 && <div className="stack">{doc.questions.map((q) => <QuestionForm key={q.id} q={q} />)}</div>}
          {doc.brief && doc.questions.length > 0 && !doc.plan.length && <div className="row"><button className="btn solid" disabled={open.length > 0} onClick={() => void investigate()}>{open.length ? `${open.length} left to answer` : 'Start the investigation'}</button>{open.length > 0 && open.every((q) => q.hint != null) && <button className="btn" onClick={() => void investigate()}>Use the defaults</button>}</div>}
        </div>
      </section>}
      {notes.length > 0 ? (
        <section className="card">
          <header><h3 className="grow">What the agent concluded</h3></header>
          {notes.map((p) => <PanelView key={p.id} panel={p} />)}
        </section>
      ) : doc.plan.length > 0 && <p className="muted">The agent’s ranking and summary appear here when it finishes.</p>}
      {doc.plan.length > 0 && (
        <section className="card">
          <header><h3 className="grow">Plan</h3><span className="muted">{doc.plan.filter((s) => s.status === 'done').length} of {doc.plan.length} steps done</span></header>
          <ol className="planlist">{doc.plan.map((s, i) => <li key={s.id} data-status={s.status}><span className="n">{i + 1}</span><span className="grow">{s.label}</span><span className="muted">{int(doc.runs.filter((r) => r.step === s.id).length)} runs</span><RunState state={s.status} /></li>)}</ol>
        </section>
      )}
    </div></div>
  )
}

/** Copy a read-only link to the open investigation. The page's own address holds the workspace id, and whoever has
    that can write, so it is never what is copied. The clipboard gets a promise: Safari only allows a copy that starts
    inside the click, and the link takes a request to make. */
async function copyLink() {
  const made = shareWorkspace()
  try {
    if (typeof ClipboardItem !== 'undefined' && navigator.clipboard?.write) await navigator.clipboard.write([new ClipboardItem({ 'text/plain': made.then((m) => new Blob([m.url], { type: 'text/plain' })) })])
    else await navigator.clipboard.writeText((await made).url)
    const { expires } = await made
    toast('Read-only link copied', { description: `Whoever opens it can look at everything and change nothing.${expires ? ` It works until ${clock(Date.parse(expires))}.` : ''}` })
  } catch {
    toast.error('No link was copied', { description: await made.then(() => 'The browser did not allow the copy.', (e: Error) => e.message) })
  }
}

export function Investigation({ id }: { id: string }) {
  const doc = useWorkspace((s) => s.doc)
  const seen = useSeen((s) => s.all[id])
  const shared = useCatalog((s) => s.shared)
  const [tab, setTab] = useState('overview')
  const runOpen = useUi((s) => s.run)
  if (shared && shared.state !== 'ready') {
    return (
      <div className="page"><div className="inner">
        {shared.state === 'loading' ? <div className="stack" role="status" aria-label="Opening the shared investigation">{[52, 34, 44, 28].map((w) => <span key={w} className="sk" style={{ width: `${w}%` }} />)}</div>
          : <Empty icon="link" title="This link has expired or was revoked" action={<button className="btn" onClick={leaveShared}>Open Threshold</button>}>A read-only link works for a set number of days. Ask whoever sent it for a new one.</Empty>}
      </div></div>
    )
  }
  if (id !== doc.id) {
    return (
      <div className="page"><div className="inner">
        {/* a link to an investigation made in another browser: its id is enough to open it, if the server still has it */}
        <Empty icon="runs" title={seen?.brief || 'This investigation is not the open one'} action={seen || id.startsWith('ws_') ? <button className="btn solid" onClick={() => openSeen(id)}>Open it</button> : <button className="btn" onClick={() => (doc.id ? goInvestigation(doc.id) : newInvestigation())}>Go to the open investigation</button>}>
          {seen ? `Last changed ${ago(seen.last)}: ${seen.findings} checks made. Opening it loads the page again.` : 'It is not in this browser’s list. Opening it replaces the investigation open in this browser and loads the page again.'}
        </Empty>
      </div></div>
    )
  }
  const status = statusOf(doc)
  const failed = doc.runs.filter((r) => r.status === 'failed').length
  return (
    <div className="listpage">
      <header className="pagehead inv-head">
        <div className="ttl"><h2 className="trunc">{doc.brief?.text ?? 'Untitled investigation'}</h2><p className="muted">{shared ? `Read-only link${shared.expires ? ` · works until ${clock(Date.parse(shared.expires))}` : ''}` : seen ? `First seen here ${clock(seen.first)} · last change ${ago(seen.last)}` : 'Not started'}</p></div>
        <button className="btn" onClick={() => void copyLink()} title="Copy a link that lets someone look, not change anything"><Icon name="link" size={13} />Copy read-only link</button>
        <DownloadReport workspace={doc.id} name={doc.brief?.text} disabled={!doc.runs.some((r) => r.status === 'done')} />
        <button className="btn" aria-pressed={runOpen} onClick={() => useUi.getState().setRun(!runOpen)}><Icon name="runs" size={14} />Agent panel</button>
      </header>
      <div className="inv-stats">
        <Stats items={[
          // the run count is on the Activity tab and the time each took is in its rows: the strip keeps what a person asks first
          { label: 'Status', value: <RunState state={STATUS[status].state}>{STATUS[status].label}</RunState> },
          { label: 'Steps done', value: doc.plan.length ? `${doc.plan.filter((s) => s.status === 'done').length} of ${doc.plan.length}` : '–' },
          { label: 'Checks made', value: <>{int(doc.findings.length)}{failed > 0 && <span className="st" data-status="fail" title="Tool runs that failed; see Activity">{failed} failed</span>}</> },
          { label: 'Kept', value: int(doc.shortlist.length) },
        ]} />
      </div>
      <Tabs.Root className="tabpage" value={tab} onValueChange={(v) => setTab(String(v))}>
        <Tabs.List className="tabs">
          <Tabs.Tab value="overview">Overview</Tabs.Tab>
          <Tabs.Tab value="findings">Checks<span className="count">{doc.findings.length}</span></Tabs.Tab>
          <Tabs.Tab value="runs">Activity<span className="count">{doc.runs.length}</span></Tabs.Tab>
          <Tabs.Tab value="tools">Tools<span className="count">{doc.tools.length}</span></Tabs.Tab>
          <Tabs.Tab value="learned">Learned<span className="count">{doc.prefs.length}</span></Tabs.Tab>
          <Tabs.Tab value="kept">Kept<span className="count">{doc.shortlist.length}</span></Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="overview" className="tabbody"><OverviewTab doc={doc} /></Tabs.Panel>
        <Tabs.Panel value="runs" className="tabbody"><Runs doc={doc} /></Tabs.Panel>
        <Tabs.Panel value="findings" className="tabbody"><Findings doc={doc} /></Tabs.Panel>
        <Tabs.Panel value="tools" className="tabbody"><ToolsTab doc={doc} /></Tabs.Panel>
        <Tabs.Panel value="learned" className="tabbody"><div className="page"><div className="inner narrow"><section className="card"><header><h3 className="grow">What has been learned</h3><span className="muted">Each item says where it came from and can be undone</span></header><Learned /></section></div></div></Tabs.Panel>
        <Tabs.Panel value="kept" className="tabbody">
          {doc.shortlist.length === 0 ? <Empty icon="keep" title="Nothing kept in this investigation">Keep a scan from its page, or let the agent shortlist.</Empty> : (
            <div className="page"><div className="inner narrow"><ul className="rows">{doc.shortlist.map((s) => <li key={s.sid}><button type="button" onClick={() => goScan(s.sid)}><Icon name="building" /><span className="grow"><span className="trunc">{s.name}</span><span className="s">{[s.address.split(',')[0], s.note].filter(Boolean).join(' · ')}</span></span><Icon name="go" size={12} /></button></li>)}</ul></div></div>
          )}
        </Tabs.Panel>
      </Tabs.Root>
    </div>
  )
}
