// The Smoke clock's fire played in the rooms. /api/show/<sid>/smoke gives CFAST's own numbers for every five
// seconds: each room's smoke layer height, its temperature and thickness, when the room is lost, and the bedrooms'
// routes out with the second each stretch is lost. Nothing here estimates: the smoke is drawn from the modelled layer
// height up to the ceiling, as dense as the modelled optical density.
import * as THREE from 'three'
import { Line2 } from 'three/addons/lines/Line2.js'
import { LineGeometry } from 'three/addons/lines/LineGeometry.js'
import { LineMaterial } from 'three/addons/lines/LineMaterial.js'
import { centroid } from '../model.ts'
import type { LabelSpec } from '../engine/labels.ts'
import type { Vec3 } from '../types.ts'
import { fetchJson, type Player, type ShowCtx, type ShowSpec, type SmokeRow, type SourceLine } from './types.ts'

interface Smoke {
  available: boolean; reason?: string; doors: 'open' | 'closed'; time: number[]; end_s: number; stopped_early: boolean
  fire_room: { id: string; label: string }; growth: string; peak_kw: number
  rooms: { id: string; label: string; floor: string; floor_z: number; ceiling_m: number | null; bedroom: boolean; fire: boolean; layer_m: number[]; upper_c: number[]; od: number[]; untenable_s: number | null; cause: string | null }[]
  routes: { room: string; label: string; floor: string; points: Vec3[]; red_s: (number | null)[] }[]
  source: { confidence: string; text: string }
}

