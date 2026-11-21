import type { ReactElement } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { isLoggedIn } from '../lib/auth'

/**
 * Route guards (reform plan §3.2).
 *
 * - Unauthenticated on any /app/* → /login?next=<original path>, so
 *   login can return the user to the page they wanted.
 * - Authenticated on /login or /register → /app.
 * - Authenticated on / (landing) → NO redirect; the landing header
 *   shows 进入应用 instead of 登录/注册.
 */

/** Wraps the /app/* subtree. */
export function RequireAuth({ children }: { children: ReactElement }) {
  const location = useLocation()
  if (!isLoggedIn()) {
    const next = `${location.pathname}${location.search}`
    return <Navigate to={`/login?next=${encodeURIComponent(next)}`} replace />
  }
  return children
}

/** Wraps /login and /register. */
export function PublicOnly({ children }: { children: ReactElement }) {
  if (isLoggedIn()) {
    return <Navigate to="/app" replace />
  }
  return children
}
