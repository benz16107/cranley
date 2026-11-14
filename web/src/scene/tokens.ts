import type { Palette, RGB } from './model.ts'

export interface Tokens extends Palette { stage: RGB; paper: RGB; ink: RGB; glass: RGB; water: RGB }

const FALLBACK: Record<string, string> = {
  stage: '#e7e4dc', paper: '#f7f4ed', ink: '#20242b', accent: '#2447d6', glass: '#cdd8dc', water: '#3a7d92',
  'ramp-lo': '#e4e9f5', 'ramp-hi': '#1c2e84', pass: '#1a7f50', warn: '#d08a0c', fail: '#c93426', unknown: '#6f757d',
}

export const hex = (c: RGB) => '#' + c.map((v) => Math.round(v * 255).toString(16).padStart(2, '0')).join('')

/** Reads the --scene-* colours from tokens.css as sRGB triples in 0..1, for shaders and SVG fills. */
export function readTokens(el: Element): Tokens {
  const css = getComputedStyle(el)
  const get = (name: string): RGB => {
    const v = css.getPropertyValue(`--scene-${name}`).trim()
    const h = /^#[0-9a-f]{6}$/i.test(v) ? v : FALLBACK[name]
    return [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16) / 255) as RGB
  }
  return {
    stage: get('stage'), paper: get('paper'), ink: get('ink'), accent: get('accent'), glass: get('glass'), water: get('water'),
    rampLo: get('ramp-lo'), rampHi: get('ramp-hi'), pass: get('pass'), warn: get('warn'), fail: get('fail'), unknown: get('unknown'),
  }
}
