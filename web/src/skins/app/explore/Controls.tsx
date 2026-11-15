import { useEffect, useState } from 'react'
import { Slider } from '@base-ui/react/slider'
import {
  BASE_VIEWS, CITIES, MAP_CREDIT, fetchWeather, sunDay, sunPosition, zonedInstant,
  type BaseView, type CityId, type MapLayer, type Weather,
} from '../../../core/index.ts'
import { Icon, IconBtn, Menu, MenuBtn, Seg, Tip } from '../design/ui.tsx'
import { CLOSE_Z, hueOf, useWorld } from './WorldMap.tsx'

/* The controls that sit on the map: which ground it is drawn on, which data is laid over it, the camera, and the
   small readouts (weather, sun). All of them are quiet: one row in a corner, a menu, a strip. */

export const ZONE: Record<CityId, string> = { hou: 'America/Chicago', la: 'America/Los_Angeles' }
const reduced = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches
const swatch = (l: MapLayer) => <i className="swatch" data-shape={l.shape} style={{ ['--hue' as string]: `var(${hueOf(l)})` }} />
/** What a layer's copy is dated: the source's own date when it gives one, else the day we fetched it. */
const dated = (l: MapLayer) => { const d = l.data_date ? l.data_date : l.fetched ? `fetched ${l.fetched}` : ''; return d && (l.attribution || l.source).endsWith(d) ? '' : d } // a source that names its year is not dated twice

/** The layer list and the base view, one row in the map's corner. The list is the catalogue's: one row per group,
    closed until asked for, so a layer added on the server appears here under its group with nothing changed. */
export function MapTools({ base, onBase, layers, on, toggle, reset, city }: { base: BaseView; onBase: (b: BaseView) => void; layers: MapLayer[]; on: string[]; toggle: (id: string) => void; reset: () => void; city: CityId }) {
  const zoom = useWorld((s) => s.zoom)
  const groups = [...new Set(layers.map((l) => l.group))]
  const shown = layers.filter((l) => on.includes(l.id) && l.available)
  return (
    <div className="maptools">
      <MenuBtn trigger={<button type="button" className="btn" aria-label={`Layers: ${shown.length} shown`}><Icon name="stack" size={14} />Layers<span className="count">{shown.length}</span></button>}>
        {!layers.length && <div className="mh">The layer list did not load. Is the data server running?</div>}
        {groups.map((g) => {
          const list = layers.filter((l) => l.group === g), n = list.filter((l) => shown.includes(l)).length
          return (
            <Menu.SubmenuRoot key={g}>
              <Menu.SubmenuTrigger>{g}<small>{n ? `${n} of ${list.length} on` : list.length}</small><Icon name="right" size={11} /></Menu.SubmenuTrigger>
              <Menu.Portal><Menu.Positioner sideOffset={2} alignOffset={-4} style={{ zIndex: 61 }}><Menu.Popup className="menu">
                {list.map((l) => (
                  <Menu.CheckboxItem key={l.id} checked={shown.includes(l)} disabled={!l.available} closeOnClick={false} onCheckedChange={() => toggle(l.id)}
                    title={`${l.attribution || l.source}${dated(l) ? `, ${dated(l)}` : ''}. ${l.note}`}>
                    <span className="mi-check"><Menu.CheckboxItemIndicator><Icon name="check" size={12} /></Menu.CheckboxItemIndicator></span>
                    {swatch(l)}{l.title}
                    <small>{!l.available ? `not in ${CITIES[city].name}` : on.includes(l.id) && (zoom < l.minzoom || zoom > l.maxzoom) ? (zoom < l.minzoom ? 'zoom in to see' : 'zoom out to see') : ''}</small>
                  </Menu.CheckboxItem>
                ))}
              </Menu.Popup></Menu.Positioner></Menu.Portal>
            </Menu.SubmenuRoot>
          )
        })}
        {shown.some((l) => !l.on) && <><hr /><Menu.Item onClick={reset}>Turn the added layers off</Menu.Item></>}
      </MenuBtn>
      <Seg label="Base map" value={base} onChange={onBase} options={BASE_VIEWS.map((b) => ({ id: b.id, label: b.label, title: b.hint }))} />
    </div>
  )
}

