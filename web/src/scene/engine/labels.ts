// DOM labels pinned to points in the building: room names, pins, measurements. Text stays crisp and selectable.
import * as THREE from 'three'
import { sightBlocked, type Model } from '../model.ts'
import type { Vec3 } from '../types.ts'

export interface LabelSpec {
  id: string; pos: Vec3; floor: number
  make: () => HTMLElement   // called once per id
  spanM?: number            // real width the label stands for; hidden when that is too few pixels to hold it
  minPx?: number
  skipWall?: string         // the label's own wall never hides it
  modes?: ('doll' | 'pano')[]
  ride?: number             // sits on top of the walls: this is the wall height, and the label follows the cut-away down
  elem?: number             // style slot whose wall height the label rides
}

export class Labels {
  root = document.createElement('div')
  private items = new Map<string, { spec: LabelSpec; el: HTMLElement; on: boolean }>()
  private v = new THREE.Vector3()
  private m: Model
  constructor(m: Model) {
    this.m = m; this.root.className = 'th-labels'
  }

  sync(specs: LabelSpec[]) {
    const keep = new Set(specs.map((s) => s.id))
    for (const [id, it] of this.items) if (!keep.has(id)) { it.el.remove(); this.items.delete(id) }
    for (const spec of specs) {
      const it = this.items.get(spec.id)
      if (it) { it.spec = spec; continue }
      const el = spec.make(); el.classList.add('th-label'); el.hidden = true
      this.root.appendChild(el); this.items.set(spec.id, { spec, el, on: false })
    }
  }

  /** Place every label. `lift(floor)` is how far that floor is currently raised; `eye` is set inside a panorama. */
  update(camera: THREE.PerspectiveCamera, w: number, h: number, lift: (f: number) => number, cut: (elem: number | undefined, full: number) => number, shown: (f: number) => boolean, pano: { eye: Vec3; floorId: string | null } | null, opacity: number) {
    const f = h / 2 / Math.tan((camera.fov * Math.PI) / 360)
    this.root.style.opacity = String(opacity)
    for (const it of this.items.values()) {
      const { spec, el } = it
      let on = shown(spec.floor) && (!spec.modes || spec.modes.includes(pano ? 'pano' : 'doll'))
      if (on) {
        this.v.set(spec.pos[0], spec.pos[1], spec.pos[2] + lift(spec.floor) + (spec.ride ? cut(spec.elem, spec.ride) : 0)).applyMatrix4(camera.matrixWorldInverse)
        const depth = -this.v.z
        on = depth > 0.1
        if (on && spec.spanM) on = (spec.spanM * f) / depth >= (spec.minPx ?? 40)
        if (on && pano) {
          const d = Math.hypot(spec.pos[0] - pano.eye[0], spec.pos[1] - pano.eye[1])
          on = d < 14 && this.m.plan.floors[spec.floor]?.id === pano.floorId && !sightBlocked(this.m, pano.floorId!, pano.eye[0], pano.eye[1], spec.pos[0], spec.pos[1], spec.skipWall)
        }
        if (on) {
          const x = w / 2 + (this.v.x * f) / depth, y = h / 2 - (this.v.y * f) / depth
          on = x > -80 && x < w + 80 && y > -40 && y < h + 40
          if (on) el.style.transform = `translate(${x.toFixed(1)}px, ${y.toFixed(1)}px)`
        }
      }
      if (on !== it.on) { el.hidden = !on; it.on = on }
    }
  }
}

/** Small element builder: tag.class with text children. */
export function h(tag: string, cls: string, ...kids: (string | HTMLElement)[]) {
  const el = document.createElement(tag); el.className = cls; el.append(...kids); return el
}
