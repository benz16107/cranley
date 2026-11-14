// Contract 4 overlays as 3D objects: route, water, box, pins, plus opening measurements. Lens and rule are styles (model.ts).
// Everything here lives in scan coordinates, so the same objects are right in the dollhouse and inside a panorama.
import * as THREE from 'three'
import { Line2 } from 'three/addons/lines/Line2.js'
import { LineGeometry } from 'three/addons/lines/LineGeometry.js'
import { LineMaterial } from 'three/addons/lines/LineMaterial.js'
import { LineSegments2 } from 'three/addons/lines/LineSegments2.js'
import { LineSegmentsGeometry } from 'three/addons/lines/LineSegmentsGeometry.js'
import { anchorPoint, centroid, fmtM, openingSpan, sightBlocked, statusColor, wallBoxes, waterDepth, type Model, type RGB, anchorKey } from '../model.ts'
import type { Tokens } from '../tokens.ts'
import type { Overlay, Pick, Status, Vec3 } from '../types.ts'
import type { Dollhouse } from './dollhouse.ts'
import { h, type LabelSpec } from './labels.ts'
import { modelGeometry, modelMaterial } from './models.ts'

type Of<K extends string> = Extract<Overlay, { kind: K }>

const WATER_FRAG = /* glsl */ `
  varying vec3 vW; uniform vec3 uCol; uniform float uOn, uFade; uniform vec2 uCentre;
  void main() {
    vec3 v = normalize(cameraPosition - vW);
    float fres = pow(1.0 - abs(v.z), 3.0);                 // more reflective at a grazing angle, clearer looking down
    vec3 col = mix(uCol, vec3(0.86, 0.91, 0.93), fres * 0.55);
    float edge = uFade > 0.0 ? 1.0 - smoothstep(uFade * 0.7, uFade, distance(vW.xy, uCentre)) : 1.0; // wide water ends where the surroundings do
    gl_FragColor = vec4(col, (0.42 + 0.4 * fres) * uOn * edge);
  }`

// A label keeps its DOM element for as long as its id stays the same, so every id below carries what its chip says:
// an id made only of the overlay's place in the list let one tool's chip keep its words when another tool's
// overlays took that place.
export class Overlays3D {
  group = new THREE.Group()
  private made: THREE.Object3D[] = []
  private models: THREE.InstancedMesh[] = [] // their geometry is shared and cached, so it is never disposed with them
  /** A model a box asked for has arrived: the engine sets the overlays again. */
  onModels = () => {}
  private water: THREE.Mesh
  private waterOn = { cur: 0, goal: 0 }
  private waterLines = new THREE.Group() // rides at the water level
  private res = new THREE.Vector2(1, 1)

  private m: Model; private tok: Tokens; private doll: Dollhouse; private onPick: (p: Pick) => void
  constructor(m: Model, tok: Tokens, doll: Dollhouse, onPick: (p: Pick) => void) {
    this.m = m; this.tok = tok; this.doll = doll; this.onPick = onPick
    const b = m.bounds, pad = 9
    const geo = new THREE.PlaneGeometry(b.maxX - b.minX + pad * 2, b.maxY - b.minY + pad * 2)
    this.water = new THREE.Mesh(geo, new THREE.ShaderMaterial({
      vertexShader: 'varying vec3 vW; void main(){ vW = (modelMatrix * vec4(position,1.0)).xyz; gl_Position = projectionMatrix * viewMatrix * vec4(vW,1.0); }',
      fragmentShader: WATER_FRAG, uniforms: { uCol: { value: new THREE.Vector3(...tok.water) }, uOn: { value: 0 }, uFade: { value: 0 }, uCentre: { value: new THREE.Vector2((b.minX + b.maxX) / 2, (b.minY + b.maxY) / 2) } }, transparent: true, depthWrite: false, side: THREE.DoubleSide,
    }))
    this.span = Math.max(b.maxX - b.minX, b.maxY - b.minY) + pad * 2
    this.water.position.set((b.minX + b.maxX) / 2, (b.minY + b.maxY) / 2, 0)
    this.water.renderOrder = 5; this.water.visible = false
    this.group.add(this.water, this.waterLines)
  }

