/**
 * `ThemeProvider` — the component half of the theme module (see
 * `./theme.ts` for the storage key, mapping and context). Kept in its
 * own file so this file exports only the component (oxlint
 * only-export-components).
 *
 * Mirrors `LanguageProvider`: lazy init from storage, `setTheme`
 * writes the key + sets `document.documentElement.dataset.theme`.
 * The pre-paint inline script in `web/index.html` already sets the
 * attribute from the same key before first paint; the layout effect
 * below keeps it in sync if storage changed elsewhere.
 */
import { useLayoutEffect, useMemo, useState, type ReactNode } from 'react'
import {
  THEME_STORAGE_KEY,
  ThemeContext,
  applyTheme,
  getStoredTheme,
  type Theme,
  type ThemeContextValue,
} from './theme'

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(() => getStoredTheme())

  const setTheme = (next: Theme) => {
    setThemeState(next)
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, next)
    } catch {
      // storage unavailable — the choice lives for this session only.
    }
    applyTheme(next)
  }

  useLayoutEffect(() => {
    applyTheme(theme)
  }, [theme])

  const value = useMemo<ThemeContextValue>(
    () => ({ theme, setTheme }),
    [theme],
  )
  return (
    <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
  )
}
