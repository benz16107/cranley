// The drone Gaussian splat, drawn by Spark in the same three.js scene. The file is 70 to 660 MB and its Gaussians are in
// no spatial order, so a prefix is a fair sample of the whole: we read one stream and show 4 MB, then 24 MB, then 72 MB.
import * as THREE from 'three'
import type { SparkRenderer, SplatEdit, SplatEditSdf, SplatMesh } from '@sparkjsdev/spark'

type Spark = typeof import('@sparkjsdev/spark')
let spark: Spark | null = null
let loading: Promise<Spark> | null = null
/** Spark is 2.7 MB, so it loads with the first splat shown, not with the building view. */
export const loadSpark = (): Promise<Spark> => (loading ??= import('@sparkjsdev/spark').then((m) => (spark = m)))
import { splatUrlDev } from '../dev/splatSource.ts'

/** The one place that knows where a splat comes from. Swap the body for the data route once it lands. */
export async function splatUrl(api: string, sid: string): Promise<string> {
  const route = `${api}/api/scan/${sid}/splat`
  const ok = await fetch(route, { method: 'HEAD' }).then((r) => r.ok).catch(() => false)
  return ok ? route : splatUrlDev(sid)
}

// 72 MB is about 1.1 million Gaussians. 96 MB (1.48 million) dropped a small house seen close, inside its
// surroundings, to 45 frames a second on a Radeon 780M; the picture is filled by them and the fill is the cost.
const STAGES_MB = [4, 24, 72]

interface Prefix { bytes: Uint8Array; count: number; total: number; centre: THREE.Vector3; radius: number }

/** Turn the first `len` bytes of an INRIA splat PLY into a valid, smaller PLY. Exported for the self-check below.
    `stray` names points where the capture can hold nothing real (inside the rooms); Gaussians there are dropped. */
export function plyPrefix(buf: Uint8Array, len: number, stray?: (x: number, y: number, z: number) => boolean): Prefix | null {
  const head = new TextDecoder().decode(buf.subarray(0, Math.min(len, 4096)))
  const end = head.indexOf('end_header\n')
  if (end < 0) return null
  const headLen = end + 'end_header\n'.length, header = head.slice(0, headLen)
  const props = [...header.matchAll(/property float (\w+)/g)].map((m) => m[1])
  const total = Number(/element vertex (\d+)/.exec(header)?.[1] ?? 0), rec = props.length * 4
  const count = Math.min(total, Math.floor((len - headLen) / rec))
  if (!rec || count < 1) return null
  const newHead = new TextEncoder().encode(header.replace(/element vertex \d+/, `element vertex ${count}`))
  const out = new Uint8Array(newHead.length + count * rec)
  out.set(newHead); out.set(buf.subarray(headLen, headLen + count * rec), newHead.length)
  const f = new DataView(out.buffer, newHead.length), ix = props.indexOf('x') * 4, iy = props.indexOf('y') * 4, iz = props.indexOf('z') * 4
  const scales = ['scale_0', 'scale_1', 'scale_2'].map((p) => props.indexOf(p) * 4), iop = props.indexOf('opacity') * 4
  // A sample has gaps where the missing Gaussians were. Grow each one a little (scales are stored as logs) to close them.
  const grow = Math.log(Math.min(2.4, Math.pow(total / count, 0.4)))
  const zs: number[] = []
  for (let i = 0; i < count; i++) {
    const o = i * rec, x = f.getFloat32(o + ix, true), y = f.getFloat32(o + iy, true), z = f.getFloat32(o + iz, true)
    if (grow > 0.01) for (const s of scales) if (s >= 0) f.setFloat32(o + s, f.getFloat32(o + s, true) + grow, true)
    if ((Math.hypot(x, y) > 70 || stray?.(x, y, z)) && iop >= 0) f.setFloat32(o + iop, -12, true) // far background (the drone's horizon haze), or a stray inside the house
    else if (i % 8 === 0 && Math.hypot(x, y) < 9) zs.push(z)
  }
  // The capture is centred on the property: orbit the origin, at the typical height of what stands there.
  const mid = (v: number[]) => v.sort((a, b) => a - b)[v.length >> 1] ?? 0
  return { bytes: out, count, total, centre: new THREE.Vector3(0, 0, mid(zs)), radius: 26 }
}

/** Spark draws every splat in the scene through one renderer object. Whoever shows a splat first makes it. */
export async function sparkFor(renderer: THREE.WebGLRenderer, scene: THREE.Scene, onDirty: () => void): Promise<SparkRenderer> {
  const { SparkRenderer } = await loadSpark()
  const held = scene.userData as { spark?: SparkRenderer }
  // Each Gaussian is drawn out to sqrt(6) standard deviations (Spark's default is sqrt(8)) and no wider than 256 px:
  // a quarter less of the screen to fill per Gaussian, which is what a close view of a capture is short of.
  if (!held.spark) { held.spark = new SparkRenderer({ renderer, onDirty, maxStdDev: Math.sqrt(6), maxPixelRadius: 256 }); scene.add(held.spark) }
  return held.spark
}