  setSize(w: number, hgt: number) { this.res.set(w, hgt) }
  private span: number
  /** In real surroundings the water covers the street and the neighbours too, out to `fade` metres; 0 keeps it to the building. */
  setReach(fade: number) {
    const k = fade ? (fade * 2.2) / this.span : 1
    this.water.scale.set(k, k, 1); (this.water.material as THREE.ShaderMaterial).uniforms.uFade.value = fade
  }

  private line(points: number[], color: RGB, width: number, opts: { segments?: boolean; opacity?: number; order?: number; overlay?: boolean } = {}) {
    const mat = new LineMaterial({ linewidth: width, transparent: true, opacity: opts.opacity ?? 1, resolution: this.res, depthTest: !opts.overlay, depthWrite: false })
    mat.color.setRGB(color[0], color[1], color[2], THREE.SRGBColorSpace)
    const obj = opts.segments ? new LineSegments2(new LineSegmentsGeometry().setPositions(points), mat) : new Line2(new LineGeometry().setPositions(points), mat)
    obj.renderOrder = opts.order ?? 7
    return obj
  }
  /** A line that reads on any photo: a pale casing under a coloured core. */
  private cased(parent: THREE.Object3D, points: number[], color: RGB, width: number, segments = false) {
    const a = this.line(points, this.tok.paper, width + 3.5, { segments, opacity: 0.92, order: 7 }), b = this.line(points, color, width, { segments, order: 8 })
    parent.add(a, b); this.made.push(a, b)
  }

