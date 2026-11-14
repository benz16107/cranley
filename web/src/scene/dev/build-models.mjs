// Builds web/public/models/<class>.glb and LICENSES.md from the CC0 and CC-BY sources listed in SOURCES.
//
// Every output is one mesh with one material, colours baked into the vertices, z up, and normalised to a unit cube:
// x is the length (a vehicle's nose at +x, a piece of furniture's front toward -y), y the width, z the height. The
// scene scales that cube to the exact box a tool measured, so nothing here carries a dimension.
//
// Not a web dependency. Run it from a scratch folder that has the tools and the downloaded sources:
//   npm i @gltf-transform/core@4 @gltf-transform/extensions@4 @gltf-transform/functions@4 meshoptimizer pngjs
//   node build-models.mjs <sources dir> <repo>/web/public/models
// Sources dir: Kenney's kits unzipped as x-car-kit, x-furniture-kit, x-watercraft-kit; Poly Pizza files as pz/<name>.glb.
import { mkdirSync, statSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { Document, NodeIO } from '@gltf-transform/core'
import { ALL_EXTENSIONS, EXTMeshoptCompression, KHRMeshQuantization } from '@gltf-transform/extensions'
import { reorder } from '@gltf-transform/functions'
import { MeshoptDecoder, MeshoptEncoder } from 'meshoptimizer'
import { PNG } from 'pngjs'

const [SRC, OUT] = process.argv.slice(2)
if (!SRC || !OUT) { console.error('usage: node build-models.mjs <sources dir> <out dir>'); process.exit(2) }

const CC0 = 'CC0 1.0', BY = 'CC BY 3.0'
const kenney = (kit, title, file) => ({ file: `x-${kit}/Models/${file}`, title, author: 'Kenney', licence: CC0, url: `https://kenney.nl/assets/${kit}` })
const pizza = (id, file, title, author, licence) => ({ file: `pz/${file}.glb`, title, author, licence, url: `https://poly.pizza/m/${id}` })
const car = (n) => kenney('car-kit', `Car Kit 3.1: ${n}`, `GLB format/${n}.glb`)
const furn = (n) => kenney('furniture-kit', `Furniture Kit 2.0: ${n}`, `GLTF format/${n}.glb`)
const SOURCES = {
  sedan: pizza('Cz6yDaUcM9', 'sedan', 'Car', 'Quaternius', CC0),
  coupe: pizza('1mkmFkAz5v', 'coupe', 'Sports Car', 'Quaternius', CC0),
  hatchback: pizza('unqqkULtRU', 'hatchback', 'Car', 'Quaternius', CC0),
  suv: pizza('xsMtZhBkxL', 'suv', 'SUV', 'Quaternius', CC0),
  pickup: pizza('qn4grQgHm8', 'pickup', 'Pickup Truck', 'Quaternius', CC0),
  van: car('van'), delivery: car('delivery'), wheel: car('wheel-default'),
  boat: kenney('watercraft-kit', 'Watercraft Kit 2.1: boat-speed-j', 'GLB format/boat-speed-j.glb'),
  cruiser: pizza('5_MTCnqfUTr', 'motorcycle-touring', 'Motorcycle', 'Poly by Google', BY),
  sport: pizza('dse64pqMKAR', 'motorcycle-sport', 'Motorcycle', 'Poly by Google', BY),
  bicycle: pizza('19VoUuA2pcN', 'bicycle', 'Bicycle', 'Poly by Google', BY),
  caravan: pizza('77t77GQMubf', 'caravan', 'Caravan', 'Poly by Google', BY),
  piano: pizza('1YoE664mJTd', 'piano', 'Piano', 'Poly by Google', BY),
  crib: pizza('4iV2yZ0wIf1', 'crib', 'Crib', 'Poly by Google', BY),
  sofa: furn('loungeSofa'), sectional: furn('loungeSofaLong'), armchair: furn('loungeChair'),
  bedSingle: furn('bedSingle'), bedDouble: furn('bedDouble'), table: furn('table'), chair: furn('chair'),
  desk: furn('desk'), wardrobe: furn('bookcaseClosedDoors'), bookshelf: furn('bookcaseOpen'),
  fridge: furn('kitchenFridgeLarge'), washer: furn('washer'), coffee: furn('tableCoffee'), tv: furn('cabinetTelevision'),
}

// A part: { src, turn (degrees about the vertical, after standing the source up), at (offset), height (metres, to size
// it against other parts), drop (node names to leave out), yaw (a source that sits at an angle) }. `make` adds parts drawn here instead of read from a file.
const one = (src, turn = 0, more = {}) => [{ src, turn, ...more }]
const SPECS = {
  'vehicle/sedan': one('sedan', 90), 'vehicle/coupe': one('coupe', 90), 'vehicle/hatchback': one('hatchback', 90),
  'vehicle/suv': one('suv', 90), 'vehicle/pickup': one('pickup', 90),
  'vehicle/minivan': one('suv', 90), // a people carrier has the wagon's outline; the kit's van is a cargo van
  'vehicle/van': one('van', 90), 'vehicle/rv': one('delivery', 90),
  'vehicle/motorcycle': one('cruiser', 0), 'vehicle/motorcycle-sport': one('sport', 90),
  'vehicle/bicycle': one('bicycle', 0),
  'vehicle/bicycles': [0, 1, 2].map((i) => ({ src: 'bicycle', turn: 0, at: [i % 2 ? 0.25 : 0, (i - 1) * 1.45, 0] })),
  'vehicle/camper-trailer': one('caravan', 90),
  'vehicle/trailer': [{ make: 'trailer', rails: true }],
  'vehicle/boat-trailer': [{ make: 'trailer' }, { src: 'boat', turn: 90, at: [-0.35, 0, 0.62], height: 1.5 }],
  'furniture/sofa': one('sofa'), 'furniture/sectional': one('sectional'), 'furniture/armchair': one('armchair'),
  'furniture/bed-single': one('bedSingle', 90), 'furniture/bed-double': one('bedDouble', 90),
  'furniture/table': one('table'), 'furniture/chair': one('chair'), 'furniture/desk': one('desk'),
  'furniture/dining-set': [{ src: 'table' }, ...[[0.34, 0.05, 180], [0.7, 0.05, 180], [0.14, 0.4, 0], [0.5, 0.4, 0]].map(([x, y, turn]) => ({ src: 'chair', turn, at: [x, y, 0] }))],
  'furniture/wardrobe': one('wardrobe'), 'furniture/bookshelf': one('bookshelf'), 'furniture/fridge': one('fridge'),
  'furniture/washer': one('washer'), 'furniture/coffee-table': one('coffee'), 'furniture/tv-stand': one('tv'),
  'furniture/piano': one('piano', 0, { drop: ['Box002', 'Box003', 'Box004', 'Box005', 'Box006'], yaw: 6.7 }),
  'furniture/crib': one('crib'),
}

const io = new NodeIO().registerExtensions(ALL_EXTENSIONS).registerDependencies({ 'meshopt.encoder': MeshoptEncoder, 'meshopt.decoder': MeshoptDecoder })
await MeshoptEncoder.ready
const lin = (v) => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4)

