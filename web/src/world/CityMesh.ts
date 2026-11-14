// Vexcel's 3D city mesh drawn inside the map's own canvas, as a MapLibre custom layer that shares the map's WebGL
// context with three.js. The map asks for the tiles round where it looks (the server picks them: fine near, coarser
// far, each area once); they are drawn in the same unlit way as the building scene draws its surroundings, so the
// two pictures agree when one hands over to the other. A sun can be set: the mesh then casts shadows on itself.
import * as THREE from 'three'
import { DRACOLoader } from 'three/addons/loaders/DRACOLoader.js'
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js'
import { KTX2Loader } from 'three/addons/loaders/KTX2Loader.js'
import dracoJs from 'three/examples/jsm/libs/draco/gltf/draco_wasm_wrapper.js?url'
import dracoWasm from 'three/examples/jsm/libs/draco/gltf/draco_decoder.wasm?url'
import basisJs from 'three/examples/jsm/libs/basis/basis_transcoder.js?url'
import basisWasm from 'three/examples/jsm/libs/basis/basis_transcoder.wasm?url'
import { groundScale } from './handoff.ts'
import { MercatorCoordinate, type CustomLayerInterface, type CustomRenderMethodInput, type Map as MapLibreMap } from 'maplibre-gl'

export interface CityPatch {
  anchor: { lat: number; lon: number }
  tiles: { url: string; zoom: number; dist_m: number }[]
  capture: (string | null)[]; copyright: string | null
}
type Tile = { state: 'loading' | 'ready' | 'failed'; group: THREE.Object3D | null; born: THREE.IUniform<number>; used: number; made: { dispose(): void }[] }

// the same decoder files the building scene uses (world/WorldView.ts keeps its own copy of these six lines)
const DECODERS: Record<string, string> = { 'draco_wasm_wrapper.js': dracoJs, 'draco_decoder.wasm': dracoWasm, 'basis_transcoder.js': basisJs, 'basis_transcoder.wasm': basisWasm }
const decoders = new THREE.LoadingManager()
decoders.setURLModifier((url) => DECODERS[url.split('/').pop() ?? ''] ?? url)

const RAD = Math.PI / 180
const A = 6378137, E2 = 6.69437999014e-3 // WGS84
const KEEP = 520      // tiles held in memory; the least recently wanted go first
const AT_ONCE = 6
const SHADOW_M = 420  // shadows are worked out this far round the middle of the view

/** East/north/up about a point on the ellipsoid, from earth-centred coordinates. */
export function enuFromEcef(latDeg: number, lonDeg: number): THREE.Matrix4 {
  const lat = latDeg * RAD, lon = lonDeg * RAD
  const sl = Math.sin(lat), cl = Math.cos(lat), so = Math.sin(lon), co = Math.cos(lon), n = A / Math.sqrt(1 - E2 * sl * sl)
  const o = new THREE.Vector3(n * cl * co, n * cl * so, n * (1 - E2) * sl)
  return new THREE.Matrix4().set(-so, co, 0, 0, -sl * co, -sl * so, cl, 0, cl * co, cl * so, sl, 0, 0, 0, 0, 1).multiply(new THREE.Matrix4().makeTranslation(-o.x, -o.y, -o.z))
}

const VERT = /* glsl */ `
  #include <common>
  #include <shadowmap_pars_vertex>
  varying vec2 vUv;
  void main() {
    vUv = uv;
    vec3 transformedNormal = vec3(0.0, 0.0, 1.0);
    vec4 worldPosition = modelMatrix * vec4(position, 1.0);
    gl_Position = projectionMatrix * viewMatrix * worldPosition;
    #include <shadowmap_vertex>
  }`
// Display values straight through, as the building scene does (no colour-space pass), so the two match.
const FRAG = /* glsl */ `
  #include <common>
  #include <packing>
  #include <bsdfs>
  #include <lights_pars_begin>
  #include <shadowmap_pars_fragment>
  #include <shadowmask_pars_fragment>
  varying vec2 vUv;
  uniform sampler2D map; uniform float uShow, uBorn, uShade, uNight;
  float hash(vec2 p) { return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }
  void main() {
    float k = uShow * uBorn;
    if (k < 0.999 && hash(floor(gl_FragCoord.xy)) > k) discard;  // arrives and leaves as a dither: no blending, so no sorting
    vec3 c = texture2D(map, vUv).rgb;
    float lit = mix(1.0, getShadowMask(), uShade) * (1.0 - uNight);
    gl_FragColor = vec4(c * mix(0.46, 1.0, lit), 1.0);
  }`

