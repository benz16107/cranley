// Panorama viewer: six cube faces on a box around the scan position, in the same scene as the walls.
// Face layout, checked by drawing ScanPlan doorways into panoramas of three scans (<scan-id>, <scan-id>, <scan-id>):
// in the panorama's own frame face 1 looks along +x, face 2 is to its right (-y), 3 behind, 4 left, 0 up, 5 down,
// and the frame is turned into the scan frame by the panorama's `rotation` quaternion.
import * as THREE from 'three'
import type { Pano } from '../types.ts'

const HALF = 12 // metres from the scan position to each face; a finite box makes a walk read as travel

// centre, image-right and image-up directions of each face, in the panorama's own frame
const FACES: [THREE.Vector3Tuple, THREE.Vector3Tuple, THREE.Vector3Tuple][] = [
  [[0, 0, 1], [0, -1, 0], [-1, 0, 0]], // 0 up: top of the image points backwards
  [[1, 0, 0], [0, -1, 0], [0, 0, 1]],  // 1 forward
  [[0, -1, 0], [-1, 0, 0], [0, 0, 1]], // 2 right
  [[-1, 0, 0], [0, 1, 0], [0, 0, 1]],  // 3 back
  [[0, 1, 0], [1, 0, 0], [0, 0, 1]],   // 4 left
  [[0, 0, -1], [0, -1, 0], [1, 0, 0]], // 5 down: top of the image points forwards
]

const FRAG = /* glsl */ `
  varying vec2 vUv;
  uniform sampler2D tA, tB; uniform float uHasB, uWipe, uOpacity, uWidth;
  void main() {
    bool empty = uHasB > 0.5 && uWipe >= 0.0 && gl_FragCoord.x > uWipe * uWidth; // furnished left of the divider, empty right
    gl_FragColor = vec4((empty ? texture2D(tB, vUv) : texture2D(tA, vUv)).rgb, uOpacity);
  }`

class Cube {
  group = new THREE.Group()
  uniforms = { uHasB: { value: 0 }, uWipe: { value: -1 }, uOpacity: { value: 0 }, uWidth: { value: 1 } }
  private mats: THREE.ShaderMaterial[] = []
  private textures: THREE.Texture[] = []
  constructor(order: number) {
    FACES.forEach(([c, r, u]) => {
      const C = new THREE.Vector3(...c).multiplyScalar(HALF), R = new THREE.Vector3(...r).multiplyScalar(HALF), U = new THREE.Vector3(...u).multiplyScalar(HALF)
      const g = new THREE.BufferGeometry()
      const p = [C.clone().sub(R).sub(U), C.clone().add(R).sub(U), C.clone().add(R).add(U), C.clone().sub(R).add(U)]
      g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(p.flatMap((v) => v.toArray())), 3))
      g.setAttribute('uv', new THREE.BufferAttribute(new Float32Array([0, 0, 1, 0, 1, 1, 0, 1]), 2))
      g.setIndex([0, 1, 2, 0, 2, 3])
      const mat = new THREE.ShaderMaterial({
        vertexShader: 'varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }',
        fragmentShader: FRAG, uniforms: { ...this.uniforms, tA: { value: null }, tB: { value: null } },
        side: THREE.DoubleSide, depthTest: false, depthWrite: false, transparent: true,
      })
      const mesh = new THREE.Mesh(g, mat); mesh.renderOrder = order; mesh.frustumCulled = false
      this.mats.push(mat); this.group.add(mesh)
    })
    this.group.visible = false
  }
  set(pano: Pano, furnished: THREE.Texture[], empty: THREE.Texture[] | null) {
    this.disposeTextures()
    this.textures = [...furnished, ...(empty ?? [])]
    this.mats.forEach((m, i) => { m.uniforms.tA.value = furnished[i]; m.uniforms.tB.value = empty?.[i] ?? null })
    this.uniforms.uHasB.value = empty ? 1 : 0
    this.group.position.set(...pano.position)
    if (pano.rotation) this.group.quaternion.set(...pano.rotation); else this.group.quaternion.identity()
  }
  addEmpty(empty: THREE.Texture[]) {
    this.textures.push(...empty)
    this.mats.forEach((m, i) => (m.uniforms.tB.value = empty[i]))
    this.uniforms.uHasB.value = 1
  }
  disposeTextures() { this.textures.forEach((t) => t.dispose()); this.textures = [] }
}

