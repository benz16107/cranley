// The dollhouse: extruded walls with openings cut out, one photo-textured quad per floor, scan-position rings.
// Every room, wall and opening reads its look from one small style texture, so a rule or a lens never rebuilds geometry.
import * as THREE from 'three'
import { Line2 } from 'three/addons/lines/Line2.js'
import { LineGeometry } from 'three/addons/lines/LineGeometry.js'
import { LineMaterial } from 'three/addons/lines/LineMaterial.js'
import { STUB, openingSpan, roomAt, sightBlocked, wallBoxes, wallHeight, type Model, type RGB, type Style } from '../model.ts'
import type { Tokens } from '../tokens.ts'
import type { Pick, Vec3 } from '../types.ts'

export const MAX_FLOORS = 8
const EXPLODE_GAP = 3.4 // extra metres between floors when fully pulled apart

const STYLE_GLSL = /* glsl */ `
  uniform sampler2D uStyle;
  uniform float uFloorZ[${MAX_FLOORS}];
  uniform float uFloorShow[${MAX_FLOORS}];
  uniform float uCut, uMaxH, uReveal, uWater, uOccluder, uXray, uLift;
  uniform vec3 uPaper, uInk, uGlass, uStage, uWaterCol;
  vec4 styleA(float e) { return texelFetch(uStyle, ivec2(int(e + 0.5), 0), 0); } // tint rgb, tint amount
  vec4 styleB(float e) { return texelFetch(uStyle, ivec2(int(e + 0.5), 1), 0); } // wash, height, alpha
`

const WALL_VERT = /* glsl */ `
  attribute float aElem, aFloor, aKind;
  varying vec3 vN, vW; varying float vLz, vElem, vKind, vFloor;
  ${STYLE_GLSL}
  void main() {
    vec3 p = position; vLz = p.z; p.z += uFloorZ[int(aFloor + 0.5)];
    vW = p; vN = normal; vElem = aElem; vKind = aKind; vFloor = aFloor;
    gl_Position = projectionMatrix * viewMatrix * vec4(p, 1.0);
  }`

const WALL_FRAG = /* glsl */ `
  varying vec3 vN, vW; varying float vLz, vElem, vKind, vFloor;
  ${STYLE_GLSL}
  void main() {
    vec4 A = styleA(vElem), B = styleB(vElem);
    float show = uFloorShow[int(vFloor + 0.5)];
    if (uOccluder > 0.5) { if (vKind > 0.5) discard; gl_FragColor = vec4(1.0); return; } // panorama: walls only hide what is behind them
    // The cut-away. A dimmed room's walls drop to a stub; a hidden room's walls sink into the floor.
    float cut = min(uCut, mix(${STUB.toFixed(2)}, uMaxH + 0.01, B.y)) * B.z * show * uReveal;
    if (vKind < 1.5 && vLz > cut + 1e-4) discard;
    if (B.z * show < 0.02) discard;
    vec3 n = normalize(vN);
    bool cap = vKind < 0.5 && ((!gl_FrontFacing && uXray < 0.5) || n.z > 0.9); // back faces seen through the cut read as a solid cut face (not in x-ray, where every face is glass)
    float lit = 0.80 + 0.20 * dot(n, normalize(vec3(-0.45, -0.62, 0.64)));
    float ao = mix(0.84, 1.0, smoothstep(0.0, 0.55, vLz));
    vec3 col = vKind < 0.5 ? uPaper * lit * ao : vKind < 1.5 ? uGlass * (0.9 + 0.1 * lit) : mix(uPaper, uInk, 0.3);
    if (cap) col = uInk;
    col = mix(col, cap ? mix(A.rgb, uInk, 0.25) : A.rgb, A.a);
    if (uWater > -900.0) { // flood: tint what is under water and draw the water line where it meets the wall
      float d = uWater - vW.z;
      col = mix(col, uWaterCol, step(0.0, d) * 0.5);
      float w = fwidth(vW.z) * 1.2 + 0.006;
      col = mix(col, vec3(1.0), (1.0 - smoothstep(w * 0.5, w, abs(d))) * 0.85);
    }
    gl_FragColor = vec4(col, mix(1.0, cap ? 0.92 : 0.13, uXray)); // x-ray: glass faces, inked tops
  }`

const FLOOR_VERT = /* glsl */ `
  varying vec3 vW; uniform float uFloorIdx;
  ${STYLE_GLSL}
  void main() {
    vec3 p = position; p.z += uFloorZ[int(uFloorIdx + 0.5)] + uLift; vW = p;
    gl_Position = projectionMatrix * viewMatrix * vec4(p, 1.0);
  }`