/** Zoom, north and tilt. */
export function MapNav() {
  const map = useWorld((s) => s.map), bearing = useWorld((s) => s.bearing), pitch = useWorld((s) => s.pitch)
  const ms = (n: number) => (reduced() ? 0 : n)
  return (
    <div className="mapctl">
      <IconBtn icon="plus" label="Zoom in" className="btn icon" onClick={() => map?.zoomIn()} />
      <IconBtn icon="minus" label="Zoom out" className="btn icon" onClick={() => map?.zoomOut()} />
      <Tip label="Face north"><button type="button" className="btn icon" aria-label={`Face north. The view faces ${Math.round(((bearing % 360) + 360) % 360)} degrees.`} onClick={() => map?.easeTo({ bearing: 0, duration: ms(400) })}>
        <span className="needle" style={{ rotate: `${-bearing}deg` }}><Icon name="north" size={14} /></span>
      </button></Tip>
      <IconBtn icon="cube" label={pitch > 5 ? 'Look straight down' : 'Tilt the view'} aria-pressed={pitch > 5} className="btn icon" onClick={() => map?.easeTo({ pitch: pitch > 5 ? 0 : 58, duration: ms(500) })} />
    </div>
  )
}

/** What is drawn, where each layer comes from and how old our copy is, and the credit for the ground itself. */
export function Legend({ layers, on, base, marks, drawn }: { layers: MapLayer[]; on: string[]; base: BaseView; marks: number; drawn: boolean }) {
  const close = useWorld((s) => s.zoom >= CLOSE_Z - 0.6), city3d = useWorld((s) => s.city3d), deep = useWorld((s) => s.zoom >= CLOSE_Z - 0.2)
  const shown = layers.filter((l) => on.includes(l.id) && l.available && l.shape !== 'readout')
  return (
    <p className="maplegend">
      {shown.map((l) => (
        <span key={l.id} title={l.note}>{swatch(l)}{l.title}
          {/* an area coloured by value: what each step of the ramp stands for, as the catalogue gives it */}
          {l.legend && <span className="stops">{l.legend.stops.map(([level, label]) => <span key={level}><i style={{ background: `var(--ramp-${Math.min(6, Math.max(1, level + 1))})` }} />{label}</span>)}{l.legend.unit && <span className="muted">{l.legend.unit}</span>}</span>}
          <span className="muted">{l.attribution || l.source}{dated(l) && `, ${dated(l)}`}</span>
        </span>
      ))}
      {marks > 0 && <span><i className="ringmark" />In this investigation ({marks})</span>}
      {drawn && <span><i className="pathmark" />Drawn by a tool</span>}
      <span className="muted">{close && base !== 'aerial' ? MAP_CREDIT.close : MAP_CREDIT[base]}{close && base === 'aerial' ? ` · ${MAP_CREDIT.close}` : ''}{deep && city3d.status !== 'idle' && city3d.status !== 'none' ? ` · 3D city mesh${city3d.capture ? `, flown ${city3d.capture}` : ''}` : ''}</span>
      {deep && city3d.status === 'loading' && <span className="muted" role="status">Loading the 3D city, {Math.round(city3d.progress * 100)}%</span>}
    </p>
  )
}

/** Conditions now, as the server passes them on from Open-Meteo. */
export function WeatherChip({ city, source }: { city: CityId; source?: MapLayer }) {
  const [got, setGot] = useState<{ city: CityId; w?: Weather; error?: string } | null>(null)
  useEffect(() => {
    let on = true
    const load = () => fetchWeather(city).then((w) => on && setGot({ city, w }), (e: Error) => on && setGot({ city, error: e.message }))
    void load()
    const t = setInterval(load, 600000)
    return () => { on = false; clearInterval(t) }
  }, [city])
  const w = got?.city === city ? got.w : undefined
  if (got?.city === city && got.error && !w) return <p className="mapread" role="status">The weather did not load. {got.error}</p>
  if (!w) return <p className="mapread" role="status"><span className="sk" style={{ width: 220 }} /></p>
  const n = (v: number | null, unit: string) => (v == null ? null : <><span className="num">{v}</span> {unit}</>)
  return (
    <p className="mapread" title={source?.note}>
      <b>{CITIES[city].name} now</b>
      {w.sky && <span>{w.sky}</span>}
      {w.temperature_c != null && <span>{n(w.temperature_c, '°C')}</span>}
      {w.wind_kmh != null && <span>wind {n(w.wind_kmh, 'km/h')}{w.wind_from_deg != null && <> from {n(w.wind_from_deg, '°')}</>}</span>}
      {w.rain_mm != null && <span>rain {n(w.rain_mm, 'mm')}</span>}
      <span className="muted">{w.source}, <span className="num">{w.time.slice(11)}</span> {w.timezone}</span>
    </p>
  )
}

