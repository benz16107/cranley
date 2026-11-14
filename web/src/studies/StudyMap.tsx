// One map for every study: the shell's basemap style with a study's own palette and camera, deck.gl layers on top,
// and React nodes pinned to places. The shell's CityMap is left alone.
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { MapLibreOverlay } from '@deck.gl/maplibre'
import type { Layer } from 'deck.gl'
import { Map as MapLibre, Marker } from '../core/maplibre.ts'
import { mapStyle, type MapPalette } from '../core/basemap.ts'

export type Pin = { key: string; lon: number; lat: number; node: ReactNode; anchor?: 'bottom' | 'center' | 'bottom-left' | 'left' }
export type Camera = { center: [number, number]; zoom: number; pitch?: number; bearing?: number }
type Props = {
  palette: MapPalette; camera: Camera; layers?: Layer[]; pins?: Pin[]; className?: string
  blocks?: string       // draw the basemap's buildings as extruded blocks in this colour
  names?: boolean       // place and street names
  onView?: (metresPerPx: number) => void
}

export function StudyMap({ palette, camera, layers = [], pins = [], blocks, names = true, className, onView }: Props) {
  const el = useRef<HTMLDivElement>(null), overlay = useRef<MapLibreOverlay | null>(null)
  const [map, setMap] = useState<MapLibre | null>(null)
  useEffect(() => {
    const style = mapStyle(palette)
    if (!names) style.layers = style.layers.filter((l) => l.type !== 'symbol')
    if (blocks) style.layers.splice(style.layers.findIndex((l) => l.id === 'building'), 2, {
      id: 'blocks', type: 'fill-extrusion', source: 'omt', 'source-layer': 'building', minzoom: 12,
      paint: { 'fill-extrusion-color': blocks, 'fill-extrusion-height': ['coalesce', ['get', 'render_height'], 5], 'fill-extrusion-opacity': 0.92 },
    })
    const m = new MapLibre({ container: el.current!, style, attributionControl: false, maxPitch: 70, ...camera })
    overlay.current = new MapLibreOverlay({ interleaved: false, layers: [] })
    m.addControl(overlay.current as never)
    const view = () => onView?.((40075016.686 * Math.cos((m.getCenter().lat * Math.PI) / 180)) / (512 * 2 ** m.getZoom()))
    m.on('load', () => { setMap(m); view() })
    m.on('zoomend', view)
    return () => { m.remove(); setMap(null) }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { overlay.current?.setProps({ layers }) }, [layers, map])
  return <div ref={el} className={className}>{map && pins.map((p) => <MapPin key={p.key} map={map} pin={p} />)}</div>
}

function MapPin({ map, pin }: { map: MapLibre; pin: Pin }) {
  const [host] = useState(() => document.createElement('div'))
  useEffect(() => {
    const mk = new Marker({ element: host, anchor: pin.anchor ?? 'bottom' }).setLngLat([pin.lon, pin.lat]).addTo(map)
    return () => { mk.remove() }
  }, [map, host, pin.lon, pin.lat, pin.anchor])
  return createPortal(pin.node, host)
}