export class CityMesh implements CustomLayerInterface {
  readonly id = 'city3d'
  readonly type = 'custom' as const
  readonly renderingMode = '3d' as const
  /** The patch being drawn (its capture dates and credit are for a caption). */
  patch: CityPatch | null = null
  /** 'none': the place has no city mesh. */
  status: 'idle' | 'loading' | 'ready' | 'none' = 'idle'
  /** Called when the status, the progress or the patch changes. */
  onChange: () => void = () => {}
  /** Rendered frames, for a frame-rate reading. */
  frames = 0

  private map: MapLibreMap | null = null
  private renderer: THREE.WebGLRenderer | null = null
  private loader: GLTFLoader | null = null
  private scene = new THREE.Scene()
  private camera = new THREE.Camera()
  private ecef = new THREE.Group() // every tile, in earth-centred coordinates; its matrix stands them east/north/up about the anchor
  private sunLight = new THREE.DirectionalLight(0xffffff, 1)
  private material: THREE.ShaderMaterial
  private shared: Record<string, THREE.IUniform>
  private tiles = new Map<string, Tile>()
  private shown: string[] = []
  private next: { patch: CityPatch; ring: [number, number][]; urls: string[]; key: string; exact: boolean } | null = null
  /** Which request the drawn patch answers: `sid:<id>` or `lat,lon`. A hand-off waits for its scan's patch. */
  key = ''
  // A scan's patch is laid out in the map's own metres (Web Mercator's sphere), so the map's camera and the building
  // scene's are exact copies of each other. A roaming patch is laid out in true metres on the ellipsoid, which keeps
  // it on the aerial photo to its edge; the two differ by 0.4% north to south.
  private exact = false
  private queue: string[] = []; private loading = 0
  private anchor = { lat: 0, lon: 0 }
  private ground = 0 // ellipsoid height of the ground at the anchor: drawn at the map's zero
  private show = { cur: 0, goal: 0 }
  private last = 0
  private tick = 0
  private gone = false
  private ray = new THREE.Raycaster()
  private api: string

  constructor(api = '') {
    this.api = api
    this.shared = { uShow: { value: 0 }, uShade: { value: 0 }, uNight: { value: 0 } }
    this.material = new THREE.ShaderMaterial({ vertexShader: VERT, fragmentShader: FRAG, lights: true, side: THREE.DoubleSide, // the map's matrix mirrors y, so the winding cannot be trusted
      uniforms: THREE.UniformsUtils.merge([THREE.UniformsLib.lights, { map: { value: null }, uBorn: { value: 1 }, uShow: { value: 0 }, uShade: { value: 0 }, uNight: { value: 0 } }]) })
    this.ecef.matrixAutoUpdate = false
    this.scene.add(this.ecef)
    const s = this.sunLight.shadow
    s.mapSize.set(4096, 4096); s.bias = -0.0004; s.normalBias = 0
    Object.assign(s.camera, { left: -SHADOW_M, right: SHADOW_M, top: SHADOW_M, bottom: -SHADOW_M, near: 10, far: 3000 })
    s.camera.updateProjectionMatrix()
    this.scene.add(this.sunLight.target)
  }

  // ---- MapLibre's side ------------------------------------------------------------------------------------------

  onAdd(map: MapLibreMap, gl: WebGL2RenderingContext) {
    this.map = map
    if (this.renderer) return // put back after a change of style: everything is already made
    const r = this.renderer = new THREE.WebGLRenderer({ canvas: map.getCanvas(), context: gl, antialias: true })
    r.autoClear = false
    r.shadowMap.enabled = true; r.shadowMap.type = THREE.PCFShadowMap; r.shadowMap.autoUpdate = false
    const draco = new DRACOLoader(decoders), ktx = new KTX2Loader(decoders).detectSupport(r)
    this.loader = new GLTFLoader().setDRACOLoader(draco).setKTX2Loader(ktx)
    this.pump()
  }
  onRemove() { /* a change of style takes the layer off and the look puts it back; dispose() is the real end */ }

