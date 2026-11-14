import { useEffect, useState } from 'react'
import { create } from 'zustand'

export type Theme = 'system' | 'light' | 'dark'
const KEY = 'threshold.theme' // the same key the Sheet look uses, so the choice follows the person between looks
const stored = (): Theme => { try { return (localStorage.getItem(KEY) as Theme) || 'system' } catch { return 'system' } }
const apply = (t: Theme) => { if (t === 'system') delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme = t }
apply(stored())

export const useTheme = create<{ theme: Theme; setTheme: (t: Theme) => void }>((set) => ({
  theme: stored(),
  setTheme: (theme) => { apply(theme); try { localStorage.setItem(KEY, theme) } catch { /* not remembered */ } set({ theme }) },
}))

/** The scheme actually showing, for canvases (the map, the 3D scene) that are drawn from the tokens. */
export function useScheme(): 'light' | 'dark' {
  const theme = useTheme((s) => s.theme)
  const [sys, setSys] = useState(() => window.matchMedia('(prefers-color-scheme: dark)').matches)
  useEffect(() => {
    const m = window.matchMedia('(prefers-color-scheme: dark)')
    const on = () => setSys(m.matches)
    m.addEventListener('change', on)
    return () => m.removeEventListener('change', on)
  }, [])
  return theme === 'system' ? (sys ? 'dark' : 'light') : theme
}
