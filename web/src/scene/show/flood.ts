// Hurricane Harvey played on the house. The level for every half hour, the ground grid and each room's entry level
// come from /api/show/<sid>/storm (server/threshold/world/storm.py says where each number is from). Here the water
// is only drawn: outdoors where Vexcel's bare ground is under the level, indoors once the level passes the sill the
// flood tool found for that room.
import * as THREE from 'three'
import { centroid } from '../model.ts'
import { h, type LabelSpec } from '../engine/labels.ts'
import type { Vec2 } from '../types.ts'
import { fetchJson, type LossItem, type Player, type ShowCtx, type ShowSpec, type SourceLine } from './types.ts'

interface Storm {
  available: boolean; reason?: string; event: string
  time: number[]; tz_offset_h: number; level: number[]; high: number[]; outside_m: number[]; inside_m: number[]; rooms_wet: number[]
  ground_z: number; floor_z: number; window: [number, number]
  ground: { n: number; rect: [number, number, number, number]; z0: number; range: number; b64: string } | null
  rooms: { id: string; label: string; floor_z: number; floods_at: number | null }[]
  sources: SourceLine[]
}
interface Belongings { available: boolean; reason?: string; items: (LossItem & { point: [number, number, number] })[]; loss_usd: [number, number][]; wet_count: number[]; source: { confidence: string; text: string } }

const STEPS_PER_S = 4      // two hours of storm a second
const REACH_M = 300
const WEEKDAY = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'], MONTH = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

const VERT = /* glsl */ `varying vec3 vW; void main() { vW = (modelMatrix * vec4(position, 1.0)).xyz; gl_Position = projectionMatrix * viewMatrix * vec4(vW, 1.0); }`
const FRAG = /* glsl */ `
  varying vec3 vW;
  uniform sampler2D uGround, uRooms; uniform vec4 uGroundRect, uRoomRect; uniform vec2 uCentre;
  uniform float uZ0, uZr, uLevel, uTime, uHasGround, uFade; uniform vec3 uCol;
  float unpack(float r) { return uZ0 + r * (255.0 / 254.0) * uZr; }
  bool inside(vec2 p) { return p.x > 0.0 && p.x < 1.0 && p.y > 0.0 && p.y < 1.0; }
  void main() {
    float depth = 0.5;                                        // beyond the ground grid the drawn surroundings decide
    vec2 r = (vW.xy - uRoomRect.xy) / uRoomRect.zw, g = (vW.xy - uGroundRect.xy) / uGroundRect.zw;
    vec4 room = inside(r) ? texture2D(uRooms, r) : vec4(0.0);
    if (room.g > 0.5) {                                       // in a room: dry until the level passes its sill
      if (uLevel < unpack(room.r)) discard;
      depth = uLevel - unpack(room.b);
    } else if (uHasGround > 0.5 && inside(g)) {               // outdoors: only where the bare ground is lower
      float c = texture2D(uGround, g).r;
      depth = uLevel - unpack(c);
      if (c > 0.985 || depth <= 0.0) discard;                 // under a roof or a tree, or dry
    }
    vec3 v = normalize(cameraPosition - vW);
    vec2 q = vW.xy * 0.9;                                     // slow ripples: two crossing wave trains tilt the surface
    vec3 n = normalize(vec3(0.05 * sin(q.x * 1.7 + uTime * 0.9) + 0.035 * sin(q.y * 2.3 - uTime * 0.7 + q.x * 0.6),
                            0.05 * cos(q.y * 1.5 + uTime * 0.8) + 0.035 * cos(q.x * 2.1 + uTime * 0.6 - q.y * 0.5), 1.0));
    float fres = pow(1.0 - abs(dot(v, n)), 3.0);
    vec3 col = mix(uCol * 1.18, uCol * 0.72, smoothstep(0.0, 0.9, depth));   // deeper is darker
    col = mix(col, vec3(0.86, 0.91, 0.93), fres * 0.6);
    float edge = 1.0 - smoothstep(uFade * 0.7, uFade, distance(vW.xy, uCentre));
    gl_FragColor = vec4(col, (0.34 + 0.34 * smoothstep(0.0, 0.5, depth) + 0.3 * fres) * smoothstep(0.0, 0.05, depth) * edge);
  }`

