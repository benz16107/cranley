import { create } from 'zustand'
import type { Fix } from './dsp.ts'

/* The phone's link to the server: one pairing token (from the desktop's QR code, or made here when the phone is used
   by itself), the phone view it opens, and capture uploads. Routes: server/threshold/api/capture.py. */

export type Status = 'pass' | 'warn' | 'fail' | 'unknown'
export type Outcome = { verdict: 'confirmed' | 'contradicted' | 'measured'; status: Status; value: number | null; err: number | null; text: string; method: string; confidence: string; points?: Points | null }
export type TaskKind = 'width' | 'step' | 'slope' | 'alarm' | 'floor_height' | 'heading'
export type Task = { id: string; kind: TaskKind; sid: string; title: string; why: string; how: string; tools: string[]; findings: string[]; room: string | null; opening: string | null
  scan_value: number | null; threshold: number | null; unit: string; standard: string | null; status: 'open' | 'done'; outcome: Outcome | null; capture: string | null }
export type Room = { id: string; label: string; floor: string | null }
export type Building = { sid: string; name: string; address: string | null; lat?: number | null; lon?: number | null; walls: boolean; rooms: Room[] }
export type Metric = { id: string; label: string; value: number | null; unit: string }
export type Check = { id: string; rule: string; measured: number | null; threshold: number | null; unit: string; status: Status; standard: string | null; kind?: string }
export type Finding = { id: string; title: string; status: Status; detail: string; media: { kind: string; ref: string }[]; source: { layer: string; method: string; confidence: string; note: string | null } }
export type Action = { id: string; label: string; tool: string; inputs: Record<string, unknown> }
export type Result = { run: string; tool: string; sid: string | null; status: 'running' | 'done' | 'error'; at: number | null; phone: boolean; verdict: { status: Status; text: string } | null; error: string | null
  step: string | null; metrics: Metric[]; checks: Check[]; findings: Finding[]; actions: Action[] }
export type Capture = { id: string; at: number; kind: 'photo' | 'video' | 'audio' | 'reading'; task?: string; tool?: string; scan?: string; room?: string; note?: string; values?: Record<string, unknown>; file: string | null; mime: string | null; result: Record<string, unknown> | null }
export type Question = { id: string; text: string; input: { type?: string; enum?: string[]; 'x-unit'?: string; minimum?: number; maximum?: number; default?: unknown } }
export type View = { brief: string | null; summary: string | null; buildings: Building[]; questions: Question[]; tasks: Task[]; captures: Capture[]; results: Result[]; busy: boolean; plan: { text: string; status: string }[]; seq: number }
export type Points = { corners: [number, number][]; a: [number, number]; b: [number, number] }
export type Meta = { kind: Capture['kind']; task?: string; tool?: string; scan?: string | null; room?: string | null; opening?: string | null; note?: string; fix?: Fix | null
  heading_deg?: number | null; heading_accuracy_deg?: number | null; tilt?: Record<string, number>; values?: Record<string, unknown> }
export type Reply = { capture: Capture; outcome?: Outcome; problem?: string; points?: Points | null; run?: string; status?: Status; text?: string; metrics?: Metric[]; view: View }
export type Place = { address: string | null; city: string | null; lat: number; lon: number; distance_m: number; scans: { sid: string; name: string; kind: string }[] }

const KEY = 'threshold.phone', SID = 'threshold.phone.sid'
const mem = { get: (k: string) => { try { return localStorage.getItem(k) } catch { return null } }, set: (k: string, v: string | null) => { try { if (v == null) localStorage.removeItem(k); else localStorage.setItem(k, v) } catch { /* private window */ } } }

export type Unit = 'in' | 'cm'
type State = { token: string | null; paired: boolean; view: View | null; state: 'idle' | 'loading' | 'ready' | 'expired' | 'offline'; sid: string | null; unit: Unit }
export const usePhone = create<State>(() => ({ token: null, paired: false, view: null, state: 'idle', sid: mem.get(SID), unit: mem.get(KEY + '.unit') === 'cm' ? 'cm' : 'in' }))
/** Lengths are shown and typed in the person's unit; the server only ever sees metres. */
export function setUnit(unit: Unit) { mem.set(KEY + '.unit', unit); usePhone.setState({ unit }) }
const set = usePhone.setState

function show(view: View) {
  const cur = usePhone.getState().sid
  const sid = view.buildings.some((b) => b.sid === cur) ? cur : view.buildings.at(-1)?.sid ?? null
  set({ view, state: 'ready', sid })
}
export function choose(sid: string) { mem.set(SID, sid); set({ sid }) }
export const building = (s: State) => s.view?.buildings.find((b) => b.sid === s.sid) ?? null

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const token = usePhone.getState().token
  const r = await fetch(`/api/phone/${token}${path}`, init).catch(() => null)
  if (!r) { set({ state: usePhone.getState().view ? 'ready' : 'offline' }); throw new Error('The server is not answering. Check that this phone is on the same network.') }
  if (r.status === 401) { mem.set(KEY, null); set({ token: null, view: null, state: 'expired', paired: false }); throw new Error('This phone link has expired.') }
  if (!r.ok) throw new Error(((await r.json().catch(() => ({}))) as { detail?: string }).detail ?? `The server answered ${r.status}.`)
  return r.json()
}
const json = (body: unknown): RequestInit => ({ method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) })

