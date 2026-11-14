import { useEffect } from 'react'
import { LOOKS, useBuildings, useRoute, useWorkspace, type LookId } from '../core/index.ts'

/* What an empty look shows until its workstream builds it: proof that the look is wired to the product (the place
   from the URL, the building list, the workspace), and nothing a real look should keep. Replace the whole Root. */
export function Placeholder({ look }: { look: LookId }) {
  const route = useRoute()
  const buildings = useBuildings((s) => s.all.length), state = useBuildings((s) => s.state), load = useBuildings((s) => s.load)
  const doc = useWorkspace((s) => s.doc)
  useEffect(load, [load])
  const name = LOOKS.find((l) => l.id === look)!.name
  return (
    <main style={{ font: '15px/1.5 system-ui, sans-serif', maxWidth: 560, margin: '18vh auto', padding: 24 }}>
      <h1 style={{ font: '600 28px/1.2 system-ui, sans-serif', margin: '0 0 12px' }}>{name}</h1>
      <p>This look has not been built yet. It is wired to the product:</p>
      <ul>
        <li>Place: <code>{route.path}{route.sid ? `/${route.sid}` : ''}</code></li>
        <li>Buildings: {state === 'ready' ? buildings.toLocaleString('en-US') : state}</li>
        <li>Workspace: {doc.brief ? `“${doc.brief.text}”` : 'no brief yet'}, {doc.tools.length} tools, {doc.panels.length} panels</li>
      </ul>
      <p>Start in <code>web/src/core/README.md</code>.</p>
    </main>
  )
}