  render(gl: WebGL2RenderingContext, args: CustomRenderMethodInput) {
    const r = this.renderer, map = this.map
    if (!r || !map) return
    const now = performance.now(), dt = Math.min(0.05, (now - this.last) / 1000 || 0.016); this.last = now
    const s = this.show
    let moving = s.cur !== s.goal
    if (moving) s.cur += Math.sign(s.goal - s.cur) * Math.min(Math.abs(s.goal - s.cur), dt / 0.45)
    this.shared.uShow.value = s.cur
    for (const u of this.shown) { const t = this.tiles.get(u); if (t && t.born.value < 1) { t.born.value = Math.min(1, t.born.value + dt / 0.5); moving = true } }
    if (s.cur <= 0.001 || !this.shown.length) { if (moving) map.triggerRepaint(); return }
    // the map's matrix takes Web Mercator (0..1, y south) to the screen; this puts metres east/north/up about the anchor into it
    // (true metres on the ellipsoid across the ground; the map's own metre upward, so its camera heights are ours)
    const mc = MercatorCoordinate.fromLngLat([this.anchor.lon, this.anchor.lat], 0), k = mc.meterInMercatorCoordinateUnits(), g = groundScale(this.anchor.lat)
    this.camera.projectionMatrix.fromArray(args.defaultProjectionData.mainMatrix as unknown as number[])
      .multiply(new THREE.Matrix4().makeTranslation(mc.x, mc.y, 0).scale(this.exact ? new THREE.Vector3(k, -k, k) : new THREE.Vector3(1 / (2 * Math.PI * g.east), -1 / (2 * Math.PI * g.north), k)))
    this.camera.projectionMatrixInverse.copy(this.camera.projectionMatrix).invert()
    r.resetState()
    r.setViewport(0, 0, gl.drawingBufferWidth, gl.drawingBufferHeight) // three keeps the size it was made at; the map resizes its canvas
    // The map leaves a narrowed depth range set for its own layers. A shadow map drawn through it stores depths about
    // 0.1% short, which reads back as everything being in shade, so the frame that redraws the shadows uses the full range.
    const shadows = this.sunLight.parent && r.shadowMap.needsUpdate, range = shadows ? (gl.getParameter(gl.DEPTH_RANGE) as Float32Array) : null
    if (shadows) { this.aimSun(); gl.depthRange(0, 1) }
    r.render(this.scene, this.camera)
    if (range) gl.depthRange(range[0], range[1])
    r.resetState()
    this.frames++
    if (moving) map.triggerRepaint()
  }

  // ---- the look's side ------------------------------------------------------------------------------------------

  /** Draw or hide. Fades as a dither over half a second. */
  setShown(on: boolean) { if ((on ? 1 : 0) !== this.show.goal) { this.show.goal = on ? 1 : 0; this.map?.triggerRepaint() } }
  get visible() { return this.show.goal === 1 }
  /** 0..1 of the wanted patch's tiles that have arrived. */
  get progress() { const n = this.next; if (!n) return 1; return n.urls.length ? n.urls.filter((u) => this.tiles.get(u)?.state !== 'loading' && this.tiles.has(u)).length / n.urls.length : 1 }

  /** Ask for the patch round a point, or round a scan (then the near tiles are the ones its building scene draws).
      `ring`: where the ground is sampled, as east/north metres about the patch's anchor; missing is a 30 m circle. */
  async want(at: { lat: number; lon: number } | { sid: string }, ring?: [number, number][]): Promise<CityPatch | null> {
    const my = ++this.tick
    const q = 'sid' in at ? `sid=${encodeURIComponent(at.sid)}` : `lat=${at.lat.toFixed(5)}&lon=${at.lon.toFixed(5)}`
    let patch: CityPatch | null = null
    try { patch = await fetch(`${this.api}/api/layers/city3d?${q}`).then((r) => (r.ok ? r.json() : null)) } catch { patch = null }
    if (this.gone || my !== this.tick) return patch // a later request overtook this one
    if (!patch || !patch.tiles.length) { if (!this.shown.length) { this.status = 'none'; this.onChange() } return patch }
    const same = this.patch && this.exact === 'sid' in at && this.patch.anchor.lat === patch.anchor.lat && this.patch.anchor.lon === patch.anchor.lon && this.patch.tiles.length === patch.tiles.length
    if (same && !this.next) return patch
    const urls = patch.tiles.map((t) => t.url)
    this.next = { patch, urls, key: 'sid' in at ? `sid:${at.sid}` : q, exact: 'sid' in at, ring: ring ?? Array.from({ length: 16 }, (_, i) => [Math.cos((i / 16) * 2 * Math.PI) * 30, Math.sin((i / 16) * 2 * Math.PI) * 30] as [number, number]) }
    this.status = 'loading'
    urls.forEach((u) => { const t = this.tiles.get(u); if (t) t.used = performance.now() })
    this.queue = urls.filter((u) => !this.tiles.has(u))
    // the first patch shows as it arrives; a later one replaces the first in one step, so no area is drawn at two levels of detail
    if (!this.shown.length) this.adopt(false)
    this.pump(); this.settle(); this.onChange()
    return patch
  }

