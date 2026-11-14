import { create } from 'zustand'
import { toast } from 'sonner'
import { useWorkspace } from './store.ts'
import type { Op } from './types.ts'
import { toDoc, toServerOp, type J, type Manifest, type Names } from './serverDoc.ts'
import { currentRoute, navigate } from '../lib/router.ts'
import { useBuildings } from '../map/buildings.ts'

/* The live link to the agent server: one workspace id (kept in localStorage so a reload shows the same workspace),
   turns as server-sent events, user ops, and tool runs. serverDoc.ts turns what comes back into the shell's Doc. */

export const useCatalog = create<{ live: boolean | null; tools: Manifest[] }>(() => ({ live: null, tools: [] }))
const manifests = () => new Map(useCatalog.getState().tools.map((m) => [m.id, m]))
const KEY = 'threshold.workspace'
const store = { get: (k: string) => { try { return localStorage.getItem(k) } catch { return null } }, set: (k: string, v: string | null) => { try { if (v == null) localStorage.removeItem(k); else localStorage.setItem(k, v) } catch { /* private window */ } } }
let id = store.get(KEY)
let ws: J | null = null // the server document last seen
let seenCamera: number | null | undefined
let ask: { tool: string; sid: string } | null = null // a dock run waiting on questions its tool asked
const profile = () => { let p = store.get('threshold.profile'); if (!p) { p = 'p' + Math.random().toString(36).slice(2, 10); store.set('threshold.profile', p) } return p }
const json = { 'content-type': 'application/json' }
const names: Names = (sid) => { for (const b of useBuildings.getState().all) { const s = b.scans.find((x) => x.sid === sid); if (s) return { name: s.name, address: b.address } } }

let probe: Promise<boolean> | null = null
/** Is the agent server there? Asked once; its tool list is the catalog. */
export function connect(): Promise<boolean> {
  probe ??= fetch('/api/tools').then((r) => (r.ok ? r.json() : Promise.reject())).then(
    (tools: Manifest[]) => { useCatalog.setState({ live: true, tools }); return true },
    () => { useCatalog.setState({ live: false }); return false })
  return probe
}
export const isLive = () => useCatalog.getState().live === true
export const serverDoc = () => ws

function show(view: J, resumed = false) {
  ws = view.doc as J
  id = ws.id; store.set(KEY, id)
  const cur = useWorkspace.getState().doc.camera, sc = ws.camera as J | null
  let camera = cur
  if (sc && sc.at !== seenCamera) { // the agent looked somewhere new
    const here = !resumed || ('sid' in sc.anchor && sc.anchor.sid === currentRoute().sid) // a reload stays where it is
    if (here) camera = { anchor: sc.anchor, by: 'agent', finding: (ws.findings as J[]).find((f) => f.anchor && JSON.stringify(f.anchor) === JSON.stringify(sc.anchor))?.id }
  }
  seenCamera = sc?.at
  useWorkspace.setState({ doc: toDoc(ws, view.learned ?? [], manifests(), names, camera) })
}
export async function sync(resumed = false): Promise<boolean> {
  if (!id) return false
  const r = await fetch(`/api/workspace/${id}`).catch(() => null)
  if (!r?.ok) { if (r?.status === 404) forget(); return false }
  show(await r.json(), resumed)
  return true
}
let timer: ReturnType<typeof setTimeout> | undefined
let streaming = false // a turn's event stream is open in this tab
const soon = () => { timer ??= setTimeout(() => { timer = undefined; void sync() }, 250) }

/** A new brief starts a new workspace. */
export function forget() { id = null; ws = null; ask = null; seenCamera = undefined; store.set(KEY, null) }
/** After a reload: the server kept the workspace, so show it again. */
export async function resume() {
  if (!(await connect()) || !id) return // the probe runs either way: the tool menu lists what the server has
  const b = useBuildings.getState()
  if (b.state === 'loading') await new Promise<void>((res) => { const off = useBuildings.subscribe((x) => { if (x.state !== 'loading') { off(); res() } }) })
  await sync(true)
  // A turn that was running when the page went away is still running on the server: keep reading until it settles.
  const busy = () => (ws?.runs as J[] | undefined)?.some((r) => r.status === 'running') || (ws?.plan as J[] | undefined)?.some((s) => s.status === 'in_progress')
  for (let i = 0; i < 300 && busy() && !streaming; i++) { await new Promise((r) => setTimeout(r, 2000)); if (!streaming) await sync() }
}
async function ensure(): Promise<boolean> {
  if (id && ws) return true
  if (id && (await sync())) return true
  const r = await fetch(`/api/workspace?profile=${profile()}`, { method: 'POST' }).catch(() => null)
  if (!r?.ok) return false
  show(await r.json())
  return true
}

/** Send user ops; the reply is the document after them. */
export async function post(ops: J | J[]): Promise<boolean> {
  if (!(await ensure())) return false
  const r = await fetch(`/api/workspace/${id}/ops`, { method: 'POST', headers: json, body: JSON.stringify(ops) }).catch(() => null)
  if (!r?.ok) { toast.error('The server did not take that change.', { description: r ? ((await r.json().catch(() => ({}))) as J).detail : 'It is not answering.' }); void sync(); return false }
  show(await r.json())
  return true
}