/** On load: a token in the link (from the QR code) wins and is taken out of the address bar; else the one kept here. */
export async function boot() {
  const q = new URLSearchParams(location.search), linked = q.get('t')
  if (linked) { mem.set(KEY, linked); mem.set(KEY + '.paired', '1'); q.delete('t'); history.replaceState(history.state, '', location.pathname + (q.size ? '?' + q : '')) }
  const token = mem.get(KEY)
  if (!token) { set({ state: 'idle' }); return }
  set({ token, paired: mem.get(KEY + '.paired') === '1', state: 'loading' })
  await refresh()
}
export async function refresh() {
  if (!usePhone.getState().token) return
  try { show(await call<View>('')) } catch { /* the state says why */ }
}
/** A phone used by itself makes its own workspace the first time it needs one. */
export async function ensure(): Promise<void> {
  if (usePhone.getState().token) return
  const r = await fetch('/api/phone/start', json({})).catch(() => null)
  if (!r?.ok) throw new Error('The server is not answering.')
  const { token } = (await r.json()) as { token: string }
  mem.set(KEY, token); mem.set(KEY + '.paired', null)
  set({ token, paired: false })
  await refresh()
}
export function forget() { mem.set(KEY, null); mem.set(KEY + '.paired', null); set({ token: null, view: null, state: 'idle', paired: false, sid: null }) }

/** Send one capture. XHR, not fetch, because a video upload needs a progress bar. */
export async function send(meta: Meta, file?: Blob | null, onProgress?: (fraction: number) => void): Promise<Reply> {
  await ensure()
  const token = usePhone.getState().token
  return new Promise((resolve, reject) => {
    const x = new XMLHttpRequest()
    x.open('POST', `/api/phone/${token}/capture?meta=${encodeURIComponent(JSON.stringify({ taken: Date.now() / 1000, device: navigator.userAgent.slice(0, 280), ...meta }))}`)
    x.upload.onprogress = (e) => { if (e.lengthComputable) onProgress?.(e.loaded / e.total) }
    x.onerror = () => reject(new Error('The upload did not reach the server. It is still on this phone: try again.'))
    x.onload = () => {
      let body: Reply & { detail?: string }
      try { body = JSON.parse(x.responseText) } catch { reject(new Error(`The server answered ${x.status}.`)); return }
      if (x.status === 401) { reject(new Error('This phone link has expired.')); return }
      if (x.status >= 400) { reject(new Error(body.detail ?? `The server answered ${x.status}.`)); return }
      show(body.view); resolve(body)
    }
    x.send(file ?? null)
  })
}

export async function locate(fix: Fix) {
  await ensure()
  return call<{ here: Place[]; verdict: { status: Status; text: string } | null; actions: Action[] }>('/locate', json({ lat: fix.lat, lon: fix.lon, accuracy_m: fix.accuracy_m }))
}
export async function place(sid: string) { await ensure(); show(await call<View>('/place', json({ sid }))); choose(sid) }
export async function brief(text: string | null, sid?: string | null) { await ensure(); await call('/brief', json({ text, sid: sid ?? null })); set((s) => ({ view: s.view && { ...s.view, busy: true } })) }
export async function answer(id: string, value: unknown) { show(await call<View>('/answer', json({ id, value }))) }
export async function runTool(tool: string, inputs: Record<string, unknown>) {
  await ensure()
  const r = await call<{ status: string; error?: string | null; view: View }>(`/run/${tool}`, json(inputs))
  show(r.view)
  return r
}
export const captureFile = (id: string) => `/api/capture/${id}/file`
export const captureFrame = (ref: string) => { const [id, n] = ref.split('#'); return n == null ? captureFile(id) : `/api/capture/${id}/frame/${n}.jpg` }

/** A photo as an upright JPEG no longer than `px` on its long side: smaller to send, and never HEIC. */
export async function shrink(file: Blob, px = 2000): Promise<Blob> {
  try {
    const bmp = await createImageBitmap(file, { imageOrientation: 'from-image' })
    const s = Math.min(1, px / Math.max(bmp.width, bmp.height))
    const c = document.createElement('canvas')
    c.width = Math.round(bmp.width * s); c.height = Math.round(bmp.height * s)
    c.getContext('2d')!.drawImage(bmp, 0, 0, c.width, c.height)
    bmp.close()
    return await new Promise<Blob>((res, rej) => c.toBlob((b) => (b ? res(b) : rej(new Error('encode'))), 'image/jpeg', 0.86))
  } catch { return file } // a browser that cannot decode it sends the original; the server says if it cannot read it
}