/** Triangles of one source file as flat vertices { p, n, c }, y up, in its own units. */
async function read(file, drop = []) {
  const doc = await io.read(join(SRC, file)), out = []
  const images = new Map()
  for (const node of doc.getRoot().listNodes()) {
    const mesh = node.getMesh()
    if (!mesh || drop.includes(node.getName())) continue
    const m = node.getWorldMatrix()
    const flip = m[0] * (m[5] * m[10] - m[6] * m[9]) - m[1] * (m[4] * m[10] - m[6] * m[8]) + m[2] * (m[4] * m[9] - m[5] * m[8]) < 0
    for (const prim of mesh.listPrimitives()) {
      if (prim.getMode() !== 4) continue
      const pos = prim.getAttribute('POSITION'), nor = prim.getAttribute('NORMAL'), uv = prim.getAttribute('TEXCOORD_0'), col = prim.getAttribute('COLOR_0')
      const mat = prim.getMaterial(), base = mat?.getBaseColorFactor() ?? [1, 1, 1, 1], tex = mat?.getBaseColorTexture()
      let img = null
      if (tex && uv) { if (!images.has(tex)) images.set(tex, PNG.sync.read(Buffer.from(tex.getImage()))); img = images.get(tex) }
      const vert = (i) => {
        const [x, y, z] = pos.getElement(i, []), c = base.slice(0, 3)
        if (img) { // the kits paint from a swatch texture: one texel per vertex is the whole colour
          const [u, v] = uv.getElement(i, []), px = Math.min(img.width - 1, Math.floor((u - Math.floor(u)) * img.width)), py = Math.min(img.height - 1, Math.floor((v - Math.floor(v)) * img.height)), o = (py * img.width + px) * 4
          for (let k = 0; k < 3; k++) c[k] *= lin(img.data[o + k] / 255)
        }
        if (col) { const e = col.getElement(i, []); for (let k = 0; k < 3; k++) c[k] *= e[k] }
        const p = [m[0] * x + m[4] * y + m[8] * z + m[12], m[1] * x + m[5] * y + m[9] * z + m[13], m[2] * x + m[6] * y + m[10] * z + m[14]]
        let n = null
        if (nor) { const [a, b, d] = nor.getElement(i, []); n = [m[0] * a + m[4] * b + m[8] * d, m[1] * a + m[5] * b + m[9] * d, m[2] * a + m[6] * b + m[10] * d] } // rotation and uniform scale only in these files
        return { p, n, c }
      }
      const idx = prim.getIndices(), count = idx ? idx.getCount() : pos.getCount()
      for (let t = 0; t + 2 < count; t += 3) {
        const tri = [0, 1, 2].map((k) => vert(idx ? idx.getScalar(t + k) : t + k))
        if (flip) tri.reverse()
        out.push(...tri)
      }
    }
  }
  return out
}