const STEPS_PER_S = 2.4 // twelve seconds of fire a second
export const mmss = (s: number) => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, '0')}`

const VERT = /* glsl */ `varying vec3 vW; varying vec3 vN; void main() { vN = normal; vW = (modelMatrix * vec4(position, 1.0)).xyz; gl_Position = projectionMatrix * viewMatrix * vec4(vW, 1.0); }`
// A slab of smoke seen from outside: how much of the room behind shows is Beer-Lambert through the slab, with the
// modelled optical density and the length of the sight line inside it. Capped, so the room never goes fully black.
const FRAG = /* glsl */ `
  varying vec3 vW; varying vec3 vN;
  uniform float uOD, uThick, uHot, uTime, uSeed;
  float hash(vec3 p) { return fract(sin(dot(p, vec3(12.9898, 78.233, 37.719))) * 43758.5453); }
  float noise(vec3 p) { vec3 i = floor(p), f = fract(p); f = f * f * (3.0 - 2.0 * f);
    return mix(mix(mix(hash(i), hash(i + vec3(1, 0, 0)), f.x), mix(hash(i + vec3(0, 1, 0)), hash(i + vec3(1, 1, 0)), f.x), f.y),
               mix(mix(hash(i + vec3(0, 0, 1)), hash(i + vec3(1, 0, 1)), f.x), mix(hash(i + vec3(0, 1, 1)), hash(i + vec3(1, 1, 1)), f.x), f.y), f.z); }
  void main() {
    vec3 v = normalize(cameraPosition - vW);
    float path = abs(vN.z) > 0.5 ? uThick / max(abs(v.z), 0.2) : 1.6;         // through the top, or in through a side
    float billow = 0.72 + 0.56 * noise(vec3(vW.xy * 1.3 + uSeed, vW.z * 2.0 - uTime * 0.25));
    float a = min(0.9, 1.0 - exp(-uOD * path * 0.55 * billow));
    vec3 col = mix(vec3(0.34, 0.33, 0.32), vec3(0.07, 0.065, 0.06), a);
    col = mix(col, vec3(1.0, 0.42, 0.08), uHot * 0.55 * billow);              // the upper layer glows where it is hot
    gl_FragColor = vec4(col, a);
  }`

export class FireShow implements Player {
  group: THREE.Object3D | null = null
  labels: LabelSpec[] = []
  private data: Smoke | null = null
  private status: 'loading' | 'ready' | 'missing' = 'loading'
  private reason = ''
  private pos = 0; private playing = false; private seekN = -1; private sent = ''; private doors: 'open' | 'closed' | null = null
  private rooms: { r: Smoke['rooms'][number]; slab: THREE.Mesh; wash: THREE.Mesh; u: Record<string, THREE.IUniform> }[] = []
  private routes: { line: Line2; red: (number | null)[]; n: number }[] = []
  private flame: THREE.Mesh | null = null
  private made: { dispose(): void }[] = []; private objs: THREE.Object3D[] = []
  private res = new THREE.Vector2(1, 1)
  private cut: number | null | undefined
  private gone = false

  private ctx: ShowCtx
  constructor(ctx: ShowCtx) { this.ctx = ctx }

  private async load(doors: 'open' | 'closed') {
    this.clear(); this.status = 'loading'; this.report(true)
    try {
      const d = await fetchJson<Smoke>(`${this.ctx.api}/api/show/${this.ctx.sid}/smoke?doors=${doors}`)
      if (this.gone || doors !== this.doors) return
      if (!d.available) { this.status = 'missing'; this.reason = d.reason ?? 'No fire model for this scan.'; this.report(true); return }
      this.data = d; this.pos = Math.min(this.pos, d.time.length - 1)
      this.build(d); this.status = 'ready'
      // whole walls: the smoke is read against them. The person's own cut comes back when the show ends.
      if (this.cut === undefined) { this.cut = this.ctx.view().cut ?? null; this.ctx.setView({ cut: null, floor: d.rooms.find((r) => r.fire)?.floor ?? this.ctx.view().floor }) }
    } catch { if (!this.gone) { this.status = 'missing'; this.reason = 'The fire model could not be loaded.' } }
    this.report(true)
  }

  private build(d: Smoke) {
    const { model: m, doll, tokens: tok } = this.ctx, byId = new Map(m.plan.rooms.map((r) => [r.id, r]))
    const add = (f: number, o: THREE.Object3D) => { doll.floorGroups[f]?.add(o); this.objs.push(o) }
    for (const r of d.rooms) {
      const room = byId.get(r.id), f = m.floorOf.get(r.floor) ?? 0
      if (!room || room.polygon.length < 3) continue
      const shape = new THREE.Shape(room.polygon.map(([x, y]) => new THREE.Vector2(x, y)))
      const geo = new THREE.ExtrudeGeometry(shape, { depth: 1, bevelEnabled: false }), flat = new THREE.ShapeGeometry(shape)
      const u = { uOD: { value: 0 }, uThick: { value: 0 }, uHot: { value: 0 }, uTime: { value: 0 }, uSeed: { value: this.rooms.length * 7.3 } }
      const mat = new THREE.ShaderMaterial({ vertexShader: VERT, fragmentShader: FRAG, uniforms: u, transparent: true, depthWrite: false })
      const slab = new THREE.Mesh(geo, mat); slab.renderOrder = 6; slab.visible = false
      const wm = new THREE.MeshBasicMaterial({ transparent: true, opacity: 0, depthWrite: false })
      wm.color.setRGB(tok.fail[0], tok.fail[1], tok.fail[2], THREE.SRGBColorSpace)
      const wash = new THREE.Mesh(flat, wm); wash.position.z = 0.04; wash.renderOrder = 4; wash.visible = false
      add(f, slab); add(f, wash); this.made.push(geo, flat, mat, wm)
      this.rooms.push({ r, slab, wash, u })
      if (r.fire) { // where the fire burns: CFAST puts it in the middle of the room
        const c = centroid(room.polygon), fg = new THREE.CircleGeometry(1, 24)
        const fm = new THREE.ShaderMaterial({ uniforms: { uTime: u.uTime, uSize: { value: 0 } }, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
          vertexShader: /* glsl */ `varying vec2 vP; void main() { vP = position.xy; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
          fragmentShader: /* glsl */ `varying vec2 vP; uniform float uTime, uSize;
            void main() { float d = length(vP); float k = 0.85 + 0.15 * sin(uTime * 9.0 + d * 7.0);
              gl_FragColor = vec4(mix(vec3(1.0, 0.82, 0.4), vec3(1.0, 0.3, 0.05), d), (1.0 - smoothstep(0.0, 1.0, d)) * k * uSize); }` })
        this.flame = new THREE.Mesh(fg, fm); this.flame.position.set(c[0], c[1], 0.1); this.flame.renderOrder = 5
        add(f, this.flame); this.made.push(fg, fm)
      }
    }
    for (const rt of d.routes) {
      const f = m.floorOf.get(rt.floor) ?? 0, fz = m.floorZ[f]
      const pts = rt.points.flatMap((p) => [p[0], p[1], Math.max(p[2] - fz, 0) + 0.1])
      const cg = new LineGeometry().setPositions(pts), cm = new LineMaterial({ linewidth: 8, transparent: true, opacity: 0.92, resolution: this.res, depthWrite: false })
      cm.color.setRGB(tok.paper[0], tok.paper[1], tok.paper[2], THREE.SRGBColorSpace)
      const casing = new Line2(cg, cm); casing.renderOrder = 7
      const lg = new LineGeometry().setPositions(pts), lm = new LineMaterial({ linewidth: 4.5, vertexColors: true, resolution: this.res, depthWrite: false })
      const line = new Line2(lg, lm); line.renderOrder = 8
      add(f, casing); add(f, line); this.made.push(cg, cm, lg, lm)
      this.routes.push({ line, red: rt.red_s, n: -1 })
    }
  }

  private clear() {
    for (const o of this.objs) o.removeFromParent()
    this.made.forEach((m) => m.dispose())
    this.objs = []; this.made = []; this.rooms = []; this.routes = []; this.flame = null; this.data = null
  }

  set(spec: ShowSpec) {
    const doors = spec.doors ?? 'open'
    if (doors !== this.doors) { this.doors = doors; void this.load(doors) }
    const d = this.data
    if (spec.seek && spec.seek.n !== this.seekN) { this.seekN = spec.seek.n; this.pos = Math.max(0, d ? Math.min(spec.seek.step, d.time.length - 1) : spec.seek.step) }
    if (spec.playing && !this.playing && d && this.pos >= d.time.length - 1.01) this.pos = 0
    this.playing = spec.playing
    this.report(true)
  }

  private at<T extends number>(a: T[]): number {
    const i = Math.min(Math.floor(this.pos), a.length - 2), k = this.pos - i
    return a[i] + (a[i + 1] - a[i]) * k
  }

  private report(force = false) {
    const d = this.data, i = d ? Math.min(Math.round(this.pos), d.time.length - 1) : 0
    const key = `${this.status}:${i}:${this.playing}:${this.doors}`
    if (!force && key === this.sent) return
    this.sent = key
    const t = d ? d.time[i] : 0
    const rows: SmokeRow[] = d ? d.rooms.map((r) => ({ id: r.id, label: r.label, fire: r.fire, layer_m: r.layer_m[i], ceiling_m: r.ceiling_m, upper_c: r.upper_c[i], untenable_s: r.untenable_s, cause: r.cause, lost: r.untenable_s != null && t >= r.untenable_s })) : []
    const sources: SourceLine[] = d ? [{ what: 'Smoke, heat and survivable time', confidence: d.source.confidence, text: d.source.text },
      { what: 'The fire', confidence: 'low', text: `An assumed ${d.growth} t-squared fire in the ${d.fire_room.label.toLowerCase()}, growing to ${d.peak_kw} kW. Bedroom doors ${d.doors}. Routes out are the egress tool's walking routes.` }] : []
    this.ctx.emit({
      kind: 'fire', status: this.status, reason: this.reason || undefined, playing: this.playing, step: i, steps: d ? d.time.length - 1 : 0, clock: mmss(t),
      title: d ? `Fire in the ${d.fire_room.label.toLowerCase()}, NIST CFAST model` : 'Smoke clock', sources,
      fire: d ? { rooms: rows, doors: d.doors, end: mmss(d.end_s) } : undefined,
    })
  }

  update(dt: number): boolean {
    const d = this.data
    if (!d) return false
    const before = this.pos
    if (this.playing) {
      this.pos = Math.min(d.time.length - 1, this.pos + dt * STEPS_PER_S)
      if (this.pos >= d.time.length - 1) { this.playing = false; this.report(true) }
    }
    const t = this.at(d.time), outside = this.ctx.view().mode === 'dollhouse' // seen from outside only: untested from a panorama
    for (const { r, slab, wash, u } of this.rooms) {
      const layer = this.at(r.layer_m), top = r.ceiling_m ?? layer, thick = Math.max(0, top - layer)
      slab.visible = thick > 0.03 && this.at(r.od) > 0.02 && outside
      slab.position.z = layer; slab.scale.z = Math.max(thick, 0.001)
      u.uOD.value = this.at(r.od); u.uThick.value = thick; u.uHot.value = Math.min(1, Math.max(0, (this.at(r.upper_c) - 150) / 550))
      if (this.playing) u.uTime.value += dt
      const lost = r.untenable_s != null && t >= r.untenable_s, m = wash.material as THREE.MeshBasicMaterial
      m.opacity += ((lost ? 0.34 : 0) - m.opacity) * Math.min(1, dt * 6); wash.visible = m.opacity > 0.01
    }
    const burning = this.rooms.find((x) => x.r.fire)
    if (this.flame && burning) { // the glow grows with the fire room's modelled upper-layer temperature
      const k = Math.min(1, Math.max(0, (this.at(burning.r.upper_c) - 20) / 380))
      ;(this.flame.material as THREE.ShaderMaterial).uniforms.uSize.value = Math.min(1, 0.3 + k); this.flame.scale.setScalar(0.3 + 0.9 * k)
    }
    const tok = this.ctx.tokens, c = new THREE.Color()
    for (const rt of this.routes) { // a route's colours change only when another stretch is lost
      const n = rt.red.filter((s) => s != null && t >= s).length
      if (n === rt.n) continue
      rt.n = n
      const cols: number[] = []
      for (const s of rt.red) { const col = s != null && t >= s ? tok.fail : tok.pass; c.setRGB(col[0], col[1], col[2], THREE.SRGBColorSpace); cols.push(c.r, c.g, c.b) }
      rt.line.geometry.setColors(cols)
    }
    this.report()
    return this.playing || this.pos !== before || this.rooms.some((x) => { const o = (x.wash.material as THREE.MeshBasicMaterial).opacity; return o > 0.01 && o < 0.33 })
  }

  setSize(w: number, hgt: number) { this.res.set(w, hgt) }

  dispose() {
    this.gone = true; this.clear()
    if (this.cut !== undefined) this.ctx.setView({ cut: this.cut })
  }
}
