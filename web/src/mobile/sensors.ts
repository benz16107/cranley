import { useCallback, useEffect, useRef, useState } from 'react'
import { A_GAIN_DB, A_STAGES, bestFix, headingFromAlpha, headingMean, level, mean, spread, tilt, type Fix } from './dsp.ts'

/* The phone's sensors as hooks. Each one says plainly when a sensor is missing or refused, so a screen can fall back
   (type the number, pick the direction) and never sits waiting on a sensor that will not come. */

export type Sense = 'unknown' | 'need-permission' | 'on' | 'denied' | 'missing'
type Asking = { requestPermission?: () => Promise<'granted' | 'denied'> }

/** iOS asks for motion and orientation once, and only from a tap. Elsewhere there is nothing to ask. */
export async function askMotion(): Promise<boolean> {
  const asks = [(globalThis as { DeviceMotionEvent?: Asking }).DeviceMotionEvent, (globalThis as { DeviceOrientationEvent?: Asking }).DeviceOrientationEvent]
  try {
    for (const a of asks) if (a?.requestPermission && (await a.requestPermission()) !== 'granted') return false
    return true
  } catch { return false }
}
const needsAsk = () => typeof (globalThis as { DeviceMotionEvent?: Asking }).DeviceMotionEvent?.requestPermission === 'function'

/** Live tilt in degrees (see dsp.tilt), and `sample(ms)`: hold still and average. */
export function useTilt() {
  const [state, setState] = useState<Sense>(() => (!('DeviceMotionEvent' in globalThis) ? 'missing' : needsAsk() ? 'need-permission' : 'unknown'))
  const [now, setNow] = useState<{ long: number; short: number } | null>(null)
  const buf = useRef<{ long: number; short: number; t: number }[]>([])
  const listen = useCallback(() => {
    let last = 0
    const on = (e: DeviceMotionEvent) => {
      const g = e.accelerationIncludingGravity
      if (!g || g.x == null || g.y == null || g.z == null) return
      const t = tilt({ x: g.x, y: g.y, z: g.z }), at = performance.now()
      buf.current.push({ ...t, t: at })
      if (buf.current.length > 600) buf.current.splice(0, 200)
      if (at - last > 100) { last = at; setNow(t); setState('on') } // ten readouts a second is plenty to read
    }
    addEventListener('devicemotion', on)
    const none = setTimeout(() => setState((s) => (s === 'unknown' ? 'missing' : s)), 2500) // a desktop has the API and no sensor
    return () => { removeEventListener('devicemotion', on); clearTimeout(none) }
  }, [])
  const off = state === 'need-permission' || state === 'denied' || state === 'missing'
  useEffect(() => (off ? undefined : listen()), [off, listen])
  const allow = useCallback(async () => setState((await askMotion()) ? 'unknown' : 'denied'), [])
  const sample = useCallback((ms = 2000) => new Promise<{ long: number; short: number; spread: number; n: number } | null>((res) => {
    const from = performance.now()
    setTimeout(() => {
      const xs = buf.current.filter((b) => b.t >= from)
      res(xs.length < 5 ? null : { long: mean(xs.map((x) => x.long)), short: mean(xs.map((x) => x.short)), spread: Math.max(spread(xs.map((x) => x.long)), spread(xs.map((x) => x.short))), n: xs.length })
    }, ms)
  }), [])
  return { state, now, allow, sample }
}

