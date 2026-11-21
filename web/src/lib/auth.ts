/**
 * Auth client for the IMSF website — port of the Taro auth service
 * (`frontend/src/services/auth.ts`, design doc §8.4), with `fetch`
 * instead of `Taro.request` and same-origin relative URLs
 * (`/api/v2/...` — no base URL, no CORS needed).
 *
 * - Storage keys: `imsf2.access_token` / `imsf2.refresh_token` /
 *   `imsf2.household_id` (localStorage, same keys as the Taro app).
 * - Access token 15 min / refresh token 7 days (backend mint).
 * - Refresh response returns ONLY a new access token — the old refresh
 *   token is kept.
 * - Single-flight: `refreshPromise` in-memory; every request that hits
 *   401 while a refresh is running awaits the same promise.
 * - Proactive refresh: when the access token has < 60s left (decoded
 *   `exp` from the JWT payload client-side — expiry check only, no
 *   verify), refresh before the request.
 * - 401 → refresh once → retry once. Refresh failure → tokens cleared
 *   → caller redirects to /login (see `RequireAuth` / `AuthExpiredError`).
 */

export const STORAGE_KEYS = {
  access: 'imsf2.access_token',
  refresh: 'imsf2.refresh_token',
  household: 'imsf2.household_id',
  /** Display name for the landing header (name, else email). The
   *  backend has no display-name endpoint yet (FE-04 caveat), so the
   *  name from the last login/register response is kept locally. */
  userName: 'imsf2.user_name',
} as const

export interface AuthUser {
  id: string
  email?: string
  name?: string
  wechat_openid?: string
}

export interface HouseholdSummary {
  id: string
  name: string
}

export interface AuthResponse {
  access_token: string
  refresh_token: string
  user: AuthUser
  households: HouseholdSummary[]
}

/** Thrown by `apiFetch` when the session cannot be refreshed. The
 *  caller must clear state (already done) and redirect to /login. */
export class AuthExpiredError extends Error {
  constructor() {
    super('Session expired')
    this.name = 'AuthExpiredError'
  }
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

const REFRESH_EARLY_MS = 60_000

let refreshPromise: Promise<string> | null = null

/** Test-only reset of the in-memory single-flight state. */
export function resetAuthState(): void {
  refreshPromise = null
}

function storageGet(key: string): string {
  try {
    return window.localStorage.getItem(key) ?? ''
  } catch {
    return ''
  }
}

function storageSet(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value)
  } catch {
    // storage full / unavailable — token lives only in-memory for the
    // next call, same fallback as the Taro client.
  }
}

function storageRemove(key: string): void {
  try {
    window.localStorage.removeItem(key)
  } catch {
    // ignore
  }
}

export function getAccessToken(): string {
  return storageGet(STORAGE_KEYS.access)
}

export function getRefreshToken(): string {
  return storageGet(STORAGE_KEYS.refresh)
}

export function getStoredHouseholdId(): string | null {
  return storageGet(STORAGE_KEYS.household) || null
}

export function setStoredHouseholdId(id: string): void {
  storageSet(STORAGE_KEYS.household, id)
}

export function getStoredUserName(): string | null {
  return storageGet(STORAGE_KEYS.userName) || null
}

export function setStoredUserName(name: string): void {
  storageSet(STORAGE_KEYS.userName, name)
}

/** Remember the display name from a login/register response. */
function storeUserName(user: AuthUser): void {
  const display = (user.name ?? '').trim() || (user.email ?? '').trim()
  if (display) setStoredUserName(display)
}

export function setTokens(accessToken: string, refreshToken: string): void {
  storageSet(STORAGE_KEYS.access, accessToken)
  storageSet(STORAGE_KEYS.refresh, refreshToken)
}

export function setAccessToken(accessToken: string): void {
  storageSet(STORAGE_KEYS.access, accessToken)
}

/** Clear both tokens (refresh fail → login page, §8.4). */
export function clearTokens(): void {
  storageRemove(STORAGE_KEYS.access)
  storageRemove(STORAGE_KEYS.refresh)
}

export function logout(): void {
  clearTokens()
  storageRemove(STORAGE_KEYS.household)
  storageRemove(STORAGE_KEYS.userName)
}

export function isLoggedIn(): boolean {
  return getAccessToken().length > 0
}

function base64UrlDecode(input: string): string {
  const base64 = input.replace(/-/g, '+').replace(/_/g, '/')
  const padded = base64 + '='.repeat((4 - (base64.length % 4)) % 4)
  return globalThis.atob(padded)
}

/** Decode `exp` from a JWT payload — expiry check only, no verify. */
export function decodeJwtExp(token: string): number | null {
  try {
    const payload = token.split('.')[1]
    if (!payload) return null
    const json = JSON.parse(base64UrlDecode(payload)) as { exp?: number }
    return typeof json.exp === 'number' ? json.exp * 1000 : null
  } catch {
    return null
  }
}