const FLOOR_FRAG = /* glsl */ `
  varying vec3 vW; uniform float uFloorIdx, uHasPhoto, uPanoTint;
  uniform sampler2D uPhoto, uIds, uAo;
  uniform vec4 uGrid, uPhotoRect; // x, y, width, height in metres
  uniform vec2 uGridPx;
  ${STYLE_GLSL}
  void main() {
    vec2 g = (vW.xy - uGrid.xy) / uGrid.zw;
    vec4 id = texelFetch(uIds, ivec2(clamp(g, 0.0, 0.9999) * uGridPx), 0);
    float elem = floor(id.r * 255.0 + 0.5) + floor(id.g * 255.0 + 0.5) * 256.0;
    vec4 A = styleA(elem), B = styleB(elem);
    float show = uFloorShow[int(uFloorIdx + 0.5)];
    if (uPanoTint > 0.5) { // inside a panorama only the lens or rule colour is laid over the photographed floor
      if (A.a < 0.02 || elem < 0.5) discard;
      gl_FragColor = vec4(A.rgb, A.a * 0.42 * B.z); return;
    }
    vec2 uv = (vW.xy - uPhotoRect.xy) / uPhotoRect.zw;
    vec4 photo = (uHasPhoto > 0.5 && uv.x > 0.0 && uv.x < 1.0 && uv.y > 0.0 && uv.y < 1.0) ? texture2D(uPhoto, uv) : vec4(0.0);
    if (elem < 0.5 && photo.a < 0.5) discard; // neither a room nor a photographed surface
    vec3 col = mix(mix(uPaper, uStage, 0.35), photo.rgb, photo.a);
    col *= 1.0 - 0.34 * texture2D(uAo, g).r;   // soft shade where walls meet the floor
    col = mix(col, mix(uStage, uPaper, 0.4), B.x);
    float l = dot(col, vec3(0.3, 0.59, 0.11));
    col = mix(col, A.rgb * mix(0.72, 1.12, l), A.a);
    float alpha = (elem < 0.5 ? 1.0 : B.z) * show * uReveal;
    if (alpha < 0.01) discard;
    gl_FragColor = vec4(col, alpha);
  }`

const DOT_VERT = /* glsl */ `
  attribute vec3 aPos; attribute float aState;
  varying vec2 vUv; varying float vState;
  uniform float uPano;
  ${STYLE_GLSL}
  void main() {
    vUv = uv; vState = aState;
    float f = aPos.z, show = uFloorShow[int(f + 0.5)];
    float size = uPano > 0.5 ? (aState > 0.5 ? 0.46 : 0.0) : 0.3;
    vec3 p = vec3(aPos.xy + (uv - 0.5) * size * step(0.5, show), uFloorZ[int(f + 0.5)] + 0.03);
    gl_Position = projectionMatrix * viewMatrix * vec4(p, 1.0);
  }`

const DOT_FRAG = /* glsl */ `
  varying vec2 vUv; varying float vState;
  uniform vec3 uPaper, uInk, uAccent; uniform float uPano, uReveal;
  void main() {
    float r = length(vUv - 0.5) * 2.0, w = fwidth(r);
    float disc = 1.0 - smoothstep(1.0 - w, 1.0, r);
    float ring = smoothstep(0.52 - w, 0.52, r);
    vec3 col; float a;
    if (uPano > 0.5) { // a walk target: a pale ring with a hairline of ink so it reads on light and dark floors
      float band = smoothstep(0.70 - w, 0.70, r) * (1.0 - smoothstep(0.90 - w, 0.90, r));
      col = mix(uInk, vState > 1.5 ? uAccent : uPaper, max(band, vState > 1.5 ? 1.0 : 0.0));
      a = disc * max(band * 0.95, vState > 1.5 ? 0.8 : smoothstep(0.90 - w, 0.90, r) * 0.45 + 0.10);
    } else {
      col = mix(vState > 1.5 ? uAccent : uPaper, vState > 1.5 ? uPaper : uInk, ring);
      a = disc * 0.85;
    }
    a *= uReveal;
    if (a < 0.01) discard;
    gl_FragColor = vec4(col, a);
  }`