// ---- parts drawn here: a box and a wheel are all a trailer needs (z up, metres) ----
const STEEL = [0.2, 0.21, 0.23], TYRE = [0.02, 0.02, 0.02], DECK = [0.42, 0.33, 0.24]
function box(c, s, col) {
  const out = [], F = [[0, 1, 2, 1], [0, 1, 2, -1], [1, 2, 0, 1], [1, 2, 0, -1], [2, 0, 1, 1], [2, 0, 1, -1]]
  for (const [a, b, k, sign] of F) {
    const n = [0, 0, 0]; n[k] = sign
    const q = [[-1, -1], [1, -1], [1, 1], [-1, 1]].map(([u, v]) => { const p = [0, 0, 0]; p[a] = c[a] + (u * s[a]) / 2; p[b] = c[b] + (v * s[b]) / 2; p[k] = c[k] + (sign * s[k]) / 2; return { p, n, c: col } })
    out.push(...(sign > 0 ? [q[0], q[1], q[2], q[0], q[2], q[3]] : [q[0], q[2], q[1], q[0], q[3], q[2]]))
  }
  return out
}
function wheel(c, r, w) { // axle along y
  const out = [], N = 14
  for (let i = 0; i < N; i++) {
    const a0 = (i / N) * Math.PI * 2, a1 = ((i + 1) / N) * Math.PI * 2
    const P = (a, y) => [c[0] + Math.cos(a) * r, c[1] + y, c[2] + Math.sin(a) * r], nm = (a) => [Math.cos(a), 0, Math.sin(a)]
    const v = (a, y) => ({ p: P(a, y), n: nm(a), c: TYRE })
    out.push(v(a0, -w / 2), v(a1, w / 2), v(a1, -w / 2), v(a0, -w / 2), v(a0, w / 2), v(a1, w / 2))
    for (const s of [-1, 1]) { const tri = [{ p: [c[0], c[1] + (s * w) / 2, c[2]], n: [0, s, 0], c: STEEL }, { p: P(a0, (s * w) / 2), n: [0, s, 0], c: TYRE }, { p: P(a1, (s * w) / 2), n: [0, s, 0], c: TYRE }]; out.push(...(s > 0 ? tri.reverse() : tri)) }
  }
  return out
}
function trailer({ rails }) { // 4.3 m long with its tongue, 2 m over the wheels
  const out = [...box([-0.35, 0, 0.5], [3.1, 1.5, 0.1], rails ? DECK : STEEL), ...box([1.7, 0, 0.47], [1.2, 0.1, 0.1], STEEL), ...box([2.2, 0, 0.3], [0.08, 0.08, 0.6], STEEL)]
  for (const s of [-1, 1]) out.push(...wheel([-0.5, s * 0.87, 0.32], 0.32, 0.22), ...box([-0.5, s * 0.87, 0.68], [0.85, 0.26, 0.05], STEEL))
  if (rails) { for (const s of [-1, 1]) out.push(...box([-0.35, s * 0.73, 0.75], [3.1, 0.04, 0.4], STEEL)); out.push(...box([1.18, 0, 0.75], [0.04, 1.5, 0.4], STEEL)) }
  else for (const s of [-1, 1]) out.push(...box([-0.35, s * 0.35, 0.58], [3.0, 0.12, 0.08], DECK)) // the bunks the hull sits on
  return out
}