export interface CutBox { centre: number[]; half: number[] }
/** Hides the Gaussians of one splat inside boxes and beyond a radius: the roof off a house, the haze off a horizon. */
export class SplatCut {
  // made on first use: a mesh means Spark has loaded
  private edit: SplatEdit | null = null
  private pool: SplatEditSdf[] = []
  private far: SplatEditSdf | null = null
  private key = ''
  /** boxes: centres and half sizes in the splat's own frame. beyond: metres from `about`, 0 for no limit. */
  set(mesh: SplatMesh | null, boxes: CutBox[], beyond = 0, about: number[] = [0, 0, 0]) {
    if (!mesh || !spark) return
    const { SplatEdit, SplatEditSdf, SplatEditSdfType } = spark
    this.edit ??= new SplatEdit({ softEdge: 0.15 })
    this.far ??= new SplatEditSdf({ type: SplatEditSdfType.SPHERE, opacity: 0, invert: true })
    const { edit, far } = this
    const on = boxes.length > 0 || beyond > 0
    if (on && edit.parent !== mesh) mesh.add(edit); else if (!on) edit.removeFromParent()
    const key = JSON.stringify([boxes, beyond, about, mesh.uuid])
    if (key === this.key) return
    this.key = key
    while (this.pool.length < boxes.length) this.pool.push(new SplatEditSdf({ type: SplatEditSdfType.BOX, opacity: 0 }))
    const used = this.pool.slice(0, boxes.length)
    used.forEach((sdf, i) => { sdf.position.set(boxes[i].centre[0], boxes[i].centre[1], boxes[i].centre[2]); sdf.scale.set(boxes[i].half[0], boxes[i].half[1], boxes[i].half[2]) })
    if (beyond > 0) { far.position.set(about[0], about[1], about[2]); far.radius = beyond }
    edit.sdfs = [...used, ...(beyond > 0 ? [far] : [])]
    for (const sdf of edit.sdfs) { if (sdf.parent !== edit) edit.add(sdf); sdf.updateMatrixWorld(true) }
  }
}

export class SplatView {
  group = new THREE.Group()
  cut = new SplatCut()
  /** The mesh on show, for `cut`. It changes as more of the file arrives. */
  get shown() { return this.mesh }
  centre = new THREE.Vector3(); radius = 26
  status: 'idle' | 'loading' | 'ready' | 'missing' = 'idle'
  progress = 0 // 0..1 of the bytes we mean to read
  splats = 0; total = 0
  onChange: () => void = () => {}
  private spark: SparkRenderer | null = null
  private mesh: SplatMesh | null = null
  private opacity = { cur: 0, goal: 0 }
  private abort: AbortController | null = null
  private gone = false

  private renderer: THREE.WebGLRenderer; private scene: THREE.Scene; private api: string; private sid: string
  private stray?: (x: number, y: number, z: number) => boolean
  /** `stray`: where the capture can hold nothing real. The capture shares the scan's frame, so this is the plan's rooms. */
  constructor(renderer: THREE.WebGLRenderer, scene: THREE.Scene, api: string, sid: string, stray?: (x: number, y: number, z: number) => boolean) {
    this.renderer = renderer; this.scene = scene; this.api = api; this.sid = sid; this.stray = stray; this.group.visible = false
  }

  /** Start streaming. Safe to call again; it only loads once. */
  async load() {
    if (this.status !== 'idle') return
    this.status = 'loading'; this.onChange()
    try {
      const sr = await sparkFor(this.renderer, this.scene, () => this.onChange())
      if (this.gone) return // closed while Spark loaded; dispose() already cleared the scene
      this.spark = sr
      this.abort = new AbortController()
      const res = await fetch(await splatUrl(this.api, this.sid), { signal: this.abort.signal })
      if (!res.ok || !res.body) throw new Error(`splat ${res.status}`)
      const want = STAGES_MB[STAGES_MB.length - 1] * 2 ** 20
      const buf = new Uint8Array(Math.min(want, Number(res.headers.get('content-length')) || want))
      const reader = res.body.getReader()
      let got = 0, stage = 0
      while (got < buf.length) {
        const { done, value } = await reader.read()
        if (done) break
        const take = Math.min(value.length, buf.length - got)
        buf.set(value.subarray(0, take), got); got += take
        this.progress = got / buf.length
        if (got >= Math.min(STAGES_MB[stage] * 2 ** 20, buf.length)) { await this.swap(buf, got); stage++ }
        else this.onChange()
      }
      void reader.cancel().catch(() => {})
      if (stage === 0 || got < buf.length) await this.swap(buf, got)
      this.status = this.mesh ? 'ready' : 'missing'
    } catch (e) {
      if ((e as Error).name !== 'AbortError') { console.warn('[scene] splat unavailable:', (e as Error).message); this.status = this.mesh ? 'ready' : 'missing' }
    }
    this.onChange()
  }

  private async swap(buf: Uint8Array, len: number) {
    const p = plyPrefix(buf, len, this.stray)
    if (!p) return
    const { SplatMesh } = spark! // loaded by sparkFor in load()
    const mesh = new SplatMesh({ fileBytes: p.bytes, fileName: 'splat.ply' } as ConstructorParameters<typeof SplatMesh>[0])
    await mesh.initialized
    mesh.opacity = this.opacity.cur
    const old = this.mesh
    this.group.add(mesh); this.mesh = mesh
    if (old) { old.removeFromParent(); old.dispose() }
    if (!old) { this.centre.copy(p.centre); this.radius = p.radius }
    this.splats = p.count; this.total = p.total
    this.onChange()
  }

  show(on: boolean) { this.opacity.goal = on ? 1 : 0; if (on) void this.load() }

  update(dt: number): boolean {
    const o = this.opacity
    const moving = o.cur !== o.goal
    if (moving) { o.cur += Math.sign(o.goal - o.cur) * Math.min(Math.abs(o.goal - o.cur), dt / 0.7); }
    this.group.visible = o.cur > 0.001 && !!this.mesh
    if (this.mesh) this.mesh.opacity = o.cur * o.cur * (3 - 2 * o.cur)
    return moving
  }

  dispose() {
    this.gone = true
    this.abort?.abort(); this.mesh?.dispose(); this.mesh = null
    if (this.spark) { this.spark.removeFromParent(); (this.spark as unknown as { dispose?: () => void }).dispose?.(); delete (this.scene.userData as { spark?: SparkRenderer }).spark }
  }
}
