// The interior Gaussian splat of a scan, trained offline from its panoramas (the splat workstream), drawn by Spark in
// the scan's own frame. It is the most lifelike interior where it exists; where it does not, the scene falls back to
// the scanned mesh. The file is at /api/scan/<sid>/interior-splat (.spz or .ply) and its placing at
// /api/scan/<sid>/interior-splat.json: { transform: 16 numbers, row by row, splat space to scan frame }.
import * as THREE from 'three'
import { SplatMesh } from '@sparkjsdev/spark'
import { SplatCut, sparkFor } from '../scene/engine/splat.ts'

export class InteriorSplat {
  group = new THREE.Group()
  /** 'none': this scan has no interior splat (the usual case). */
  status: 'unknown' | 'none' | 'there' | 'loading' | 'ready' = 'unknown'
  cut = new SplatCut()
  onChange: () => void = () => {}
  private mesh: SplatMesh | null = null
  private place = new THREE.Matrix4()
  private show_ = { cur: 0, goal: 0 }
  private gone = false

  private renderer: THREE.WebGLRenderer; private scene: THREE.Scene; private url: string
  constructor(renderer: THREE.WebGLRenderer, scene: THREE.Scene, api: string, sid: string) {
    this.renderer = renderer; this.scene = scene; this.url = `${api}/api/scan/${sid}/interior-splat`
    this.group.visible = false
    void this.probe()
  }

  /** Ask once whether there is one, by reading its placing. */
  private async probe() {
    const meta = await fetch(`${this.url}.json`).then((r) => (r.ok ? r.json() : null), () => null) as { transform?: number[] | number[][] } | null
    if (this.gone) return
    const t = meta?.transform?.flat()
    if (t?.length === 16) this.place.set(...(t as Parameters<THREE.Matrix4['set']>))
    this.status = meta ? 'there' : 'none'
    if (meta && this.show_.goal) void this.load()
    this.onChange()
  }

  get shown() { return this.mesh }
  show(on: boolean) { this.show_.goal = on ? 1 : 0; if (on && this.status === 'there') void this.load() }

  private async load() {
    this.status = 'loading'; this.onChange()
    sparkFor(this.renderer, this.scene, () => this.onChange())
    try {
      const mesh = new SplatMesh({ url: this.url })
      await mesh.initialized
      if (this.gone) { mesh.dispose(); return }
      mesh.applyMatrix4(this.place)
      mesh.opacity = 0
      this.group.add(mesh); this.mesh = mesh; this.status = 'ready'
    } catch (e) {
      console.warn('[scene] interior splat unavailable:', (e as Error).message)
      this.status = 'none'
    }
    this.onChange()
  }

  update(dt: number): boolean {
    const s = this.show_, moving = s.cur !== s.goal
    if (moving) s.cur += Math.sign(s.goal - s.cur) * Math.min(Math.abs(s.goal - s.cur), dt / 0.5)
    this.group.visible = s.cur > 0.001 && !!this.mesh
    if (this.mesh) this.mesh.opacity = s.cur
    return moving && !!this.mesh
  }

  dispose() { this.gone = true; this.mesh?.dispose() }
}
