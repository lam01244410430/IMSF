/**
 * Shared shell for the public auth + legal pages: logo (links home) +
 * language switcher in a 64px header, then a centred ~400px column.
 * The auth pages are email-only — there is deliberately no WeChat
 * button on web (reform plan §7.8).
 */
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import logoUrl from '../assets/logo.svg'
import logoDarkUrl from '../assets/logo-dark.svg'
import { useTheme } from '../lib/theme'
import { LanguageSwitcher } from './LanguageSwitcher'
import { ThemeToggle } from './ThemeToggle'

export function AuthLayout({
  title,
  children,
}: {
  title: string
  children: ReactNode
}) {
  const { theme } = useTheme()
  return (
    <div className="auth-page">
      <header className="auth-header">
        <Link to="/" className="landing-brand" aria-label="IMSF">
          <img
            src={theme === 'dark' ? logoDarkUrl : logoUrl}
            alt="IMSF"
            className="landing-logo"
          />
        </Link>
        <span className="auth-header-right">
          <ThemeToggle />
          <LanguageSwitcher className="lang-switcher" />
        </span>
      </header>
      <main className="auth-main">
        <h1>{title}</h1>
        {children}
      </main>
    </div>
  )
}
