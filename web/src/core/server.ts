import { create } from 'zustand'
import { notify } from './notices.ts'
import { useWorkspace } from './store.ts'
import type { Op } from './types.ts'
import { toDoc, toServerOp, type J, type Manifest, type Names } from './serverDoc.ts'
import { currentRoute, navigate } from './router.ts'
import { pathIn, sharedToken, splitPath, DEFAULT_LOOK } from './looks.ts'
import { useBuildings } from './buildings.ts'
import { gate, serial, single } from './sync.ts'

/* The live link to the agent server: one workspace id (kept in localStorage so a reload shows the same workspace),
   turns as server-sent events, user ops, and tool runs. serverDoc.ts turns what comes back into the shell's Doc. */

/** `shared` is set when the page is a read-only link: the workspace is shown and followed, never written. */
export type Shared = { state: 'loading' | 'ready' | 'gone'; expires?: string }
export const useCatalog = create<{ live: boolean | null; tools: Manifest[]; shared: Shared | null }>(() => ({ live: null, tools: [], shared: null }))
const manifests = () => new Map(useCatalog.getState().tools.map((m) => [m.id, m]))
const KEY = 'threshold.workspace'
const store = { get: (k: string) => { try { return localStorage.getItem(k) } catch { return null } }, set: (k: string, v: string | null) => { try { if (v == null) localStorage.removeItem(k); else localStorage.setItem(k, v) } catch { /* private window */ } } }
let id = store.get(KEY)
let ws: J | null = null // the server document last seen
let seenCamera: number | null | undefined
let ask: { tool: string; sid: string | null } | null = null // a dock run waiting on questions its tool asked
let token: string | null = null // a read-only link's token, when that is what the page shows
const fresh = gate() // which responses may still be shown (sync.ts)
const writes = serial() // user ops reach the server in the order they were made
const turns = serial() // one turn at a time: Start pressed while the composing turn still streams waits for it to end
let reading: { cancel: () => Promise<void> } | null = null // the turn stream being read, so start-over can let go of it
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
/** Is there a workspace on the server to come back to: one remembered in this browser, or a read-only link? */
export const remembered = () => !!id || !!token
/** Every user op made so far is on the server. */
export const settled = () => writes.idle()
/** A read-only link takes no change. Says so once per attempt and puts the server's document back. */
export function refused(): boolean {
  if (!token) return false
  notify('This is a read-only link.', { description: 'You can look at everything. To change or run something, open your own workspace.' })
  void sync()
  return true
}

let writing: string[] = [] // runs the server is still writing the findings, panel and camera of
/** Show a view the server sent. `asked` is the generation its request started in (fresh.now()): a response from
    before a start-over, or older than the document on screen, is dropped. True when it was shown. */
function show(view: J, asked: number, resumed = false): boolean {
  if (!fresh.take(asked, typeof view.seq === 'number' ? view.seq : undefined)) return false
  ws = view.doc as J
  writing = view.busy ?? []
  if (!token) { id = ws.id; store.set(KEY, id) } // a link's view carries no id: the person's own workspace stays theirs
  const cur = useWorkspace.getState().doc.camera, sc = ws.camera as J | null
  let camera = cur
  if (sc && sc.at !== seenCamera) { // the agent looked somewhere new
    const here = !resumed || ('sid' in sc.anchor && sc.anchor.sid === currentRoute().sid) // a reload stays where it is
    if (here) camera = { anchor: sc.anchor, by: 'agent', finding: (ws.findings as J[]).find((f) => f.anchor && JSON.stringify(f.anchor) === JSON.stringify(sc.anchor))?.id }
  }
  seenCamera = sc?.at
  if (resumed) { // a link with ?f opens on that finding, where the link points
    const f = currentRoute().q.get('f'), hit = f ? (ws.findings as J[]).find((x) => x.id === f && x.anchor) : null
    if (hit) camera = { anchor: hit.anchor, finding: hit.id, by: 'user', stay: true }
  }
  useWorkspace.setState({ doc: toDoc(ws, view.learned ?? [], manifests(), names, camera) })
  if (token) useCatalog.setState({ shared: { state: 'ready', expires: view.share?.expires } })
  return true
}
export async function sync(resumed = false): Promise<boolean> {
  const asked = fresh.now(), path = token ? `/api/shared/${encodeURIComponent(token)}` : id ? `/api/workspace/${encodeURIComponent(id)}` : null
  if (!path) return false
  const r = await fetch(path).catch(() => null)
  if (!r?.ok) {
    if (r?.status === 404 && asked === fresh.now()) { if (token) useCatalog.setState({ shared: { state: 'gone' } }); else forget() }
    return false
  }
  show(await r.json(), asked, resumed)
  return true
}
let timer: ReturnType<typeof setTimeout> | undefined
let streaming = false // a turn's event stream is open in this tab, or is being followed after it dropped
const soon = () => { timer ??= setTimeout(() => { timer = undefined; void sync() }, 250) }
/** Is anything in the document still working: a run, a plan step, a result being written? */
const working = () => (ws?.runs as J[] | undefined)?.some((r) => r.status === 'running') || (ws?.plan as J[] | undefined)?.some((s) => s.status === 'in_progress') || writing.length > 0