async function build(id, parts) {
  const verts = []
  for (const part of parts) {
    if (part.make) { verts.push(...trailer(part)); continue }
    const src = await read(SOURCES[part.src].file, part.drop)
    // Each file has its own unit, so a part of a composed model can ask for its height in metres.
    const ys = src.map((v) => v.p[1]), k = part.height ? part.height / (Math.max(...ys) - Math.min(...ys)) : 1
    const a = (((part.turn ?? 0) + (part.yaw ?? 0)) * Math.PI) / 180, cs = Math.cos(a), sn = Math.sin(a), at = part.at ?? [0, 0, 0]
    const stand = ([x, y, z]) => { const X = x, Y = -z; return [X * cs - Y * sn, X * sn + Y * cs, y] } // y up becomes z up, then the turn
    for (let t = 0; t < src.length; t += 3) {
      const tri = src.slice(t, t + 3).map((v) => ({ p: stand(v.p).map((q, i) => q * k + at[i]), n: v.n && stand(v.n), c: v.c }))
      if (tri.some((v) => !v.n)) { // a source with no normals is shaded flat
        const [A, B, C] = tri.map((v) => v.p), e1 = B.map((q, i) => q - A[i]), e2 = C.map((q, i) => q - A[i])
        const n = [e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0]]
        for (const v of tri) v.n = n
      }
      verts.push(...tri)
    }
  }
  const lo = [0, 1, 2].map((i) => Math.min(...verts.map((v) => v.p[i]))), hi = [0, 1, 2].map((i) => Math.max(...verts.map((v) => v.p[i])))
  const ext = hi.map((v, i) => v - lo[i])
  const seen = new Map(), P = [], N = [], C = [], I = []
  for (const v of verts) {
    const p = v.p.map((q, i) => Math.round(((q - lo[i]) / ext[i] - 0.5) * 32767))
    const nn = v.n.map((q, i) => q * ext[i]), len = Math.hypot(...nn) || 1 // squeezing into the cube tilts the normals the other way
    const n = nn.map((q) => Math.round((q / len) * 127)), c = v.c.map((q) => Math.round(Math.min(1, Math.max(0, q)) * 255))
    const key = `${p}|${n}|${c}`
    if (!seen.has(key)) { seen.set(key, P.length / 3); P.push(...p); N.push(...n); C.push(...c, 255) }
    I.push(seen.get(key))
  }
  const doc = new Document(), buffer = doc.createBuffer()
  const acc = (type, array, normalized = true) => doc.createAccessor().setType(type).setArray(array).setNormalized(normalized).setBuffer(buffer)
  const prim = doc.createPrimitive().setAttribute('POSITION', acc('VEC3', new Int16Array(P))).setAttribute('NORMAL', acc('VEC3', new Int8Array(N)))
    .setAttribute('COLOR_0', acc('VEC4', new Uint8Array(C))).setIndices(acc('SCALAR', P.length / 3 > 65535 ? new Uint32Array(I) : new Uint16Array(I), false))
    .setMaterial(doc.createMaterial('paint').setRoughnessFactor(1).setMetallicFactor(0))
  doc.createScene().addChild(doc.createNode(id).setMesh(doc.createMesh(id).addPrimitive(prim)))
  doc.createExtension(KHRMeshQuantization).setRequired(true)
  await doc.transform(reorder({ encoder: MeshoptEncoder }))
  doc.createExtension(EXTMeshoptCompression).setRequired(true).setEncoderOptions({ method: EXTMeshoptCompression.EncoderMethod.QUANTIZE })
  const path = join(OUT, `${id}.glb`)
  mkdirSync(dirname(path), { recursive: true })
  await io.write(path, doc)
  return { id, tris: I.length / 3, bytes: statSync(path).size, shape: ext.map((v) => +(v / ext[2]).toFixed(2)) }
}