export class FloodShow implements Player {
  group = new THREE.Group()
  labels: LabelSpec[] = []
  /** A storm that cannot play here leaves a tool's own water level on the building. */
  get ownsWater() { return this.status !== 'missing' }
  private storm: Storm | null = null
  private things: Belongings | null = null
  private list: 'loading' | 'ready' | 'none' = 'loading'
  private status: 'loading' | 'ready' | 'missing' = 'loading'
  private reason = ''
  private pos = 0; private playing = false; private seekN = -1; private sent = ''
  private water: THREE.Mesh; private dots: THREE.Points | null = null
  private chips = new Map<string, { el: HTMLElement; num: HTMLElement; floor_z: number; floods_at: number }>()
  private uniforms: Record<string, THREE.IUniform>
  private made: { dispose(): void }[] = []
  private gone = false

  private ctx: ShowCtx
  constructor(ctx: ShowCtx) {
    this.ctx = ctx
    const b = ctx.model.bounds, c: Vec2 = [(b.minX + b.maxX) / 2, (b.minY + b.maxY) / 2]
    this.uniforms = {
      uGround: { value: null }, uRooms: { value: null }, uGroundRect: { value: new THREE.Vector4(0, 0, 1, 1) }, uRoomRect: { value: new THREE.Vector4(0, 0, 1, 1) },
      uCentre: { value: new THREE.Vector2(...c) }, uZ0: { value: 0 }, uZr: { value: 1 }, uLevel: { value: -1000 }, uTime: { value: 0 }, uHasGround: { value: 0 },
      uFade: { value: REACH_M }, uCol: { value: new THREE.Vector3(...ctx.tokens.water) }, uHigh: { value: -1000 },
    }
    const geo = new THREE.PlaneGeometry(REACH_M * 2, REACH_M * 2), mat = new THREE.ShaderMaterial({ vertexShader: VERT, fragmentShader: FRAG, uniforms: this.uniforms, transparent: true, depthWrite: false, side: THREE.DoubleSide })
    this.water = new THREE.Mesh(geo, mat)
    this.water.position.set(c[0], c[1], 0); this.water.renderOrder = 5; this.water.visible = false; this.water.frustumCulled = false
    this.group.add(this.water); this.made.push(geo, mat)
    void this.load()
  }

  private async load() {
    const { api, sid } = this.ctx
    try {
      const s = await fetchJson<Storm>(`${api}/api/show/${sid}/storm`)
      if (this.gone) return
      if (!s.available) { this.status = 'missing'; this.reason = s.reason ?? 'No storm record for this scan.'; this.report(); this.ctx.relabel(); return }
      this.storm = s; this.pos = s.window[0]
      this.textures(s); this.roomChips(s)
      this.status = 'ready'; this.report(); this.ctx.relabel()
    } catch { if (!this.gone) { this.status = 'missing'; this.reason = 'The storm record could not be loaded.'; this.report(); this.ctx.relabel() } return }
    try { // slow the first time for a scan: a vision model reads the rooms. The water plays without it.
      const t = await fetchJson<Belongings>(`${api}/api/show/${sid}/storm/belongings`)
      if (this.gone) return
      if (t.available && t.items.length) { this.things = t; this.list = 'ready'; this.itemDots(t) } else this.list = 'none'
    } catch { this.list = 'none' }
    this.report(true)
  }

