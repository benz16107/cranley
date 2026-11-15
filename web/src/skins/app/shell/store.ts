import { useEffect, useMemo, useState } from 'react'
import { create } from 'zustand'
import { useBuildings } from '../../../core/index.ts'
import { nameIds } from '../lib/names.ts'

/* What is open in the shell. The run panel and the narrow sidebar are remembered per browser. */
const kept = (k: string, d: boolean) => { try { const v = localStorage.getItem(`threshold.app.${k}`); return v == null ? d : v === '1' } catch { return d } }
const put = (k: string, v: boolean) => { try { localStorage.setItem(`threshold.app.${k}`, v ? '1' : '0') } catch { /* not remembered */ } }

type Ui = {
  /** The agent's run panel is open. */
  run: boolean
  /** The sidebar is narrowed to icons. */
  rail: boolean
  /** The sidebar is hidden altogether. Shown again it is full or icons, as `rail` says: three states. */
  hidden: boolean
  /** The sidebar is sliding in or out after a press of its button; null at rest. */
  sliding: 'in' | 'out' | null
  /** The command menu: everything, or only tools to add. */
  menu: false | 'all' | 'tools'
  /** The shortcut list. */
  keys: boolean
  /** A result opened over the page: its panel id. */
  panel: string | null
  /** The form that starts a tool by hand: which tool, and the scan to run on when one is in view. */
  start: { tool: string; sid: string | null } | null
  /** Phone: the navigation drawer. */
  nav: boolean
  /** The guided first run: asking who you are, narrating the agent's work, showing where it ended; null when it is not on. */
  first: null | 'ask' | 'watch' | 'end'
  setRun: (on: boolean) => void
  setRail: (on: boolean) => void
  setHidden: (on: boolean) => void
  /** Show or hide the sidebar. `slide`: it was a press with a pointer, so the width travels; from the keyboard, with
      reduced motion, or pressed again mid-way, it is there or gone at once. */
  toggleSide: (slide?: boolean) => void
}
const SLIDE = 200 // --dur-3, the look's time for a drawer; leaving takes 80% of it
let slid: ReturnType<typeof setTimeout> | undefined
export const useUi = create<Ui>((set, get) => ({
  // on a phone the agent panel is a drawer over the page: it opens when asked for, never because it was left open on a desk
  run: kept('run', false) && !window.matchMedia('(max-width: 760px)').matches, rail: kept('rail', false), hidden: kept('hidden', false), sliding: null, menu: false, keys: false, panel: null, start: null, nav: false, first: null,
  setRun: (run) => { put('run', run); set({ run }) },
  setRail: (rail) => { put('rail', rail); set({ rail }) },
  setHidden: (hidden) => { clearTimeout(slid); put('hidden', hidden); set({ hidden, sliding: null }) },
  toggleSide: (slide = false) => {
    const { hidden, sliding, setHidden } = get()
    clearTimeout(slid)
    if (!slide || sliding || window.matchMedia('(prefers-reduced-motion: reduce)').matches) { setHidden(!hidden); return }
    if (hidden) { put('hidden', false); set({ hidden: false, sliding: 'in' }); slid = setTimeout(() => set({ sliding: null }), SLIDE) }
    else { set({ sliding: 'out' }); slid = setTimeout(() => setHidden(true), SLIDE * 0.8) }
  },
}))

/** A press of the button that hides or shows the sidebar. With a pointer its width travels. From the keyboard (a
    click with no pointer has detail 0) it does not, and the focus goes to the button that undoes it, since the one
    that was pressed is gone. */
export function pressSide(e: { detail: number }) {
  const byKey = e.detail === 0
  useUi.getState().toggleSide(!byKey)
  if (byKey) requestAnimationFrame(() => document.querySelector<HTMLElement>('[data-side-toggle]')?.focus())
}

export function useIsPhone() {
  const [phone, setPhone] = useState(() => window.matchMedia('(max-width: 760px)').matches)
  useEffect(() => { const m = window.matchMedia('(max-width: 760px)'); const on = () => setPhone(m.matches); m.addEventListener('change', on); return () => m.removeEventListener('change', on) }, [])
  return phone
}

/** Scan and property ids put in words (lib/names.ts), from the building list. */
export function useNames() {
  const all = useBuildings((s) => s.all)
  return useMemo(() => nameIds(all), [all])
}