const GROUND_FRAG = /* glsl */ `
  varying vec3 vW; uniform vec3 uInk; uniform vec2 uCentre; uniform vec4 uBox; uniform float uRadius, uReveal;
  float grid(vec2 p, float step) { vec2 g = abs(fract(p / step - 0.5) - 0.5) / fwidth(p / step); return 1.0 - min(min(g.x, g.y), 1.0); }
  void main() {
    float fade = 1.0 - smoothstep(uRadius * 0.9, uRadius * 2.2, distance(vW.xy, uCentre));
    vec2 q = abs(vW.xy - uBox.xy) - uBox.zw;                    // distance outside the building's footprint box
    float out_ = length(max(q, 0.0)), shade = 0.16 * exp(-out_ * 0.9) * step(0.0, max(q.x, q.y));
    float a = max((grid(vW.xy, 1.0) * 0.05 + grid(vW.xy, 5.0) * 0.07) * fade, shade) * uReveal; // 1 m and 5 m lines: a scale, not decoration
    if (a < 0.003) discard;
    gl_FragColor = vec4(uInk, a);
  }`

interface Anim { cur: number; goal: number; rate: number }

export class Dollhouse {
  group = new THREE.Group()
  floorGroups: THREE.Group[] = []   // children ride with their floor when floors are pulled apart
  uniforms: Record<string, THREE.IUniform>
  anim: Record<string, Anim> = {
    cut: { cur: 99, goal: 99, rate: 14 }, explode: { cur: 0, goal: 0, rate: 7 }, reveal: { cur: 1, goal: 1, rate: 5 },
    water: { cur: -1000, goal: -1000, rate: 2.4 },
  }
  private showAnim: Anim[]
  private styleCur: Float32Array; private styleGoal: Float32Array; private styleTex: THREE.DataTexture
  private styles: Style[] = []
  private styleDirty = true
  private walls: THREE.Mesh; private floors: THREE.Mesh[] = []; private dots: THREE.Mesh; private ground: THREE.Mesh
  private dotState: THREE.InstancedBufferAttribute
  private outlines = new Map<number, Line2>()
  private lineRes = new THREE.Vector2(1, 1)
  private textures: THREE.Texture[] = []
  onChange: () => void = () => {}

  readonly m: Model; readonly tok: Tokens
  constructor(m: Model, tok: Tokens, api: string) {
    this.m = m; this.tok = tok
    const { plan } = m, nF = Math.min(plan.floors.length, MAX_FLOORS), N = m.elemCount
    this.showAnim = plan.floors.map(() => ({ cur: 1, goal: 1, rate: 9 }))
    this.styleCur = new Float32Array(N * 8); this.styleGoal = new Float32Array(N * 8)
    this.styleTex = new THREE.DataTexture(this.styleCur, N, 2, THREE.RGBAFormat, THREE.FloatType)
    this.styleTex.minFilter = this.styleTex.magFilter = THREE.NearestFilter
    const v3 = (c: RGB) => ({ value: new THREE.Vector3(...c) })
    this.uniforms = {
      uStyle: { value: this.styleTex }, uFloorZ: { value: new Float32Array(MAX_FLOORS) }, uFloorShow: { value: new Float32Array(MAX_FLOORS).fill(1) },
      uCut: { value: 99 }, uMaxH: { value: m.maxH }, uReveal: { value: 1 }, uWater: { value: -1000 }, uOccluder: { value: 0 },
      uPaper: v3(tok.paper), uInk: v3(tok.ink), uGlass: v3(tok.glass), uStage: v3(tok.stage), uWaterCol: v3(tok.water), uAccent: v3(tok.accent),
      uPano: { value: 0 }, uXray: { value: 0 }, uLift: { value: 0 },
    }
    for (let f = 0; f < nF; f++) { const g = new THREE.Group(); this.floorGroups.push(g); this.group.add(g) }

    this.walls = new THREE.Mesh(this.wallGeometry(), new THREE.ShaderMaterial({ vertexShader: WALL_VERT, fragmentShader: WALL_FRAG, uniforms: this.uniforms, side: THREE.DoubleSide }))
    this.walls.frustumCulled = false
    this.group.add(this.walls)

    for (let f = 0; f < nF; f++) this.floors.push(this.makeFloor(f, api))
    this.dots = this.makeDots(); this.dotState = (this.dots.geometry as THREE.InstancedBufferGeometry).getAttribute('aState') as THREE.InstancedBufferAttribute
    this.group.add(this.dots)

    const b = m.bounds, r = Math.hypot(b.maxX - b.minX, b.maxY - b.minY) / 2 + 4
    this.ground = new THREE.Mesh(new THREE.PlaneGeometry(r * 6, r * 6), new THREE.ShaderMaterial({
      vertexShader: 'varying vec3 vW; void main(){ vW = (modelMatrix * vec4(position,1.0)).xyz; gl_Position = projectionMatrix * viewMatrix * vec4(vW,1.0); }',
      fragmentShader: GROUND_FRAG, transparent: true, depthWrite: false,
      uniforms: { uInk: { value: new THREE.Vector3(...tok.grid) }, uCentre: { value: new THREE.Vector2((b.minX + b.maxX) / 2, (b.minY + b.maxY) / 2) }, uRadius: { value: r }, uReveal: this.uniforms.uReveal,
        uBox: { value: new THREE.Vector4((b.minX + b.maxX) / 2, (b.minY + b.maxY) / 2, (b.maxX - b.minX) / 2, (b.maxY - b.minY) / 2) } },
    }))
    this.ground.position.set((b.minX + b.maxX) / 2, (b.minY + b.maxY) / 2, m.floorZ[0] - 0.03)
    this.ground.renderOrder = -1
    this.group.add(this.ground)
    this.update(1)
  }