  /** The ground grid as a texture, and the entry floor's rooms drawn into another: red is the level a room takes
      water at, green says "a room", blue is its floor. Both use the grid's own 2 cm height steps. */
  private textures(s: Storm) {
    const u = this.uniforms, g = s.ground
    const z0 = g?.z0 ?? s.ground_z - 3, zr = g?.range ?? 5
    u.uZ0.value = z0; u.uZr.value = zr
    if (g) {
      const tex = new THREE.DataTexture(Uint8Array.from(atob(g.b64), (c) => c.charCodeAt(0)), g.n, g.n, THREE.RedFormat)
      tex.minFilter = tex.magFilter = THREE.LinearFilter; tex.needsUpdate = true
      u.uGround.value = tex; (u.uGroundRect.value as THREE.Vector4).set(...g.rect); u.uHasGround.value = 1; this.made.push(tex)
    }
    const byId = new Map(this.ctx.model.plan.rooms.map((r) => [r.id, r]))
    const rooms = s.rooms.filter((r) => r.floods_at != null && Math.abs(r.floor_z - s.floor_z) < 1 && (byId.get(r.id)?.polygon.length ?? 0) > 2)
    const pts = rooms.flatMap((r) => byId.get(r.id)!.polygon)
    if (!pts.length) return
    const x0 = Math.min(...pts.map((p) => p[0])) - 1, y0 = Math.min(...pts.map((p) => p[1])) - 1, w = Math.max(...pts.map((p) => p[0])) + 1 - x0, hgt = Math.max(...pts.map((p) => p[1])) + 1 - y0
    const cv = document.createElement('canvas'); cv.width = cv.height = 512
    const c = cv.getContext('2d')!, enc = (z: number) => Math.round(Math.min(254, Math.max(0, ((z - z0) / zr) * 254)))
    c.fillStyle = '#000'; c.fillRect(0, 0, 512, 512)
    for (const r of rooms) {
      c.fillStyle = `rgb(${enc(r.floods_at!)}, 255, ${enc(r.floor_z)})`
      c.beginPath(); byId.get(r.id)!.polygon.forEach(([x, y], i) => c[i ? 'lineTo' : 'moveTo'](((x - x0) / w) * 512, (1 - (y - y0) / hgt) * 512)); c.closePath(); c.fill()
    }
    const tex = new THREE.CanvasTexture(cv); tex.colorSpace = THREE.NoColorSpace; tex.minFilter = tex.magFilter = THREE.NearestFilter; tex.generateMipmaps = false
    u.uRooms.value = tex; (u.uRoomRect.value as THREE.Vector4).set(x0, y0, w, hgt); this.made.push(tex)
  }

  /** A depth chip on the larger rooms of the entry floor, shown once the room is wet. */
  private roomChips(s: Storm) {
    const m = this.ctx.model, byId = new Map(m.plan.rooms.map((r) => [r.id, r]))
    const rooms = s.rooms.filter((r) => r.floods_at != null && Math.abs(r.floor_z - s.floor_z) < 1 && byId.get(r.id)?.polygon.length).sort((a, b) => (byId.get(b.id)!.area ?? 0) - (byId.get(a.id)!.area ?? 0)).slice(0, 8)
    this.labels = rooms.map((r) => {
      const room = byId.get(r.id)!, c = centroid(room.polygon), f = m.floorOf.get(room.floor) ?? 0
      const num = h('span', 'th-num', ''), el = h('div', 'th-chip th-chip-water th-chip-show', h('span', 'th-chip-text', r.label), num)
      el.dataset.off = ''
      this.chips.set(r.id, { el, num, floor_z: r.floor_z, floods_at: r.floods_at! })
      return { id: `flood.${r.id}`, pos: [c[0], c[1], r.floor_z + 0.3], floor: f, spanM: Math.sqrt(room.area ?? 9), minPx: 58, modes: ['doll' as const], make: () => el }
    })
  }

