import { post, serverDoc, sync } from '../core/server.ts'
import type { SwitcherPlace } from '../core/switcher.ts'

/* "Continue on phone", on the desktop. A small tab beside the look switcher opens a QR code that brings this
   workspace up on a phone, and lists what the phone sends as it arrives. While it is paired the desktop follows the
   workspace's live stream (the same route a MongoDB change stream feeds), so findings a capture changes are redrawn
   without a reload. Like the switcher it lives in a shadow root: no look's CSS reaches it, and its CSS reaches no look. */

type Cap = { id: string; at: number; kind: string; task?: string; tool?: string; note?: string; file: string | null; result?: { text?: string; verdict?: string; status?: string } | null }
const PLACES: Record<SwitcherPlace, string> = {
  bottom: 'left: calc(50% + 62px); bottom: 0;', top: 'left: calc(50% + 62px); top: 0;',
  'bottom-left': 'left: 130px; bottom: 0;', 'bottom-right': 'right: 130px; bottom: 0;', 'top-left': 'left: 130px; top: 0;', 'top-right': 'right: 130px; top: 0;',
}
const WORD: Record<string, string> = { photo: 'Photo', video: 'Video', audio: 'Voice note', reading: 'Reading' }
const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]!)

export function mountPhoneLink(place: SwitcherPlace = 'bottom') {
  if (!(place in PLACES)) place = 'bottom'
  const top = place.startsWith('top')
  const host = document.createElement('div')
  host.setAttribute('data-phone-link', '')
  const root = host.attachShadow({ mode: 'open' })
  root.innerHTML = `<style>
    :host { all: initial; position: fixed; ${PLACES[place]} z-index: 2147483000; font: 500 12px/1.4 ui-sans-serif, system-ui, sans-serif; }
    .tab { all: unset; cursor: pointer; display: block; padding: 2px 9px; font: 500 10.5px/14px ui-monospace, 'SF Mono', Menlo, monospace; letter-spacing: 0.04em;
      background: rgb(22 24 28 / 0.82); color: #fff; border-radius: ${top ? '0 0 5px 5px' : '5px 5px 0 0'}; opacity: 0.5; transition: opacity 120ms ease; }
    .tab:hover, .tab:focus-visible, .tab[aria-expanded='true'] { opacity: 1; }
    .tab:focus-visible { outline: 2px solid #8fb5ff; outline-offset: 1px; }
    .tab b { font-weight: 700; margin-left: 6px; }
    .pop { position: absolute; ${top ? 'top: 22px' : 'bottom: 22px'}; left: 50%; translate: -50% 0; width: 268px; max-height: min(78vh, 620px); overflow: auto; background: #fbfaf6; color: #18212b;
      border-radius: 4px; box-shadow: 0 0 0 1px rgb(24 33 43 / 0.4), 0 14px 30px -14px rgb(24 33 43 / 0.5); padding: 14px; display: grid; gap: 10px;
      transform-origin: ${top ? 'top' : 'bottom'} center; transition: opacity 160ms cubic-bezier(0.23, 1, 0.32, 1), scale 160ms cubic-bezier(0.23, 1, 0.32, 1); }
    .pop[hidden] { display: none; }
    @starting-style { .pop { opacity: 0; scale: 0.97; } }
    h2 { all: unset; display: block; font-weight: 650; font-size: 13px; }
    p { margin: 0; color: #4a5563; }
    .qr { background: #fff; border: 1px solid rgb(24 33 43 / 0.15); padding: 6px; display: grid; place-items: center; min-height: 236px; }
    .qr svg { width: 100%; height: auto; display: block; }
    .url { font: 11px/1.3 ui-monospace, Menlo, monospace; color: #4a5563; word-break: break-all; user-select: all; }
    .warn { color: #a65f00; }
    .lab { font: 600 10px/1.2 ui-sans-serif, system-ui, sans-serif; letter-spacing: 0.1em; text-transform: uppercase; color: #5f6a78; border-bottom: 1px solid rgb(24 33 43 / 0.42); padding-bottom: 4px; display: flex; justify-content: space-between; }
    ul { all: unset; display: grid; }
    li { display: grid; grid-template-columns: 44px 1fr; gap: 8px; align-items: center; padding: 6px 0; border-bottom: 1px solid rgb(24 33 43 / 0.15); }
    li img, li .k { width: 44px; height: 33px; object-fit: cover; border-radius: 2px; outline: 1px solid rgb(0 0 0 / 0.1); outline-offset: -1px; }
    li .k { display: grid; place-items: center; font: 500 8.5px/1 ui-monospace, Menlo, monospace; text-transform: uppercase; color: #5f6a78; background: repeating-linear-gradient(135deg, transparent 0 5px, rgb(24 33 43 / 0.12) 5px 6px); }
    li b { display: block; font-weight: 600; } li span { color: #5f6a78; font-size: 11px; }
    li[data-new] { animation: arrive 900ms ease-out; }
    @keyframes arrive { from { background: rgb(37 69 184 / 0.14); } }
    button.again { all: unset; cursor: pointer; text-decoration: underline; text-underline-offset: 3px; color: #4a5563; font-size: 11px; }
    button.again:focus-visible { outline: 2px solid #2545b8; outline-offset: 2px; }
    @media (prefers-reduced-motion: reduce) { .pop { transition: none; } li[data-new] { animation: none; } }
    @media print { :host { display: none; } }
  </style>
  <button class="tab" aria-expanded="false" aria-controls="pop" title="Continue this workspace on a phone">Phone<b hidden></b></button>
  <div class="pop" id="pop" role="dialog" aria-label="Continue on phone" hidden>
    <h2>Continue on phone</h2>
    <p>Scan this with the phone's camera. It opens this workspace's on-site checks; what the phone captures appears here as it is sent.</p>
    <div class="qr" aria-live="polite">Making a link</div>
    <div class="url"></div>
    <p class="note"></p>
    <div class="lab"><span>From the phone</span><span class="n">0</span></div>
    <ul></ul>
    <p class="none">Nothing yet.</p>
  </div>`
  const $ = <T extends Element>(q: string) => root.querySelector<T>(q)!
  const tab = $<HTMLButtonElement>('.tab'), pop = $<HTMLDivElement>('.pop'), badge = $<HTMLElement>('.tab b'), list = $<HTMLUListElement>('ul')
  let ws: string | null = null, stream: EventSource | null = null, known = new Set<string>(), first = true, timer: ReturnType<typeof setTimeout> | undefined

  async function captures() {
    if (!ws) return
    const caps: Cap[] = await fetch(`/api/workspace/${ws}/captures`).then((r) => (r.ok ? r.json() : [])).catch(() => [])
    list.innerHTML = caps.slice(0, 30).map((c) => {
      const what = c.task ? 'Answers an on-site check' : c.tool ? c.tool.replaceAll('_', ' ') : c.note || 'Note'
      const said = c.result?.text ?? ''
      const pic = c.kind === 'photo' ? `<img src="/api/capture/${c.id}/file" alt="" loading="lazy">` : `<span class="k">${esc(c.kind)}</span>`
      return `<li${!first && !known.has(c.id) ? ' data-new' : ''}>${pic}<div><b>${esc(WORD[c.kind] ?? c.kind)}: ${esc(what)}</b><span>${esc(new Date(c.at * 1000).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }))}${said ? ' · ' + esc(said.slice(0, 90)) : ''}</span></div></li>`
    }).join('')
    const fresh = caps.filter((c) => !known.has(c.id)).length
    if (!first && fresh && pop.hidden) { badge.hidden = false; badge.textContent = String((Number(badge.textContent) || 0) + fresh) }
    known = new Set(caps.map((c) => c.id)); first = false
    $<HTMLElement>('.n').textContent = String(caps.length)
    $<HTMLElement>('.none').hidden = caps.length > 0
  }
  /** Follow the workspace: every op any writer appends (the phone's captures among them) redraws the look and this list. */
  function follow(after: number) {
    stream?.close()
    stream = new EventSource(`/api/workspace/${ws}/live?after=${after}`)
    stream.addEventListener('op', () => { clearTimeout(timer); timer = setTimeout(() => { void sync(); void captures() }, 200) })
  }
  async function pair() {
    const qr = $<HTMLElement>('.qr'), note = $<HTMLElement>('.note')
    if (!serverDoc() && !(await post([]))) { qr.textContent = 'The server is not answering.'; return } // a workspace to pair with
    const doc = serverDoc() as { id: string } | null
    if (!doc) { qr.textContent = 'The server is not answering.'; return }
    const changed = doc.id !== ws
    ws = doc.id
    const r = await fetch(`/api/workspace/${ws}/pair`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ origin: location.origin }) }).catch(() => null)
    if (!r?.ok) { qr.textContent = 'The server could not make a link.'; return }
    const p = (await r.json()) as { url: string; qr: string; expires: number; secure: boolean }
    qr.innerHTML = p.qr // an SVG the server drew from its own token: no user text in it
    $<HTMLElement>('.url').textContent = p.url
    const until = new Date(p.expires * 1000).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
    note.className = p.secure ? 'note' : 'note warn'
    note.innerHTML = (p.secure ? `Works until ${esc(until)}, for captures only. ` : 'This address is not HTTPS, so a phone will refuse it the camera and sensors. Open the desktop at its HTTPS address first. ') + '<button class="again">New code</button>'
    note.querySelector('.again')!.addEventListener('click', () => void pair())
    if (changed) { first = true; known = new Set(); await captures(); follow(((await fetch(`/api/workspace/${ws}`).then((x) => x.json()).catch(() => ({ seq: 0 }))) as { seq: number }).seq) }
  }
  const close = () => { pop.hidden = true; tab.setAttribute('aria-expanded', 'false') }
  tab.addEventListener('click', () => {
    if (!pop.hidden) { close(); return }
    pop.hidden = false; tab.setAttribute('aria-expanded', 'true'); badge.hidden = true; badge.textContent = ''
    if (!ws || (serverDoc() as { id?: string } | null)?.id !== ws) void pair(); else void captures()
  })
  root.addEventListener('keydown', (e) => { if ((e as KeyboardEvent).key === 'Escape') { close(); tab.focus() } })
  document.addEventListener('pointerdown', (e) => { if (!pop.hidden && !e.composedPath().includes(host)) close() })
  document.body.append(host)
}
