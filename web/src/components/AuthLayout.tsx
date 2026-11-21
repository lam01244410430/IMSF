/**
 * Shared shell for the public auth + legal pages: logo (links home) +
 * language switcher in a 64px header, then a centred ~400px column.
 * The auth pages are email-only — there is deliberately no WeChat
 * button on web (reform plan §7.8).
 */
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import logoUrl from '../assets/logo.svg'
import { LanguageSwitcher } from './LanguageSwitcher'

export function AuthLayout({
  title,
  children,
}: {
  title: string
  children: ReactNode
}) {
  return (
    <div className="auth-page">
      <header className="auth-header">
        <Link to="/" className="landing-brand" aria-label="IMSF">
          <img src={logoUrl} alt="IMSF" className="landing-logo" />
        </Link>
        <LanguageSwitcher className="lang-switcher" />
      </header>
      <main className="auth-main">
        <h1>{title}</h1>
        {children}
      </main>
    </div>
  )
}
