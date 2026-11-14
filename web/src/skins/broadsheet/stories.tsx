import { setQuery, useRoute, useWorkspace, type Panel } from '../../core/index.ts'
import { G } from './parts.tsx'

/* Which story the page is showing. A scan's stories are the panels about that scan; the city's are the panels about
   no single scan (a census, a query). The chosen one is in the link (`b_s`), the latest when none is chosen. */
export function useStories(): { story: Panel | null; stories: Panel[] } {
  const { path, sid, q } = useRoute()
  const panels = useWorkspace((s) => s.doc.panels)
  const stories = path === '/scan' ? panels.filter((p) => p.sid === sid) : path === '/map' ? panels.filter((p) => !p.sid) : []
  return { stories, story: stories.find((p) => p.id === q.get('b_s')) ?? stories.at(-1) ?? null }
}

/** The finding the page is on. A place in the building is the camera's; a place on the aerial photograph is in the link. */
export function useCurrent(): string | undefined {
  const { q } = useRoute()
  const cam = useWorkspace((s) => s.doc.camera?.finding)
  return (q.get('b_v') === 'air' ? q.get('f') : null) ?? cam ?? q.get('f') ?? undefined
}

/** Turn to another story on this page. */
export function readStory(id: string) {
  setQuery({ b_s: id, b_v: null }, false)
  window.scrollTo({ top: 0 })
}

/** The stories on this page, as a line of contents. */
export function Contents({ stories, story }: { stories: Panel[]; story: Panel | null }) {
  if (stories.length < 2) return null
  return (
    <nav className="contents" aria-label="On this page">
      {stories.map((p) => {
        const v = p.blocks.find((b) => b.type === 'VerdictHeader')
        return <button key={p.id} aria-current={p.id === story?.id || undefined} onClick={() => readStory(p.id)}>{v?.type === 'VerdictHeader' && <span data-s={v.status}><G s={v.status} /></span>}{p.title}</button>
      })}
    </nav>
  )
}
