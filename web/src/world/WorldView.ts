// The building's real surroundings, in the scan's own frame: Vexcel's 3D city mesh where it exists (the server picks
// a fixed ring of its 3D Tiles round the building: fine near, coarser far), else Vexcel's surface model draped with
// the orthophoto. The building itself is cut out of either, so the model stands in
// the hole; the cut closes again as the camera pulls away, which is the whole "from the street into a room" move.
import * as THREE from 'three'
import { DRACOLoader } from 'three/addons/loaders/DRACOLoader.js'
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js'
import { KTX2Loader } from 'three/addons/loaders/KTX2Loader.js'
import dracoJs from 'three/examples/jsm/libs/draco/gltf/draco_wasm_wrapper.js?url'
import dracoWasm from 'three/examples/jsm/libs/draco/gltf/draco_decoder.wasm?url'
import basisJs from 'three/examples/jsm/libs/basis/basis_transcoder.js?url'
import basisWasm from 'three/examples/jsm/libs/basis/basis_transcoder.wasm?url'
import type { Vec2 } from '../scene/types.ts'

export interface Site {
  available: boolean; note?: string
  anchor: { lat: number; lon: number }
  scan_to_enu: { rot_deg: number; t: [number, number]; verified: boolean }
  georef: { verified: boolean; note: string }
  footprint_enu: Vec2[] | null
  floor_above_ground_m: number
  tiles3d: { url: string; capture: (string | null)[]; copyright: string | null } | null
  terrain: string
}
interface Terrain { width: number; height: number; bounds_enu: number[]; heights_cm_b64: string; ortho: { url: string; bounds_enu: number[] }[] }

// The Draco and Basis decoders ship inside three. The loaders ask for them by file name under a folder; this hands
// each name the address the bundler gave that file.
const DECODERS: Record<string, string> = { 'draco_wasm_wrapper.js': dracoJs, 'draco_decoder.wasm': dracoWasm, 'basis_transcoder.js': basisJs, 'basis_transcoder.wasm': basisWasm }
const decoders = new THREE.LoadingManager()
decoders.setURLModifier((url) => DECODERS[url.split('/').pop() ?? ''] ?? url)
const FADE_M = 300                // the surroundings dissolve into the stage past this distance from the building
const RAD = Math.PI / 180
const A = 6378137, E2 = 6.69437999014e-3 // WGS84

/** East/north/up about a point on the ellipsoid, from earth-centred coordinates. */
function enuFromEcef(lat: number, lon: number): THREE.Matrix4 {
  const sl = Math.sin(lat), cl = Math.cos(lat), so = Math.sin(lon), co = Math.cos(lon), n = A / Math.sqrt(1 - E2 * sl * sl)
  const o = new THREE.Vector3(n * cl * co, n * cl * so, n * (1 - E2) * sl)
  return new THREE.Matrix4().set(-so, co, 0, 0, -sl * co, -sl * so, cl, 0, cl * co, cl * so, sl, 0, 0, 0, 0, 1).multiply(new THREE.Matrix4().makeTranslation(-o.x, -o.y, -o.z))
}

const VERT = /* glsl */ `
  varying vec2 vUv; varying vec3 vW;
  void main() { vUv = uv; vec4 w = modelMatrix * vec4(position, 1.0); vW = w.xyz; gl_Position = projectionMatrix * viewMatrix * w; }`

// Shared by tiles and terrain. Colours are display values end to end, like the rest of the scene (no colour-space pass).
const FRAG_HEAD = /* glsl */ `
  varying vec2 vUv; varying vec3 vW;
  uniform sampler2D uMask; uniform vec4 uMaskRect; uniform vec2 uCentre; uniform vec3 uStage;
  uniform float uHole, uDisc, uShow, uFade, uMute, uIn;
  float hash(vec2 p) { return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }
  vec3 place(vec3 c) {
    vec2 m = (vW.xy - uMaskRect.xy) / uMaskRect.zw;
    float inside = (m.x > 0.0 && m.x < 1.0 && m.y > 0.0 && m.y < 1.0) ? texture2D(uMask, m).r : 0.0;
    float d = distance(vW.xy, uCentre);
    float n = hash(floor(vW.xy * 5.0));
    if (inside > 0.5 && n < uHole) discard;                    // the building dissolves in hand-sized blocks
    if (uDisc > 0.0 && 1.0 - smoothstep(uDisc * 0.9, uDisc, d) > n) discard;  // a short ragged edge under the splat's own soft one
    float l = dot(c, vec3(0.3, 0.59, 0.11));
    c = mix(c, mix(uStage, vec3(l), 0.55), uMute);            // quieter when a result is drawn on the building
    return mix(uStage, c, uShow * uIn * (1.0 - smoothstep(uFade * 0.7, uFade, d)));
  }`
