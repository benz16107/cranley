// Our photoreal dollhouse: the scanned mesh of the building, coloured by the server from the panoramas (each
// triangle takes the panorama that sees it best). The geometry arrives in a second or two and is drawn as a plain
// clay model; the colour atlas takes a minute or two the first time a scan is asked for, and is swapped in when it is
// ready. Back faces are not drawn, so from outside you look through the near walls into the rooms.
// Every triangle knows its floor, so the cut, the floor buttons and "pull apart" work as they do on the drawn walls.
import * as THREE from 'three'

const FLOORS = 8 // as the dollhouse's MAX_FLOORS
const VERT = /* glsl */ `
  attribute vec4 aNormal; // xyz the normal, w the floor index
  varying vec2 vUv; varying vec3 vW, vN; varying float vAbove, vFloor;
  uniform float uFloorBase[${FLOORS}], uFloorZ[${FLOORS}];
  void main() {
    int f = int(aNormal.w + 0.5);
    vUv = uv; vN = aNormal.xyz / 127.0; vFloor = aNormal.w;
    vAbove = position.z - uFloorBase[f];                      // height above its own floor, for the cut
    vec3 p = position; p.z += uFloorZ[f] - uFloorBase[f];     // floors pulled apart ride with the dollhouse's
    vW = p; gl_Position = projectionMatrix * viewMatrix * vec4(p, 1.0);
  }`

const FRAG = /* glsl */ `
  varying vec2 vUv; varying vec3 vW, vN; varying float vAbove, vFloor;
  uniform sampler2D map; uniform float uHasMap, uCut, uShow, uWater, uClay;
  uniform float uFloorShow[${FLOORS}];
  uniform vec3 uPaper, uInk, uStage, uWaterCol;
  float hash(vec2 p) { return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }
  void main() {
    if (vAbove > uCut || uFloorShow[int(vFloor + 0.5)] < 0.5) discard;
    if (hash(floor(gl_FragCoord.xy)) > uShow) discard;      // arrives and leaves as a dither, so it never needs sorting
    vec3 n = normalize(vN);
    float lit = 0.74 + 0.26 * dot(n, normalize(vec3(-0.45, -0.62, 0.64)));
    vec3 clay = uPaper * lit;
    vec3 col = mix(texture2D(map, vUv).rgb, clay, max(uClay, 1.0 - uHasMap));
    if (uWater > -900.0) {                                   // flood: the same tint and water line as the drawn walls
      float d = uWater - vW.z;
      col = mix(col, uWaterCol, step(0.0, d) * 0.5);
      float w = fwidth(vW.z) * 1.2 + 0.006;
      col = mix(col, vec3(1.0), (1.0 - smoothstep(w * 0.5, w, abs(d))) * 0.85);
    }
    gl_FragColor = vec4(col, 1.0);
  }`

export class ScanMesh {
  group = new THREE.Group()
  status: 'idle' | 'loading' | 'ready' | 'missing' = 'idle'
  /** The colour atlas: 'baking' with a progress, 'ready', or 'none' when it could not be made. */
  colour: 'none' | 'baking' | 'ready' = 'none'
  progress = 0
  triangles = 0
  onChange: () => void = () => {}
  uniforms: Record<string, THREE.IUniform>
  private show_ = { cur: 0, goal: 0 }
  private mesh: THREE.Mesh | null = null
  private timer = 0
  private gone = false

  private api: string; private sid: string
  /** `floors`: the dollhouse's own uniforms for the cut height, which floors show and where each floor stands, and
      each floor's resting height, so the mesh follows the same controls. */
  constructor(api: string, sid: string, tok: { paper: number[]; ink: number[]; stage: number[]; water: number[] }, floors: { uCut: THREE.IUniform; uFloorShow: THREE.IUniform; uFloorZ: THREE.IUniform; base: number[] }) {
    this.api = api; this.sid = sid
    const v3 = (c: number[]) => ({ value: new THREE.Vector3(c[0], c[1], c[2]) })
    const base = new Float32Array(FLOORS); base.set(floors.base.slice(0, FLOORS))
    this.uniforms = {
      uCut: floors.uCut, uFloorShow: floors.uFloorShow, uFloorZ: floors.uFloorZ, uFloorBase: { value: base },
      map: { value: null }, uHasMap: { value: 0 }, uShow: { value: 0 }, uWater: { value: -1000 }, uClay: { value: 0 },
      uPaper: v3(tok.paper), uInk: v3(tok.ink), uStage: v3(tok.stage), uWaterCol: v3(tok.water),
    }
    this.group.visible = false
  }

