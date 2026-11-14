/* The phone companion in a real browser: an emulated phone and a desktop on the same workspace.

   node scripts/mobile-e2e.mjs [prep] [stage ...]   stages: pair tasks instruments media standalone webkit (default: all)

   Needs the API on 127.0.0.1:8821 and the web app at THRESHOLD_E2E_ORIGIN, and playwright-core (PLAYWRIGHT_CORE: the
   path of any install whose browsers are downloaded; it is not a dependency of this repo). `prep` makes the
   workspace the stages use: door_widths, step_free_route, daylight and flood_rehearsal run on a scan with walls
   (THRESHOLD_E2E_SID, or the first house in the data folder's test list); it is remembered in THRESHOLD_E2E. Scan ids and screenshots stay in the data folder: nothing sponsor-derived is written to the repo.
   Sensors are simulated: devicemotion and deviceorientation events are dispatched into the page, geolocation is
   the context's, and Chromium's fake camera and microphone stand in for the real ones. */
import { createRequire } from 'node:module'
import fs from 'node:fs'
import path from 'node:path'

const require = createRequire(import.meta.url)
const { chromium, webkit, devices } = require(process.env.PLAYWRIGHT_CORE ?? 'playwright-core')
const DATA = process.env.THRESHOLD_DATA_DIR ?? '~/Code/hackathons/hackprinceton26-data' // the server's own default (threshold/config.py)
// Where the web app answers. 127.0.0.1 counts as a secure context, so sensors work there; set this to the HTTPS address to test that path.
const ORIGIN = process.env.THRESHOLD_E2E_ORIGIN ?? 'http://127.0.0.1:5231'
const OUT = path.join(DATA, 'shots/mobile')
const stages = process.argv.slice(2)
const PREPARED = process.env.THRESHOLD_E2E ?? '/tmp/threshold-mobile-e2e.json'
if (stages.includes('prep') || !fs.existsSync(PREPARED)) { // a fresh workspace on the first house in the data folder's test list, with the four source tools run
  const post = async (p, body) => (await fetch(`http://127.0.0.1:8821/api${p}`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) })).json()
  const sid = process.env.THRESHOLD_E2E_SID ?? Object.values(JSON.parse(fs.readFileSync(path.join(DATA, 'fixtures/test_sids.json'), 'utf8')).compass_houses).flat()[0]
  const ws = (await post('/workspace', {})).doc.id
  await post(`/workspace/${ws}/ops`, [{ op: 'brief.set', scope: { sids: [sid] } }, ...['door_widths', 'step_free_route', 'daylight', 'flood_rehearsal'].map((tool) => ({ op: 'tool.enable', tool, reason: 'End-to-end test' }))])
  for (const [tool, inputs] of [['door_widths', { min_width_m: 0.815 }], ['step_free_route', { min_width_m: 0.815, read_panoramas: false }], ['daylight', {}], ['flood_rehearsal', { depth_m: 0.6 }]])
    console.log('prep:', tool, (await post(`/tools/${tool}/run?workspace=${ws}`, { scan: sid, ...inputs })).verdict)
  fs.writeFileSync(PREPARED, JSON.stringify({ ws, sid }))
}
const { ws, sid } = JSON.parse(fs.readFileSync(PREPARED, 'utf8'))
const on = (s) => !stages.filter((x) => x !== 'prep').length || stages.includes(s)
const log = (...a) => console.log(...a)
const results = []
const check = (name, ok, detail = '') => { results.push({ name, ok }); log(ok ? '  ok  ' : '  FAIL', name, detail) }
const api = async (p, body) => (await fetch(`http://127.0.0.1:8821/api${p}`, body === undefined ? {} : { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) })).json()