export type SunAt = { date: string; minutes: number }
/** Today and the current ten minutes on a city's own clock. */
export function sunNow(city: CityId): SunAt {
  const p = Object.fromEntries(new Intl.DateTimeFormat('en-CA', { timeZone: ZONE[city], hourCycle: 'h23', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).formatToParts(new Date()).map((x) => [x.type, x.value]))
  return { date: `${p.year}-${p.month}-${p.day}`, minutes: Math.floor((Number(p.hour) * 60 + Number(p.minute)) / 10) * 10 }
}
export const sunInstant = (at: SunAt, city: CityId) => { const [y, m, d] = at.date.split('-').map(Number); return zonedInstant(y, m, d, at.minutes, ZONE[city]) }
const clock = (m: number) => `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`

/** The day and hour the shadows are cast for, and where the sun then stands over the middle of the map. */
export function SunBar({ city, value, onChange, source }: { city: CityId; value: SunAt; onChange: (v: SunAt) => void; source?: MapLayer }) {
  const map = useWorld((s) => s.map), mesh = useWorld((s) => s.mesh), ready = useWorld((s) => s.city3d.status === 'ready'), close = useWorld((s) => s.zoom >= CLOSE_Z - 0.2)
  useWorld((s) => Math.round(s.tick / 30)) // the readout follows the map, a few times a second at most
  const c = map?.getCenter() ?? { lat: CITIES[city].center[1], lng: CITIES[city].center[0] }
  const t = sunInstant(value, city), pos = sunPosition(t, c.lat, c.lng), day = sunDay(t, c.lat, c.lng)
  const hm = (d: Date | null) => (d ? new Intl.DateTimeFormat('en-GB', { timeZone: ZONE[city], hour: '2-digit', minute: '2-digit' }).format(d) : 'none')
  const [hours, setHours] = useState<{ key: string; text: string } | null>(null)
  const key = `${value.date}|${c.lat.toFixed(5)},${c.lng.toFixed(5)}`
  const measure = () => {
    if (!mesh || !day.rise || !day.set) return
    const r = mesh.sunlight(c.lng, c.lat, day.rise, day.set, (x) => sunPosition(x, c.lat, c.lng))
    setHours({ key, text: r ? `${r.hours.toFixed(1)} h of direct sun at the middle of the view, of ${((r.samples * 10) / 60).toFixed(1)} h the sun is up` : 'The 3D city has nothing under the middle of the view.' })
  }
  return (
    <div className="sunbar" role="group" aria-label="Sun and shadows" title={source?.note}>
      <Icon name="sun" size={14} />
      <input type="date" className="field" value={value.date} onChange={(e) => e.target.value && onChange({ ...value, date: e.target.value })} aria-label="Day" />
      <Slider.Root className="grow" value={value.minutes} min={0} max={1430} step={10} onValueChange={(n) => onChange({ ...value, minutes: n as number })} aria-label="Time of day">
        <Slider.Control className="slider"><Slider.Track className="track"><Slider.Indicator className="range" /><Slider.Thumb className="thumb" /></Slider.Track></Slider.Control>
      </Slider.Root>
      <span className="num">{clock(value.minutes)}</span>
      <span className="small">{pos.altitude > 0 ? <>sun <span className="num">{pos.altitude.toFixed(0)}°</span> up, to the <span className="num">{pos.azimuth.toFixed(0)}°</span></> : 'the sun is down'}</span>
      <span className="small muted">up <span className="num">{hm(day.rise)}</span> to <span className="num">{hm(day.set)}</span>, <span className="num">{day.hours.toFixed(1)}</span> h</span>
      {close && ready ? <button type="button" className="btn sm quiet" onClick={measure} title="Cast a ray to the sun every ten minutes of this day from the 3D city under the middle of the view">Sun hours here</button>
        : <span className="small muted">{close ? 'shadows appear when the 3D city has loaded' : 'zoom in for shadows on the 3D city'}</span>}
      {hours?.key === key && <span className="small" role="status">{hours.text}</span>}
    </div>
  )
}