  show(on: boolean) { this.show_.goal = on ? 1 : 0; if (on && this.status === 'idle') void this.load() }
  setWater(z: number) { this.uniforms.uWater.value = z }
  /** 1 draws the bare form with no photo colour. */
  setClay(k: number) { this.uniforms.uClay.value = k }

  private async load() {
    this.status = 'loading'; this.onChange()
    try {
      // v is the file layout's number: the answer is cached for a day, so a new layout needs a new address
      const buf = await fetch(`${this.api}/api/world/${this.sid}/mesh?v=5`).then((r) => (r.ok ? r.arrayBuffer() : Promise.reject(new Error(`mesh ${r.status}`))))
      if (this.gone) return
      const head = new DataView(buf)
      if (new TextDecoder().decode(buf.slice(0, 4)) !== 'THM2') throw new Error('not a mesh')
      const n = head.getUint32(4, true) * 3 // corners
      const geo = new THREE.BufferGeometry()
      geo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(buf, 8, n * 3), 3))
      geo.setAttribute('aNormal', new THREE.BufferAttribute(new Int8Array(buf, 8 + n * 12, n * 4), 4)) // not normalised: w is a floor index
      geo.setAttribute('uv', new THREE.BufferAttribute(new Uint16Array(buf, 8 + n * 16, n * 2), 2, true))
      this.mesh = new THREE.Mesh(geo, new THREE.ShaderMaterial({ vertexShader: VERT, fragmentShader: FRAG, uniforms: this.uniforms, side: THREE.FrontSide }))
      this.mesh.frustumCulled = false
      this.group.add(this.mesh)
      this.triangles = n / 3; this.status = 'ready'
      void this.poll()
    } catch (e) {
      console.warn('[scene] scanned mesh unavailable:', (e as Error).message)
      this.status = 'missing'
    }
    this.onChange()
  }

  /** Ask for the colour atlas until it is baked. The first request for a scan starts the bake. */
  private async poll() {
    if (this.gone) return
    const st = await fetch(`${this.api}/api/world/${this.sid}/mesh/status`).then((r) => r.json()).catch(() => ({ state: 'failed' }))
    if (this.gone) return
    if (st.state === 'ready') {
      // the atlas only fits the mesh it was baked for, and both are cached for a day: name the bake in the address
      new THREE.TextureLoader().load(`${this.api}/api/world/${this.sid}/mesh/atlas.jpg?v=${st.version}-${st.triangles}`, (t) => {
        // every triangle has its own cell in the atlas, so smaller mip levels would mix neighbours that are not neighbours
        t.colorSpace = THREE.NoColorSpace; t.generateMipmaps = false; t.minFilter = t.magFilter = THREE.LinearFilter
        if (this.gone) { t.dispose(); return }
        this.uniforms.map.value = t; this.uniforms.uHasMap.value = 1; this.colour = 'ready'; this.onChange()
      })
    } else if (st.state === 'baking') {
      this.colour = 'baking'; this.progress = st.progress ?? 0; this.onChange()
      this.timer = window.setTimeout(() => void this.poll(), 2500)
    } else { this.colour = 'none'; this.onChange() }
  }

  update(dt: number): boolean {
    const s = this.show_, moving = s.cur !== s.goal
    if (moving) s.cur += Math.sign(s.goal - s.cur) * Math.min(Math.abs(s.goal - s.cur), dt / 0.5)
    this.group.visible = s.cur > 0.001 && !!this.mesh
    this.uniforms.uShow.value = s.cur
    return moving
  }

  dispose() {
    this.gone = true; clearTimeout(this.timer)
    this.mesh?.geometry.dispose(); (this.mesh?.material as THREE.Material | undefined)?.dispose()
    ;(this.uniforms.map.value as THREE.Texture | null)?.dispose()
  }
}