  /** The sun, as the direction to it (compass degrees, degrees above the horizon), or null for none. Below the
      horizon everything is in shade. */
  setSun(sun: { azimuth: number; altitude: number } | null) {
    const on = !!sun && sun.altitude > 0
    this.shared.uShade.value = on ? 1 : 0
    this.shared.uNight.value = sun && sun.altitude <= 0 ? 1 : 0
    if (on) {
      const a = sun.azimuth * RAD, h = sun.altitude * RAD
      this.sunDir.set(Math.sin(a) * Math.cos(h), Math.cos(a) * Math.cos(h), Math.sin(h))
      this.sunLight.castShadow = true
      this.sunLight.shadow.bias = -0.0004 / Math.max(0.15, Math.sin(h)) // a low sun grazes flat ground: more slack, or the ground stripes
      if (!this.sunLight.parent) this.scene.add(this.sunLight)
    } else if (this.sunLight.parent) this.scene.remove(this.sunLight)
    if (this.renderer) this.renderer.shadowMap.needsUpdate = true
    this.map?.triggerRepaint()
  }
  private sunDir = new THREE.Vector3(0, 0, 1)
  /** Shadows are worked out round a point (east/north metres about the anchor): call when the view has moved on. */
  shadowsAt(lon: number, lat: number) {
    const p = this.enuOf(lon, lat)
    if (Math.hypot(p[0] - this.sunLight.target.position.x, p[1] - this.sunLight.target.position.y) < 60) return
    this.sunLight.target.position.set(p[0], p[1], 0)
    if (this.renderer && this.sunLight.parent) { this.renderer.shadowMap.needsUpdate = true; this.map?.triggerRepaint() }
  }
  private aimSun() {
    const t = this.sunLight.target.position
    this.sunLight.position.copy(t).addScaledVector(this.sunDir, 1500)
    this.sunLight.target.updateMatrixWorld(); this.sunLight.updateMatrixWorld()
  }

  /** Hours of direct sun at a point on the mesh between two instants, by casting a ray to the sun every `stepMin`
      minutes. `sunAt` gives the sun for an instant. Returns null where the mesh has nothing under the point. */
  sunlight(lon: number, lat: number, from: Date, to: Date, sunAt: (t: Date) => { azimuth: number; altitude: number }, stepMin = 10): { hours: number; samples: number } | null {
    const [e, n] = this.enuOf(lon, lat), meshes = this.meshes(this.shown)
    this.ray.set(new THREE.Vector3(e, n, 2000), new THREE.Vector3(0, 0, -1)); this.ray.far = Infinity
    const top = this.ray.intersectObjects(meshes, false)[0]
    if (!top) return null
    const at = top.point.clone().setZ(top.point.z + 0.3) // just off the surface, so it does not shade itself
    let lit = 0, samples = 0
    for (let t = from.getTime(); t < to.getTime(); t += stepMin * 60000) {
      const s = sunAt(new Date(t))
      if (s.altitude <= 0) continue
      samples++
      const a = s.azimuth * RAD, h = s.altitude * RAD
      this.ray.set(at, new THREE.Vector3(Math.sin(a) * Math.cos(h), Math.cos(a) * Math.cos(h), Math.sin(h)))
      if (!this.ray.intersectObjects(meshes, false).length) lit++
    }
    return { hours: (lit * stepMin) / 60, samples }
  }

  dispose() {
    this.gone = true
    for (const t of this.tiles.values()) t.made.forEach((m) => m.dispose())
    this.tiles.clear(); this.material.dispose(); this.sunLight.shadow.map?.dispose()
    // the context is the map's: three's renderer is dropped without losing it
  }

  // ---- tiles ----------------------------------------------------------------------------------------------------

  private enuOf(lon: number, lat: number): [number, number] {
    const a = MercatorCoordinate.fromLngLat([this.anchor.lon, this.anchor.lat], 0), p = MercatorCoordinate.fromLngLat([lon, lat], 0), g = groundScale(this.anchor.lat), k = a.meterInMercatorCoordinateUnits()
    return this.exact ? [(p.x - a.x) / k, -(p.y - a.y) / k] : [(p.x - a.x) * 2 * Math.PI * g.east, -(p.y - a.y) * 2 * Math.PI * g.north]
  }
  private meshes(urls: string[]) {
    const out: THREE.Object3D[] = []
    for (const u of urls) this.tiles.get(u)?.group?.traverse((o) => { if ((o as THREE.Mesh).isMesh) out.push(o) })
    return out
  }

