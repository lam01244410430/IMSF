/**
 * Language switcher (reform plan §4.1): a native <select> showing the
 * language in its own name (中文 / Tiếng Việt / English). Native select
 * = keyboard accessible with no custom dropdown code. The choice is
 * stored in localStorage by the i18n provider; switching re-renders
 * the same route.
 */
import { LANGUAGES, useLanguage, type Language } from '../lib/i18n'

export function LanguageSwitcher({
  id,
  className,
}: {
  id?: string
  className?: string
}) {
  const { lang, setLanguage, t } = useLanguage()
  return (
    <span className={className ?? 'lang-switcher'}>
      <select
        id={id}
        aria-label={t['lang.label']}
        value={lang}
        onChange={(event) => {
          setLanguage(event.target.value as Language)
        }}
      >
        {LANGUAGES.map((option) => (
          <option key={option.code} value={option.code}>
            {option.label}
          </option>
        ))}
      </select>
    </span>
  )
}
