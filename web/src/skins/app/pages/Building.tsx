import { Suspense, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { Slider } from '@base-ui/react/slider'
import { Tabs } from '@base-ui/react/tabs'
import {
  Scene, SceneBoundary, fetchRecord, focusFinding, panoFace, runTool, useBuildingView, useBuildings, useWorkspace,
  type Doc, type SceneCamera, type SceneMode, type SceneProps, type SceneState, type SceneView, type ScanPlan, type Status,
} from '../../../core/index.ts'
import { PanelView } from '../blocks/blocks.tsx'
import { Edge, Fill, Pane, Split } from '../design/split.tsx'
import { Copy, Empty, Icon, IconBtn, Menu, MenuBtn, RunState, Seg, SourceChip, St, Stats, StatusGlyph, ToolKey, type IconName } from '../design/ui.tsx'
import { dur, int, plural } from '../lib/format.ts'
import { facts } from '../lib/pending.ts'
import { go, goScan } from '../lib/place.ts'
import { tally, worstVerdict } from '../lib/verdict.ts'
import { FAMILIES, useTools, type ToolInfo } from '../lib/tools.ts'
import { useScheme } from '../shell/theme.ts'
import { startTool } from '../shell/StartTool.tsx'
import { DownloadReport } from '../report/DownloadReport.tsx'
import { useIsPhone, useUi } from '../shell/store.ts'
import { CompareScenes, WhatIfMenu, useWhatIf } from '../whatif/WhatIf.tsx'

const MODES: { id: SceneMode; label: string; icon: IconName; none: string }[] = [
  { id: 'dollhouse', label: '3D', icon: 'cube', none: '' }, { id: 'plan', label: 'Plan', icon: 'plan', none: '' },
  { id: 'pano', label: 'Inside', icon: 'walk', none: 'This scan has no 360° positions' }, { id: 'splat', label: 'Drone', icon: 'drone', none: 'No drone capture for this building' },
]
const WORST: Record<Status, number> = { fail: 0, warn: 1, unknown: 2, pass: 3 }
type F = Doc['findings'][number]
/** What the scene reports about a show (flood, fire, tour) while it plays, and what the toolbar sets to drive it. */
type ShowState = NonNullable<Parameters<NonNullable<SceneProps['onShow']>>[0]>
type ShowSpec = NonNullable<SceneView['show']>
type ShowKind = ShowSpec['kind']
const SHOWS: { id: ShowKind; label: string; icon: IconName; title: string }[] = [
  { id: 'flood', label: 'Flood', icon: 'drop', title: 'Hurricane Harvey\'s water at this house, hour by hour' },
  { id: 'fire', label: 'Fire', icon: 'fire', title: 'A fire in these rooms and its smoke, minute by minute' },
  { id: 'tour', label: 'Tour', icon: 'walk', title: 'A camera tour of what was found here, read aloud' },
]

/** The transport of whatever is playing on the building: play and pause, the time slider, the clock. It keeps the
    playhead's state itself (the scene hands each step to `sink`), so a step redraws this row and not the page. */
function Transport({ spec, sink, set, seek, close }: { spec: ShowSpec; sink: React.RefObject<((s: ShowState | null) => void) | null>; set: (patch: Partial<ShowSpec>) => void; seek: (step: number) => void; close: () => void }) {
  const [got, setShow] = useState<ShowState | null>(null)
  useEffect(() => { sink.current = setShow; return () => { sink.current = null } }, [sink])
  const show = got?.kind === spec.kind ? got : null, ready = show?.status === 'ready'
  return (
    <>
      <button type="button" className="btn sm" style={{ minWidth: 62 }} disabled={!ready} onClick={() => set({ playing: !spec.playing })}>{spec.playing ? 'Pause' : <><Icon name="play" size={12} />Play</>}</button>
      {spec.kind === 'tour' && <>
        <IconBtn icon="left" label="Previous stop" className="btn icon quiet sm" disabled={!show || show.step <= 0} onClick={() => seek((show?.step ?? 0) - 1)} />
        <IconBtn icon="right" label="Next stop" className="btn icon quiet sm" disabled={!show || show.step >= show.steps} onClick={() => seek((show?.step ?? 0) + 1)} />
      </>}
      <Slider.Root style={{ flex: '1 1 160px', minWidth: 120 }} value={show?.step ?? 0} min={0} max={Math.max(1, show?.steps ?? 1)} step={1} disabled={!ready} onValueChange={(n) => seek(n as number)}
        aria-label={spec.kind === 'flood' ? 'Time in the storm' : spec.kind === 'fire' ? 'Time since the fire started' : 'Stop of the tour'}>
        <Slider.Control className="slider"><Slider.Track className="track"><Slider.Indicator className="range" /><Slider.Thumb className="thumb" /></Slider.Track></Slider.Control>
      </Slider.Root>
      <span className="num small" style={{ minWidth: spec.kind === 'flood' ? 118 : 44, textAlign: 'right' }}>{show?.clock}</span>
      {spec.kind === 'fire' && <button type="button" className="btn sm quiet" aria-pressed={spec.doors === 'closed'} title="Run the same fire with the bedroom doors closed" onClick={() => set({ doors: spec.doors === 'closed' ? 'open' : 'closed' })}>Doors {spec.doors === 'closed' ? 'closed' : 'open'}</button>}
      {spec.kind === 'tour' && <button type="button" className="btn sm quiet" aria-pressed={spec.voice !== false} title="Read each stop aloud" onClick={() => set({ voice: spec.voice === false })}>Voice {spec.voice === false ? 'off' : 'on'}</button>}
      <IconBtn icon="close" label="Stop and close" className="btn icon quiet sm" onClick={close} />
    </>
  )
}

/** A menu of every tool: the investigation's own first, then by family. One that needs more than this scan opens
    its form (marked with an ellipsis), the rest run at once. */
export function RunToolMenu({ sid, trigger }: { sid: string; trigger: React.ReactElement }) {
  const tools = useTools().filter((t) => !t.planned)
  const mine = useWorkspace((s) => s.doc.tools)
  const item = (t: ToolInfo) => <Menu.Item key={t.id} onClick={() => startTool(t, sid)}><ToolKey id={t.id} title={t.title} />{t.title}{t.form && '…'}{t.slow && <small>slow</small>}</Menu.Item>
  const own = tools.filter((t) => mine.some((m) => m.id === t.id))
  return (
    <MenuBtn align="end" trigger={trigger}>
      {own.length > 0 && <><div className="mh">In this investigation</div>{own.map(item)}<hr /></>}
      <div className="mh">All tools, by family</div>
      {FAMILIES.map((f) => {
        const list = tools.filter((t) => t.family === f.id)
        if (!list.length) return null
        return (
          <Menu.SubmenuRoot key={f.id}>
            <Menu.SubmenuTrigger><Icon name={f.icon} />{f.label}<small>{list.length}</small><Icon name="right" size={11} /></Menu.SubmenuTrigger>
            <Menu.Portal><Menu.Positioner sideOffset={2} alignOffset={-4} style={{ zIndex: 61 }}><Menu.Popup className="menu">{list.map(item)}</Menu.Popup></Menu.Positioner></Menu.Portal>
          </Menu.SubmenuRoot>
        )
      })}
      <hr />
      <Menu.Item onClick={() => go('tools', { app_sid: sid })}><Icon name="tool" />Browse the tool catalogue</Menu.Item>
    </MenuBtn>
  )
}

function Summary({ plan, sid, panels, findings, onResults }: { plan: ScanPlan; sid: string; panels: Doc['panels']; findings: F[]; onResults: (panel: string) => void }) {
  const b = useBuildings((s) => s.all.find((x) => x.scans.some((y) => y.sid === sid)))
  const q = plan.quality
  const can: [string, boolean | undefined, string?][] = q ? [
    ['Walls', q.walls, q.walls_source === 'dxf' ? 'recovered from the drawing, not measured' : q.walls_confidence ? `${q.walls_confidence} confidence` : undefined],
    ['Room outlines', q.polygons], ['Doors and windows', q.openings], ['Room names', q.labels], ['Position on the map checked', q.georef],
  ] : []
  const verdict = worstVerdict(panels)
  // what a phone on site can settle: a check the scan could not measure, or one it was unsure of
  const open = findings.filter((f) => f.status === 'unknown' || f.status === 'warn').length
  return (
    <div className="stack ins-pad">
      {/* First: the verdict, in the words of the tool that gave it, and what to do about it. */}
      {verdict ? (
        <section className="sum-verdict" aria-label="Verdict">
          <St status={verdict.status} />
          <p className="text">{verdict.text}</p>
          <p className="muted small">{panels.length === 1 ? verdict.title : `${verdict.title} · ${panels.length} results: ${tally(panels)}`}</p>
          <div className="row wrap">
            <button type="button" className="btn solid" onClick={() => onResults(verdict.panel)}>{verdict.status === 'pass' ? 'See the checks' : 'See what was checked'}</button>
            {open > 0 && <button type="button" className="btn" onClick={() => window.dispatchEvent(new Event('threshold:phone'))} title="Pair a phone and settle on site what the scan could not measure"><Icon name="camera" size={13} />Check on site</button>}
            <button type="button" className="btn quiet" onClick={() => useUi.getState().setRun(true)}>Ask the agent</button>
          </div>
        </section>
      ) : (
        <section className="sum-verdict" aria-label="Verdict">
          <p className="text">Nothing has been checked here yet.</p>
          <p className="muted small">Pick a tool to measure this building, or ask the agent in your own words.</p>
          <div className="row wrap">
            <RunToolMenu sid={sid} trigger={<button type="button" className="btn solid"><Icon name="play" size={13} />Run a tool<Icon name="down" size={11} /></button>} />
            <button type="button" className="btn quiet" onClick={() => useUi.getState().setRun(true)}>Ask the agent</button>
          </div>
        </section>
      )}
      {panels.length > 1 && (
        <section className="ins-sec">
          <h3>Results</h3>
          <ul className="rows">
            {panels.map((p) => {
              const v = p.blocks.find((x) => x.type === 'VerdictHeader')
              return <li key={p.id}><button type="button" onClick={() => onResults(p.id)}><ToolKey id={p.tool} title={p.title} /><span className="grow trunc">{p.title}</span>{v && v.type === 'VerdictHeader' && <St status={v.status} />}</button></li>
            })}
          </ul>
        </section>
      )}
      {/* Everything about the scan itself: there when wanted, out of the way of the verdict. */}
      <details className="ins-fold" open={panels.length === 0 || undefined}>
        <summary><Icon name="right" size={11} />About this scan</summary>
        <div className="stack">
          <Stats items={[
        { label: 'Rooms', value: int(plan.rooms.length) }, { label: 'Doorways', value: int(plan.openings.filter((o) => o.type === 'doorway').length) },
        { label: 'Floors', value: int(plan.floors.length) }, { label: '360° positions', value: int(plan.panos.length) },
          ]} />
      {can.length > 0 && (
        <section className="ins-sec">
          <h3>What this scan can answer</h3>
          <ul className="can">
            {can.map(([label, ok, note]) => <li key={label}><StatusGlyph status={ok ? 'pass' : 'unknown'} /><span className="grow">{label}{note && <span className="muted">, {note}</span>}</span><span className="muted">{ok ? 'yes' : 'no'}</span></li>)}
            <li><StatusGlyph status={plan.has.splat ? 'pass' : 'unknown'} /><span className="grow">Drone capture</span><span className="muted">{plan.has.splat ? 'yes' : 'no'}</span></li>
            <li><StatusGlyph status={plan.has.defurnished ? 'pass' : 'unknown'} /><span className="grow">Empty-room photos</span><span className="muted">{plan.has.defurnished ? 'yes' : 'no'}</span></li>
          </ul>
          {q?.notes?.map((n) => <p key={n} className="muted small">{n}</p>)}
        </section>
      )}
      <section className="ins-sec">
        <h3>Details</h3>
        <dl className="kv">
          <dt>Address</dt><dd>{plan.address || 'Not recorded'}</dd>
          {plan.city && <><dt>City</dt><dd>{plan.city}</dd></>}
          <dt>Kind</dt><dd style={{ textTransform: 'capitalize' }}>{plan.segment || 'Not recorded'}</dd>
          <dt>Scan id</dt><dd className="row"><span className="num">{sid}</span><Copy text={sid} label="Copy the scan id" /></dd>
          {plan.geo && <><dt>Position</dt><dd className="num">{plan.geo.lat.toFixed(5)}, {plan.geo.lon.toFixed(5)}</dd></>}
        </dl>
      </section>
        </div>
      </details>
      {b && b.scans.length > 1 && (
        <details className="ins-fold">
          <summary><Icon name="right" size={11} />Other scans at this address<span className="count">{b.scans.length - 1}</span></summary>
          <ul className="rows">{b.scans.filter((x) => x.sid !== sid).slice(0, 30).map((x) => <li key={x.sid}><button type="button" onClick={() => goScan(x.sid)}><Icon name="building" /><span className="grow trunc">{x.name}</span><span className="muted">{plural(x.rooms, 'room')}</span></button></li>)}</ul>
        </details>
      )}
    </div>
  )
}

function Evidence({ findings }: { findings: F[] }) {
  const current = useWorkspace((s) => s.doc.camera?.finding)
  const tools = useWorkspace((s) => s.doc.tools)
  if (!findings.length) return <Empty icon="target" title="No evidence on this scan yet">Each thing a tool checks is listed here with its photo, and can be shown in the building.</Empty>
  return (
    <ul className="evid">
      {findings.map((f) => {
        const m = f.media?.find((x) => x.kind === 'pano'), [a, b, c] = m?.ref.split('/') ?? []
        return (
          <li key={f.id}>
            <button type="button" disabled={!f.anchor} aria-current={current === f.id || undefined} onClick={() => focusFinding(f, { stay: true })} title={f.anchor ? 'Show this in the building' : 'This finding has no place to show'}>
              {m && b && <img src={panoFace(a, b, c ? Number(c) : 1)} alt="" loading="lazy" width={72} height={54} onError={(e) => { e.currentTarget.style.display = 'none' }} />}
              <span className="grow">
                <span className="t"><StatusGlyph status={f.status} />{f.title}</span>
                {f.detail && <span className="s">{f.detail}</span>}
                <span className="m"><span className="muted">{tools.find((t) => t.id === f.tool)?.title ?? f.tool}</span><SourceChip source={f.source} plain /></span>
              </span>
            </button>
          </li>
        )
      })}
    </ul>
  )
}

const words = (k: string) => k.replace(/_/g, ' ').replace(/([a-z])([A-Z])/g, '$1 $2').replace(/^./, (c) => c.toUpperCase())
const show = (v: unknown) => (v === true ? 'Yes' : v === false ? 'No' : String(v))
/** Leaves of a record, as rows. Long text and lists of objects are left to their own section. */
function leaves(o: unknown, path: string[] = [], out: [string, string][] = []): [string, string][] {
  if (o == null || out.length > 400) return out
  if (Array.isArray(o)) { if (o.length && o.every((x) => typeof x !== 'object')) out.push([path.map(words).join(' · '), o.join(', ')]); else o.slice(0, 12).forEach((x, i) => leaves(x, [...path, String(i + 1)], out)) }
  else if (typeof o === 'object') for (const [k, v] of Object.entries(o)) leaves(v, [...path, k], out)
  else if (o !== '') out.push([path.map(words).join(' · '), show(o)])
  return out
}
function Record({ sid }: { sid: string }) {
  const [rec, setRec] = useState<Record<string, unknown> | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [find, setFind] = useState('')
  useEffect(() => { let on = true; setRec(null); setErr(null); fetchRecord(sid).then((r) => on && setRec(r), (e: Error) => on && setErr(e.message)); return () => { on = false } }, [sid])
  const claims = (rec?.claims ?? {}) as Record<string, { value: unknown; unit: string | null; path: string }>
  const sections = useMemo(() => Object.entries(rec ?? {}).filter(([k]) => !['sid', 'claims', 'trimmed', 'match'].includes(k)).map(([k, v]) => [k, leaves(v)] as const).filter(([, rows]) => rows.length), [rec])
  if (err) return <Empty icon="record" title="No record for this scan">{err === 'Nothing there.' ? 'The scan is not matched to a property record or a listing.' : err}</Empty>
  if (!rec) return <div className="ins-pad stack">{[70, 40, 55, 35, 60].map((w, i) => <span key={i} className="sk" style={{ width: `${w}%` }} />)}</div>
  const hit = (s: string) => !find || s.toLowerCase().includes(find.toLowerCase())
  return (
    <div className="stack ins-pad">
      <section className="ins-sec">
        <h3>What the record says <SourceChip source={{ layer: 'costar', method: 'lookup', confidence: 'high' }} /></h3>
        {Object.keys(claims).length === 0 ? <p className="muted">The record makes no claim a scan can check.</p> : (
          <dl className="kv">
            {Object.entries(claims).map(([k, c]) => <div key={k} style={{ display: 'contents' }}><dt title={c.path}>{words(k)}</dt><dd>{c.value == null ? <span className="muted">not stated</span> : <><span className={typeof c.value === 'number' ? 'num' : undefined}>{show(c.value)}</span>{c.unit && <span className="muted"> {c.unit}</span>}</>}</dd></div>)}
          </dl>
        )}
        <p className="muted small">Run “Record versus reality” to check these against the scan.</p>
      </section>
      <section className="ins-sec">
        <h3>Full record</h3>
        <label className="inset"><Icon name="search" size={13} /><input className="field" value={find} onChange={(e) => setFind(e.target.value)} placeholder="Find a field" aria-label="Find a field in the record" /></label>
        {sections.map(([k, rows]) => {
          const shown = rows.filter(([a, b]) => hit(a) || hit(b))
          if (!shown.length) return null
          return (
            <details key={k} className="recsec" open={!!find || undefined}>
              <summary><Icon name="right" size={11} />{words(k)}<span className="count">{shown.length}</span></summary>
              <dl className="kv">{shown.map(([a, b], i) => <div key={i} style={{ display: 'contents' }}><dt>{a}</dt><dd>{b.length > 220 ? b.slice(0, 220) + '…' : b}</dd></div>)}</dl>
            </details>
          )
        })}
      </section>
    </div>
  )
}

function History({ sid, runs }: { sid: string; runs: Doc['runs'] }) {
  const tools = useWorkspace((s) => s.doc.tools), panels = useWorkspace((s) => s.doc.panels)
  return (
    <div className="stack ins-pad">
      <section className="ins-sec">
        <h3>Runs on this scan, in this investigation <span className="count">{runs.length}</span></h3>
        {!runs.length ? <p className="muted">Nothing has run on this scan in the open investigation.</p> : (
          <ul className="rows tall">
            {runs.map((r) => {
              const p = panels.find((x) => x.run === r.id), title = tools.find((t) => t.id === r.tool)?.title ?? r.label.split(' · ')[0]
              return (
                <li key={r.id}><button type="button" disabled={!p} onClick={() => p && useUi.setState({ panel: p.id })}>
                  <ToolKey id={r.tool} title={title} />
                  <span className="grow"><span className="trunc">{title}</span>{r.summary && <span className="s">{r.summary}</span>}</span>
                  {r.status === 'done' ? <span className="num muted">{dur(r.ms)}</span> : <RunState state={r.status} />}
                </button></li>
              )
            })}
          </ul>
        )}
      </section>
      <section className="ins-sec">
        <h3>Measured facts over time</h3>
        {facts.fetchFactHistory ? <FactHistory sid={sid} /> : <p className="note"><Icon name="info" size={13} /><span>Not connected yet. Every value a tool measures on this scan is kept in the facts database with its date, and this tab will list them once the app can read it.</span></p>}
      </section>
    </div>
  )
}
function FactHistory({ sid }: { sid: string }) {
  const [rows, setRows] = useState<Record<string, unknown>[] | null>(null)
  useEffect(() => { let on = true; facts.fetchFactHistory!(sid).then((r) => on && setRows(r), () => on && setRows([])); return () => { on = false } }, [sid])
  if (!rows) return <span className="sk" style={{ width: '60%' }} />
  if (!rows.length) return <p className="muted">No facts recorded for this scan yet.</p>
  return <dl className="kv">{rows.slice(0, 60).map((r, i) => <div key={i} style={{ display: 'contents' }}><dt>{String(r.field ?? '')}</dt><dd className="num">{String(r.value ?? '')} {String(r.unit ?? '')}</dd></div>)}</dl>
}

export function Building({ sid }: { sid: string }) {
  const doc = useWorkspace((s) => s.doc)
  const scheme = useScheme()
  const phone = useIsPhone()
  const runs = useMemo(() => doc.runs.filter((r) => r.sid === sid), [doc.runs, sid])
  const panels = useMemo(() => doc.panels.filter((p) => p.sid === sid), [doc.panels, sid])
  const citywide = useMemo(() => doc.panels.filter((p) => !p.sid && (p.role ?? 'tool') === 'tool'), [doc.panels])
  const focused = doc.camera?.finding ? doc.findings.find((f) => f.id === doc.camera!.finding)?.tool : undefined
  // Which tools draw on the building. Left alone, it is the one result in view: the tool of the focused finding, else
  // the latest result. Five tools drawing at once cannot be read.
  const drawn = useMemo(() => [...new Set(doc.overlays.filter((o) => !o.sid || o.sid === sid).map((o) => o.tool))], [doc.overlays, sid])
  const [pick, setPick] = useState<string[] | null>(null)
  // The result in view: the one the person opened, else the focused finding's, else the latest. null is "none open".
  const [chosen, setChosen] = useState<string | null | undefined>(undefined)
  const inView = chosen !== undefined ? panels.find((p) => p.id === chosen) ?? null : (focused && panels.findLast((p) => p.tool === focused)) || panels.at(-1) || null
  // nothing open, or a result that draws nothing: the plain building. Every tool at once is the Overlays menu's "Show all".
  const on = pick ?? (inView && drawn.includes(inView.tool) ? [inView.tool] : [])
  const v = useBuildingView(sid, on.length === drawn.length ? undefined : { tools: on })
  const b = useBuildings((s) => s.all.find((x) => x.scans.some((y) => y.sid === sid)))
  // This look's starting view of a scan: walls cut at 1.4 m, so the rooms, their photographed floors and the pins on
  // them show from outside (whole walls hide all three). A cut the person then sets, "full" included, stays.
  // The frame keeps the building left of the scene's cut control. Its negative edges say the ground may run off that
  // side: with no frame the scene's fit crops a room in a narrow picture, with a plain one the building sits small.
  useEffect(() => { v.setView((x) => ({ ...x, cut: x.cut === undefined ? 1.4 : x.cut, frame: { top: -20, right: 20, bottom: -20, left: -100 } })) }, []) // eslint-disable-line react-hooks/exhaustive-deps
  const [interior, setInterior] = useState(false) // this scan has an interior splat (the scene finds out)
  // The photoreal view on its site is this look's opening view of a building, when it is ready the moment the
  // building opens. If it is still being made, the building opens as measured, the toolbar says quietly how far
  // along it is, and the person switches when they like: what they are looking at never changes under them.
  const [baked, setBake] = useState<{ sid: string; colour: SceneState['scan']['colour']; progress: number }>({ sid, colour: 'unknown', progress: 0 })
  const bake = baked.sid === sid ? baked : { colour: 'unknown' as const, progress: 0 } // what is known of this scan's bake
  const opened = useRef<string | null>(null), chose = useRef<string | null>(null) // the scan whose opening view is settled; the scan on which the person picked a view themselves
  const onScene = (s: SceneState) => {
    setInterior(s.interior.status !== 'none' && s.interior.status !== 'unknown')
    setBake((b) => (b.sid === sid && b.colour === s.scan.colour && b.progress === s.scan.progress ? b : { sid, colour: s.scan.colour, progress: s.scan.progress }))
    if (s.scan.colour === 'unknown' || opened.current === sid) return
    opened.current = sid
    const plan = v.plan
    if (s.scan.colour !== 'ready' || chose.current === sid || !plan) return
    // on its site only where the placing can be trusted: fitted to the aerial footprint, or tied to its own drone capture
    const sited = (plan as { geo?: { lat?: number | null } | null }).geo?.lat != null && (!!plan.quality?.georef || plan.has.splat)
    v.setView((x) => ({ ...x, surface: 'scan', env: sited ? 'aerial' : x.env }))
  }
  // What if: the renovated plan beside this one. A new what-if result opens the comparison; the person can close it.
  const wi = useWhatIf(sid)
  const [compare, setCompare] = useState(false)
  const camera = useRef<((c: SceneCamera) => void) | null>(null)
  const showCompare = compare && !!wi.after
  useEffect(() => { if (wi.after && performance.now() - born.current > 2500) setCompare(true) }, [wi.after])
  const kept = useRef<{ surface: typeof v.view.surface; env: typeof v.view.env; measures: typeof v.view.measures; frame: typeof v.view.frame; pick: string[] | null } | null>(null)
  useEffect(() => {
    if (!showCompare) return
    kept.current = { surface: v.view.surface, env: v.view.env, measures: v.view.measures, frame: v.view.frame, pick } // given back on close
    setPick(['renovate']) // both sides mark the same edits
    v.setView((x) => ({ ...x, surface: 'model', env: 'studio', measures: true, frame: { top: -20, right: 20, bottom: -20, left: 20 } }))
    if (v.mode !== 'dollhouse' && v.mode !== 'plan') v.setMode('dollhouse')
    const t = setTimeout(v.stepBack, 400) // the scene is half as wide now: frame the building again
    return () => {
      clearTimeout(t)
      const k = kept.current
      if (!k) return
      setPick(k.pick)
      v.setView((x) => ({ ...x, surface: k.surface, env: k.env, measures: k.measures, frame: k.frame }))
      setTimeout(v.stepBack, 400)
    }
  }, [showCompare]) // eslint-disable-line react-hooks/exhaustive-deps
  const [picked, setTab] = useState<string | null>(null)
  const tab = picked ?? 'overview' // until the person picks: the summary, which leads with the verdict

  const findings = useMemo(() => {
    const mine = new Set(runs.map((r) => r.id))
    return doc.findings.filter((f) => (f.anchor && 'sid' in f.anchor && f.anchor.sid === sid) || (f.run && mine.has(f.run))).sort((x, y) => WORST[x.status] - WORST[y.status])
  }, [doc.findings, runs, sid])
  const working = runs.filter((r) => r.status === 'running' && !panels.some((p) => p.run === r.id))
  // a run that failed leaves no result: it stays listed here until the same tool runs again on this scan
  const failed = runs.filter((r, i) => r.status === 'failed' && !runs.slice(i + 1).some((l) => l.tool === r.tool))
  const catalogue = useTools()

  // A result that arrives while the person is on this scan is shown; so is the result of a focused finding.
  const count = panels.length, last = panels.at(-1)
  const mine = !!last && !doc.runs.find((r) => r.id === last.run)?.step
  useEffect(() => { setChosen(undefined) }, [count, doc.camera?.finding]) // a new result, or a finding focused: that is the one in view
  const arrived = `${count}:${last?.run ?? ''}`, seen = useRef(arrived), born = useRef(performance.now())
  useEffect(() => {
    if (arrived === seen.current) return
    seen.current = arrived
    // shortcut: results that show up in the first moments are the saved document loading, not a new run; a link to a
    // finding must keep its close-up. Upgrade to a "this run just finished" signal from core if one appears.
    if (!count || performance.now() - born.current < 2500) return
    setTab('results')
    // a tool the person ran: the server's camera closes in on its worst finding, so frame the whole building again
    if (mine && last?.tool !== 'tour') { const t = setTimeout(v.stepBack, 900); return () => clearTimeout(t) }
  }, [arrived]) // eslint-disable-line react-hooks/exhaustive-deps
  // a run that fails while the person is here is shown too: its reason is on the Results tab
  const fails = failed.length, hadFails = useRef(fails)
  useEffect(() => { if (fails > hadFails.current && performance.now() - born.current > 2500) setTab('results'); hadFails.current = fails }, [fails])

  // ---- shows: something played on the building. The scene plays it; this toolbar starts it and holds the transport.
  const sink = useRef<((s: ShowState | null) => void) | null>(null)
  const spec = v.view.show ?? null
  const held = useRef<Partial<SceneView> | null>(null)
  // the latest Tour run's findings are the tour's stops, in order; each line is that finding's own words
  const stops = useMemo(() => {
    const all = doc.findings.filter((f) => f.tool === 'tour' && f.anchor && 'sid' in f.anchor && f.anchor.sid === sid), run = all.at(-1)?.run
    return all.filter((f) => f.run === run).sort((a, b) => a.id.localeCompare(b.id)).map((f) => ({ id: f.id, title: f.title, line: f.detail ?? f.title, status: f.status, anchor: f.anchor })) as NonNullable<ShowSpec['stops']>
  }, [doc.findings, sid])
  const play = (kind: ShowKind | null) => {
    chose.current = sid
    if (kind === 'tour' && !stops.length && spec?.kind !== 'tour') { // no tour yet: make one from what the workspace has found here (or let the tool gather)
      const evidence = findings.filter((f) => f.tool !== 'tour' && f.anchor).map(({ id, title, status, detail, anchor, tool, source, media }) => ({ id, title, status, detail: detail ?? '', anchor, tool, source, media: media ?? [] }))
      void runTool('tour', { question: doc.brief?.text, findings: evidence.length ? evidence : undefined }, sid)
      return
    }
    // while something plays, only its own drawing is on the building (a tour's path); the person's choice comes back after
    setPick(kind && spec?.kind !== kind ? (kind === 'tour' && drawn.includes('tour') ? ['tour'] : []) : null)
    const x: SceneView = { ...v.view, ...held.current } // the view the person had before a show set its own
    held.current = null
    if (!kind || spec?.kind === kind) { v.setView({ ...x, show: null }); return }
    const placed = (v.plan as { geo?: { lat?: number | null } | null } | null)?.geo?.lat != null, photo = bake.colour === 'ready'
    held.current = { cut: x.cut, env: x.env, pose: x.pose, surface: x.surface, frame: x.frame }
    // each show in the view it reads best in: the flood on its site; the fire in the house alone with whole walls,
    // seen from low enough to look under the smoke
    const beside = { top: -20, right: 20, bottom: -20, left: 150 } // the show's own panel stands at the left of the picture: the building keeps clear of it
    const look: Partial<SceneView> = kind === 'flood' ? { env: placed ? 'aerial' : x.env, frame: beside } : kind === 'fire' ? { env: 'studio', cut: photo ? null : x.cut, pose: { pitch: 62 }, frame: beside } : {}
    v.setView({ ...x, mode: 'dollhouse', surface: photo ? 'scan' : x.surface, ...look, show: kind === 'tour' ? { kind, playing: true, stops } : { kind, playing: true } })
  }
  useEffect(() => { held.current = null }, [sid]) // another scan starts with nothing to put back
  const setSpec = (patch: Partial<ShowSpec>) => v.setView((x) => (x.show ? { ...x, show: { ...x.show, ...patch } } : x))
  const seek = (step: number) => v.setView((x) => (x.show ? { ...x, show: { ...x.show, seek: { n: (x.show.seek?.n ?? 0) + 1, step } } } : x))
  const onShow = (st: ShowState | null) => {
    sink.current?.(st)
    if (st && !st.playing) v.setView((x) => (x.show?.playing && x.show.kind === st.kind ? { ...x, show: { ...x.show, playing: false } } : x)) // it ended, or the person took the camera
  }
  // a tour that arrives while the person is here (they asked for it, or the agent ended its turn with one) plays
  const stopsKey = stops.map((x) => x.id + x.line).join('|'), toured = useRef(stopsKey)
  const busy = doc.runs.some((r) => r.status === 'running') || doc.plan.some((x) => x.status === 'active') // an agent turn still moves the camera: the tour waits for it to end
  useEffect(() => {
    if (stopsKey === toured.current || busy) return
    toured.current = stopsKey
    if (!stops.length || performance.now() - born.current < 2500) return
    setPick(['tour'])
    v.setView((x) => ({ ...x, mode: 'dollhouse', surface: bake.colour === 'ready' ? 'scan' : x.surface, show: { kind: 'tour', playing: true, stops } }))
  }, [stopsKey, busy]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement
      if (e.metaKey || e.ctrlKey || e.altKey || /^(input|textarea|select)$/i.test(t.tagName) || document.querySelector('[cmdk-root], [role="dialog"], [role="menu"]')) return
      const m = MODES[Number(e.key) - 1]
      if (m && v.modes.includes(m.id)) v.setMode(m.id)
      else if (e.key.toLowerCase() === 'k') v.toggleKeep()
    }
    window.addEventListener('keydown', key)
    return () => window.removeEventListener('keydown', key)
  })

  const i = b ? b.scans.findIndex((x) => x.sid === sid) : -1
  const verdict = worstVerdict(panels)
  const tools = doc.tools
  const fault = (text: string): ReactNode => <div className="scene-state"><Empty icon="warn" title={text} action={<button className="btn" onClick={v.retry}>Try again</button>} /></div>

  return (
    <div className="bld">
      <header className="pagehead">
        <IconBtn icon="back" label="Back to the map" onClick={() => go('explore', { city: b?.metro ?? undefined, b: b?.id })} />
        <div className="ttl">
          <h2 className="row">{v.plan ? <span className="trunc">{v.plan.name}</span> : v.error ? 'Scan not available' : <span className="sk" style={{ width: 180, display: 'inline-block' }} />}{verdict && <St status={verdict.status} />}</h2>
          <p className="muted trunc">{v.plan ? [(v.plan.address ?? '').split(',')[0], v.plan.city, plural(v.plan.rooms.length, 'room'), plural(v.plan.floors.length, 'floor')].filter((x) => x && x !== v.plan!.name).join(' · ') : ' '}</p>
        </div>
        {b && b.scans.length > 1 && (
          <div className="pager" role="group" aria-label="Scans at this address">
            <IconBtn icon="left" label="Previous scan at this address" disabled={i <= 0} onClick={() => goScan(b.scans[i - 1].sid)} />
            <span className="muted">{i + 1} of {b.scans.length}</span>
            <IconBtn icon="right" label="Next scan at this address" disabled={i >= b.scans.length - 1} onClick={() => goScan(b.scans[i + 1].sid)} />
          </div>
        )}
        {v.plan && <WhatIfMenu sid={sid} plan={v.plan} />}
        <RunToolMenu sid={sid} trigger={<button type="button" className="btn" disabled={!v.plan}><Icon name="play" size={13} />Run a tool<Icon name="down" size={11} /></button>} />
        <button type="button" className="btn quiet" aria-pressed={v.kept} onClick={v.toggleKeep} disabled={!v.plan} title="Keep this scan in Buildings ( K )"><Icon name="keep" size={14} />{v.kept ? 'Kept' : 'Keep'}</button>
        <DownloadReport workspace={doc.id} sid={sid} name={v.plan?.name} disabled={!runs.some((r) => r.status === 'done')} />
      </header>

      <Split className="bld-body" off={phone}>
        <Fill id="scene" min={320}>
        <section className="work" aria-label="Building view">
          <div className="worktools">
            <Seg label="View" value={v.mode} onChange={v.setMode} options={MODES.map((m) => ({ id: m.id, label: m.label, icon: m.icon, disabled: !v.modes.includes(m.id), title: v.plan && !v.modes.includes(m.id) ? m.none : undefined }))} />
            {/* What the building is drawn from and what stands round it, behind one button. These edit the scene's view; the scene's own copy of the controls is switched off below. */}
            {v.plan && (v.mode === 'dollhouse' || v.mode === 'splat') && (() => {
              const placed = (v.plan as { geo?: { lat?: number | null } | null }).geo?.lat != null, doll = v.mode === 'dollhouse'
              const surface = v.view.surface === 'splat' && !interior ? 'scan' : v.view.surface ?? 'model'
              // one button says how the building looks now and opens the choices: what it is drawn from, what stands round it
              const lookSaid = [doll ? (surface === 'model' ? 'Measured' : surface === 'scan' ? 'Photoreal' : 'Splat') : 'Drone capture', v.view.env === 'aerial' ? 'on its site' : null].filter(Boolean).join(', ')
              return (
                <>
                  <MenuBtn trigger={<button type="button" className="btn quiet" aria-label={`How the building looks: ${lookSaid}`}><Icon name={surface === 'model' ? 'ruler' : 'camera'} size={14} /><span className="lbl">{lookSaid}</span><Icon name="down" size={11} /></button>}>
                    {doll && <>
                      <div className="mh">Drawn from</div>
                      <Menu.RadioGroup value={surface} onValueChange={(x) => { chose.current = sid; v.setView((w) => ({ ...w, surface: x as typeof surface })) }}>
                        <Menu.RadioItem value="model" closeOnClick={false}><span className="mi-check"><Menu.RadioItemIndicator><Icon name="check" size={12} /></Menu.RadioItemIndicator></span>Measured<small>walls and doors as measured</small></Menu.RadioItem>
                        <Menu.RadioItem value="scan" closeOnClick={false}><span className="mi-check"><Menu.RadioItemIndicator><Icon name="check" size={12} /></Menu.RadioItemIndicator></span>Photoreal<small>{bake.colour === 'baking' ? `being made, ${Math.round(bake.progress * 100)}%` : 'the rooms in photo colour'}</small></Menu.RadioItem>
                        {interior && <Menu.RadioItem value="splat" closeOnClick={false}><span className="mi-check"><Menu.RadioItemIndicator><Icon name="check" size={12} /></Menu.RadioItemIndicator></span>Splat<small>trained from the 360° photos</small></Menu.RadioItem>}
                      </Menu.RadioGroup>
                      <hr />
                    </>}
                    <div className="mh">Surroundings</div>
                    <Menu.RadioGroup value={v.view.env ?? 'studio'} onValueChange={(env) => { chose.current = sid; v.setView((w) => ({ ...w, env: env as 'studio' | 'aerial' })) }}>
                      <Menu.RadioItem value="studio" closeOnClick={false}><span className="mi-check"><Menu.RadioItemIndicator><Icon name="check" size={12} /></Menu.RadioItemIndicator></span>Alone</Menu.RadioItem>
                      <Menu.RadioItem value="aerial" closeOnClick={false} disabled={!placed}><span className="mi-check"><Menu.RadioItemIndicator><Icon name="check" size={12} /></Menu.RadioItemIndicator></span>On its site<small>{placed ? 'from the aerial survey' : 'this scan has no position'}</small></Menu.RadioItem>
                    </Menu.RadioGroup>
                    <hr />
                    <Menu.CheckboxItem checked={v.view.style === 'xray'} onCheckedChange={(yes) => v.setView((x) => ({ ...x, style: yes ? 'xray' : 'solid' }))}>
                      <span className="mi-check"><Menu.CheckboxItemIndicator><Icon name="check" size={12} /></Menu.CheckboxItemIndicator></span>{doll ? 'Walls as glass (x-ray)' : 'Measured model inside the capture'}
                    </Menu.CheckboxItem>
                    {doll && <Menu.Item onClick={() => v.setView((x) => ({ ...x, tour: (x.tour ?? 0) + 1 }))}><span className="mi-check" />Fly in from above</Menu.Item>}
                  </MenuBtn>
                </>
              )
            })()}
            <span className="grow" />
            {wi.after && <button type="button" className="btn quiet" aria-pressed={showCompare} onClick={() => setCompare(!showCompare)} title="The plan as it is beside the plan after the what-if edits"><Icon name="split" size={14} /><span className="lbl">Now and after</span></button>}
            {/* Play something on the building: a flood, a fire, a tour. Each says what it is before it starts. */}
            {v.plan && (
              <MenuBtn align="end" trigger={<button type="button" className="btn quiet" aria-pressed={!!spec}><Icon name="play" size={13} /><span className="lbl">Play</span><Icon name="down" size={11} /></button>}>
                <div className="mh">Play on the building</div>
                {SHOWS.map((x) => <Menu.Item key={x.id} className="mi two" onClick={() => play(x.id)}><Icon name={x.icon} /><span className="grow"><b>{x.label}{spec?.kind === x.id && ' (playing, stop)'}</b><span className="s">{x.title}</span></span></Menu.Item>)}
              </MenuBtn>
            )}
            {drawn.length > 0 && (
              <MenuBtn align="end" trigger={<button type="button" className="btn quiet" aria-label={`Overlays: ${on.length} of ${drawn.length} tools drawn on the building`}><Icon name={on.length ? 'eye' : 'eyeoff'} size={14} /><span className="lbl">Overlays</span><span className="count">{on.length} of {drawn.length}</span></button>}>
                <div className="mh">Draw on the building</div>
                {drawn.map((t) => (
                  <Menu.CheckboxItem key={t} checked={on.includes(t)} closeOnClick={false} onCheckedChange={(yes) => setPick(yes ? [...on, t] : on.filter((x) => x !== t))}>
                    <span className="mi-check"><Menu.CheckboxItemIndicator><Icon name="check" size={12} /></Menu.CheckboxItemIndicator></span>{tools.find((x) => x.id === t)?.title ?? t}
                  </Menu.CheckboxItem>
                ))}
                <hr />
                <Menu.Item closeOnClick={false} onClick={() => setPick(on.length === drawn.length ? [] : drawn)}>{on.length === drawn.length ? 'Hide all' : 'Show all'}</Menu.Item>
                {pick && <Menu.Item onClick={() => setPick(null)}>Follow the result in view</Menu.Item>}
              </MenuBtn>
            )}
            <IconBtn icon="expand" label="Show the whole building" onClick={v.stepBack} disabled={!v.plan} />
          </div>
          {/* What is playing on the building, with its transport. The row is there only while something plays. */}
          {v.plan && spec && (
            <div className="worktools playing" role="group" aria-label={`Playing: ${SHOWS.find((x) => x.id === spec.kind)?.label}`}>
              <b className="lbl">{SHOWS.find((x) => x.id === spec.kind)?.label}</b>
              <Transport spec={spec} sink={sink} set={setSpec} seek={seek} close={() => play(null)} />
            </div>
          )}
          <div className="scene-host">
            {v.error && fault(v.error)}
            {!v.plan && !v.error && <div className="scene-state loading" role="status"><span className="sk" /><span className="sk" /><span className="muted small">Loading the plan</span></div>}
            {v.sceneProps && (
              <Suspense fallback={<div className="scene-state loading" role="status"><span className="sk" /><span className="sk" /><span className="muted small">Loading the building view</span></div>}>
                {/* keyed by scan and scheme: the scene builds its model for one plan and reads its colours when it mounts */}
                {(() => {
                  const scene = (
                    <SceneBoundary key={`${v.sceneKey}:${scheme}`} fallback={fault('The building view stopped on this scan.')}>
                      <Scene {...v.sceneProps} className="app-scene" switcher={false} prepare onState={onScene} onShow={onShow} onCamera={(c) => camera.current?.(c)} />
                    </SceneBoundary>
                  )
                  return <CompareScenes open={showCompare} sid={sid} after={wi.after} mode={v.mode} cameraRef={camera}>{scene}</CompareScenes>
                })()}
              </Suspense>
            )}
          </div>
        </section>
        </Fill>
        <Edge of="insp" label="Resize the inspector" />
        <Pane id="insp" size={window.innerWidth <= 1180 ? 360 : window.innerWidth <= 1700 ? 352 : 408} min={300} max={760}>
        <Tabs.Root className="insp" value={tab} onValueChange={(t) => setTab(String(t))} aria-label="Inspector">
          <Tabs.List className="tabs">
            <Tabs.Tab value="overview">Summary</Tabs.Tab>
            <Tabs.Tab value="results">Results{panels.length > 0 && <span className="count">{panels.length}</span>}{working.length > 0 && <i className="ring" />}{working.length === 0 && failed.length > 0 && <span className="faildot" role="img" aria-label={`${failed.length} failed`} />}</Tabs.Tab>
            <Tabs.Tab value="evidence">Evidence{findings.length > 0 && <span className="count">{findings.length}</span>}</Tabs.Tab>
            <Tabs.Tab value="record">Record</Tabs.Tab>
          </Tabs.List>
          <Tabs.Panel value="overview" className="insp-body scroll">
            {v.plan ? <Summary plan={v.plan} sid={sid} panels={panels} findings={findings} onResults={(id) => { setChosen(id); setPick(null); setTab('results') }} />
              : v.error ? <Empty icon="building" title="Nothing to show for this scan" action={<button className="btn" onClick={() => go('explore')}>Back to the map</button>}>{v.error}</Empty>
              : <div className="ins-pad stack">{[60, 80, 45].map((w, k) => <span key={k} className="sk" style={{ width: `${w}%` }} />)}</div>}
          </Tabs.Panel>
          <Tabs.Panel value="results" className="insp-body scroll">
            {working.map((r) => <div key={r.id} className="b-loading working"><RunState state="running">{r.label.split(' · ')[0]}</RunState>{r.summary && <p className="muted small">{r.summary}</p>}<span className="sk" style={{ width: '64%' }} /></div>)}
            {failed.map((r) => {
              const t = catalogue.find((x) => x.id === r.tool)
              return (
                <div key={r.id} className="b-failed" role="status">
                  <span className="row"><RunState state="failed">{t?.title ?? r.label.split(' · ')[0]} did not run</RunState><span className="grow" />{t && <button type="button" className="btn sm" onClick={() => startTool(t, sid, true)}>Try again</button>}</span>
                  {r.summary && <p>{r.summary}</p>}
                </div>
              )
            })}
            {panels.length === 0 && working.length === 0 && failed.length === 0 && citywide.length === 0 && (
              <Empty icon="play" title="No results on this scan" action={<RunToolMenu sid={sid} trigger={<button type="button" className="btn solid">Run a tool<Icon name="down" size={11} /></button>} />}>
                Pick a tool to measure this scan. Its result, checks and evidence appear here, and it draws on the building.
              </Empty>
            )}
            {[...panels].reverse().map((p) => <PanelView key={p.id} panel={p} open={p.id === inView?.id} onOpen={(o) => { setChosen(o ? p.id : null); setPick(null) }} />)}
            {/* a rollup or a search run from here is about no one scan: it stays within reach, folded, under its own heading */}
            {citywide.length > 0 && <h3 className="insp-h">Across the city, in this investigation<span className="count">{citywide.length}</span></h3>}
            {[...citywide].reverse().map((p) => <PanelView key={p.id} panel={p} folded />)}
            {/* every run on this scan, with how long it took: the working, for whoever wants it */}
            {runs.length > 0 && <details className="ins-fold flush"><summary><Icon name="right" size={11} />Run history<span className="count">{runs.length}</span></summary><History sid={sid} runs={runs} /></details>}
          </Tabs.Panel>
          <Tabs.Panel value="evidence" className="insp-body scroll"><Evidence findings={findings} /></Tabs.Panel>
          <Tabs.Panel value="record" className="insp-body scroll"><Record sid={sid} /></Tabs.Panel>
        </Tabs.Root>
        </Pane>
      </Split>
    </div>
  )
}