/** Live compass heading of the phone's top edge, degrees clockwise from magnetic north, held flat. */
export function useHeading() {
  const [state, setState] = useState<Sense>(() => (!('DeviceOrientationEvent' in globalThis) ? 'missing' : needsAsk() ? 'need-permission' : 'unknown'))
  const [now, setNow] = useState<{ heading: number; accuracy: number | null; flat: boolean } | null>(null)
  const buf = useRef<{ h: number; t: number }[]>([])
  const off = state === 'need-permission' || state === 'denied' || state === 'missing'
  useEffect(() => {
    if (off) return
    let last = 0
    const on = (e: DeviceOrientationEvent) => {
      const ios = (e as DeviceOrientationEvent & { webkitCompassHeading?: number; webkitCompassAccuracy?: number })
      const h = ios.webkitCompassHeading ?? (e.absolute && e.alpha != null ? headingFromAlpha(e.alpha) : null)
      if (h == null) return
      const at = performance.now()
      buf.current.push({ h, t: at })
      if (buf.current.length > 600) buf.current.splice(0, 200)
      if (at - last > 100) { last = at; setState('on'); setNow({ heading: h, accuracy: ios.webkitCompassAccuracy != null && ios.webkitCompassAccuracy >= 0 ? ios.webkitCompassAccuracy : null, flat: Math.abs(e.beta ?? 0) < 30 && Math.abs(e.gamma ?? 0) < 30 }) }
    }
    addEventListener('deviceorientationabsolute', on as EventListener)
    addEventListener('deviceorientation', on)
    const none = setTimeout(() => setState((s) => (s === 'unknown' ? 'missing' : s)), 3000)
    return () => { removeEventListener('deviceorientationabsolute', on as EventListener); removeEventListener('deviceorientation', on); clearTimeout(none) }
  }, [off])
  const allow = useCallback(async () => setState((await askMotion()) ? 'unknown' : 'denied'), [])
  const sample = useCallback((ms = 2000) => new Promise<{ heading: number; spread: number } | null>((res) => {
    const from = performance.now()
    setTimeout(() => { const xs = buf.current.filter((b) => b.t >= from).map((b) => b.h); const m = headingMean(xs); res(xs.length < 5 ? null : { heading: m.mean, spread: m.spread }) }, ms)
  }), [])
  return { state, now, allow, sample }
}

/** One GPS fix averaged over a few seconds. Rejects with a sentence the person can act on. */
export function getFix(ms = 6000): Promise<Fix> {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) { reject(new Error('This browser has no location.')); return }
    const got: Parameters<typeof bestFix>[0] = []
    let failed: string | null = null
    const id = navigator.geolocation.watchPosition(
      (p) => got.push({ lat: p.coords.latitude, lon: p.coords.longitude, accuracy_m: p.coords.accuracy ?? null, altitude_m: p.coords.altitude, altitude_accuracy_m: p.coords.altitudeAccuracy }),
      (e) => { failed = e.code === e.PERMISSION_DENIED ? 'Location is switched off for this page. Allow it in the browser settings, or pick the building from the list.' : 'The phone could not get a fix here. Step outside or near a window and try again.' },
      { enableHighAccuracy: true, maximumAge: 0, timeout: ms })
    const done = () => { navigator.geolocation.clearWatch(id); const f = bestFix(got); if (f) resolve(f); else reject(new Error(failed ?? 'No fix came in time. Try again near a window.')) }
    const early = setInterval(() => { if (failed && !got.length) { clearInterval(early); clearTimeout(end); done() } }, 300)
    const end = setTimeout(() => { clearInterval(early); done() }, ms)
  })
}

