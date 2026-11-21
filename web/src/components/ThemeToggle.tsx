/**
 * Theme toggle (Dashboard Phase A, D2) — the header control for
 * switching light/dark. Hand-drawn inline SVG icons (sun / moon,
 * 20px, stroke 1.5, currentColor), same stroke language as
 * `NotificationsBell` and `Icon.tsx`. No unicode glyph as the icon.
 *
 * Shows the MOON in light mode (action: switch to dark) and the SUN
 * in dark mode (action: switch to light). The aria-label (and the
 * hover tooltip) names the action, from i18n `theme.switchToDark` /
 * `theme.switchToLight`.
 */
import { useLanguage } from '../lib/i18n'
import { useTheme } from '../lib/theme'

function MoonIcon() {
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d="M16.5 12.8A7 7 0 1 1 7.2 3.5a5.5 5.5 0 0 0 9.3 9.3Z" />
    </svg>
  )
}

function SunIcon() {
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      aria-hidden="true"
      focusable="false"
    >
      <circle cx="10" cy="10" r="4" />
      <path d="M10 1.5v2" />
      <path d="M10 16.5v2" />
      <path d="M1.5 10h2" />
      <path d="M16.5 10h2" />
      <path d="M4.2 4.2l1.4 1.4" />
      <path d="M14.4 14.4l1.4 1.4" />
      <path d="M15.8 4.2l-1.4 1.4" />
      <path d="M5.6 14.4l-1.4 1.4" />
    </svg>
  )
}

export function ThemeToggle({ className }: { className?: string }) {
  const { theme, setTheme } = useTheme()
  const { t } = useLanguage()
  const dark = theme === 'dark'
  const label = dark ? t['theme.switchToLight'] : t['theme.switchToDark']
  return (
    <button
      type="button"
      className={className ?? 'theme-toggle'}
      aria-label={label}
      title={label}
      onClick={() => {
        setTheme(dark ? 'light' : 'dark')
      }}
    >
      {dark ? <SunIcon /> : <MoonIcon />}
    </button>
  )
}
