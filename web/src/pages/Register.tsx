/**
 * Email registration (reform plan §7.8). Web = email only, no WeChat
 * button. Fields: email + password + confirm password (frontend-only
 * match check, never sent to the server) + name (optional, sent as the
 * display name). Frontend validation first: valid email, password ≥ 8
 * chars, passwords match. 409 shows the exact plan string with a link
 * to /login. On success the backend already returned tokens (the auth
 * client stored them), so registration auto-logs-in → /app.
 */
import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { registerWithEmail } from '../lib/auth'
import {
  classifyAuthError,
  isValidEmail,
  type BannerKey,
  type FieldErrorKey,
} from '../lib/authForm'
import { useLanguage } from '../lib/i18n'
import { AuthLayout } from '../components/AuthLayout'

export function RegisterPage() {
  const { t } = useLanguage()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const nextParam = params.get('next')
  const next =
    nextParam !== null && nextParam.startsWith('/') ? nextParam : '/app'

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [name, setName] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [showConfirmPassword, setShowConfirmPassword] = useState(false)
  const [fieldErrors, setFieldErrors] = useState<{
    email?: FieldErrorKey
    password?: FieldErrorKey
    confirm?: FieldErrorKey
  }>({})
  const [banner, setBanner] = useState<BannerKey | null>(null)
  const [loading, setLoading] = useState(false)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (loading) return

    const errors: typeof fieldErrors = {}
    if (!isValidEmail(email.trim())) errors.email = 'err.invalidEmail'
    if (password.length < 8) errors.password = 'err.passwordShort'
    if (password !== confirmPassword) {
      errors.confirm = 'err.passwordMismatch'
    }
    setFieldErrors(errors)
    setBanner(null)
    if (Object.keys(errors).length > 0) return

    setLoading(true)
    try {
      await registerWithEmail(
        email.trim(),
        password,
        undefined,
        name.trim() === '' ? undefined : name.trim(),
      )
      navigate(next, { replace: true })
    } catch (err: unknown) {
      const result = classifyAuthError(err, 'register')
      if (result.field) {
        setFieldErrors({ email: result.field })
      } else if (result.banner) {
        setBanner(result.banner)
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthLayout title={t['auth.registerTitle']}>
      <p className="auth-note">{t['auth.note']}</p>
      <form className="auth-form" onSubmit={handleSubmit} noValidate>
        <div className="auth-field">
          <label htmlFor="register-email">{t['auth.email']}</label>
          <input
            id="register-email"
            type="email"
            autoComplete="email"
            value={email}
            aria-invalid={fieldErrors.email !== undefined}
            aria-describedby={
              fieldErrors.email ? 'register-email-error' : undefined
            }
            onChange={(event) => {
              setEmail(event.target.value)
            }}
          />
          {fieldErrors.email ? (
            <p id="register-email-error" className="field-error">
              {t[fieldErrors.email]}
            </p>
          ) : null}
        </div>
        <div className="auth-field">
          <label htmlFor="register-password">{t['auth.password']}</label>
          <div className="password-wrap">
            <input
              id="register-password"
              className="password-input"
              type={showPassword ? 'text' : 'password'}
              autoComplete="new-password"
              value={password}
              aria-invalid={fieldErrors.password !== undefined}
              aria-describedby={
                fieldErrors.password ? 'register-password-error' : undefined
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
            <p id="register-password-error" className="field-error">
              {t[fieldErrors.password]}
            </p>
          ) : null}
        </div>
        <div className="auth-field">
          <label htmlFor="register-confirm">
            {t['auth.confirmPassword']}
          </label>
          <div className="password-wrap">
            <input
              id="register-confirm"
              className="password-input"
              type={showConfirmPassword ? 'text' : 'password'}
              autoComplete="new-password"
              value={confirmPassword}
              aria-invalid={fieldErrors.confirm !== undefined}
              aria-describedby={
                fieldErrors.confirm ? 'register-confirm-error' : undefined
              }
              onChange={(event) => {
                setConfirmPassword(event.target.value)
              }}
            />
            <button
              type="button"
              className="password-toggle"
              aria-label={
                showConfirmPassword
                  ? t['auth.hidePassword']
                  : t['auth.showPassword']
              }
              onClick={() => {
                setShowConfirmPassword((show) => !show)
              }}
            >
              {showConfirmPassword
                ? t['auth.hidePassword']
                : t['auth.showPassword']}
            </button>
          </div>
          {fieldErrors.confirm ? (
            <p id="register-confirm-error" className="field-error">
              {t[fieldErrors.confirm]}
            </p>
          ) : null}
        </div>
        <div className="auth-field">
          <label htmlFor="register-name">{t['auth.name']}</label>
          <input
            id="register-name"
            type="text"
            autoComplete="name"
            value={name}
            onChange={(event) => {
              setName(event.target.value)
            }}
          />
        </div>
        {banner ? (
          <p role="alert" className="auth-banner">
            {t[banner]}
            {banner === 'err.emailTaken' ? (
              <>
                {' '}
                <Link to="/login">{t['auth.goLogin']}</Link>
              </>
            ) : null}
          </p>
        ) : null}
        <button type="submit" className="auth-submit" disabled={loading}>
          {loading ? t['auth.loadingRegister'] : t['auth.registerSubmit']}
        </button>
      </form>
      <p className="auth-switch">
        <Link to="/login">{t['auth.hasAccount']}</Link>
      </p>
    </AuthLayout>
  )
}