export function accessTokenExpiresInMs(): number | null {
  const token = getAccessToken()
  if (!token) return null
  const exp = decodeJwtExp(token)
  if (exp === null) return null
  return exp - Date.now()
}

/** Refresh when the access token has < 60s left — call before starting
 *  a sensitive request (e.g. an upload). */
export async function ensureFreshAccessToken(): Promise<void> {
  const remaining = accessTokenExpiresInMs()
  if (remaining !== null && remaining < REFRESH_EARLY_MS) {
    await refreshAccessToken()
  }
}

export async function refreshAccessToken(): Promise<string> {
  if (refreshPromise) return refreshPromise
  refreshPromise = (async () => {
    const rt = getRefreshToken()
    if (!rt) throw new AuthExpiredError()
    let res: Response
    try {
      res = await fetch('/api/v2/auth/refresh', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: rt }),
      })
    } catch {
      throw new AuthExpiredError()
    }
    if (!res.ok) throw new AuthExpiredError()
    const data = (await res.json().catch(() => null)) as {
      access_token?: string
    } | null
    const access = data?.access_token
    if (!access) throw new AuthExpiredError()
    setAccessToken(access)
    return access
  })()
  try {
    return await refreshPromise
  } catch (err) {
    // A failed refresh ends the session: clear tokens so the guard
    // sends the user to /login instead of retrying forever.
    clearTokens()
    throw err
  } finally {
    refreshPromise = null
  }
}

async function parseError(res: Response): Promise<ApiError> {
  const data = (await res.json().catch(() => null)) as {
    detail?: string
  } | null
  const message =
    typeof data?.detail === 'string' && data.detail.length > 0
      ? data.detail
      : `Request failed (${res.status})`
  return new ApiError(res.status, message)
}

export interface ApiFetchOptions extends Omit<RequestInit, 'headers'> {
  headers?: Record<string, string>
  /** Set false for the auth endpoints themselves (no token attached). */
  auth?: boolean
}

/**
 * Same-origin fetch with auth: attaches the access token, refreshes
 * proactively when it expires within 60s, and on 401 refreshes once
 * and retries once. Refresh failure clears the tokens and throws
 * `AuthExpiredError`.
 */
export async function apiFetch(
  path: string,
  options: ApiFetchOptions = {},
): Promise<Response> {
  const { auth = true, headers = {}, ...init } = options
  if (auth) {
    await ensureFreshAccessToken().catch(() => {
      // ensureFreshAccessToken throws AuthExpiredError only when a
      // refresh was attempted and failed; in that case the tokens are
      // already cleared — surface it instead of firing the request
      // with a dead token.
      throw new AuthExpiredError()
    })
  }
  const doFetch = (token: string | null): Promise<Response> => {
    const allHeaders: Record<string, string> = { ...headers }
    if (auth && token) allHeaders['Authorization'] = `Bearer ${token}`
    return fetch(path, { ...init, headers: allHeaders })
  }

  let res = await doFetch(auth ? getAccessToken() : null)
  if (res.status === 401 && auth) {
    const access = await refreshAccessToken()
    res = await doFetch(access)
    if (res.status === 401) {
      clearTokens()
      throw new AuthExpiredError()
    }
  }
  return res
}

/** GET JSON helper — throws ApiError / AuthExpiredError on failure. */
export async function apiGetJson<T>(path: string): Promise<T> {
  const res = await apiFetch(path, { method: 'GET' })
  if (!res.ok) throw await parseError(res)
  return (await res.json()) as T
}

/** Email login (Phase 2, migration 0006). Stores both tokens and the
 *  first household id when the backend returns households. */
export async function loginWithEmail(
  email: string,
  password: string,
): Promise<AuthResponse> {
  const res = await fetch('/api/v2/auth/email/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  if (!res.ok) throw await parseError(res)
  const data = (await res.json()) as AuthResponse
  setTokens(data.access_token, data.refresh_token)
  storeUserName(data.user)
  if (data.households.length > 0) {
    setStoredHouseholdId(data.households[0].id)
  }
  return data
}

/** Email registration (Phase 2). Same response shape as login.
 *  `name` is the optional display name; `householdName` the optional
 *  household name. Neither is required by the backend. */
export async function registerWithEmail(
  email: string,
  password: string,
  householdName?: string,
  name?: string,
): Promise<AuthResponse> {
  const res = await fetch('/api/v2/auth/email/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      email,
      password,
      name: name ?? null,
      household_name: householdName ?? null,
    }),
  })
  if (!res.ok) throw await parseError(res)
  const data = (await res.json()) as AuthResponse
  setTokens(data.access_token, data.refresh_token)
  storeUserName(data.user)
  if (data.households.length > 0) {
    setStoredHouseholdId(data.households[0].id)
  }
  return data
}
