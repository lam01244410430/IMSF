/**
 * `LanguageProvider` — the component half of the i18n module (see
 * `./i18n.ts` for the dictionaries). Kept in its own file so this file
 * exports only the component (oxlint only-export-components).
 */
import { useEffect, useMemo, useState, type ReactNode } from 'react'
import {
  DICTS,
  LANGUAGE_STORAGE_KEY,
  LanguageContext,
  getStoredLanguage,
  type Language,
  type LanguageContextValue,
} from './i18n'

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Language>(() => getStoredLanguage())

  const setLanguage = (next: Language) => {
    setLangState(next)
    try {
      window.localStorage.setItem(LANGUAGE_STORAGE_KEY, next)
    } catch {
      // storage unavailable — the choice lives for this session only.
    }
  }

  // Keep the document language in sync so screen readers and the
  // browser use the right language for the current copy.
  useEffect(() => {
    document.documentElement.lang = lang
  }, [lang])

  const value = useMemo<LanguageContextValue>(
    () => ({ lang, setLanguage, t: DICTS[lang] }),
    [lang],
  )
  return (
    <LanguageContext.Provider value={value}>
      {children}
    </LanguageContext.Provider>
  )
}
