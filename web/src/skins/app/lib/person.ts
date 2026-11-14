import { create } from 'zustand'
import { toast } from 'sonner'
import { isLive, useCatalog, useWorkspace, type Doc } from '../../../core/index.ts'
import { sync } from '../../../core/server.ts'

/* What Cranley knows about the person across investigations, where the open investigation used it, and feedback on
   a check. The server works all of it out (server/threshold/agent/profile.py); nothing here computes a number.

   This file stands in for a core client, as lib/pending.ts does: a look may not fetch, and core does not export
   these yet. The requests that replace it: fetchPerson(profile, workspace), fetchBecause(workspace),
   sendFeedback(workspace, finding, verdict), the profile id, and `sync` from core/index. */

export type Origin = { workspace: string; investigation: string; at: number; how: 'answer' | 'edit' | 'removed' | 'feedback' }
export type Fact = {
  key: string; group: 'about' | 'matters'; label: string; value: unknown; shown: string; unit: string | null
  origin: Origin | null; why: string; said: string; at: number | null
  edit: { type: 'number' | 'integer' | 'string'; min: number | null; max: number | null; options: string[] | null } | null
}
export type Person = {
  profile: string; who: { persona: string; title: string; said: string } | null; facts: Fact[]
  /** Corrections that belong to one building (a room's name, a rejected check): counted, listed in that investigation. */
  on_buildings: number; investigations: number
  sessions: { workspace: string; created: number; investigation: string }[]
  /** One row per measure, one value per investigation in order. Empty until there are two. */
  adapted: { id: string; label: string; values: (number | null)[] }[]
}
export type Note = {
  kind: 'input' | 'not_asked' | 'left_out' | 'kept_back' | 'first'; key: string; text: string; why: string; origin: Origin | null
  runs?: string[]; tools?: string[]; tool?: string; findings?: string[]; count?: number
  /** For an input: the profile brought it (false: said in this investigation). */
  carried?: boolean
}

type State = { person: Person | null; notes: Note[]; open: boolean; loading: boolean }
export const usePerson = create<State>(() => ({ person: null, notes: [], open: false, loading: false }))

const profile = () => { try { return localStorage.getItem('threshold.profile') } catch { return null } }
const get = <T,>(url: string): Promise<T | null> => fetch(url).then((r) => (r.ok ? (r.json() as Promise<T>) : null), () => null)
const wsId = () => { const id = useWorkspace.getState().doc.id; return id.startsWith('ws_') ? id : null }

let asked = 0
/** Read the person again. `full` also measures each investigation, which the page needs and a chip does not. */
export async function loadPerson(full = usePerson.getState().open) {
  const p = profile(), my = ++asked
  if (!p || !isLive() || useCatalog.getState().shared) return
  if (full) usePerson.setState({ loading: true })
  const ws = wsId()
  const person = await get<Person>(`/api/person/${encodeURIComponent(p)}?sessions=${full}${ws ? `&workspace=${encodeURIComponent(ws)}` : ''}`)
  if (my !== asked) return
  // a light read keeps the measured rows of the full one before it
  const old = usePerson.getState().person
  usePerson.setState({ person: person && !full && old ? { ...person, sessions: old.sessions, adapted: old.adapted } : person, loading: false })
}
async function loadNotes() {
  const ws = wsId()
  if (!ws || !isLive() || useCatalog.getState().shared) { usePerson.setState({ notes: [] }); return }
  const r = await get<{ notes: Note[] }>(`/api/workspace/${encodeURIComponent(ws)}/because`)
  if (ws === wsId()) usePerson.setState({ notes: r?.notes ?? [] })
}
export const openKnows = (open = true) => { usePerson.setState({ open }); if (open) void loadPerson(true) }

// What was learned or used changes when the document does: a run ended, a setting moved, a check was marked.
const digest = (d: Doc) => [d.id, d.prefs.map((p) => `${p.key}=${String(p.value)}`).join(','), d.runs.map((r) => r.status[0]).join(''), d.findings.length, d.tools.length, d.questions.length].join('|')
let seen = '', timer: ReturnType<typeof setTimeout> | undefined
useWorkspace.subscribe(({ doc }) => {
  const key = digest(doc)
  if (key === seen) return
  seen = key
  clearTimeout(timer)
  timer = setTimeout(() => { void loadNotes(); void loadPerson() }, 350)
})
useCatalog.subscribe((s, was) => { if (s.live && !was.live) { void loadNotes(); void loadPerson() } })

/** Mark a check useful or not relevant. "Not relevant" also hides the others of its kind, here and next time; the
    toast says how many and takes it all back. */
export async function mark(finding: string, verdict: 'useful' | 'not_relevant') {
  const ws = wsId()
  if (!ws) return
  const post = (path: string, body: unknown) => fetch(`/api/workspace/${encodeURIComponent(ws)}/${path}`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) })
  const r = await post('feedback', { finding, verdict }).catch(() => null)
  if (!r?.ok) { toast.error('That was not saved.', { description: 'The server did not take it. Try again.' }); return }
  const out = (await r.json()) as { undo: number; hidden: number; kind: string }
  await sync()
  const undo = { label: 'Undo', onClick: () => void post('undo', { seq: out.undo }).then(() => sync()) }
  if (verdict === 'useful') toast(`“${out.kind}” checks will be listed first.`, { description: 'Kept in what Cranley knows about you.', action: undo })
  else toast(out.hidden ? `Hidden, with ${out.hidden} similar ${out.hidden === 1 ? 'check' : 'checks'}.` : 'Hidden.', { description: `“${out.kind}” checks stay out of your later investigations too.`, action: undo })
}

/** A date as a person says it: "14 Nov". */
export const day = (at: number) => new Date(at * 1000).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
