import { create } from 'zustand'
import { apply, emptyDoc, inverse } from './reducer.ts'
import type { Doc, Op, OpInput } from './types.ts'

type State = {
  doc: Doc
  undoStack: Op[]
  /** When on, the view goes where the agent looks. The user can take the camera back at any time. */
  follow: boolean
  /** The agent link (server stream or fixtures) hears every user op here. */
  onUserOp: ((op: Op, doc: Doc) => void) | null
  dispatch: (op: Op) => void
  undo: () => void
  reset: (id?: string) => void
  setFollow: (on: boolean) => void
}

export const useWorkspace = create<State>((set, get) => ({
  doc: emptyDoc(),
  undoStack: [],
  follow: true,
  onUserOp: null,
  dispatch: (op) => {
    const before = get().doc
    const stamped = { ...op, at: op.at ?? Date.now() }
    const doc = apply(before, stamped)
    if (doc === before) return
    const inv = op.by === 'user' ? inverse(before, stamped) : null
    set({ doc, undoStack: inv ? [...get().undoStack, inv] : get().undoStack })
    if (op.by === 'user') get().onUserOp?.(stamped, doc)
  },
  undo: () => {
    const stack = get().undoStack
    const inv = stack.at(-1)
    if (!inv) return
    const doc = apply(get().doc, { ...inv, at: Date.now() })
    set({ doc, undoStack: stack.slice(0, -1) })
    get().onUserOp?.(inv, doc)
  },
  reset: (id) => set({ doc: emptyDoc(id), undoStack: [] }),
  setFollow: (follow) => set({ follow }),
}))

export const dispatch = (op: Op) => useWorkspace.getState().dispatch(op)
export const userOp = (op: OpInput) => dispatch({ ...op, by: 'user' } as Op)