const TILE_FRAG = FRAG_HEAD + /* glsl */ `
  uniform sampler2D map;
  void main() { gl_FragColor = vec4(place(texture2D(map, vUv).rgb), 1.0); }`
const TERRAIN_FRAG = FRAG_HEAD + /* glsl */ `
  uniform sampler2D uFar, uNear; uniform vec4 uFarRect, uNearRect; varying vec3 vE;
  void main() {
    vec2 a = (vE.xy - uNearRect.xy) / uNearRect.zw, b = (vE.xy - uFarRect.xy) / uFarRect.zw;
    float k = smoothstep(0.0, 0.06, min(min(a.x, a.y), min(1.0 - a.x, 1.0 - a.y)));
    gl_FragColor = vec4(place(mix(texture2D(uFar, b).rgb, texture2D(uNear, a).rgb, k)), 1.0);
  }`
const TERRAIN_VERT = /* glsl */ `
  varying vec2 vUv; varying vec3 vW, vE;
  void main() { vUv = uv; vE = position; vec4 w = modelMatrix * vec4(position, 1.0); vW = w.xyz; gl_Position = projectionMatrix * viewMatrix * w; }`

export class WorldView {
  group = new THREE.Group()
  status: 'idle' | 'loading' | 'ready' | 'missing' = 'idle'
  kind: 'city mesh' | 'terrain' | null = null
  site: Site | null = null
  /** Scan-frame height of the ground beside the building. */
  ground = 0
  onChange: () => void = () => {}
  private show_ = { cur: 0, goal: 0 }
  private tiles: THREE.Group | null = null // the city mesh, in earth-centred coordinates under one placing transform
  private placed = new THREE.Matrix4()    // earth-centred to scan, with the ellipsoid at z = 0
  private groundH: number | null = null   // ellipsoid height of the ground beside the building
  private lift = 0
  private arriving: THREE.IUniform[] = [] // tiles fading in
  private loaded = 0; private total = 0
  private gone = false
  private uniforms: Record<string, THREE.IUniform>
  private made: { dispose(): void }[] = []
  private ray = new THREE.Raycaster()
  private wanted = false

  private renderer: THREE.WebGLRenderer; private api: string; private sid: string
  private outline: Vec2[][]; private centre: THREE.Vector2; private radius: number
  /** `outline`: the scan's own room outlines (scan frame); they are cut out of the surroundings with the footprint. */
  constructor(renderer: THREE.WebGLRenderer, api: string, sid: string, stage: [number, number, number], outline: Vec2[][], centre: Vec2, radius: number) {
    this.renderer = renderer; this.api = api; this.sid = sid
    this.outline = outline; this.centre = new THREE.Vector2(...centre); this.radius = radius
    this.group.visible = false
    this.uniforms = {
      uMask: { value: null }, uMaskRect: { value: new THREE.Vector4(0, 0, 1, 1) }, uCentre: { value: this.centre }, uStage: { value: new THREE.Vector3(...stage) },
      uHole: { value: 0 }, uDisc: { value: 0 }, uShow: { value: 0 }, uFade: { value: FADE_M }, uMute: { value: 0 }, uIn: { value: 1 },
    }
  }

  /** Show or hide. The first show loads the site; nothing is fetched for a scan nobody asks to see outdoors. */
  show(on: boolean) { this.wanted = on; this.show_.goal = on && this.status === 'ready' ? 1 : 0; if (on && this.status === 'idle') void this.load() }
  /** hole: 0 the building is whole in the surroundings, 1 it is cut out. disc: also clear this radius (the splat's own ground). */
  setHole(hole: number, disc = 0) { this.uniforms.uHole.value = hole; this.uniforms.uDisc.value = disc }
  setMute(m: number) { this.uniforms.uMute.value = m }

  private async load() {
    this.status = 'loading'; this.onChange()
    try {
      const site: Site = await fetch(`${this.api}/api/world/${this.sid}/site`).then((r) => (r.ok ? r.json() : Promise.reject(new Error(`site ${r.status}`))))
      this.site = site
      if (!site.available) throw new Error(site.note ?? 'no geocoordinates')
      const { rot_deg, t } = site.scan_to_enu
      const scanFromEnu = new THREE.Matrix4().makeRotationZ(-rot_deg * RAD).multiply(new THREE.Matrix4().makeTranslation(-t[0], -t[1], 0))
      this.mask(site, scanFromEnu)
      const list: { url: string }[] = site.tiles3d ? await fetch(`${this.api}${site.tiles3d.url}`).then((r) => (r.ok ? r.json() : { tiles: [] })).then((j) => j.tiles ?? [], () => []) : []
      if (list.length) this.loadTiles(site, scanFromEnu, list); else await this.loadTerrain(site, scanFromEnu)
    } catch (e) {
      console.warn('[scene] surroundings unavailable:', (e as Error).message)
      this.status = 'missing'
    }
    this.onChange()
  }