export class PanoView {
  group = new THREE.Group()
  current: Pano | null = null
  hasEmpty = false
  private a = new Cube(-10); private b = new Cube(-9) // b fades in over a, then they swap
  private fade = 1
  private loader = new THREE.TextureLoader()
  private token = 0

  private api: string; private sid: string; private defurnished: boolean
  constructor(api: string, sid: string, defurnished: boolean) {
    this.api = api; this.sid = sid; this.defurnished = defurnished
    this.group.add(this.a.group, this.b.group)
  }

  private faces(pano: Pano, view: 'furnished' | 'defurnished') {
    return Promise.all(FACES.map((_, k) => this.loader.loadAsync(`${this.api}/api/scan/${this.sid}/pano/${pano.id}/${k}.jpg?res=2k&view=${view}`).then((t) => {
      t.colorSpace = THREE.NoColorSpace; t.generateMipmaps = false; t.minFilter = t.magFilter = THREE.LinearFilter
      t.wrapS = t.wrapT = THREE.ClampToEdgeWrapping
      return t
    })))
  }

  /** Load a scan position and cross-fade to it. Resolves once its faces are on screen-ready; rejects if superseded. */
  async show(pano: Pano): Promise<void> {
    const token = ++this.token
    const furnished = await this.faces(pano, 'furnished')
    if (token !== this.token) { furnished.forEach((t) => t.dispose()); throw new Error('superseded') }
    this.b.set(pano, furnished, null)
    this.b.uniforms.uWipe.value = this.a.uniforms.uWipe.value
    this.b.group.visible = true; this.b.uniforms.uOpacity.value = 0
    this.fade = this.current ? 0 : 1
    this.current = pano; this.hasEmpty = false
    if (this.defurnished) this.faces(pano, 'defurnished').then((empty) => { // the empty view arrives second; the wipe waits for it
      if (this.current !== pano) { empty.forEach((t) => t.dispose()); return }
      (this.shown === pano ? this.a : this.b).addEmpty(empty); this.hasEmpty = true; this.onLoad()
    }).catch(() => {})
  }
  private shown: Pano | null = null
  onLoad: () => void = () => {}

  setWipe(x: number | null, width: number) {
    for (const c of [this.a, this.b]) { c.uniforms.uWipe.value = x ?? -1; c.uniforms.uWidth.value = width }
  }

  /** Opacity of the whole viewer (for the dive in from the dollhouse) and the cross-fade between positions. */
  update(dt: number, presence: number): boolean {
    let moving = false
    if (this.current && this.shown !== this.current) {
      this.fade = Math.min(1, this.fade + dt / 0.55); moving = true
      if (this.fade >= 1) { // the incoming cube becomes the resting one
        const old = this.a; this.a = this.b; this.b = old
        this.b.group.visible = false; this.b.disposeTextures()
        this.a.group.children.forEach((m) => ((m as THREE.Mesh).renderOrder = -10)); this.b.group.children.forEach((m) => ((m as THREE.Mesh).renderOrder = -9))
        this.shown = this.current
      }
    }
    const k = this.fade * this.fade * (3 - 2 * this.fade)
    if (this.shown === this.current) { this.a.uniforms.uOpacity.value = presence; this.a.group.visible = presence > 0.001 }
    else { this.a.uniforms.uOpacity.value = presence; this.b.uniforms.uOpacity.value = presence * k; this.a.group.visible = this.b.group.visible = presence > 0.001 }
    return moving
  }

  dispose() { this.token++; this.a.disposeTextures(); this.b.disposeTextures() }
}
