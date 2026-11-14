// A box overlay may name a model class ("vehicle/pickup"). Each class is one GLB under public/models: a unit cube of
// geometry with baked vertex colours (web/src/scene/dev/build-models.mjs), fetched once per page and shared.
// The overlay scales that cube to the box the tool measured, so the model never brings a size of its own.
import * as THREE from 'three'

const CLASS = /^[a-z]+\/[a-z0-9-]+$/ // the id comes from a tool result and becomes part of a URL
const ready = new Map<string, THREE.BufferGeometry | null>() // null: no such model, or it failed to load; the box stays
const waiting = new Map<string, Set<() => void>>()

/** The class's geometry if it has arrived. Otherwise null, and `onLoad` is called once when it does. */
export function modelGeometry(id: string, onLoad: () => void): THREE.BufferGeometry | null {
  const have = ready.get(id)
  if (have !== undefined) return have
  if (!CLASS.test(id)) { ready.set(id, null); return null }
  let w = waiting.get(id)
  if (!w) {
    waiting.set(id, (w = new Set()))
    load(id).catch(() => null).then((geo) => { ready.set(id, geo); const fns = waiting.get(id)!; waiting.delete(id); if (geo) for (const f of fns) f() })
  }
  w.add(onLoad)
  return null
}

async function load(id: string): Promise<THREE.BufferGeometry> {
  // the loader and decoder are only fetched by a page that draws a model
  const [{ GLTFLoader }, { MeshoptDecoder }] = await Promise.all([import('three/addons/loaders/GLTFLoader.js'), import('three/addons/libs/meshopt_decoder.module.js')])
  const gltf = await new GLTFLoader().setMeshoptDecoder(MeshoptDecoder).loadAsync(`${import.meta.env.BASE_URL}models/${id}.glb`)
  let geo: THREE.BufferGeometry | null = null
  gltf.scene.traverse((o) => { geo ??= (o as THREE.Mesh).isMesh ? (o as THREE.Mesh).geometry : null })
  const col = (geo as THREE.BufferGeometry | null)?.getAttribute('color')
  if (!geo || !col) throw new Error(`models/${id}.glb has no coloured mesh`)
  // Clay: the source's paint becomes a light body with dark glass and tyres, so the status tint is the only colour a
  // model carries. Done once here, in the sRGB the scene's other shaders write.
  const c = new THREE.Color()
  for (let i = 0; i < col.count; i++) {
    c.fromBufferAttribute(col, i).convertLinearToSRGB()
    const l = 0.2126 * c.r + 0.7152 * c.g + 0.0722 * c.b, t = Math.min(1, Math.max(0, (l - 0.22) / 0.2)), v = 0.2 + 0.8 * t * t * (3 - 2 * t) // the sources' glass and tyres sit under 0.25, their paint over 0.4
    const k = (x: number) => Math.min(1, Math.max(0, v + (x - l) * 0.12)) // the attribute is 8-bit: past 1 it would wrap
    col.setXYZ(i, k(c.r), k(c.g), k(c.b))
  }
  return geo
}

/** One material for every model: the walls' light direction, vertex colour times the instance's tint. */
export const modelMaterial = new THREE.ShaderMaterial({
  vertexColors: true, // three declares `color` and the instance attributes itself
  vertexShader: /* glsl */ `
    varying vec3 vCol;
    void main() {
      mat3 im = mat3(instanceMatrix);
      vec3 n = normalize(mat3(modelMatrix) * (im * (normal / vec3(dot(im[0], im[0]), dot(im[1], im[1]), dot(im[2], im[2]))))); // right under a stretch
      float lit = 0.74 + 0.26 * dot(n, normalize(vec3(-0.45, -0.62, 0.64)));
      vCol = color.rgb * instanceColor * lit;
      gl_Position = projectionMatrix * viewMatrix * modelMatrix * instanceMatrix * vec4(position, 1.0);
    }`,
  fragmentShader: /* glsl */ `varying vec3 vCol; void main() { gl_FragColor = vec4(vCol, 1.0); }`,
})
