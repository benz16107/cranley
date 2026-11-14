// Dev-only splat source for the scene workstream. Run: node src/scene/dev/splat-proxy.mjs   (from web/)
// GET http://127.0.0.1:8797/splat/<sid> streams splat.ply with CORS. The hackathon site answers with a signed link
// that browsers cannot read cross-origin and that ignores Range, so this keeps the first 100 MB of each splat in
// $THRESHOLD_DATA_DIR/cache/splat (outside the repo: sponsor data) and serves that. One upstream download per scan.
import { createReadStream, createWriteStream, existsSync, mkdirSync, renameSync, statSync } from 'node:fs'
import { createServer } from 'node:http'
import { join } from 'node:path'
import { Readable } from 'node:stream'

const SITE = (process.env.HACKATHON_SITE ?? 'https://beta-app.matterport.com/2026-princeton-hackathon').replace(/\/$/, '')
const DIR = join(process.env.THRESHOLD_DATA_DIR ?? '~/Code/hackathons/hackprinceton26-data', 'cache', 'splat')
const KEEP = 100 * 2 ** 20
const busy = new Map() // sid -> promise of the cached file path
mkdirSync(DIR, { recursive: true })

async function cached(sid) {
  const full = join(DIR, `${sid}.ply`), head = join(DIR, `${sid}.head.ply`)
  if (existsSync(full)) return full
  if (existsSync(head)) return head
  if (!busy.has(sid)) busy.set(sid, (async () => {
    const res = await fetch(`${SITE}/resources/${sid}/splat/splat.ply`)
    if (!res.ok || !res.body) throw new Error(`upstream ${res.status}`)
    const out = createWriteStream(head + '.part')
    let got = 0
    for await (const chunk of Readable.fromWeb(res.body)) {
      const take = chunk.subarray(0, KEEP - got)
      if (!out.write(take)) await new Promise((r) => out.once('drain', r))
      if ((got += take.length) >= KEEP) break // stop early: the rest of the file is never downloaded
    }
    await new Promise((r) => out.end(r))
    renameSync(head + '.part', head)
    return head
  })().finally(() => busy.delete(sid)))
  return busy.get(sid)
}

createServer(async (req, res) => {
  const sid = /^\/splat\/([A-Za-z0-9]{6,20})$/.exec(req.url ?? '')?.[1] // ids only: nothing else reaches the file system
  res.setHeader('Access-Control-Allow-Origin', '*')
  if (!sid) { res.writeHead(404).end(); return }
  try {
    const file = await cached(sid), size = Math.min(statSync(file).size, KEEP)
    res.writeHead(200, { 'Content-Type': 'application/octet-stream', 'Content-Length': size, 'Cache-Control': 'max-age=86400' })
    if (req.method === 'HEAD') { res.end(); return }
    createReadStream(file, { end: size - 1 }).pipe(res)
  } catch (e) { res.writeHead(502).end(String(e.message)) }
}).listen(8797, process.env.SPLAT_PROXY_HOST ?? '127.0.0.1', () => console.log(`splat proxy on :8797, cache ${DIR}`))