  /** Rebuild from the overlay list. Returns the labels that go with the 3D objects. */
  set(overlays: Overlay[], measures: boolean, eye: { pos: Vec3; floorId: string | null } | null = null): LabelSpec[] {
    const { m, tok, doll } = this
    for (const o of this.made) { o.removeFromParent(); const mesh = o as THREE.Mesh; mesh.geometry?.dispose(); (mesh.material as THREE.Material)?.dispose() }
    this.made = []
    for (const im of this.models) { im.removeFromParent(); im.dispose() }
    this.models = []
    const stand: Record<string, { geo: THREE.BufferGeometry; floor: number; at: THREE.Matrix4[]; tint: THREE.Color[] }> = {} // one instanced mesh per model and floor
    const labels: LabelSpec[] = []
    const chip = (cls: string, status: Status | null, ...kids: (string | HTMLElement)[]) => { const el = h('div', `th-chip ${cls}`, ...kids); if (status) el.dataset.status = status; return el }
    let waterLevel: number | null = null

    overlays.forEach((ov, oi) => {
      if (ov.kind === 'route') {
        const r = ov as Of<'route'>, f = m.floorOf.get(r.floor) ?? 0, fz = m.floorZ[f], g = doll.floorGroups[f]
        if (!g || !Array.isArray(r.points) || r.points.length < 2) return
        const flat = r.points.flatMap((p) => [p[0], p[1], Math.max(p[2] - fz, 0) + 0.06])
        this.cased(g, flat, tok.accent, 3.5)
        let len = 0
        for (let i = 1; i < r.points.length; i++) len += Math.hypot(r.points[i][0] - r.points[i - 1][0], r.points[i][1] - r.points[i - 1][1])
        const end = r.points[r.points.length - 1]
        labels.push({ id: `route${oi}.${r.label ?? ''}.${r.points.length}.${r.points[0]?.join(',')}`, pos: [end[0], end[1], fz + 0.3], floor: f, make: () => chip('th-chip-route', null, h('span', 'th-chip-text', r.label ?? 'Route'), h('span', 'th-num', fmtM(len))) })
        for (const [ci, c] of (r.chokes ?? []).entries()) {
          // the caliper: a bar across the path, exactly as wide as the measured clearance
          let best = 0, bd = Infinity
          for (let i = 0; i + 1 < r.points.length; i++) {
            const mx = (r.points[i][0] + r.points[i + 1][0]) / 2, my = (r.points[i][1] + r.points[i + 1][1]) / 2, d = Math.hypot(mx - c.point[0], my - c.point[1])
            if (d < bd) { bd = d; best = i }
          }
          const a = r.points[best], b = r.points[best + 1], L = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1
          const nx = -(b[1] - a[1]) / L, ny = (b[0] - a[0]) / L, tx = (b[0] - a[0]) / L, ty = (b[1] - a[1]) / L, hw = c.width / 2, z = 0.09, tk = 0.11
          const P = (s: number, t: number) => [c.point[0] + nx * s + tx * t, c.point[1] + ny * s + ty * t, z]
          this.cased(g, [...P(-hw, 0), ...P(hw, 0), ...P(-hw, -tk), ...P(-hw, tk), ...P(hw, -tk), ...P(hw, tk)], statusColor(c.status, tok), 3, true)
          labels.push({ id: `choke${oi}.${ci}.${c.width}.${c.status}`, pos: [c.point[0], c.point[1], fz + 0.5], floor: f, make: () => chip('th-chip-measure', c.status, h('span', 'th-num', fmtM(c.width))) })
        }
      } else if (ov.kind === 'water') {
        const w = ov as Of<'water'>
        if (typeof w.level_m !== 'number') return
        waterLevel = w.level_m
        const rooms = m.plan.rooms.filter((r) => r.polygon.length > 2 && r.label !== 'Void').sort((a, b) => (b.area ?? 0) - (a.area ?? 0)).slice(0, 10)
        for (const r of rooms) {
          const f = m.floorOf.get(r.floor) ?? 0, d = waterDepth(m, f, w.level_m)
          if (d <= 0.005) continue
          const c = centroid(r.polygon)
          labels.push({ id: `water${oi}.${r.id}.${w.level_m}`, pos: [c[0], c[1], w.level_m + 0.02], floor: f, spanM: Math.sqrt(r.area ?? 9), minPx: 64, make: () => chip('th-chip-water', null, h('span', 'th-chip-text', 'depth'), h('span', 'th-num', fmtM(d))) })
        }
      } else if (ov.kind === 'box') {
        const b = ov as Of<'box'>
        if (!Array.isArray(b.center) || !Array.isArray(b.size)) return
        const at = anchorPoint(m, { point: b.center })!, g = doll.floorGroups[at.floor], col = statusColor(b.status, tok)
        const holder = new THREE.Group()
        holder.position.set(b.center[0], b.center[1], b.center[2] - m.floorZ[at.floor]); holder.rotation.z = ((b.yaw_deg ?? 0) * Math.PI) / 180
        // With a model, the model is the object and the box stays as a faint outline of exactly what was measured.
        const shape = typeof b.model === 'string' ? modelGeometry(b.model, this.onModels) : null
        const foot = !!shape && !!b.quiet && b.status === 'pass' // a placed piece with nothing wrong: its outline on the floor is enough
        const geo = new THREE.BoxGeometry(b.size[0], b.size[1], b.size[2])
        const fill = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ transparent: true, opacity: foot ? 0 : shape ? 0.07 : 0.2, depthWrite: false }))
        fill.material.color.setRGB(col[0], col[1], col[2], THREE.SRGBColorSpace); fill.renderOrder = 6; fill.visible = !foot
        const edges = new THREE.EdgesGeometry(geo), hx = b.size[0] / 2, hy = b.size[1] / 2, z = 0.02 - b.size[2] / 2
        const pts = foot ? [-hx, -hy, z, hx, -hy, z, hx, -hy, z, hx, hy, z, hx, hy, z, -hx, hy, z, -hx, hy, z, -hx, -hy, z] : Array.from(edges.getAttribute('position').array)
        edges.dispose()
        holder.add(fill, this.line(pts, tok.paper, shape ? 3.5 : 5, { segments: true, opacity: shape ? 0.7 : 0.9, order: 7 }), this.line(pts, col, shape ? 1.5 : 2, { segments: true, order: 8 }))
        if (shape) {
          holder.scale.set(b.size[0], b.size[1], b.size[2]); holder.updateMatrix(); holder.scale.set(1, 1, 1)
          const s = (stand[`${b.model}|${at.floor}`] ??= { geo: shape, floor: at.floor, at: [], tint: [] })
          s.at.push(holder.matrix.clone()); s.tint.push(new THREE.Color(...tok.paper).lerp(new THREE.Color(col[0], col[1], col[2]), b.status === 'pass' ? 0 : 0.3)) // colour only where something needs a look; the outline still says pass
        }
        g.add(holder); this.made.push(holder, ...holder.children)
        const dims = `${b.size[0].toFixed(2)} × ${b.size[1].toFixed(2)} × ${b.size[2].toFixed(2)} m`
        if (!b.quiet) labels.push({ id: `box${oi}.${b.label ?? ''}.${b.status}.${b.size.join('x')}`, pos: [b.center[0], b.center[1], b.center[2] + b.size[2] / 2 + 0.12], floor: at.floor, make: () => chip('th-chip-box', b.status, h('span', 'th-chip-text', b.label ?? 'Object'), h('span', 'th-num', dims)) })
      } else if (ov.kind === 'marks') { // the scene's own, never a tool's: dimension lines and zones round a placed piece (furnish.ts)
        const k = ov as unknown as { floor: number; id: string; lines: { points: Vec3[]; status: Status }[]; chips: { point: Vec3; text: string; status: Status }[] }
        const g = doll.floorGroups[k.floor], fz = m.floorZ[k.floor]
        for (const l of k.lines) this.cased(g, l.points.flatMap((q) => [q[0], q[1], q[2] - fz]), statusColor(l.status, tok), 2)
        k.chips.forEach((c, i) => labels.push({ id: `mark.${k.id}.${i}.${c.text}.${c.status}`, pos: c.point, floor: k.floor, make: () => chip('th-chip-measure', c.status === 'unknown' ? null : c.status, h('span', 'th-num', c.text)) }))
      } else if (ov.kind === 'pins') {
        const pins = (ov as Of<'pins'>).pins ?? []
        pins.forEach((p, i) => {
          const at = anchorPoint(m, p.anchor)
          if (!at) return
          const lift = 'room' in p.anchor ? 1.1 : 0
          if (lift) { // a stem ties a floating room pin to its floor
            const g = doll.floorGroups[at.floor], z0 = at.point[2] - m.floorZ[at.floor]
            const stem = this.line([at.point[0], at.point[1], z0, at.point[0], at.point[1], z0 + lift], tok.ink, 1.5, { opacity: 0.7 })
            g.add(stem); this.made.push(stem)
          }
          labels.push({
            id: `pin${oi}.${p.id}.${i}.${p.status}.${p.label}`, pos: [at.point[0], at.point[1], at.point[2] + lift], floor: at.floor, skipWall: 'wall' in p.anchor ? p.anchor.wall : 'opening' in p.anchor ? m.openingById.get(p.anchor.opening)?.wall : undefined,
            make: () => {
              const el = h('button', `th-pin${pins.length > 8 ? ' th-pin-compact' : ''}`, h('span', 'th-pin-mark', h('span', '', String(i + 1))), h('span', 'th-pin-label', p.label))
              el.dataset.status = p.status; el.dataset.at = anchorKey(p.anchor); el.setAttribute('aria-label', `${i + 1}. ${p.label} (${p.status})`)
              el.addEventListener('click', (e) => { e.stopPropagation(); this.onPick({ kind: 'pin', id: p.id }) })
              return el
            },
          })
        })
      }
    })

    for (const s of Object.values(stand)) {
      const im = new THREE.InstancedMesh(s.geo, modelMaterial, s.at.length)
      s.at.forEach((mat, i) => { im.setMatrixAt(i, mat); im.setColorAt(i, s.tint[i]) })
      im.renderOrder = 6 // with the boxes: after the floor and the panorama, before the outlines
      doll.floorGroups[s.floor].add(im); this.models.push(im)
    }

    if (measures) {
      const lines: number[][] = m.plan.floors.map(() => [])
      for (const o of m.plan.openings) {
        const f = m.floorOf.get(o.floor) ?? 0, sp = openingSpan(m, o), fz = m.floorZ[f]
        if (!o.width) continue
        const at = (s: number, z: number, off = 0) => [sp.w.a[0] + sp.dx * s - sp.dy * off, sp.w.a[1] + sp.dy * s + sp.dx * off, z]
        if (eye) { // inside a panorama: outline the opening itself, but only the ones you can actually see from here
          if (o.floor !== eye.floorId || sightBlocked(m, o.floor, eye.pos[0], eye.pos[1], o.center[0], o.center[1], o.wall)) continue
          lines[f].push(...at(sp.s0, sp.sill), ...at(sp.s0, sp.head), ...at(sp.s0, sp.head), ...at(sp.s1, sp.head), ...at(sp.s1, sp.head), ...at(sp.s1, sp.sill))
          labels.push({ id: `w.${o.id}`, pos: [o.center[0], o.center[1], fz + sp.head + 0.08], floor: f, spanM: o.width, minPx: 26, skipWall: o.wall, modes: ['pano'], make: () => chip('th-chip-measure', null, h('span', 'th-num', fmtM(o.width!))) })
        } else { // from outside: a dimension line across the opening at its foot, with end ticks
          const z = sp.sill + 0.03, tk = 0.09
          lines[f].push(...at(sp.s0, z), ...at(sp.s1, z), ...at(sp.s0, z, -tk), ...at(sp.s0, z, tk), ...at(sp.s1, z, -tk), ...at(sp.s1, z, tk))
          labels.push({ id: `w.${o.id}`, pos: [o.center[0], o.center[1], fz + 0.12], floor: f, spanM: o.width, minPx: 30, modes: ['doll'], ride: sp.sill, elem: m.wallElem.get(o.wall), make: () => chip('th-chip-measure', null, h('span', 'th-num', fmtM(o.width!))) })
        }
      }
      lines.forEach((pts, f) => {
        if (!pts.length) return
        const a = this.line(pts, tok.ink, 4.5, { segments: true, opacity: 0.6, overlay: !!eye }), b = this.line(pts, tok.paper, 1.8, { segments: true, order: 8, overlay: !!eye })
        doll.floorGroups[f].add(a, b); this.made.push(a, b)
      })
    }

    if (eye && waterLevel !== null) { // the water line drawn on each wall face, a centimetre proud of it so the wall hides the far side
      const pts: number[] = []
      for (const b of wallBoxes(m)) {
        const d = waterLevel - m.floorZ[b.floor]
        if (b.kind !== 0 || m.plan.floors[b.floor]?.id !== eye.floorId || d < b.z0 || d > b.z1) continue
        for (const off of [b.t / 2 + 0.012, -b.t / 2 - 0.012]) pts.push(b.cx + b.dx * b.s0 - b.dy * off, b.cy + b.dy * b.s0 + b.dx * off, 0, b.cx + b.dx * b.s1 - b.dy * off, b.cy + b.dy * b.s1 + b.dx * off, 0)
      }
      if (pts.length) { const l = this.line(pts, [1, 1, 1], 2, { segments: true, opacity: 0.9, order: 9 }); this.waterLines.add(l); this.made.push(l) }
    }

    doll.anim.water.goal = waterLevel ?? -1000
    this.waterOn.goal = waterLevel === null ? 0 : 1
    return labels
  }

  update(dt: number): boolean {
    const w = this.waterOn
    const moving = w.cur !== w.goal
    if (moving) { w.cur += (w.goal - w.cur) * (1 - Math.exp(-dt * 6)); if (Math.abs(w.goal - w.cur) < 0.01) w.cur = w.goal }
    this.water.visible = w.cur > 0.01
    ;(this.water.material as THREE.ShaderMaterial).uniforms.uOn.value = w.cur
    if (this.water.visible && this.doll.anim.water.cur > -900) this.water.position.z = this.waterLines.position.z = this.doll.anim.water.cur
    this.waterLines.visible = this.water.visible
    return moving
  }
}