  private wallGeometry() {
    const boxes = wallBoxes(this.m), n = boxes.length * 24
    const pos = new Float32Array(n * 3), nor = new Float32Array(n * 3), elem = new Float32Array(n), floor = new Float32Array(n), kind = new Float32Array(n)
    const index = new Uint32Array(boxes.length * 36)
    // faces as (corner indices, normal in box axes: along, across, up)
    const FACES: [number[], Vec3][] = [[[0, 1, 5, 4], [0, -1, 0]], [[2, 3, 7, 6], [0, 1, 0]], [[1, 2, 6, 5], [1, 0, 0]], [[3, 0, 4, 7], [-1, 0, 0]], [[4, 5, 6, 7], [0, 0, 1]], [[3, 2, 1, 0], [0, 0, -1]]]
    boxes.forEach((b, bi) => {
      const nx = -b.dy, ny = b.dx, h = b.t / 2
      const corner = (i: number): Vec3 => {
        const s = i % 4 === 1 || i % 4 === 2 ? b.s1 : b.s0, o = i % 4 >= 2 ? h : -h
        return [b.cx + b.dx * s + nx * o, b.cy + b.dy * s + ny * o, i < 4 ? b.z0 : b.z1]
      }
      FACES.forEach(([ids, fn], fi) => {
        const v0 = bi * 24 + fi * 4
        ids.forEach((ci, k) => {
          pos.set(corner(ci), (v0 + k) * 3)
          nor.set([b.dx * fn[0] + nx * fn[1], b.dy * fn[0] + ny * fn[1], fn[2]], (v0 + k) * 3)
          elem[v0 + k] = b.elem; floor[v0 + k] = b.floor; kind[v0 + k] = b.kind
        })
        index.set([v0, v0 + 1, v0 + 2, v0, v0 + 2, v0 + 3], (bi * 6 + fi) * 6)
      })
    })
    const g = new THREE.BufferGeometry()
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3)); g.setAttribute('normal', new THREE.BufferAttribute(nor, 3))
    g.setAttribute('aElem', new THREE.BufferAttribute(elem, 1)); g.setAttribute('aFloor', new THREE.BufferAttribute(floor, 1)); g.setAttribute('aKind', new THREE.BufferAttribute(kind, 1))
    g.setIndex(new THREE.BufferAttribute(index, 1))
    return g
  }

  private makeFloor(f: number, api: string) {
    const { m } = this, { plan } = m, fid = plan.floors[f].id
    const imgs = plan.floorplans.filter((p) => p.floor === fid && p.width && p.resolution && p.origin && (p.flags ?? []).includes('photogramy'))
    const flagsOf = (p: (typeof imgs)[number]) => (p.flags ?? []).slice().sort().join(',')
    const img = imgs.filter((p) => p.format === 'png' && flagsOf(p) === 'alpha,photogramy').sort((a, b) => b.width! - a.width!)[0]
      ?? imgs.find((p) => p.format === 'jpg' && flagsOf(p) === 'photogramy')
    const rect = img ? [img.origin!.x, img.origin!.y, img.width! / img.resolution!, img.height! / img.resolution!] : [0, 0, 1, 1]
    const fb = m.floorBounds[f], pad = 0.6
    const x0 = Math.min(fb.minX, img ? rect[0] : Infinity) - pad, y0 = Math.min(fb.minY, img ? rect[1] : Infinity) - pad
    const x1 = Math.max(fb.maxX, img ? rect[0] + rect[2] : -Infinity) + pad, y1 = Math.max(fb.maxY, img ? rect[1] + rect[3] : -Infinity) + pad
    const w = x1 - x0, h = y1 - y0, ppm = Math.min(25, 2048 / Math.max(w, h)), gw = Math.ceil(w * ppm), gh = Math.ceil(h * ppm)

    // Room number per cell (finding 4 of the research): the floor shader looks its room up here, then its style.
    const ids = new Uint8Array(gw * gh * 4)
    for (const ri of m.roomsByFloor[f]) {
      const poly = plan.rooms[ri].polygon, e = m.roomElem.get(plan.rooms[ri].id)!
      const ys = poly.map((p) => p[1]), j0 = Math.max(0, Math.floor((Math.min(...ys) - y0) * ppm)), j1 = Math.min(gh - 1, Math.ceil((Math.max(...ys) - y0) * ppm))
      for (let j = j0; j <= j1; j++) {
        const y = y0 + (j + 0.5) / ppm, xs: number[] = []
        for (let i = 0, k = poly.length - 1; i < poly.length; k = i++) {
          if ((poly[i][1] > y) !== (poly[k][1] > y)) xs.push(poly[k][0] + ((y - poly[k][1]) / (poly[i][1] - poly[k][1])) * (poly[i][0] - poly[k][0]))
        }
        xs.sort((a, b) => a - b)
        for (let k = 0; k + 1 < xs.length; k += 2) {
          const i0 = Math.max(0, Math.round((xs[k] - x0) * ppm)), i1 = Math.min(gw, Math.round((xs[k + 1] - x0) * ppm))
          for (let i = i0; i < i1; i++) { ids[(j * gw + i) * 4] = e & 255; ids[(j * gw + i) * 4 + 1] = e >> 8 }
        }
      }
    }
    const idTex = new THREE.DataTexture(ids, gw, gh, THREE.RGBAFormat, THREE.UnsignedByteType)
    idTex.minFilter = idTex.magFilter = THREE.NearestFilter; idTex.needsUpdate = true

    // Blurred wall mask as a baked ambient shade.
    const cv = document.createElement('canvas'); cv.width = gw; cv.height = gh
    const cx = cv.getContext('2d')!
    cx.fillStyle = '#000'; cx.fillRect(0, 0, gw, gh)
    cx.strokeStyle = '#fff'; cx.lineCap = 'round'
    for (const wl of plan.walls) {
      if (wl.floor !== fid || wl.type === 'invisible') continue
      cx.lineWidth = ((wl.thickness || 0.1) + 0.34) * ppm
      cx.beginPath(); cx.moveTo((wl.a[0] - x0) * ppm, (y1 - wl.a[1]) * ppm); cx.lineTo((wl.b[0] - x0) * ppm, (y1 - wl.b[1]) * ppm); cx.stroke()
    }
    // blur once, after every wall is drawn: a filter on the stroking context would blur the whole canvas per wall
    const soft = document.createElement('canvas'); soft.width = gw; soft.height = gh
    const sx = soft.getContext('2d')!
    sx.filter = `blur(${(0.32 * ppm).toFixed(1)}px)`; sx.drawImage(cv, 0, 0)
    const aoTex = new THREE.CanvasTexture(soft)
    aoTex.minFilter = aoTex.magFilter = THREE.LinearFilter; aoTex.generateMipmaps = false

    const uniforms: Record<string, THREE.IUniform> = {
      ...this.uniforms, uFloorIdx: { value: f }, uHasPhoto: { value: 0 }, uPanoTint: { value: 0 }, uPhoto: { value: null }, uIds: { value: idTex }, uAo: { value: aoTex },
      uGrid: { value: new THREE.Vector4(x0, y0, w, h) }, uGridPx: { value: new THREE.Vector2(gw, gh) }, uPhotoRect: { value: new THREE.Vector4(...rect) },
    }
    if (img) {
      const url = `${api}/api/scan/${plan.sid}/floorplan/${fid}.${img.format}?flags=${encodeURIComponent((img.flags ?? []).join(','))}`
      new THREE.TextureLoader().load(url, (t) => {
        t.colorSpace = THREE.NoColorSpace; t.anisotropy = 8; t.minFilter = THREE.LinearMipmapLinearFilter
        this.textures.push(t); uniforms.uPhoto.value = t; uniforms.uHasPhoto.value = 1; this.onChange()
      })
    }
    this.textures.push(idTex, aoTex)
    const geo = new THREE.PlaneGeometry(w, h); geo.translate(x0 + w / 2, y0 + h / 2, 0)
    const mesh = new THREE.Mesh(geo, new THREE.ShaderMaterial({ vertexShader: FLOOR_VERT, fragmentShader: FLOOR_FRAG, uniforms, transparent: true }))
    mesh.frustumCulled = false; mesh.renderOrder = 1
    this.group.add(mesh)
    return mesh
  }

  private makeDots() {
    const { m } = this, panos = m.plan.panos
    const g = new THREE.InstancedBufferGeometry()
    g.index = new THREE.BufferAttribute(new Uint16Array([0, 1, 2, 0, 2, 3]), 1)
    g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(12), 3))
    g.setAttribute('uv', new THREE.BufferAttribute(new Float32Array([0, 0, 1, 0, 1, 1, 0, 1]), 2))
    const pos = new Float32Array(panos.length * 3)
    panos.forEach((p, i) => pos.set([p.position[0], p.position[1], m.floorOf.get(p.floor ?? '') ?? 0], i * 3))
    g.setAttribute('aPos', new THREE.InstancedBufferAttribute(pos, 3))
    g.setAttribute('aState', new THREE.InstancedBufferAttribute(new Float32Array(panos.length), 1))
    g.instanceCount = panos.length
    const mesh = new THREE.Mesh(g, new THREE.ShaderMaterial({ vertexShader: DOT_VERT, fragmentShader: DOT_FRAG, uniforms: this.uniforms, transparent: true, depthWrite: false }))
    mesh.frustumCulled = false; mesh.renderOrder = 3
    return mesh
  }

  /** State per scan position: 0 plain, 1 a neighbour you can walk to, 2 the hovered or current one. */
  setDotStates(fn: (panoId: string, i: number) => number) {
    this.m.plan.panos.forEach((p, i) => this.dotState.setX(i, fn(p.id, i)))
    this.dotState.needsUpdate = true
  }

  setStyles(styles: Style[], instant = false) {
    this.styles = styles
    const N = this.m.elemCount
    styles.forEach((s, i) => {
      this.styleGoal.set([s.tint[0], s.tint[1], s.tint[2], s.amt], i * 4)
      this.styleGoal.set([s.wash, s.height, s.alpha, 0], (N + i) * 4)
      // a tint that fades in from nothing should not pass through black
      if (this.styleCur[i * 4 + 3] < 0.02) this.styleCur.set(s.tint, i * 4)
    })
    if (instant) this.styleCur.set(this.styleGoal)
    this.styleDirty = true
    this.syncOutlines()
  }

  private eye: { pos: Vec3; floorId: string | null } | null = null
  /** Inside a panorama: outlines of openings hidden behind walls are dropped, and floor outlines respect the walls. */
  setEye(eye: { pos: Vec3; floorId: string | null } | null) { this.eye = eye; this.redrawOpeningOutlines() }
  /** Cut-away height in metres above each floor. Opening outlines stop at the cut, so they are redrawn. */
  setCut(h: number) { if (h !== this.anim.cut.goal) { this.anim.cut.goal = h; this.redrawOpeningOutlines() } }
  private redrawOpeningOutlines() {
    const first = 1 + this.m.plan.rooms.length + this.m.plan.walls.length
    for (const [e, line] of this.outlines) if (e >= first) { line.removeFromParent(); line.geometry.dispose(); (line.material as LineMaterial).dispose(); this.outlines.delete(e) }
    this.syncOutlines()
  }

  private syncOutlines() {
    const { m } = this, want = new Map<number, RGB>(), R0 = m.plan.rooms.length, W0 = m.plan.walls.length
    this.styles.forEach((s, e) => { if (s.outline && s.alpha > 0) want.set(e, s.outline) })
    for (const [e, line] of this.outlines) if (!want.has(e)) { line.removeFromParent(); line.geometry.dispose(); (line.material as LineMaterial).dispose(); this.outlines.delete(e) }
    for (const [e, c] of want) {
      let line = this.outlines.get(e)
      if (!line) {
        const pts: number[] = []; let floor = 0
        const R = m.plan.rooms.length, W = m.plan.walls.length
        if (e >= 1 && e <= R) {
          const r = m.plan.rooms[e - 1]; floor = m.floorOf.get(r.floor) ?? 0
          for (const p of [...r.polygon, r.polygon[0]]) if (p) pts.push(p[0], p[1], 0.045)
        } else if (e > R + W) {
          const o = m.plan.openings[e - 1 - R - W], sp = openingSpan(m, o); floor = m.floorOf.get(o.floor) ?? 0
          const at = (s: number, z: number) => pts.push(sp.w.a[0] + sp.dx * s, sp.w.a[1] + sp.dy * s, z)
          const top = this.eye ? sp.head : Math.max(sp.sill + 0.02, Math.min(sp.head, this.anim.cut.goal)) // from outside, no taller than the cut walls
          at(sp.s0, sp.sill); at(sp.s0, top); at(sp.s1, top); at(sp.s1, sp.sill); at(sp.s0, sp.sill)
        }
        if (pts.length < 6) continue
        line = new Line2(new LineGeometry().setPositions(pts), new LineMaterial({ linewidth: 2.5, depthTest: false, transparent: true, resolution: this.lineRes }))
        line.renderOrder = 6
        this.floorGroups[floor]?.add(line); this.outlines.set(e, line)
      }
      const mat = line.material as LineMaterial, o = e > R0 + W0 ? m.plan.openings[e - 1 - R0 - W0] : null
      mat.color.setRGB(c[0], c[1], c[2], THREE.SRGBColorSpace)
      mat.depthTest = !!this.eye && !o
      line.visible = !this.eye || !o || (o.floor === this.eye.floorId && !sightBlocked(m, o.floor, this.eye.pos[0], this.eye.pos[1], o.center[0], o.center[1], o.wall))
    }
  }

  setFloorShown(shown: (floorIdx: number) => boolean) { this.showAnim.forEach((a, i) => (a.goal = shown(i) ? 1 : 0)) }
  setSize(w: number, h: number) { this.lineRes.set(w, h) }

  private look = { pano: false, scan: false, xray: false, ground: true }
  /** Panorama mode: walls only write depth, floors show lens colour only, rings mark where you can walk. */
  setPanoMode(on: boolean) { if (on !== this.look.pano) { this.look.pano = on; this.syncLook() } }
  /** 'scan': the scanned mesh is drawn instead, so the walls go and the floors keep only their lens and rule colour,
      laid just over the mesh's own floor. */
  setSurface(s: 'model' | 'scan') { if ((s === 'scan') !== this.look.scan) { this.look.scan = s === 'scan'; this.syncLook() } }
  /** Walls as glass. */
  setXray(on: boolean) { if (on !== this.look.xray) { this.look.xray = on; this.syncLook() } }
  /** The grid and the shade round the footprint. Off when real ground is drawn. */
  setGround(on: boolean) { if (on !== this.look.ground) { this.look.ground = on; this.syncLook() } }
  private syncLook() {
    const { pano, scan, xray, ground } = this.look, tintOnly = pano || scan, wm = this.walls.material as THREE.ShaderMaterial
    this.uniforms.uOccluder.value = pano ? 1 : 0; this.uniforms.uPano.value = pano ? 1 : 0
    this.uniforms.uXray.value = xray && !pano ? 1 : 0; this.uniforms.uLift.value = scan && !pano ? 0.04 : 0
    this.walls.visible = pano || !scan // inside a panorama the walls still hide what is behind them
    wm.colorWrite = !pano; wm.transparent = xray && !pano; wm.depthWrite = !wm.transparent; wm.needsUpdate = true
    for (const f of this.floors) { const mat = f.material as THREE.ShaderMaterial; mat.uniforms.uPanoTint.value = tintOnly ? 1 : 0; mat.depthWrite = !tintOnly }
    this.ground.visible = !pano && ground
    this.onChange()
  }

  floorZ(f: number) { return (this.uniforms.uFloorZ.value as Float32Array)[f] ?? 0 }
  /** 0..1: how tall this element's walls currently stand (1 whole, 0 dropped to a stub). */
  heightOf(elem: number) { return this.styles[elem]?.height ?? 1 }

  /** Advance animated values. Returns true while anything is still moving. */
  update(dt: number): boolean {
    let moving = false
    const step = (a: Anim) => {
      if (a.cur === a.goal) return
      if (Math.abs(a.cur - a.goal) > 500) a.cur = a.goal // switching an effect on: no travel from "off"
      a.cur += (a.goal - a.cur) * (1 - Math.exp(-dt * a.rate))
      if (Math.abs(a.goal - a.cur) < 1e-3) a.cur = a.goal
      moving = true
    }
    Object.values(this.anim).forEach(step); this.showAnim.forEach(step)
    const u = this.uniforms, fz = u.uFloorZ.value as Float32Array, fs = u.uFloorShow.value as Float32Array
    this.m.floorZ.slice(0, MAX_FLOORS).forEach((z, i) => {
      fz[i] = z + i * EXPLODE_GAP * this.anim.explode.cur; fs[i] = this.showAnim[i].cur
      this.floorGroups[i].position.z = fz[i]; this.floorGroups[i].visible = fs[i] > 0.5
    })
    u.uCut.value = this.anim.cut.cur; u.uReveal.value = this.anim.reveal.cur; u.uWater.value = this.anim.water.cur
    if (this.styleDirty) {
      const k = 1 - Math.exp(-dt * 11), c = this.styleCur, g = this.styleGoal
      let diff = 0
      for (let i = 0; i < c.length; i++) { const d = g[i] - c[i]; if (d !== 0) { c[i] += d * k; if (Math.abs(d) < 2e-3) c[i] = g[i]; else diff = 1 } }
      this.styleTex.needsUpdate = true
      this.styleDirty = diff > 0
      moving = true
    }
    return moving
  }

  /** What a ray hits: a scan position, an opening, a wall, or a room. Works on the cut, restyled model as drawn. */
  pick(ray: THREE.Ray, opts: { pano: boolean }): Pick | null {
    const { m } = this, { plan } = m
    let best: { t: number; pick: Pick } | null = null
    const take = (t: number, pick: Pick) => { if (t > 0 && (!best || t < best.t)) best = { t, pick } }
    const o = ray.origin, d = ray.direction
    for (let f = plan.floors.length - 1; f >= 0; f--) {
      if (this.showAnim[f].goal < 0.5 || f >= MAX_FLOORS) continue
      const z = this.floorZ(f), fid = plan.floors[f].id
      for (const w of plan.walls) {
        if (w.floor !== fid || w.type === 'invisible') continue
        const st = this.styles[m.wallElem.get(w.id)!]
        if (st && st.alpha < 0.5) continue
        const ex = w.b[0] - w.a[0], ey = w.b[1] - w.a[1], den = d.x * ey - d.y * ex
        if (Math.abs(den) < 1e-9) continue
        const t = ((w.a[0] - o.x) * ey - (w.a[1] - o.y) * ex) / den, u = ((w.a[0] - o.x) * d.y - (w.a[1] - o.y) * d.x) / den
        if (t <= 0 || u < 0 || u > 1) continue
        const lz = o.z + d.z * t - z, H = wallHeight(m, w)
        const top = opts.pano ? H : Math.min(this.anim.cut.goal, st && st.height < 0.5 ? STUB : H)
        if (lz < 0 || lz > H) continue
        const point: Vec3 = [o.x + d.x * t, o.y + d.y * t, o.z + d.z * t]
        const op = w.openings.map((id) => m.openingById.get(id)!).find((op) => { const sp = openingSpan(m, op); return u * w.length >= sp.s0 && u * w.length <= sp.s1 && lz >= sp.sill && lz <= sp.head })
        if (op) { if (opts.pano || lz <= top) take(t, { kind: 'opening', id: op.id, point }) }
        else if (lz <= top) take(t, { kind: 'wall', id: w.id, point })
      }
      if (Math.abs(d.z) < 1e-6) continue
      const t = (z - o.z) / d.z
      if (t <= 0) continue
      const x = o.x + d.x * t, y = o.y + d.y * t
      const dot = plan.panos.find((p, i) => p.floor === fid && Math.hypot(p.position[0] - x, p.position[1] - y) < (opts.pano ? 0.4 : 0.22) && (!opts.pano || this.dotState.getX(i) > 0.5))
      if (dot) { take(t - 0.05, { kind: 'pano', id: dot.id }); continue }
      if (!opts.pano) { // seen from above a wall is a thin line: accept a click right beside it
        for (const w of plan.walls) {
          if (w.floor !== fid || w.type === 'invisible') continue
          const L = w.length || 1, ux = (w.b[0] - w.a[0]) / L, uy = (w.b[1] - w.a[1]) / L
          const s = (x - w.a[0]) * ux + (y - w.a[1]) * uy, off = Math.abs((x - w.a[0]) * -uy + (y - w.a[1]) * ux)
          if (s < 0 || s > L || off > (w.thickness || 0.1) / 2 + 0.04) continue
          const op = w.openings.map((id) => m.openingById.get(id)!).find((op) => { const sp = openingSpan(m, op); return s >= sp.s0 && s <= sp.s1 })
          take(t - 0.02, op ? { kind: 'opening', id: op.id, point: [x, y, z] } : { kind: 'wall', id: w.id, point: [x, y, z] })
        }
      }
      const ri = roomAt(m, f, x, y)
      if (ri >= 0 && (this.styles[ri + 1]?.alpha ?? 1) > 0.5) take(t, { kind: 'room', id: plan.rooms[ri].id, point: [x, y, z] })
    }
    return (best as { t: number; pick: Pick } | null)?.pick ?? null
  }

  dispose() {
    this.group.traverse((o) => { const mesh = o as THREE.Mesh; mesh.geometry?.dispose?.(); (mesh.material as THREE.Material | undefined)?.dispose?.() })
    this.textures.forEach((t) => t.dispose()); this.styleTex.dispose()
  }
}