/** A new brief starts a new workspace. Responses still in flight belong to the one left behind and are dropped. */
export function forget() {
  if (token) return
  fresh.next(); id = null; ws = null; ask = null; seenCamera = undefined; store.set(KEY, null)
  void reading?.cancel().catch(() => {}) // its turn belongs to the workspace left behind; the next one need not wait for it
  reading = null
}
/** After a reload: the server kept the workspace, so show it again. A read-only link shows the workspace it names. */
export async function resume() {
  const linked = sharedToken(splitPath(window.location.pathname).place)
  if (linked) { token = linked; fresh.next(); useCatalog.setState({ shared: { state: 'loading' } }) }
  if (!(await connect()) || (!id && !token)) return // the probe runs either way: the tool menu lists what the server has
  const b = useBuildings.getState()
  if (b.state === 'loading') await new Promise<void>((res) => { const off = useBuildings.subscribe((x) => { if (x.state !== 'loading') { off(); res() } }) })
  const shown = await sync(true)
  if (token) { if (shown) void follow(fresh.now(), fresh.at(), Infinity); else if (useCatalog.getState().shared?.state !== 'gone') useCatalog.setState({ shared: { state: 'gone' } }); return }
  // A turn that was running when the page went away is still running on the server: keep reading until it settles.
  for (let i = 0; i < 300 && working() && !streaming; i++) { await new Promise((r) => setTimeout(r, 2000)); if (!streaming) await sync() }
}
/** A workspace to write to: the one in hand, the one remembered, or a new one. Shared by callers that ask at once. */
const ensure = single(async (): Promise<boolean> => {
  if (token) return false
  if (id && ws) return true
  if (id && (await sync())) return true
  const asked = fresh.now()
  const r = await fetch(`/api/workspace?profile=${profile()}`, { method: 'POST' }).catch(() => null)
  if (!r?.ok) return false
  return show(await r.json(), asked)
})

/** Send user ops; the reply is the document after them. */
export async function post(ops: J | J[]): Promise<boolean> {
  if (!(await ensure())) return false
  const asked = fresh.now()
  const r = await fetch(`/api/workspace/${id}/ops`, { method: 'POST', headers: json, body: JSON.stringify(ops) }).catch(() => null)
  if (asked !== fresh.now()) return false // start-over while it was on its way: nothing to say about the old workspace
  if (!r?.ok) { notify.error('The server did not take that change.', { description: r ? ((await r.json().catch(() => ({}))) as J).detail : 'It is not answering.' }); void sync(); return false }
  show(await r.json(), asked)
  return true
}

/** A read-only link to the open workspace, for the address bar of whoever it is sent to. It holds a token the server
    made and can revoke, never the workspace id: whoever has the id can write. Rejects with a sentence when the server
    cannot make one. On a page that is itself a link, the same link again. */
export async function share(days = 7): Promise<{ url: string; expires: string | null }> {
  const url = (t: string) => window.location.origin + pathIn(splitPath(window.location.pathname).look ?? DEFAULT_LOOK, `/shared/${t}`)
  if (token) return { url: url(token), expires: useCatalog.getState().shared?.expires ?? null }
  if (!id) throw new Error('There is nothing to share yet.')
  await writes.idle()
  const r = await fetch(`/api/workspace/${encodeURIComponent(id)}/share`, { method: 'POST', headers: json, body: JSON.stringify({ days }) }).catch(() => null)
  if (!r) throw new Error('The server is not answering.')
  if (!r.ok) throw new Error(r.status === 501 ? 'This server keeps workspaces in files, and a read-only link needs its database store.' : (((await r.json().catch(() => ({}))) as J).detail ?? `The server answered ${r.status}.`))
  const made = (await r.json()) as J
  return { url: url(made.token), expires: made.expires ?? null }
}