  private pump() {
    const loader = this.loader
    if (!loader) return
    while (this.loading < AT_ONCE && this.queue.length) {
      const url = this.queue.shift()!
      if (this.tiles.has(url)) continue
      const tile: Tile = { state: 'loading', group: null, born: { value: 0 }, used: performance.now(), made: [] }
      this.tiles.set(url, tile); this.loading++
      const done = () => { this.loading--; this.settle(); this.pump(); this.onChange() }
      loader.load(`${this.api}${url}`, (gltf) => {
        if (this.gone) return
        gltf.scene.applyMatrix4(new THREE.Matrix4().makeRotationX(Math.PI / 2)) // tile content is glTF (y up); earth-centred coordinates are z up
        gltf.scene.traverse((o) => {
          const mesh = o as THREE.Mesh, old = mesh.material as THREE.MeshStandardMaterial | undefined
          if (!mesh.isMesh || !old) return
          const map = old.map
          if (map) { map.colorSpace = THREE.NoColorSpace; tile.made.push(map) }
          const m = this.material.clone()
          m.uniforms = { ...m.uniforms, ...this.shared, map: { value: map }, uBorn: tile.born }
          mesh.material = m; mesh.castShadow = mesh.receiveShadow = true
          tile.made.push(m, mesh.geometry); old.dispose()
        })
        gltf.scene.visible = false
        tile.group = gltf.scene; tile.state = 'ready'
        this.ecef.add(gltf.scene)
        done()
      }, undefined, () => { tile.state = 'failed'; done() })
    }
  }

  /** The wanted patch has arrived (or as much of it as will): stand it on its ground and draw it in place of the last. */
  private settle() {
    const n = this.next
    if (!n) return
    const got = n.urls.filter((u) => this.tiles.get(u)?.state === 'ready').length, pending = n.urls.some((u) => !this.tiles.has(u) || this.tiles.get(u)!.state === 'loading')
    const first = this.patch === n.patch // the first patch is already being drawn as it arrives
    if (first && (got <= 12 || !pending)) this.place(n)
    if (first) this.shown = n.urls.filter((u) => this.tiles.get(u)?.state === 'ready')
    if (pending) { this.showOnly(); return }
    if (!first) this.adopt(true)
    this.next = null
    this.status = this.shown.length ? 'ready' : 'none'
    this.evict()
    if (this.renderer) this.renderer.shadowMap.needsUpdate = true
    this.showOnly()
  }
  private adopt(place: boolean) {
    const n = this.next!
    this.patch = n.patch; this.anchor = n.patch.anchor; this.key = n.key; this.exact = n.exact
    if (place) { this.shown = n.urls.filter((u) => this.tiles.get(u)?.state === 'ready'); this.place(n) } else this.shown = []
    this.sunLight.target.position.set(0, 0, 0)
  }
  private showOnly() {
    const on = new Set(this.shown)
    for (const [u, t] of this.tiles) if (t.group) t.group.visible = on.has(u)
    this.map?.triggerRepaint()
  }

  /** Find the ground in the patch's own tiles (their heights are above the ellipsoid) and stand it at the map's zero.
      The low quartile of sixteen rays, as the building scene does it, so both stand the same tiles at the same height. */
  private place(n: { patch: CityPatch; ring: [number, number][]; urls: string[] }) {
    const base = enuFromEcef(n.patch.anchor.lat, n.patch.anchor.lon)
    this.ecef.matrix.copy(base); this.ecef.updateMatrixWorld(true)
    const meshes = this.meshes(n.urls), hits: number[] = []
    this.ray.far = Infinity
    for (const [e, nn] of n.ring) {
      this.ray.set(new THREE.Vector3(e, nn, 2000), new THREE.Vector3(0, 0, -1))
      const hit = this.ray.intersectObjects(meshes, false)[0]
      if (hit) hits.push(hit.point.z)
    }
    if (hits.length >= 6) { hits.sort((a, b) => a - b); this.ground = hits[Math.floor(hits.length * 0.25)] }
    this.ecef.matrix.copy(new THREE.Matrix4().makeTranslation(0, 0, -this.ground).multiply(base)); this.ecef.updateMatrixWorld(true)
  }

  private evict() {
    if (this.tiles.size <= KEEP) return
    const keep = new Set(this.shown)
    const old = [...this.tiles].filter(([u, t]) => !keep.has(u) && t.state !== 'loading').sort((a, b) => a[1].used - b[1].used)
    for (const [u, t] of old.slice(0, this.tiles.size - KEEP)) { if (t.group) this.ecef.remove(t.group); t.made.forEach((m) => m.dispose()); this.tiles.delete(u) }
  }
}
