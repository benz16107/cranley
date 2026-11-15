import { useState } from 'react'
import { orthoImage } from '../../../core/index.ts'
import { Icon } from '../design/ui.tsx'

/** A building's aerial photo: the 70 m patch the server keeps on disk, the same one Explore shows. One small image
    per card, never a 3D view. A picture that does not load leaves a building's mark in its place. */
export function Aerial({ lat, lon }: { lat: number; lon: number }) {
  const [gone, setGone] = useState(false)
  return <span className="aerial">{gone ? <Icon name="building" size={16} /> : <img src={orthoImage(lat, lon, 70, 256)} alt="" loading="lazy" width={256} height={256} onError={() => setGone(true)} />}</span>
}
