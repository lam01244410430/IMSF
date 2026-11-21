/**
 * Email login (reform plan §7.8). Web = email only, no WeChat button.
 *
 * Behaviour from the plan's error table:
 * - Frontend validation first: valid email, password ≥ 8 chars.
 * - 401 → banner, email kept, only the password cleared.
 * - 429 → the lock message + submit disabled for 15 minutes (with a
 *   countdown; the backend returns the same 429 for the 1/min limit
 *   and the 5-wrong lock, see `lib/authForm.ts`).
 * - Network failure → network banner; 5xx → server banner.
 * - Never shows raw backend detail in the UI.
 * - On success the auth client has stored tokens + household id;
 *   redirect to `?next=` when present, else /app.
 * - A `notice` string passed in navigation state (e.g. the blog
 *   article's like/save buttons redirecting here) is shown as an
 *   informational notice above the form — it is sender-supplied UI
 *   copy, rendered as plain text, never an error banner.
 */
import { useEffect, useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { loginWithEmail } from '../lib/auth'
import {
  classifyAuthError,
  isValidEmail,
  type BannerKey,
  type FieldErrorKey,
} from '../lib/authForm'
import { fill, useLanguage } from '../lib/i18n'
import { AuthLayout } from '../components/AuthLayout'

const LOCK_MS = 15 * 60 * 1000

export function LoginPage() {
  const { t } = useLanguage()
  const navigate = useNavigate()
  const location = useLocation()
  const [params] = useSearchParams()
  const nextParam = params.get('next')
  const next =
    nextParam !== null && nextParam.startsWith('/') ? nextParam : '/app'

  // Informational notice carried in navigation state (blog like/save
  // redirect). Only a plain string is rendered; anything else is
  // ignored so a malformed state can never inject markup.
  const state = location.state as { notice?: unknown } | null
  const notice =
    state !== null &&
    typeof state === 'object' &&
    typeof state.notice === 'string' &&
    state.notice !== ''
      ? state.notice
      : null

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [fieldErrors, setFieldErrors] = useState<{
    email?: FieldErrorKey
    password?: FieldErrorKey
  }>({})
  const [banner, setBanner] = useState<BannerKey | null>(null)
  const [loading, setLoading] = useState(false)
  const [lockedUntil, setLockedUntil] = useState<number | null>(null)
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    if (lockedUntil === null) return
    const id = window.setInterval(() => {
      // Clearing the lock from inside the timer callback (not from an
      // effect body watching the countdown) keeps oxlint's
      // set-state-in-effect rule quiet.
      if (lockedUntil - Date.now() <= 0) {
        setLockedUntil(null)
        setBanner(null)
      } else {
        setNow(Date.now())
      }
    }, 1000)
    return () => {
      window.clearInterval(id)
    }
  }, [lockedUntil])

  const lockedRemaining =
    lockedUntil === null
      ? 0
      : Math.max(0, Math.ceil((lockedUntil - now) / 1000))

  const locked = lockedRemaining > 0

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (loading || locked) return

    const errors: typeof fieldErrors = {}
    if (!isValidEmail(email.trim())) errors.email = 'err.invalidEmail'
    if (password.length < 8) errors.password = 'err.passwordShort'
    setFieldErrors(errors)
    setBanner(null)
    if (Object.keys(errors).length > 0) return

    setLoading(true)
    try {
      await loginWithEmail(email.trim(), password)
      navigate(next, { replace: true })
    } catch (err: unknown) {
      const result = classifyAuthError(err, 'login')
      if (result.banner === 'err.invalidCredentials') {
        // Keep the email so the user can fix the password; clear only
        // the password (plan §7.8).
        setPassword('')
      }
      if (result.banner === 'err.locked') {
        setLockedUntil(Date.now() + LOCK_MS)
      }
      if (result.field) {
        setFieldErrors({ email: result.field })
      } else if (result.banner) {
        setBanner(result.banner)
      }
    } finally {
      setLoading(false)
    }
  }

  const mm = String(Math.floor(lockedRemaining / 60)).padStart(2, '0')
  const ss = String(lockedRemaining % 60).padStart(2, '0')

  return (
    <AuthLayout title={t['auth.loginTitle']}>
      <p className="auth-note">{t['auth.note']}</p>
      {notice ? (
        <p role="status" className="auth-notice">
          {notice}
        </p>
      ) : null}
      <form className="auth-form" onSubmit={handleSubmit} noValidate>
        <div className="auth-field">
          <label htmlFor="login-email">{t['auth.email']}</label>
          <input
            id="login-email"
            type="email"
            autoComplete="email"
            value={email}
            aria-invalid={fieldErrors.email !== undefined}
            aria-describedby={
              fieldErrors.email ? 'login-email-error' : undefined
            }
            onChange={(event) => {
              setEmail(event.target.value)
            }}
          />
          {fieldErrors.email ? (
            <p id="login-email-error" className="field-error">
              {t[fieldErrors.email]}
            </p>
          ) : null}
        </div>
        <div className="auth-field">
          <label htmlFor="login-password">{t['auth.password']}</label>
          <div className="password-wrap">
            <input
              id="login-password"
              className="password-input"
              type={showPassword ? 'text' : 'password'}
              autoComplete="current-password"
              value={password}
              aria-invalid={fieldErrors.password !== undefined}
              aria-describedby={
                fieldErrors.password ? 'login-password-error' : undefined
              }
              onChange={(event) => {
                setPassword(event.target.value)
              }}
            />
            <button
              type="button"
              className="password-toggle"
              aria-label={
                showPassword ? t['auth.hidePassword'] : t['auth.showPassword']
              }
              onClick={() => {
                setShowPassword((show) => !show)
              }}
            >
              {showPassword ? t['auth.hidePassword'] : t['auth.showPassword']}
            </button>
          </div>
          {fieldErrors.password ? (
            <p id="login-password-error" className="field-error">
              {t[fieldErrors.password]}
            </p>
          ) : null}
        </div>
        {banner ? (
          <p role="alert" className="auth-banner">
            {t[banner]}
          </p>
        ) : null}
        <button
          type="submit"
          className="auth-submit"
          disabled={loading || locked}
        >
          {loading ? t['auth.loadingLogin'] : t['auth.loginSubmit']}
        </button>
        {locked ? (
          <p className="auth-countdown">
            {fill(t['auth.lockedCountdown'], { mm, ss })}
          </p>
        ) : null}
      </form>
      <p className="auth-switch">
        <Link to="/register">{t['auth.noAccount']}</Link>
      </p>
    </AuthLayout>
  )
}