const rows = []
for (const [id, parts] of Object.entries(SPECS)) {
  const r = await build(id, parts)
  const used = [...new Set(parts.map((p) => (p.make ? null : p.src)))].map((k) => (k ? SOURCES[k] : { title: 'Trailer frame and wheels', author: 'drawn by build-models.mjs', licence: CC0, url: null }))
  rows.push({ ...r, used })
  console.log(id.padEnd(26), String(r.tris).padStart(6), 'tris', (r.bytes / 1024).toFixed(1).padStart(6), 'KB  shape', r.shape.join(' x '))
}
const total = rows.reduce((s, r) => s + r.bytes, 0)
writeFileSync(join(OUT, 'LICENSES.md'), `# 3D models: sources and licences

${rows.length} models, ${(total / 1024).toFixed(0)} KB in all. Built by \`web/src/scene/dev/build-models.mjs\`, which is also the record of what was
changed: every source was merged into one mesh, its colours were baked into the vertices, it was stood z up, turned
to face +x and rescaled to a unit cube, then compressed with meshopt. The scene stretches that cube to the box a tool
measured, so a model's proportions on screen are the measured object's, not the source's.

CC0 files need no credit; Kenney and Quaternius are credited here anyway. CC BY 3.0 files are credited as the
licence requires (https://creativecommons.org/licenses/by/3.0/). No file here is GPL, non-commercial or made by the
brand of the thing it stands for.

| Model | Size | Triangles | Source | Author | Licence |
|---|---|---|---|---|---|
${rows.map((r) => `| \`${r.id}\` | ${(r.bytes / 1024).toFixed(1)} KB | ${r.tris} | ${r.used.map((u) => (u.url ? `[${u.title}](${u.url})` : u.title)).join(' + ')} | ${[...new Set(r.used.map((u) => u.author))].join(' + ')} | ${[...new Set(r.used.map((u) => u.licence))].join(' + ')} |`).join('\n')}

Kenney: https://kenney.nl (CC0 1.0, https://creativecommons.org/publicdomain/zero/1.0/).
Quaternius: https://quaternius.com (CC0 1.0), files taken from https://poly.pizza.
Poly by Google: models first published on Google Poly under CC BY 3.0, files taken from https://poly.pizza.
`)
console.log(`${rows.length} models, ${(total / 1024).toFixed(0)} KB`)
