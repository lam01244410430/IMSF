/**
 * Theme (Dashboard Phase A, D2) — the context half of the theme module
 * (the `ThemeProvider` component lives in `./ThemeProvider.tsx`).
 *
 * - Two DaisyUI themes: `imsf-swiss` (light, default) and
 *   `imsf-swiss-dark`. The stored VALUE ('light' | 'dark') and the
 *   theme NAME are different strings — the mapping lives here, in
 *   exactly one place.
 * - The choice is stored in localStorage (`imsf.theme`) and wins over
 *   everything. `prefers-color-scheme` is NEVER read — no matchMedia,
 *   no prefersdark: true, no `@media (prefers-color-scheme: dark)`
 *   anywhere (D2: default light, choice overrides system).
 * - No stored value, or an invalid stored value, or storage
 *   unavailable → `light` (same defensive pattern as
 *   `getStoredLanguage()` in `./i18n.ts`).
 */
import { createContext, useContext } from 'react'

export type Theme = 'light' | 'dark'

export const THEME_STORAGE_KEY = 'imsf.theme'

export const THEME_NAMES: Record<Theme, string> = {
  light: 'imsf-swiss',
  dark: 'imsf-swiss-dark',
}

function isTheme(value: string): value is Theme {
  return value === 'light' || value === 'dark'
}

export function getStoredTheme(): Theme {
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY)
    if (stored && isTheme(stored)) return stored
  } catch {
    // storage unavailable — fall through to the default.
  }
  return 'light'
}

/** Apply a theme by setting `data-theme` on `<html>` (DaisyUI v5). */
export function applyTheme(theme: Theme): void {
  document.documentElement.dataset.theme = THEME_NAMES[theme]
}

export interface ThemeContextValue {
  theme: Theme
  setTheme: (theme: Theme) => void
}

export const ThemeContext = createContext<ThemeContextValue>({
  theme: 'light',
  setTheme: () => undefined,
})

export function useTheme(): ThemeContextValue {
  return useContext(ThemeContext)
}
