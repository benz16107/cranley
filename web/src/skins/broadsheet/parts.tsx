import { useEffect, useState, type ReactNode } from 'react'
import type { Source, Status } from '../../core/index.ts'
import { sourceLine, STATUS_WORD, num, unitOf } from './words.ts'

/* The small parts every page of the look is set from. */

export const G = ({ s }: { s: Status }) => <i className="g" data-s={s} aria-hidden="true" />
/** A status as a glyph and a word. Never colour alone. */
export const Stat = ({ s, children }: { s: Status; children?: ReactNode }) => <span className="stat" data-s={s}><G s={s} />{children ?? STATUS_WORD[s]}</span>
/** The marker: the yellow stroke behind the number that matters. */
export const Mark = ({ children }: { children: ReactNode }) => <mark className="mark">{children}</mark>
/** Where a number came from and how sure it is. */
export const Src = ({ source, className = 'src' }: { source: Source; className?: string }) => <span className={className} title={source.note}>{sourceLine(source)}</span>
/** A figure caption: its number, then what it shows. */
export const Fig = ({ n, children }: { n: number | string; children: ReactNode }) => <figcaption className="fig"><b>Fig. {n}</b>{children}</figcaption>
/** A measured value with its unit set smaller. */
export const Val = ({ v, unit }: { v: number | null; unit?: string }) => (v == null ? <span className="nil" role="img" aria-label="Not measured" /> : <>{num(v)}{unitOf(unit) && <small>{unitOf(unit)}</small>}</>)

/** A long list shows its first lines and says how many more there are. */
export function Fold<T>({ items, show = 6, noun, children }: { items: T[]; show?: number; noun: string; children: (shown: T[]) => ReactNode }) {
  const [all, setAll] = useState(false)
  return <>{children(all ? items : items.slice(0, show))}{items.length > show && <button className="link more" onClick={() => setAll(!all)}>{all ? 'Show fewer' : `${items.length - show} more ${noun}`}</button>}</>
}

export const reduced = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches
export function useMedia(query: string) {
  const [on, setOn] = useState(() => window.matchMedia(query).matches)
  useEffect(() => { const m = window.matchMedia(query); const f = () => setOn(m.matches); m.addEventListener('change', f); return () => m.removeEventListener('change', f) }, [query])
  return on
}