  /** The scan's rooms, and the building's footprint when the scan was fitted to it, drawn into a small mask the
      shaders cut by. A scan that was not fitted is often one unit of a larger block, whose footprint is the whole
      block: cutting that away would leave the unit alone in a hole the size of the block. */
  private mask(site: Site, scanFromEnu: THREE.Matrix4) {
    const foot = (site.georef.verified ? site.footprint_enu ?? [] : []).map(([e, n]) => { const v = new THREE.Vector3(e, n, 0).applyMatrix4(scanFromEnu); return [v.x, v.y] as Vec2 })
    const rings = [...this.outline, ...(foot.length > 2 ? [foot] : [])].filter((r) => r.length > 2)
    const xs = rings.flat().map((p) => p[0]), ys = rings.flat().map((p) => p[1])
    if (!xs.length) return
    const pad = 1.5, x0 = Math.min(...xs) - pad, y0 = Math.min(...ys) - pad, w = Math.max(...xs) + pad - x0, h = Math.max(...ys) + pad - y0
    const cv = document.createElement('canvas'); cv.width = cv.height = 256
    const c = cv.getContext('2d')!
    c.fillStyle = '#000'; c.fillRect(0, 0, 256, 256)
    c.fillStyle = c.strokeStyle = '#fff'; c.lineJoin = 'round'; c.lineWidth = (3 / w) * 256 // 1.5 m wider all round: an aerial mesh draws walls as slopes, and the placing is good to a metre or two
    c.filter = `blur(${((0.5 / w) * 256).toFixed(1)}px)` // a soft edge, so the dissolve starts in the middle and ends at the eaves
    for (const r of rings) { c.beginPath(); r.forEach(([x, y], i) => c[i ? 'lineTo' : 'moveTo'](((x - x0) / w) * 256, (1 - (y - y0) / h) * 256)); c.closePath(); c.fill(); c.stroke() }
    const tex = new THREE.CanvasTexture(cv); tex.minFilter = tex.magFilter = THREE.LinearFilter; tex.generateMipmaps = false
    this.made.push(tex)
    this.uniforms.uMask.value = tex; (this.uniforms.uMaskRect.value as THREE.Vector4).set(x0, y0, w, h)
  }

  private loadTiles(site: Site, scanFromEnu: THREE.Matrix4, list: { url: string }[]) {
    const draco = new DRACOLoader(decoders), ktx = new KTX2Loader(decoders).detectSupport(this.renderer)
    const loader = new GLTFLoader().setDRACOLoader(draco).setKTX2Loader(ktx)
    const material = new THREE.ShaderMaterial({ vertexShader: VERT, fragmentShader: TILE_FRAG })
    this.made.push(material, draco, ktx)
    const tiles = this.tiles = new THREE.Group()
    this.placed.copy(scanFromEnu).multiply(enuFromEcef(site.anchor.lat * RAD, site.anchor.lon * RAD))
    this.place(0)
    this.group.add(tiles)
    this.kind = 'city mesh'; this.total = list.length
    const zUp = new THREE.Matrix4().makeRotationX(Math.PI / 2) // tile content is glTF (y up); earth-centred coordinates are z up
    // nearest first, a few at a time: the ground beside the building is found from the first ones and the rest fade in
    let next = 0
    const pump = () => {
      if (this.gone || next >= list.length) return
      const t = list[next++]
      loader.load(`${this.api}${t.url}`, (gltf) => {
        if (this.gone) return
        gltf.scene.applyMatrix4(zUp)
        gltf.scene.traverse((o) => {
          const mesh = o as THREE.Mesh, old = mesh.material as THREE.MeshStandardMaterial | undefined
          if (!mesh.isMesh || !old) return
          const map = old.map
          if (map) { map.colorSpace = THREE.NoColorSpace; this.made.push(map) } // display values straight through, as the dollhouse does
          const m = material.clone(), born = { value: 0 }
          m.uniforms = { ...this.uniforms, map: { value: map }, uIn: born }
          this.arriving.push(born); this.made.push(m, mesh.geometry)
          mesh.material = m; mesh.frustumCulled = true; old.dispose()
        })
        tiles.add(gltf.scene); tiles.updateMatrixWorld(true)
        this.loaded++
        if (this.loaded <= 12 || this.loaded === list.length) this.calibrate()
        this.onChange(); pump()
      }, undefined, () => { this.loaded++; pump() })
    }
    for (let i = 0; i < 4; i++) pump()
  }