/** Read a workspace's live stream (the turn's own vocabulary, each op with its log length as the event id) until it
    has been quiet for `quiet` ms with nothing still working. The browser's EventSource reconnects by itself and sends
    the last id it got, so a dropped network resumes where it stopped instead of ending the turn on screen. */
function follow(asked: number, after: number, quiet = 45_000): Promise<void> {
  return new Promise((resolve) => {
    const path = token ? `/api/shared/${encodeURIComponent(token)}/live` : id ? `/api/workspace/${encodeURIComponent(id)}/live` : null
    if (!path || typeof EventSource === 'undefined') { resolve(); return }
    const es = new EventSource(`${path}?after=${Math.max(0, after)}`)
    let idle: ReturnType<typeof setTimeout> | undefined
    const stop = () => { clearTimeout(idle); es.close(); resolve() }
    const settle = () => {
      clearTimeout(idle)
      if (quiet === Infinity) return // a link is followed for as long as the page is open
      idle = setTimeout(() => void sync().then(() => (asked === fresh.now() && working() ? settle() : stop())), quiet)
    }
    es.addEventListener('op', () => { if (asked !== fresh.now()) { stop(); return } soon(); settle() })
    settle()
  })
}

/** One agent turn: the events are workspace ops, shown as they land. Resolves with the `done` event, or null. */
export function turn(body: { text?: string; sids?: string[] }): Promise<J | null> {
  if (refused()) return Promise.resolve(null)
  const asked = fresh.now()
  return turns.run(() => (asked === fresh.now() ? stream(body, asked) : Promise.resolve(null))) // start-over while it waited: not this workspace's turn any more
}
async function stream(body: { text?: string; sids?: string[] }, asked: number): Promise<J | null> {
  await writes.idle() // what the person answered or changed just before is what the turn reads
  if (asked !== fresh.now()) return null
  const r = await fetch('/api/agent/turn', { method: 'POST', headers: { ...json, accept: 'text/event-stream' }, body: JSON.stringify({ ...body, workspace: id ?? undefined, profile: profile() }) })
  if (!r.ok || !r.body) throw new Error(`turn ${r.status}`)
  const reader = r.body.pipeThrough(new TextDecoderStream()).getReader()
  let buf = '', done: J | null = null, ended = false, last = fresh.at()
  streaming = true
  reading = reader
  for (;;) {
    const { value, done: end } = await reader.read().catch(() => ({ value: undefined, done: true }))
    if (asked !== fresh.now()) { void reader.cancel().catch(() => {}); streaming = false; return null } // start-over: this turn is the old workspace's
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
        if (typeof data.seq === 'number') last = Math.max(last, data.seq)
        // the work has started: leave the front door for the map, where the plan and the runs show
        if (['plan.set', 'run.start'].includes(data.op?.op) && currentRoute().path === '/') navigate('/map', {}, { keep: true })
        soon()
      } else if (kind === 'done') { done = data; ended = true }
      else if (kind === 'error') { ended = true; notify.error('The agent stopped.', { description: data.message }) }
    }
  }
  if (reading === reader) reading = null
  // The stream closed with no `done`: the connection dropped, and the turn is still running on the server.
  if (!ended && id) await follow(asked, last)
  streaming = false
  if (asked === fresh.now()) await sync()
  return done
}

/** Run one tool, from the dock, a panel action or a moved control: on one scan, or on none (`sid` null) for a tool
    that works across the city or on what a phone sent. */
