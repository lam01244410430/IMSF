/**
 * Shared validation + error mapping for the email auth forms
 * (reform plan §7.8). The UI never shows raw backend detail: every
 * failure maps to one of the plan's exact zh-CN strings (translated
 * through the i18n dictionary by key).
 *
 * 429 note: the backend returns the identical detail ("Too many
 * requests") for both login 429 cases — the 1/min rate limit and the
 * 15-minute lock after 5 wrong passwords — so the client cannot tell
 * them apart. Login maps 429 to the lock message (the consequential
 * case: the submit button is disabled for 15 minutes); register maps
 * 429 to the rate-limit message (register has only the per-IP limit).
 */
import { ApiError } from './auth'

export type BannerKey =
  | 'err.invalidCredentials'
  | 'err.emailTaken'
  | 'err.tooFrequent'
  | 'err.locked'
  | 'err.network'
  | 'err.server'

export type FieldErrorKey =
  | 'err.invalidEmail'
  | 'err.passwordShort'
  | 'err.passwordMismatch'

export function isValidEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)
}

/**
 * Classify a thrown error from `loginWithEmail` / `registerWithEmail`.
 * Returns the banner key, except for 422 which is a field error on the
 * email field (frontend validation normally catches it first).
 */
export function classifyAuthError(
  err: unknown,
  form: 'login' | 'register',
): { banner?: BannerKey; field?: FieldErrorKey } {
  if (err instanceof ApiError) {
    switch (err.status) {
      case 401:
        return { banner: 'err.invalidCredentials' }
      case 409:
        return { banner: 'err.emailTaken' }
      case 429:
        return form === 'login'
          ? { banner: 'err.locked' }
          : { banner: 'err.tooFrequent' }
      case 422:
        return { field: 'err.invalidEmail' }
      default:
        return { banner: 'err.server' }
    }
  }
  return { banner: 'err.network' }
}
