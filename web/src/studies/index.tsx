// Design studies: three directions, each shown on the same three moments of one real investigation.
//   /study                 the index
//   /study/<a|b|c>/<door|city|building>
// Arrow keys move between the nine screens. The shell is not involved.
import { lazy, Suspense, useEffect } from 'react'
import './studies.css'

export type Moment = 'door' | 'city' | 'building'
const MOMENTS: Moment[] = ['door', 'city', 'building']
const DIRECTIONS = {
  a: { name: 'Overflight', idea: 'One camera shot from the city to the doorway. The agent speaks in subtitles.', view: lazy(() => import('./a/A.tsx')) },
  b: { name: 'Broadsheet', idea: 'The agent writes a page about the building. The verdict is the headline.', view: lazy(() => import('./b/B.tsx')) },
  c: { name: 'Maquette', idea: 'A model on a cutting mat. Findings are tags tied to the thing they measure.', view: lazy(() => import('./c/C.tsx')) },
} as const
type Dir = keyof typeof DIRECTIONS
const ORDER = (Object.keys(DIRECTIONS) as Dir[]).flatMap((d) => MOMENTS.map((m) => `/study/${d}/${m}`))

export function Studies() {
  const [, , d, m] = window.location.pathname.split('/')
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement).closest('input, textarea') || (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft')) return
      const i = ORDER.indexOf(window.location.pathname), next = ORDER[(i + (e.key === 'ArrowRight' ? 1 : ORDER.length - 1)) % ORDER.length]
      window.location.assign(next)
    }
    window.addEventListener('keydown', key)
    return () => window.removeEventListener('keydown', key)
  }, [])
  const dir = DIRECTIONS[d as Dir]
  if (!dir || !MOMENTS.includes(m as Moment)) return <Index />
  const View = dir.view
  return <Suspense fallback={null}><View moment={m as Moment} /></Suspense>
}

function Index() {
  return (
    <main className="study-index">
      <h1>Design studies</h1>
      <p>Three directions on the same three moments. Arrow keys step through all nine.</p>
      {(Object.keys(DIRECTIONS) as Dir[]).map((d) => (
        <section key={d}>
          <h2>{d.toUpperCase()}. {DIRECTIONS[d].name}</h2>
          <p>{DIRECTIONS[d].idea}</p>
          <nav>{MOMENTS.map((m) => <a key={m} href={`/study/${d}/${m}`}>{m === 'door' ? 'Front door' : m === 'city' ? 'City, agent at work' : 'Building, with a result'}</a>)}</nav>
        </section>
      ))}
    </main>
  )
}