  /** Each listed belonging as a dot where the vision model found it: pale while dry, the fail colour once wet. */
  private itemDots(t: Belongings) {
    const n = t.items.length, pos = new Float32Array(n * 3), at = new Float32Array(n)
    t.items.forEach((it, i) => { pos.set(it.point, i * 3); pos[i * 3 + 2] += 0.12; at[i] = it.wet_at })
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.BufferAttribute(pos, 3)); geo.setAttribute('aAt', new THREE.BufferAttribute(at, 1))
    const tok = this.ctx.tokens
    const mat = new THREE.ShaderMaterial({
      uniforms: { uLevel: this.uniforms.uHigh, uWet: { value: new THREE.Vector3(...tok.fail) }, uDry: { value: new THREE.Vector3(...tok.paper) }, uInk: { value: new THREE.Vector3(...tok.ink) }, uPx: { value: Math.min(devicePixelRatio, 2) } },
      vertexShader: /* glsl */ `attribute float aAt; uniform float uLevel, uPx; varying float vWet;
        void main() { vWet = step(aAt, uLevel); gl_PointSize = (7.0 + 5.0 * vWet) * uPx; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
      fragmentShader: /* glsl */ `varying float vWet; uniform vec3 uWet, uDry, uInk;
        void main() { float d = length(gl_PointCoord - 0.5) * 2.0; if (d > 1.0) discard;
          gl_FragColor = vec4(mix(mix(uDry, uWet, vWet), mix(uInk, vec3(1.0), vWet), smoothstep(0.62, 0.74, d)), 1.0); }`,
      depthTest: false, transparent: true,
    })
    this.dots = new THREE.Points(geo, mat); this.dots.renderOrder = 9; this.dots.frustumCulled = false
    this.group.add(this.dots); this.made.push(geo, mat)
  }

  set(spec: ShowSpec) {
    const s = this.storm
    if (spec.seek && spec.seek.n !== this.seekN) { this.seekN = spec.seek.n; if (s) this.pos = s.window[0] + Math.min(Math.max(spec.seek.step, 0), s.window[1] - s.window[0]) }
    if (spec.playing && !this.playing && s && this.pos >= s.window[1] - 0.01) this.pos = s.window[0] // play again from the start
    this.playing = spec.playing
    this.report(true)
  }

  private level(): number {
    const s = this.storm!, i = Math.min(Math.floor(this.pos), s.level.length - 2), k = this.pos - i
    return s.level[i] + (s.level[i + 1] - s.level[i]) * k
  }

  private report(force = false) {
    const s = this.storm, i = s ? Math.min(Math.round(this.pos), s.window[1]) : 0
    const key = `${this.status}:${i}:${this.playing}:${this.list}`
    if (!force && key === this.sent) return
    this.sent = key
    let clock = ''
    if (s) { const d = new Date((s.time[i] + s.tz_offset_h * 3600) * 1000); clock = `${WEEKDAY[d.getUTCDay()]} ${d.getUTCDate()} ${MONTH[d.getUTCMonth()]}, ${String(d.getUTCHours()).padStart(2, '0')}:${String(d.getUTCMinutes()).padStart(2, '0')}` }
    const t = this.things
    this.ctx.emit({
      kind: 'flood', status: this.status, reason: this.reason || undefined, playing: this.playing, step: s ? i - s.window[0] : 0, steps: s ? s.window[1] - s.window[0] : 0, clock,
      title: s?.event ?? 'Hurricane Harvey', sources: [...(s?.sources ?? []), ...(t ? [{ what: 'What the water reaches', confidence: t.source.confidence, text: t.source.text }] : [])],
      flood: s ? { outside_m: s.outside_m[i], inside_m: s.inside_m[i], rooms_wet: s.rooms_wet[i], items: t?.items ?? [], wet: t?.wet_count[i] ?? 0, loss_usd: t?.loss_usd[i] ?? null, list: this.list,
        listNote: this.list === 'loading' ? 'Reading the rooms for belongings. The first time on a scan this takes a minute or two.' : this.list === 'none' ? 'No belongings with a measured height in the rooms the water reaches.' : '' } : undefined,
    })
  }

  update(dt: number): boolean {
    const s = this.storm, w = this.ctx.doll.anim.water
    if (!s) return false
    if (this.playing) {
      this.pos = Math.min(s.window[1], this.pos + dt * STEPS_PER_S)
      this.uniforms.uTime.value += dt
      if (this.pos >= s.window[1]) { this.playing = false; this.report(true) }
    }
    const level = this.level()
    const moved = this.uniforms.uLevel.value !== level
    this.uniforms.uLevel.value = level
    this.uniforms.uHigh.value = s.high[Math.min(Math.round(this.pos), s.window[1])] // a belonging the water reached stays marked after it falls
    w.cur = w.goal = level                                   // the walls' own tint and water line follow
    this.water.position.z = level; this.water.visible = true
    const i = Math.min(Math.round(this.pos), s.window[1])
    for (const c of this.chips.values()) {
      const wet = level > c.floods_at && level > c.floor_z + 0.005
      if (wet) { delete c.el.dataset.off; c.num.textContent = `${Math.max(0, s.level[i] - c.floor_z).toFixed(2)} m` } else c.el.dataset.off = ''
    }
    this.report()
    return this.playing || moved
  }

  dispose() {
    this.gone = true
    const w = this.ctx.doll.anim.water; w.cur = w.goal = -1000
    this.made.forEach((m) => m.dispose())
  }
}