/** An A-weighted level meter on the microphone, voice processing off. `start()` from a tap; `stop()` returns the result. */
export function useSoundMeter() {
  const [live, setLive] = useState<number | null>(null)
  const run = useRef<{ stop: () => { leq_dba: number; lmax_dba: number; seconds: number } } | null>(null)
  const start = useCallback(async () => {
    if (!navigator.mediaDevices?.getUserMedia) throw new Error('This browser gives a page no microphone.')
    const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false } }).catch((e: Error) => {
      throw new Error(e.name === 'NotAllowedError' ? 'The microphone is switched off for this page. Allow it in the browser settings.' : 'No microphone answered.')
    })
    const Ctx = window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
    const ctx = new Ctx()
    await ctx.resume()
    let node: AudioNode = ctx.createMediaStreamSource(stream)
    for (const s of A_STAGES) { const f = ctx.createBiquadFilter(); f.type = s.type; f.frequency.value = Math.min(s.frequency, ctx.sampleRate / 2 - 100); f.Q.value = s.qDb; node.connect(f); node = f }
    const gain = ctx.createGain(); gain.gain.value = 10 ** (A_GAIN_DB / 20); node.connect(gain)
    const an = ctx.createAnalyser(); an.fftSize = 2048; gain.connect(an)
    const buf = new Float32Array(an.fftSize), squares: number[] = [], t0 = performance.now()
    let max = 0
    const tick = setInterval(() => { // one window of samples every 43 ms at 48 kHz: back to back, near enough
      an.getFloatTimeDomainData(buf)
      let s = 0
      for (let i = 0; i < buf.length; i++) s += buf[i] * buf[i]
      const ms = s / buf.length
      squares.push(ms); max = Math.max(max, ms)
      if (squares.length % 6 === 0) setLive(level(mean(squares.slice(-12))))
    }, (an.fftSize / ctx.sampleRate) * 1000)
    run.current = { stop: () => {
      clearInterval(tick); stream.getTracks().forEach((t) => t.stop()); void ctx.close(); setLive(null); run.current = null
      const body = squares.slice(Math.min(6, Math.floor(squares.length / 4))) // the first quarter second is the filters settling
      return { leq_dba: +level(mean(body)).toFixed(1), lmax_dba: +level(max).toFixed(1), seconds: +((performance.now() - t0) / 1000).toFixed(1) }
    } }
  }, [])
  const stop = useCallback(() => run.current?.stop() ?? null, [])
  useEffect(() => () => { run.current?.stop() }, [])
  return { live, start, stop }
}

/** The best container this browser's MediaRecorder writes: MP4 on iPhone, WebM on Android. Null when it has none. */
export function recorderType(kind: 'video' | 'audio'): string | null {
  if (typeof MediaRecorder === 'undefined') return null
  const tries = kind === 'video' ? ['video/mp4', 'video/webm;codecs=vp9', 'video/webm;codecs=vp8', 'video/webm'] : ['audio/mp4', 'audio/webm;codecs=opus', 'audio/webm']
  return tries.find((t) => MediaRecorder.isTypeSupported(t)) ?? null
}

type Rec = { start(): void; stop(): void; abort(): void; onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }> }) => void) | null; onend: (() => void) | null; onerror: ((e: { error: string }) => void) | null
  continuous: boolean; interimResults: boolean; lang: string }
/** Speech to text in the browser, where it has it (Safari and Chrome do; Firefox does not). */
export function useDictation(onText: (text: string, final: boolean) => void) {
  const Make = (globalThis as { SpeechRecognition?: new () => Rec; webkitSpeechRecognition?: new () => Rec }).SpeechRecognition ?? (globalThis as { webkitSpeechRecognition?: new () => Rec }).webkitSpeechRecognition
  const [on, setOn] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const rec = useRef<Rec | null>(null)
  const start = useCallback(() => {
    if (!Make) return
    const r = new Make()
    r.continuous = false; r.interimResults = true; r.lang = navigator.language || 'en-US'
    r.onresult = (e) => { let text = '', final = true; for (let i = 0; i < e.results.length; i++) { text += e.results[i][0].transcript; final &&= e.results[i].isFinal } onText(text.trim(), final) }
    r.onerror = (e) => setError(e.error === 'not-allowed' ? 'The microphone is switched off for this page.' : e.error === 'no-speech' ? 'Nothing was heard.' : 'Dictation stopped. Type it below.')
    r.onend = () => setOn(false)
    rec.current = r; setError(null); setOn(true)
    try { r.start() } catch { setOn(false) }
  }, [Make, onText])
  const stop = useCallback(() => rec.current?.stop(), [])
  useEffect(() => () => rec.current?.abort(), [])
  return { supported: !!Make, on, error, start, stop }
}