/** Sensors a page can read, simulated: gravity for the tilt sensor, a compass heading, and iOS's permission step. */
const sensors = (ios) => {
  if (typeof DeviceMotionEvent === 'undefined') return // the blank page before navigation is not a secure context
  window.__sim = { g: { x: 0, y: 0.81, z: 9.77 }, heading: 170 }
  const jitter = () => (Math.random() - 0.5) * 0.02
  setInterval(() => {
    const { g, heading } = window.__sim
    if (g) dispatchEvent(new DeviceMotionEvent('devicemotion', { accelerationIncludingGravity: { x: g.x + jitter(), y: g.y + jitter(), z: g.z + jitter() }, interval: 33 }))
    if (heading == null) return
    if (ios) {
      const e = new DeviceOrientationEvent('deviceorientation', { alpha: 0, beta: 2, gamma: 1 })
      Object.defineProperty(e, 'webkitCompassHeading', { value: heading + jitter() * 20 }); Object.defineProperty(e, 'webkitCompassAccuracy', { value: 10 })
      dispatchEvent(e)
    } else dispatchEvent(new DeviceOrientationEvent('deviceorientationabsolute', { alpha: (360 - heading + jitter() * 20) % 360, beta: 2, gamma: 1, absolute: true }))
  }, 33)
  if (ios) { DeviceMotionEvent.requestPermission = async () => 'granted'; DeviceOrientationEvent.requestPermission = async () => 'granted' }
}