export async function runTool(tool: string, sid: string | null, inputs: J = {}): Promise<void> {
  if (refused()) return
  if (!(await ensure())) { notify.error('The server is not answering.'); return }
  const m = manifests().get(tool), props = m?.inputs.properties ?? {}
  const sids: string[] = ws!.brief?.scope?.sids ?? []
  const setup: J[] = []
  if (sid && !sids.includes(sid)) setup.push({ op: 'brief.set', scope: { ...(ws!.brief?.scope ?? {}), sids: [...sids, sid] } })
  if (!(ws!.tools as J[]).some((t) => t.id === tool && t.enabled !== false)) setup.push({ op: 'tool.enable', tool, reason: sid ? 'You asked for it on this scan.' : 'You ran it yourself.' })
  if (setup.length && !(await post(setup))) return
  const poll = setInterval(() => void sync(), 900) // the run and its steps show while the request is open
  // wait=2: a tool that takes longer answers { status: 'running' } and finishes on the server (see below)
  const r = await fetch(`/api/tools/${tool}/run?workspace=${id}&wait=2`, { method: 'POST', headers: json,
    body: JSON.stringify({ ...(!sid ? {} : 'scan' in props ? { scan: sid } : 'place' in props ? { place: { scan: sid } } : {}), ...inputs }) }).catch(() => null)
  clearInterval(poll)
  let out: J = r?.ok ? await r.json() : { error: r ? `The server answered ${r.status}.` : 'The server is not answering.' }
  await sync()
  // A slow tool (a smoke simulation takes minutes) keeps running on the server. Its steps and its result arrive as
  // ordinary workspace ops, so every look shows it as a running run; here we only keep reading until it settles.
  for (let i = 0; out.status === 'running' && i < 1500; i++) {
    const run = (ws?.runs as J[] | undefined)?.find((x) => x.id === out.run)
    // "done" comes a few seconds before the run's panel and camera are written: read until those are in too
    if ((!run || run.status !== 'running') && !writing.includes(out.run)) { out =run?.status === 'error' ? { error: run.error ?? 'The tool stopped.' } : {}; break }
    await new Promise((res) => setTimeout(res, 1200))
    await sync()
  }
  const missing = /^missing inputs/.test(out.error ?? '') ? (m?.inputs.required ?? []).filter((k) => props[k]?.['x-ask'] && !(ws!.questions as J[]).some((q) => q.key === (props[k]['x-pref'] ?? `${tool}.${k}`))) : []
  if (missing.length) { // the tool needs something only the person knows: ask, then run when it is answered
    ask = { tool, sid }
    await post(missing.map((k) => ({ op: 'question.ask', question: { id: `q_${props[k]['x-pref'] ?? `${tool}.${k}`}`, key: props[k]['x-pref'] ?? `${tool}.${k}`, text: props[k]['x-ask'], tools: [tool],
      input: Object.fromEntries(Object.entries(props[k]).filter(([x]) => x !== 'x-ask' && x !== 'title')) } })))
    notify(`${m?.title ?? tool} needs an answer first.`, { description: 'It is waiting for your answer.' })
  } else if (out.error) notify.error(`${m?.title ?? tool} did not run.`, { description: out.error })
}

/** What the server should hear about a user op the shell has already applied. */
export async function onUserOp(op: Op): Promise<void> {
  if (op.op === 'pref.set' && op.key.startsWith('input:')) { // a control with no preference behind it: run again with that input
    const [, tool, input] = op.key.split(':'), last = (ws?.runs as J[] | undefined)?.findLast((r) => r.tool === tool)
    if (last) await runTool(tool, last.sid ?? null, { ...last.inputs, [input]: op.value })
    return
  }
  if (refused()) return
  // queued at once, so ops reach the server in the order they were made; what follows a post is not held in the queue
  if (!(await writes.run(async () => { const out = toServerOp(op, ws); return !!out && (await post(out)) }))) return
  if (op.op === 'question.answer' && ask && !(ws!.questions as J[]).some((q) => !q.answered && q.tools?.includes(ask!.tool))) { const a = ask; ask = null; await runTool(a.tool, a.sid) }
  if (op.op === 'pref.set') { // a changed setting runs its tools again, latest run per tool and scan, three at most
    const stale = new Map<string, J>()
    for (const r of ws!.runs as J[]) if (r.sid) { if (r.stale && r.status === 'done') stale.set(`${r.tool}:${r.sid}`, r); else stale.delete(`${r.tool}:${r.sid}`) }
    for (const r of [...stale.values()].slice(0, 3)) await runTool(r.tool, r.sid)
  }
}