/** One agent turn: the events are workspace ops, shown as they land. Resolves with the `done` event, or null. */
export async function turn(body: { text?: string; sids?: string[] }): Promise<J | null> {
  const r = await fetch('/api/agent/turn', { method: 'POST', headers: { ...json, accept: 'text/event-stream' }, body: JSON.stringify({ ...body, workspace: id ?? undefined, profile: profile() }) })
  if (!r.ok || !r.body) throw new Error(`turn ${r.status}`)
  const reader = r.body.pipeThrough(new TextDecoderStream()).getReader()
  let buf = '', done: J | null = null
  streaming = true
  for (;;) {
    const { value, done: end } = await reader.read().catch(() => ({ value: undefined, done: true }))
    if (end || value == null) break
    buf += value
    const events = buf.split('\n\n')
    buf = events.pop()!
    for (const e of events) {
      const kind = e.match(/^event: (.*)$/m)?.[1], raw = e.split('\n').filter((l) => l.startsWith('data:')).map((l) => l.slice(5).trim()).join('')
      let data: J
      try { data = JSON.parse(raw) } catch { continue } // a malformed event is skipped, the stream goes on
      if (kind === 'workspace') { id = data.id; store.set(KEY, id) }
      else if (kind === 'op') {
        // the work has started: leave the front door for the map, where the plan and the runs show
        if (['plan.set', 'run.start'].includes(data.op?.op) && currentRoute().path === '/') navigate('/map', {}, { keep: true })
        soon()
      } else if (kind === 'done') done = data
      else if (kind === 'error') toast.error('The agent stopped.', { description: data.message })
    }
  }
  streaming = false
  await sync()
  return done
}

/** Run one tool on one scan, from the dock, a panel action or a moved control. */
export async function runTool(tool: string, sid: string, inputs: J = {}): Promise<void> {
  if (!(await ensure())) { toast.error('The server is not answering.'); return }
  const m = manifests().get(tool), props = m?.inputs.properties ?? {}
  const sids: string[] = ws!.brief?.scope?.sids ?? []
  const setup: J[] = []
  if (!sids.includes(sid)) setup.push({ op: 'brief.set', scope: { ...(ws!.brief?.scope ?? {}), sids: [...sids, sid] } })
  if (!(ws!.tools as J[]).some((t) => t.id === tool && t.enabled !== false)) setup.push({ op: 'tool.enable', tool, reason: 'You asked for it on this scan.' })
  if (setup.length && !(await post(setup))) return
  const poll = setInterval(() => void sync(), 900) // the run and its steps show while the request is open
  const r = await fetch(`/api/tools/${tool}/run?workspace=${id}`, { method: 'POST', headers: json,
    body: JSON.stringify({ ...('scan' in props ? { scan: sid } : 'place' in props ? { place: { scan: sid } } : {}), ...inputs }) }).catch(() => null)
  clearInterval(poll)
  const out: J = r?.ok ? await r.json() : { error: r ? `The server answered ${r.status}.` : 'The server is not answering.' }
  await sync()
  const missing = /^missing inputs/.test(out.error ?? '') ? (m?.inputs.required ?? []).filter((k) => props[k]?.['x-ask'] && !(ws!.questions as J[]).some((q) => q.key === (props[k]['x-pref'] ?? `${tool}.${k}`))) : []
  if (missing.length) { // the tool needs something only the person knows: ask, then run when it is answered
    ask = { tool, sid }
    await post(missing.map((k) => ({ op: 'question.ask', question: { id: `q_${props[k]['x-pref'] ?? `${tool}.${k}`}`, key: props[k]['x-pref'] ?? `${tool}.${k}`, text: props[k]['x-ask'], tools: [tool],
      input: Object.fromEntries(Object.entries(props[k]).filter(([x]) => x !== 'x-ask' && x !== 'title')) } })))
    toast(`${m?.title ?? tool} needs an answer first.`, { description: 'The question is in the brief, on the left.' })
  } else if (out.error) toast.error(`${m?.title ?? tool} did not run.`, { description: out.error })
}

/** What the server should hear about a user op the shell has already applied. */
export async function onUserOp(op: Op): Promise<void> {
  if (op.op === 'pref.set' && op.key.startsWith('input:')) { // a control with no preference behind it: run again with that input
    const [, tool, input] = op.key.split(':'), last = (ws?.runs as J[] | undefined)?.findLast((r) => r.tool === tool && r.sid)
    if (last) await runTool(tool, last.sid, { ...last.inputs, [input]: op.value })
    return
  }
  const out = toServerOp(op, ws)
  if (!out || !(await post(out))) return
  if (op.op === 'question.answer' && ask && !(ws!.questions as J[]).some((q) => !q.answered && q.tools?.includes(ask!.tool))) { const a = ask; ask = null; await runTool(a.tool, a.sid) }
  if (op.op === 'pref.set') { // a changed setting runs its tools again, latest run per tool and scan, three at most
    const stale = new Map<string, J>()
    for (const r of ws!.runs as J[]) if (r.sid) { if (r.stale && r.status === 'done') stale.set(`${r.tool}:${r.sid}`, r); else stale.delete(`${r.tool}:${r.sid}`) }
    for (const r of [...stale.values()].slice(0, 3)) await runTool(r.tool, r.sid)
  }
}
