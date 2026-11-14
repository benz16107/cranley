import { useEffect, useState } from 'react'
import { create } from 'zustand'

/* What is open in the shell. The run panel and the narrow sidebar are remembered per browser. */
const get = (k: string, d: boolean) => { try { const v = localStorage.getItem(`threshold.app.${k}`); return v == null ? d : v === '1' } catch { return d } }
const put = (k: string, v: boolean) => { try { localStorage.setItem(`threshold.app.${k}`, v ? '1' : '0') } catch { /* not remembered */ } }

type Ui = {
  /** The agent's run panel is open. */
  run: boolean
  /** The sidebar is narrowed to icons. */
  rail: boolean
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
  setRun: (on: boolean) => void
  setRail: (on: boolean) => void
}
export const useUi = create<Ui>((set) => ({
  // on a phone the agent panel is a drawer over the page: it opens when asked for, never because it was left open on a desk
  run: get('run', false) && !window.matchMedia('(max-width: 760px)').matches, rail: get('rail', false), menu: false, keys: false, panel: null, start: null, nav: false,
  setRun: (run) => { put('run', run); set({ run }) },
  setRail: (rail) => { put('rail', rail); set({ rail }) },
}))

export function useIsPhone() {
  const [phone, setPhone] = useState(() => window.matchMedia('(max-width: 760px)').matches)
  useEffect(() => { const m = window.matchMedia('(max-width: 760px)'); const on = () => setPhone(m.matches); m.addEventListener('change', on); return () => m.removeEventListener('change', on) }, [])
  return phone
}
