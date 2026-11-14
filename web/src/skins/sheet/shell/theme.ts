import { useEffect, useState } from 'react'

export type Theme = 'system' | 'light' | 'dark'
const KEY = 'threshold.theme'

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(() => (localStorage.getItem(KEY) as Theme) || 'system')
  useEffect(() => {
    if (theme === 'system') delete document.documentElement.dataset.theme
    else document.documentElement.dataset.theme = theme
    localStorage.setItem(KEY, theme)
  }, [theme])
  return { theme, setTheme, cycle: () => setTheme(theme === 'system' ? 'light' : theme === 'light' ? 'dark' : 'system') }
}

/** The scheme actually showing, for canvases (the map) that have to be redrawn from the tokens. */
export function useScheme(theme: Theme): 'light' | 'dark' {
  const [sys, setSys] = useState(() => window.matchMedia('(prefers-color-scheme: dark)').matches)
  useEffect(() => {
    const m = window.matchMedia('(prefers-color-scheme: dark)')
    const on = () => setSys(m.matches)
    m.addEventListener('change', on)
    return () => m.removeEventListener('change', on)
  }, [])
  return theme === 'system' ? (sys ? 'dark' : 'light') : theme
}