const browser = await chromium.launch({ args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'] })
const building = (await api(`/scan/${sid}/plan`)).geo ?? {}
async function phone(kind, opts = {}) {
  const d = kind === 'iphone' ? devices['iPhone 15'] : devices['Pixel 7']
  const ctx = await browser.newContext({ ...d, defaultBrowserType: undefined, permissions: ['geolocation', 'camera', 'microphone', 'accelerometer', 'gyroscope', 'magnetometer'],
    geolocation: { latitude: building.lat ?? 29.76, longitude: building.lon ?? -95.37, accuracy: 6 }, ...opts })
  await ctx.addInitScript(sensors, kind === 'iphone')
  const page = await ctx.newPage()
  page.on('pageerror', (e) => check(`${kind}: no page error`, false, e.message))
  return { ctx, page, shot: (name) => page.screenshot({ path: path.join(OUT, `${kind}-${name}.png`) }) }
}
const token = async () => (await api(`/workspace/${ws}/pair`, {})).token

let desk
if (on('pair')) {
  log('pair: the desktop makes a QR code, the phone opens it, a tape measurement changes the finding on the desktop')
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  await ctx.addInitScript((id) => localStorage.setItem('threshold.workspace', id), ws)
  desk = await ctx.newPage()
  desk.on('pageerror', (e) => check('desktop: no page error', false, e.message))
  await desk.goto(`${ORIGIN}/sheet/scan/${sid}`)
  await desk.getByText('Door widths').first().waitFor({ timeout: 30000 })
  const tab = desk.locator('[data-phone-link]').getByRole('button', { name: /Phone/ })
  await tab.click()
  await desk.locator('[data-phone-link] .qr svg').waitFor({ timeout: 10000 })
  const url = (await desk.locator('[data-phone-link] .url').textContent()).trim()
  check('desktop: the QR code carries a link to /m' + (url.startsWith('https://') ? ' over HTTPS' : ''), /^https?:\/\/[^/]+\/m\?t=[\w.-]+$/.test(url), url.slice(0, 40))
  check('desktop: the link does not show the workspace id', !url.includes(ws))
  await desk.screenshot({ path: path.join(OUT, 'desktop-01-continue-on-phone-qr.png') })

  const p = await phone('pixel')
  await p.page.goto(ORIGIN + new URL(url).pathname + new URL(url).search) // the link's own path, at the address under test
  await p.page.getByText('Doorways: clear width').waitFor({ timeout: 15000 })
  check('phone: the token is taken out of the address bar', !p.page.url().includes('t='))
  check('phone: says it is linked to the desktop', await p.page.getByText('Linked to the desktop').isVisible())
  await p.shot('01-tasks')
  const before = (await api(`/workspace/${ws}`)).doc.findings
  await p.page.locator('section', { hasText: 'Doorways: clear width' }).locator('button.m-row').first().click()
  await p.page.getByLabel(/Clear width/).waitFor()
  await p.shot('02-measure-task')
  await p.page.getByLabel(/Clear width/).fill('33.5')
  await p.shot('03-measure-typed')
  await p.page.getByRole('button', { name: /Save 33.5 in/ }).click()
  await p.page.locator('.m-card').getByText(/the scan/i).first().waitFor({ timeout: 20000 })
  await p.shot('04-measure-outcome')
  const outcome = (await p.page.locator('.m-card').last().innerText()).replace(/\s+/g, ' ')
  check('phone: the outcome is shown with the scan value and the limit', /on site/i.test(outcome) && /scan/i.test(outcome) && /limit/i.test(outcome), outcome.slice(0, 120))

  // the desktop was never reloaded: the Field check panel and the capture arrive over the live stream
  await desk.getByText('Field check').first().waitFor({ timeout: 15000 })
  check('desktop: the Field check panel arrived without a reload', true)
  await desk.locator('[data-phone-link] li').first().waitFor({ timeout: 10000 })
  check('desktop: the capture is listed under "From the phone"', (await desk.locator('[data-phone-link] li').count()) >= 1)
  await desk.screenshot({ path: path.join(OUT, 'desktop-02-capture-arrived-live.png') })
  const after = (await api(`/workspace/${ws}`)).doc.findings
  const changed = after.filter((f) => f.source.layer === 'phone' && before.find((b) => b.id === f.id)?.source.layer !== 'phone')
  check('workspace: a door finding now carries the on-site value and the capture', changed.length >= 1 && changed[0].media.some((m) => m.kind === 'phone'),
    changed[0] && `${changed[0].id.split(':')[0]} ${before.find((b) => b.id === changed[0].id).status} -> ${changed[0].status}`)
  await desk.locator('[data-phone-link]').getByRole('button', { name: /Phone/ }).click() // close the popover
  await desk.getByText('Field check').first().scrollIntoViewIfNeeded()
  await desk.screenshot({ path: path.join(OUT, 'desktop-03-field-check-panel.png') })
  await p.page.goBack()
  await p.page.getByText(/Done ·/).waitFor()
  await p.shot('05-tasks-one-done')
  await p.ctx.close()
}

if (on('tasks')) {
  log('tasks: each kind of task screen, on both phones')
  for (const kind of ['iphone', 'pixel']) {
    const p = await phone(kind)
    await p.page.goto(`${ORIGIN}/m?t=${await token()}`)
    await p.page.getByText('Doorways: clear width').waitFor({ timeout: 15000 })
    const w = await p.page.evaluate(() => document.documentElement.scrollWidth - innerWidth)
    check(`${kind}: no sideways scroll on the task list`, w <= 0, `overflow ${w}px`)
    await p.shot('10-tasks')
    // floor height: steps counted, a measured riser, two fixes (the browser gives no altitude here: that path is shown)
    await p.page.locator('button.m-row', { hasText: 'Stand at the front door' }).click()
    await p.page.getByRole('button', { name: 'One more' }).click(); await p.page.getByRole('button', { name: 'One more' }).click(); await p.page.getByRole('button', { name: 'One more' }).click()
    await p.page.getByLabel(/One step's height/).fill('7')
    await p.page.getByRole('button', { name: 'Take a fix' }).first().click()
    await p.page.getByText(/± 6 m/).first().waitFor({ timeout: 15000 })
    await p.shot('11-floor-height-inputs')
    if (kind === 'pixel') {
      await p.page.getByRole('button', { name: 'Work out the floor height' }).click()
      await p.page.locator('.m-card').first().waitFor({ timeout: 180000 })
      await p.page.locator('.m-card').last().scrollIntoViewIfNeeded()
      await p.shot('12-floor-height-result')
      const t = (await p.page.locator('.m-card').last().innerText()).replace(/\s+/g, ' ')
      check('pixel: floor height reports a value with its range', /on site/i.test(t), t.slice(0, 160))
    }
    await p.page.goBack()
    // window: the compass (with iOS's permission step on the iPhone)
    await p.page.locator('section', { hasText: 'Windows: which way they face' }).locator('button.m-row').first().click()
    // iOS asks before a page may read motion sensors, and this Chromium has the same requestPermission call: the gate shows on both
    const allow = p.page.getByRole('button', { name: 'Turn on motion sensors' })
    await allow.waitFor({ timeout: 4000 }).then(async () => { await p.shot('13-window-permission'); await allow.click() }, () => check(`${kind}: motion permission gate shown`, kind !== 'iphone'))
    await p.page.getByText(/Top edge points/).waitFor({ timeout: 8000 }).catch(async (e) => { await p.shot('14-window-FAILED'); throw e })
    await p.shot('14-window-compass')
    await p.page.getByRole('button', { name: 'Record this direction' }).click()
    await p.page.locator('.m-card').first().waitFor({ timeout: 30000 })
    await p.shot('15-window-result')
    check(`${kind}: the window check says how the phone and the scan compare`, /(confirms|contradicts|first measurement)/i.test(await p.page.locator('.m-card').last().innerText()))
    await p.page.goBack()
    // a step, by photo: the reference chips and the camera button (no photo is taken here)
    const step = p.page.locator('section', { hasText: 'Steps and thresholds' }).locator('button.m-row').first()
    if (await step.count()) { await step.click(); await p.page.getByRole('radio', { name: 'Photo' }).click(); await p.page.getByRole('radio', { name: 'Bank card' }).click(); await p.shot('16-step-photo-reference'); await p.page.goBack() }
    await p.ctx.close()
  }
}

if (on('instruments')) {
  log('instruments: level, sound, where am I, results, on both phones')
  for (const kind of ['iphone', 'pixel']) {
    const p = await phone(kind)
    await p.page.goto(`${ORIGIN}/m?t=${await token()}`)
    await p.page.getByRole('button', { name: 'Tools' }).click()
    await p.page.getByText('Instruments').waitFor()
    await p.shot('20-tools')
    await p.page.locator('button.m-row', { hasText: 'Slope check' }).click()
    await p.page.getByRole('button', { name: 'Turn on motion sensors' }).click({ timeout: 4000 }).catch(() => {})
    await p.page.getByText('Tilt now').waitFor({ timeout: 8000 })
    await p.shot('21-level-live')
    await p.page.getByRole('button', { name: 'Read', exact: true }).click()
    await p.page.getByRole('button', { name: 'Read the second way' }).waitFor({ timeout: 8000 })
    await p.page.evaluate(() => { window.__sim.g = { x: 0, y: -0.69, z: 9.78 } }) // turned end for end: the slope's sign flips, the sensor's offset does not
    await p.page.waitForTimeout(400)
    await p.shot('22-level-second-reading')
    await p.page.getByRole('button', { name: 'Read the second way' }).click()
    await p.page.locator('.m-card').first().waitFor({ timeout: 20000 })
    await p.page.locator('.m-card').last().scrollIntoViewIfNeeded()
    await p.shot('23-level-result')
    const slope = (await p.page.locator('.m-card').last().innerText()).replace(/\s+/g, ' ')
    check(`${kind}: slope check judged a 7.7% ramp against 1:12`, /within the/.test(slope), slope.slice(0, 140))
    await p.page.goBack()
    await p.page.locator('button.m-row', { hasText: 'Noise level' }).click()
    await p.page.getByLabel('Room').selectOption({ index: 1 })
    await p.shot('24-sound')
    if (kind === 'pixel') {
      await p.page.getByRole('button', { name: /Measure 15 seconds/ }).click()
      await p.page.getByText('Now').waitFor({ timeout: 8000 })
      await p.page.waitForTimeout(3000)
      await p.shot('25-sound-listening')
      await p.page.locator('.m-card').first().waitFor({ timeout: 40000 })
      await p.page.locator('.m-card').last().scrollIntoViewIfNeeded()
      await p.shot('26-sound-result')
      check('pixel: the sound meter produced a level from the (fake) microphone', /dBA/.test(await p.page.locator('.m-body').innerText()))
    }
    await p.page.goBack()
    await p.page.locator('button.m-row', { hasText: 'Where am I' }).click()
    await p.page.getByRole('button', { name: 'Find where I am' }).click()
    await p.page.locator('.m-note').waitFor({ timeout: 30000 })
    await p.shot('27-where-am-i')
    check(`${kind}: where am I found the building the fix is at`, /You are at|scanned addresses are within reach/.test(await p.page.locator('.m-note').innerText()))
    await p.page.goBack()
    await p.page.getByRole('button', { name: 'Results' }).click()
    await p.page.getByText('From this phone').waitFor({ timeout: 10000 })
    await p.shot('28-results')
    await p.page.locator('.m-card .link').first().click()
    await p.shot('29-results-detail')
    await p.page.getByRole('button', { name: 'What is sent' }).click()
    await p.shot('30-what-is-sent')
    await p.ctx.close()
  }
}

if (on('media')) {
  log('media: a note photo, photo measure with a sheet of paper, a recorded walk-through (Pixel)')
  const photo = path.join(OUT, 'fixtures/doorway.jpg')
  const p = await phone('pixel')
  await p.page.goto(`${ORIGIN}/m?t=${await token()}`)
  await p.page.getByRole('button', { name: 'Tools' }).click()
  await p.page.locator('button.m-row', { hasText: 'Note' }).click()
  await p.page.getByLabel('Room').selectOption({ index: 2 })
  await p.page.getByLabel('What it shows').fill('Water stain under the window')
  await p.page.locator('input[type=file]').setInputFiles(photo)
  await p.page.getByText('Saved. It is on the desktop now.').waitFor({ timeout: 20000 })
  await p.shot('40-note-sent')
  await p.page.goBack()
  await p.page.locator('button.m-row', { hasText: 'Photo measure' }).click()
  await p.shot('41-photo-measure')
  await p.page.locator('input[type=file]').setInputFiles(photo)
  await p.page.locator('.m-points, .m-note.warn').first().waitFor({ timeout: 120000 })
  await p.page.waitForTimeout(500)
  await p.shot('42-photo-measure-read')
  const read = (await p.page.locator('.m-body').innerText()).replace(/\s+/g, ' ')
  check('pixel: photo measure answered (a length with its error, or a plain reason it could not)', /Give or take|does not show|too small/i.test(read), read.slice(-220))
  if (!(await p.page.locator('.m-points').count())) await p.page.getByRole('button', { name: 'Place the points by hand' }).click()
  const box = await p.page.locator('.m-points').boundingBox()
  const b = p.page.getByRole('button', { name: 'End B' })
  await b.dispatchEvent('pointerdown', { pointerId: 1 }).catch(() => {})
  const bb = await b.boundingBox()
  await p.page.mouse.move(bb.x + 22, bb.y + 22); await p.page.mouse.down(); await p.page.mouse.move(box.x + box.width * 0.82, bb.y + 22, { steps: 4 }); await p.page.mouse.up()
  await p.shot('43-photo-measure-points-moved')
  const again = p.page.getByRole('button', { name: 'Measure with these points' })
  check('pixel: dragging a point offers to measure again', await again.isVisible())
  if (await again.isVisible()) { await again.click(); await p.page.locator('.m-card, .m-note.warn').last().waitFor({ timeout: 30000 }); await p.page.waitForTimeout(600); await p.shot('44-photo-measure-by-hand') }
  await p.page.goBack()
  await p.page.locator('button.m-row', { hasText: 'Walk-through' }).click()
  await p.page.getByRole('button', { name: 'Record', exact: true }).click()
  await p.page.waitForTimeout(6000)
  await p.shot('45-walkthrough-recording')
  await p.page.getByRole('button', { name: /Stop and send/ }).click()
  await p.page.locator('.m-card, .m-note.warn').first().waitFor({ timeout: 240000 })
  await p.page.locator('.m-card, .m-note.warn').last().scrollIntoViewIfNeeded()
  await p.shot('46-walkthrough-result')
  const walk = (await p.page.locator('.m-body').innerText()).replace(/\s+/g, ' ')
  check('pixel: a recorded video was sent, its frames read, and a census came back', /rooms? seen|No frame/.test(walk), walk.slice(-200))
  await p.ctx.close()
}

if (on('standalone')) {
  log('standalone: a phone with no link starts its own workspace; no sensors and no permissions fall back')
  const p = await phone('iphone', { permissions: [] })
  await p.ctx.addInitScript(() => { window.__sim = { g: null, heading: null }; delete DeviceMotionEvent.requestPermission; delete DeviceOrientationEvent.requestPermission })
  await p.page.goto(`${ORIGIN}/m`)
  await p.page.getByText('Start at a building').waitFor({ timeout: 15000 })
  await p.shot('50-standalone-start')
  await p.page.getByRole('textbox').fill('I use a wheelchair and I am looking at this house')
  await p.shot('51-standalone-brief-typed')
  await p.page.locator('button.m-row', { hasText: 'Find where I am' }).click()
  await p.page.getByRole('button', { name: 'Find where I am' }).click()
  await p.page.locator('[data-sonner-toast]').first().waitFor({ timeout: 20000 })
  await p.shot('52-location-refused')
  check('iphone: a refused location says what to do', /switched off|could not get a fix|No fix/.test(await p.page.locator('[data-sonner-toast]').first().innerText()))
  await p.page.goBack()
  await p.page.getByRole('button', { name: 'Tools' }).click()
  await p.page.locator('button.m-row', { hasText: 'Slope check' }).click()
  await p.page.getByText(/has no tilt sensor/).waitFor({ timeout: 8000 })
  await p.shot('53-no-tilt-sensor')
  check('iphone: a device with no tilt sensor is told so, with a fallback', true)
  await p.page.goBack()
  await p.ctx.close()
  const e = await phone('pixel')
  await e.page.goto(`${ORIGIN}/m?t=bm90LWEtdG9rZW4.AAAA`)
  await e.page.getByText(/link has expired/).waitFor({ timeout: 10000 })
  await e.shot('54-expired-link')
  check('pixel: a bad or expired link says so and offers to carry on alone', true)
  await e.ctx.close()
}

if (on('webkit')) {
  log('webkit: the same pages in Safari\'s engine (layout only; WebKit on Linux has no camera or sensors)')
  const wk = await webkit.launch()
  const ctx = await wk.newContext({ ...devices['iPhone 15'] })
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))
  await page.goto(`${ORIGIN}/m?t=${await token()}`)
  await page.getByText('Doorways: clear width').waitFor({ timeout: 20000 })
  await page.screenshot({ path: path.join(OUT, 'webkit-01-tasks.png') })
  await page.locator('section', { hasText: 'Doorways: clear width' }).locator('button.m-row').first().click()
  await page.getByLabel(/Clear width/).fill('32')
  await page.screenshot({ path: path.join(OUT, 'webkit-02-measure.png') })
  await page.goBack()
  await page.getByRole('button', { name: 'Tools' }).click()
  await page.locator('button.m-row', { hasText: 'Floor height' }).click()
  await page.screenshot({ path: path.join(OUT, 'webkit-03-floor-height.png') })
  await page.goBack()
  await page.getByRole('button', { name: 'Results' }).click()
  await page.waitForTimeout(800)
  await page.screenshot({ path: path.join(OUT, 'webkit-04-results.png') })
  const w = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)
  check('webkit: pages render with no script error and no sideways scroll', !errors.length && w <= 0, errors.join('; '))
  await wk.close()
}

await browser.close()
const failed = results.filter((r) => !r.ok)
log(`\n${results.length - failed.length} of ${results.length} checks passed` + (failed.length ? `; failed: ${failed.map((f) => f.name).join(' | ')}` : ''))
process.exit(failed.length ? 1 : 0)
