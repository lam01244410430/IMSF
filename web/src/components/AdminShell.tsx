/**
 * Admin shell — Dashboard Phase C (plan §4, contract §5).
 *
 * Own shell, separate from the user AppShell (which is UNCHANGED):
 * a persistent "Admin / 管理后台" banner strip on top with a
 * "Return to family app" link to /app/dashboard, and a sidebar with
 * the 5 admin pages. The banner is how an admin tells at a glance
 * that they are in the admin area, not the family app (plan §4.6
 * risk 4: never confuse admin scope with household scope).
 *
 * Guard (`RequireAdmin`): on mount it calls GET /api/v2/admin/me.
 * 401 (or an expired session) → /login; 403 → a plain "no access"
 * page that reveals nothing about who the admins are; any other
 * failure → an honest load error with retry. The guard is display
 * logic only — the backend `require_admin` dependency enforces
 * access on every request.
 */
import { useEffect, useState, type ReactElement } from 'react'
import { Link, Navigate, NavLink, Outlet } from 'react-router-dom'
import { ApiError, AuthExpiredError } from '../lib/auth'
import { getAdminMe } from '../lib/admin'
import { useLanguage } from '../lib/i18n'
import { ThemeToggle } from './ThemeToggle'

const ADMIN_NAV = [
  { to: '/admin', labelKey: 'admin.overview', end: true },
  { to: '/admin/users', labelKey: 'admin.users', end: false },
  { to: '/admin/recipes', labelKey: 'admin.recipes', end: false },
  { to: '/admin/system', labelKey: 'admin.system', end: false },
  { to: '/admin/audit', labelKey: 'admin.audit', end: false },
] as const

function AdminNoAccess() {
  const { t } = useLanguage()
  return (
    <div className="page">
      <h1 className="page-title">{t['admin.noAccess']}</h1>
      <p className="page-note">{t['admin.noAccessHint']}</p>
      <p>
        <Link to="/app/dashboard">{t['admin.returnToApp']}</Link>
      </p>
    </div>
  )
}

type GuardState = 'loading' | 'ok' | 'denied' | 'login' | 'error'

export function RequireAdmin({ children }: { children: ReactElement }) {
  const { t } = useLanguage()
  const [state, setState] = useState<GuardState>('loading')
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let cancelled = false
    getAdminMe()
      .then(() => {
        if (!cancelled) setState('ok')
      })
      .catch((err: unknown) => {
        if (cancelled) return
        if (
          err instanceof AuthExpiredError ||
          (err instanceof ApiError && err.status === 401)
        ) {
          setState('login')
        } else if (err instanceof ApiError && err.status === 403) {
          setState('denied')
        } else {
          setState('error')
        }
      })
    return () => {
      cancelled = true
    }
  }, [attempt])

  if (state === 'login') return <Navigate to="/login" replace />
  if (state === 'denied') return <AdminNoAccess />
  if (state === 'error') {
    return (
      <div className="page">
        <p className="page-error">{t['admin.loadError']}</p>
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => {
            setState('loading')
            setAttempt((n) => n + 1)
          }}
        >
          {t['admin.retry']}
        </button>
      </div>
    )
  }
  if (state === 'loading') {
    return (
      <div className="page">
        <p className="page-note">{t['admin.loading']}</p>
      </div>
    )
  }
  return children
}

export function AdminShell() {
  const { t } = useLanguage()
  return (
    <div className="admin-shell">
      <div className="admin-banner">
        <span className="admin-banner-title">{t['admin.banner']}</span>
        <span className="admin-banner-spacer" />
        <ThemeToggle />
        <Link to="/app/dashboard" className="admin-banner-return">
          {t['admin.returnToApp']}
        </Link>
      </div>
      <div className="admin-body">
        <nav className="admin-sidebar" aria-label={t['admin.banner']}>
          {ADMIN_NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `admin-nav-item${isActive ? ' active' : ''}`
              }
            >
              {t[item.labelKey]}
            </NavLink>
          ))}
        </nav>
        <main className="admin-content">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
