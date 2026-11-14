/* Things the product has to tell the person that are not part of the workspace: the server did not answer, a tool
   needs an answer first. Core says them; each skin decides how they look (a toast, a subtitle, a margin note). */
export type Notice = { kind: 'info' | 'error'; title: string; description?: string }
type Listener = (n: Notice) => void

const listeners = new Set<Listener>()
let waiting: Notice[] = [] // said before any skin was listening
const say = (n: Notice) => { if (listeners.size) listeners.forEach((l) => l(n)); else waiting = [...waiting.slice(-4), n] }

/** Hear every notice. Returns the function that stops listening. */
export function onNotice(fn: Listener): () => void {
  listeners.add(fn)
  for (const n of waiting.splice(0)) fn(n)
  return () => { listeners.delete(fn) }
}
export const notify = Object.assign(
  (title: string, o?: { description?: string }) => say({ kind: 'info', title, description: o?.description }),
  { error: (title: string, o?: { description?: string }) => say({ kind: 'error', title, description: o?.description }) },
)
