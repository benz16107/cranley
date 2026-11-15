// Checks the built site (dist/): every internal link and anchor resolves, every image has alt text, nothing loads
// from another host, and nothing that looks like a home path, a tailnet name or a scan id other than the two
// made-up test scans got in. Run after `pnpm build`: `pnpm check`. Exits 1 on any finding.
import { readFileSync, readdirSync, existsSync, statSync } from 'node:fs'
import { join } from 'node:path'

const DIST = 'dist'
const walk = (d) => readdirSync(d, { withFileTypes: true }).flatMap((e) => (e.isDirectory() ? walk(join(d, e.name)) : [join(d, e.name)]))
const pages = walk(DIST).filter((f) => f.endsWith('.html'))
const html = new Map(pages.map((f) => [f, readFileSync(f, 'utf8')]))
const ids = new Map([...html].map(([f, s]) => [f, new Set([...s.matchAll(/\sid="([^"]+)"/g)].map((m) => m[1]))]))
const fileOf = (path) => {
  const p = join(DIST, decodeURIComponent(path))
  return existsSync(p) && statSync(p).isFile() ? p : existsSync(join(p, 'index.html')) ? join(p, 'index.html') : null
}
const bad = []
const FORBID = [[/(?<![\w.-])\/(?:home|Users)\/\w/, 'a home path'], [/\bts\.net\b|tailb\d+/, 'a tailnet name'], [/\b(?:linuxbox|macserver|benmac)\b/, 'a machine name'], [/—/, 'an em dash'],
  // notes to the team that must never reach a page (docs/story.md is also the team's working file)
  [/lead(?:'|’|&#39;|&#x27;)s server/i, 'a note to the team'], [/\?as=/, 'the profile switch'], [/not merged yet/i, 'a stale branch note'], [/hackprinceton26-data/, 'the data folder'], [/Team note/, 'a team note'], [/\breports\/[\w-]+\.md\b/, 'a report in the data folder']]
// the live demo's own address is on a tailnet name by design; everything else on a page still may not be
const DEMO = readFileSync('src/site/links.ts', 'utf8').match(/demo: '([^']+)'/)?.[1]
// the one thing loaded from another company: the interview on the Peri page, which the privacy page names
const EMBED = /^https:\/\/www\.youtube-nocookie\.com\/embed\/[\w-]+$/
const TEST_SCANS = new Set(['u_testhome0001', 'u_testcafe0001'])

for (const [file, s] of html) {
  for (const [, attr, url] of s.matchAll(/\s(href|src)="([^"]+)"/g)) {
    if (/^(https?:)?\/\//.test(url)) {
      // a link out is fine; a script, style, image or font from another host is not
      if (attr === 'src' && EMBED.test(url) && file.includes('tracks/peri/')) continue
      if (attr === 'src' || new RegExp(`<link[^>]+href="${url.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}"[^>]*rel="(stylesheet|preload)`).test(s)) bad.push(`${file}: loads ${url} from another host`)
      continue
    }
    if (!url.startsWith('/')) continue // #fragment, mailto:, data:
    const [path, hash] = url.split('#')
    const target = fileOf(path.split('?')[0])
    if (!target) bad.push(`${file}: ${url} does not exist`)
    else if (hash && target.endsWith('.html') && !ids.get(target)?.has(decodeURIComponent(hash))) bad.push(`${file}: ${url} has no such anchor`)
  }
  for (const [, hash] of s.matchAll(/\shref="#([^"]+)"/g)) if (!ids.get(file).has(decodeURIComponent(hash)) && hash !== '_top') bad.push(`${file}: #${hash} has no such anchor`)
  for (const [img] of s.matchAll(/<img\b[^>]*>/g)) if (!/\salt[=\s>]/.test(img)) bad.push(`${file}: an image has no alt text`)
  const text = s.replace(/<script[\s\S]*?<\/script>|<style[\s\S]*?<\/style>/g, '').replaceAll(DEMO ?? '\0', '')
  for (const [re, what] of FORBID) { const m = text.match(re); if (m) bad.push(`${file}: ${what} (${text.slice(Math.max(0, m.index - 40), m.index + 40).replace(/\s+/g, ' ')})`) }
  for (const [id] of text.matchAll(/\bu_[0-9a-z]{8,}\b/g)) if (!TEST_SCANS.has(id)) bad.push(`${file}: scan id ${id}`)
}

console.log(`${pages.length} pages checked`)
if (bad.length) { console.error(bad.slice(0, 60).join('\n')); console.error(`${bad.length} problems`); process.exit(1) }