  /** Put the ellipsoid height `h` at the ground level beside the building. */
  private place(h: number) {
    this.ground = -(this.site?.floor_above_ground_m ?? 0.2)
    this.lift = this.ground - h
    const g = this.tiles!
    new THREE.Matrix4().makeTranslation(0, 0, this.lift).multiply(this.placed).decompose(g.position, g.quaternion, g.scale); g.updateMatrixWorld(true)
  }

  /** Find the ground beside the building in the loaded tiles (their heights are above the ellipsoid, which the
      scan knows nothing about) and stand the tiles on it. */
  private calibrate() {
    const tiles = this.tiles
    if (!tiles) return
    const hits: number[] = [], r = this.radius + 3
    for (let i = 0; i < 16; i++) {
      const a = (i / 16) * Math.PI * 2
      this.ray.set(new THREE.Vector3(this.centre.x + Math.cos(a) * r, this.centre.y + Math.sin(a) * r, 400), new THREE.Vector3(0, 0, -1))
      const hit = this.ray.intersectObject(tiles, true)[0]
      if (hit) hits.push(hit.point.z - this.lift) // back to a height above the ellipsoid
    }
    if (hits.length < 6) return
    hits.sort((a, b) => a - b)
    const h = hits[Math.floor(hits.length * 0.25)] // a low quartile: lawn, not hedge or roof
    if (this.groundH === null || Math.abs(h - this.groundH) > 0.05) { this.groundH = h; this.place(h) }
    if (this.status !== 'ready') { this.status = 'ready'; this.show(this.wanted) }
  }

  private async loadTerrain(site: Site, scanFromEnu: THREE.Matrix4) {
    const t: Terrain = await fetch(`${this.api}${site.terrain}`).then((r) => (r.ok ? r.json() : Promise.reject(new Error(`terrain ${r.status}`))))
    const raw = Uint8Array.from(atob(t.heights_cm_b64), (c) => c.charCodeAt(0)), cm = new Int16Array(raw.buffer)
    const [w, s, e, n] = t.bounds_enu
    const geo = new THREE.PlaneGeometry(e - w, n - s, t.width - 1, t.height - 1) // row 0 is the north edge, as in the grid
    geo.translate((w + e) / 2, (s + n) / 2, 0)
    const pos = geo.getAttribute('position') as THREE.BufferAttribute
    for (let i = 0; i < cm.length; i++) pos.setZ(i, cm[i] === -32768 ? 0 : cm[i] / 100)
    const load = (o: Terrain['ortho'][number]) => new Promise<THREE.Texture>((done, fail) => new THREE.TextureLoader().load(`${this.api}${o.url}`, (x) => { x.colorSpace = THREE.NoColorSpace; x.anisotropy = 8; done(x) }, undefined, fail))
    const [far, near] = await Promise.all(t.ortho.map(load))
    const rect = (b: number[]) => new THREE.Vector4(b[0], b[1], b[2] - b[0], b[3] - b[1])
    const mat = new THREE.ShaderMaterial({ vertexShader: TERRAIN_VERT, fragmentShader: TERRAIN_FRAG, uniforms: { ...this.uniforms, uFar: { value: far }, uNear: { value: near }, uFarRect: { value: rect(t.ortho[0].bounds_enu) }, uNearRect: { value: rect(t.ortho[1].bounds_enu) } } })
    const mesh = new THREE.Mesh(geo, mat)
    this.ground = -site.floor_above_ground_m
    mesh.applyMatrix4(new THREE.Matrix4().makeTranslation(0, 0, this.ground).multiply(scanFromEnu)) // grid heights are already above the ground
    mesh.frustumCulled = false
    this.group.add(mesh); this.made.push(geo, mat, far, near)
    this.uniforms.uFade.value = Math.min(FADE_M, (e - w) / 2 - 8)
    this.kind = 'terrain'; this.status = 'ready'; this.show(this.wanted)
  }

  /** Advance. Returns true while anything is fading in or out. Call before rendering. */
  update(dt: number): boolean {
    const s = this.show_
    let moving = s.cur !== s.goal
    if (moving) s.cur += Math.sign(s.goal - s.cur) * Math.min(Math.abs(s.goal - s.cur), dt / 0.9)
    this.group.visible = s.cur > 0.001
    this.uniforms.uShow.value = s.cur * s.cur * (3 - 2 * s.cur)
    if (this.arriving.length) {
      for (const u of this.arriving) u.value = Math.min(1, u.value + dt / 0.6)
      this.arriving = this.arriving.filter((u) => u.value < 1); moving = true
    }
    return moving
  }

  /** 0..1 of the city mesh tiles that have arrived; 1 for terrain or when there is nothing to load. */
  get progress() { return this.total ? this.loaded / this.total : 1 }

  dispose() { this.gone = true; this.made.forEach((m) => m.dispose()) }
}
