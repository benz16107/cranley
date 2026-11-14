/* The parts of the server link that are pure, so they run under `node --test`: which response may be shown, one
   request shared by callers that ask at the same moment, and writes sent one after another. server.ts uses them. */

/** Which responses may still be shown. A response belongs to the workspace generation it was asked in (start-over
    begins a new one) and, within a generation, never replaces a document with an older one: `seq` is the length of
    the server's log, which only grows. */
export function gate() {
  let gen = 0, seq = -1, older = 0
  return {
    /** The generation a request starts in; hand it back to `take` with the response. */
    now: () => gen,
    /** Start over: every response still in flight belongs to the workspace left behind. */
    next: () => { seq = -1; older = 0; return ++gen },
    /** May a response asked in generation `asked`, at log length `at`, be shown? Showing it moves the mark. */
    take: (asked: number, at?: number) => {
      if (asked !== gen) return false
      // One late response is late. Three in a row all shorter than the mark means the server's log was replaced
      // (a restored store): believe the server again, or the page would show the old document until a reload.
      if (at != null && at < seq && ++older < 3) return false
      older = 0
      if (at != null) seq = at
      return true
    },
    /** The log length of the document on screen, or -1 before any. */
    at: () => seq,
  }
}

/** One call in flight at a time: callers that ask while it runs share its promise (two ops made before any workspace
    exists must not make two workspaces). */
export function single<T>(fn: () => Promise<T>): () => Promise<T> {
  let running: Promise<T> | null = null
  return () => (running ??= fn().finally(() => { running = null }))
}

/** Writes one after another, in the order they were made; a failed one does not hold up the next. `idle()` resolves
    when every write made so far has finished, so a turn can start after the answers it will read have landed. */
export function serial() {
  let tail: Promise<unknown> = Promise.resolve()
  return {
    run: <T>(fn: () => Promise<T>): Promise<T> => { const p = tail.then(fn, fn); tail = p.catch(() => {}); return p },
    idle: (): Promise<unknown> => tail,
  }
}
