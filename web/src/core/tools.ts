import { useMemo } from 'react'
import { TOOLS } from './fixtures/catalog.ts'
import { useCatalog } from './server.ts'

/** A tool a person can add to the dock. `code` is a two-letter key when the fixtures give one. */
export type CatalogTool = { id: string; title: string; code?: string; summary?: string; coverage?: string; planned: boolean }

/** Every tool there is to add: the server's list when it answers (planned ones last), else the fixture list. */
export function useToolCatalog(): CatalogTool[] {
  const served = useCatalog((s) => s.tools)
  return useMemo(() => (served.length
    ? [...served].sort((a, b) => Number(a.status === 'planned') - Number(b.status === 'planned'))
      .map((m) => ({ id: m.id, title: m.title, code: undefined, summary: m.status === 'planned' ? `Planned, not built yet. ${m.summary}` : m.summary, planned: m.status === 'planned' }))
    : Object.values(TOOLS).map((t) => ({ ...t, planned: false }))), [served])
}
