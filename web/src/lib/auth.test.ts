import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  AuthExpiredError,
  apiFetch,
  getAccessToken,
  getRefreshToken,
  getStoredHouseholdId,
  getStoredHouseholdName,
  getStoredUserName,
  isLoggedIn,
  loginWithEmail,
  registerWithEmail,
  logout,
  refreshAccessToken,
  resetAuthState,
  setStoredHouseholdId,
  setTokens,
} from './auth'

function base64Url(obj: unknown): string {
  // btoa is ASCII-safe here: the fake payload is plain JSON.
  return btoa(JSON.stringify(obj))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '')
}

/** Fake unsigned JWT with a given `exp` (seconds since epoch). */
function fakeJwt(expSeconds: number): string {
  return `${base64Url({ alg: 'none' })}.${base64Url({ exp: expSeconds, sub: 'u1' })}.sig`
}

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('auth client', () => {
  beforeEach(() => {
    window.localStorage.clear()
    resetAuthState()
    vi.stubGlobal('fetch', vi.fn())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  const fetchMock = () => vi.mocked(globalThis.fetch)

  it('valid session: apiFetch attaches the access token and passes 200 through', async () => {
    setTokens(fakeJwt(Math.floor(Date.now() / 1000) + 600), 'refresh-1')
    fetchMock().mockResolvedValueOnce(jsonResponse(200, { ok: true }))
    const res = await apiFetch('/api/v2/fridge')
    expect(res.status).toBe(200)
    expect(fetchMock()).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock().mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v2/fridge')
    expect(
      (init.headers as Record<string, string>)['Authorization'],
    ).toMatch(/^Bearer /)
    expect(isLoggedIn()).toBe(true)
  })

  it('expiry: token expiring within 60s is refreshed proactively before the request', async () => {
    const newAccess = fakeJwt(Math.floor(Date.now() / 1000) + 900)
    setTokens(fakeJwt(Math.floor(Date.now() / 1000) + 30), 'refresh-1')
    fetchMock()
      .mockResolvedValueOnce(jsonResponse(200, { access_token: newAccess }))
      .mockResolvedValueOnce(jsonResponse(200, { ok: true }))
    const res = await apiFetch('/api/v2/fridge')
    expect(res.status).toBe(200)
    expect(fetchMock()).toHaveBeenCalledTimes(2)
    // First call is the refresh, second is the API call with the new token.
    expect(fetchMock().mock.calls[0][0]).toBe('/api/v2/auth/refresh')
    const [, init] = fetchMock().mock.calls[1] as [string, RequestInit]
    expect(
      (init.headers as Record<string, string>)['Authorization'],
    ).toBe(`Bearer ${newAccess}`)
    expect(getAccessToken()).toBe(newAccess)
    // Refresh returns ONLY a new access token — the old refresh token stays.
    expect(getRefreshToken()).toBe('refresh-1')
  })

  it('401 → refresh once → retry once with the new token', async () => {
    const newAccess = fakeJwt(Math.floor(Date.now() / 1000) + 900)
    setTokens(fakeJwt(Math.floor(Date.now() / 1000) + 600), 'refresh-1')
    fetchMock()
      .mockResolvedValueOnce(jsonResponse(401, { detail: 'expired' }))
      .mockResolvedValueOnce(jsonResponse(200, { access_token: newAccess }))
      .mockResolvedValueOnce(jsonResponse(200, { ok: true }))
    const res = await apiFetch('/api/v2/fridge')
    expect(res.status).toBe(200)
    expect(fetchMock()).toHaveBeenCalledTimes(3)
    expect(fetchMock().mock.calls[1][0]).toBe('/api/v2/auth/refresh')
  })

  it('refresh failure: tokens are cleared and AuthExpiredError is thrown', async () => {
    setTokens(fakeJwt(Math.floor(Date.now() / 1000) + 600), 'refresh-1')
    fetchMock()
      .mockResolvedValueOnce(jsonResponse(401, { detail: 'expired' }))
      .mockResolvedValueOnce(jsonResponse(401, { detail: 'bad refresh' }))
    await expect(apiFetch('/api/v2/fridge')).rejects.toBeInstanceOf(
      AuthExpiredError,
    )
    expect(getAccessToken()).toBe('')
    expect(getRefreshToken()).toBe('')
    expect(isLoggedIn()).toBe(false)
  })

  it('multiple concurrent 401s trigger exactly one refresh (single-flight)', async () => {
    const newAccess = fakeJwt(Math.floor(Date.now() / 1000) + 900)
    setTokens(fakeJwt(Math.floor(Date.now() / 1000) + 600), 'refresh-1')
    let refreshCalls = 0
    let apiCalls = 0
    fetchMock().mockImplementation((url, init) => {
      const u = String(url)
      if (u === '/api/v2/auth/refresh') {
        refreshCalls += 1
        return Promise.resolve(jsonResponse(200, { access_token: newAccess }))
      }
      apiCalls += 1
      const auth = (init as RequestInit | undefined)?.headers as
        | Record<string, string>
        | undefined
      if (auth?.['Authorization'] === `Bearer ${newAccess}`) {
        return Promise.resolve(jsonResponse(200, { ok: true }))
      }
      return Promise.resolve(jsonResponse(401, { detail: 'expired' }))
    })
    const results = await Promise.all([
      apiFetch('/api/v2/fridge'),
      apiFetch('/api/v2/transactions'),
      apiFetch('/api/v2/spending'),
    ])
    expect(results.map((r) => r.status)).toEqual([200, 200, 200])
    expect(refreshCalls).toBe(1)
    expect(apiCalls).toBe(6) // 3 first attempts + 3 retries
  })

  it('refreshAccessToken keeps the old refresh token', async () => {
    const newAccess = fakeJwt(Math.floor(Date.now() / 1000) + 900)
    setTokens(fakeJwt(Math.floor(Date.now() / 1000) + 600), 'refresh-keep')
    fetchMock().mockResolvedValueOnce(
      jsonResponse(200, { access_token: newAccess }),
    )
    const access = await refreshAccessToken()
    expect(access).toBe(newAccess)
    expect(getRefreshToken()).toBe('refresh-keep')
  })

  it('logout clears tokens and household id', () => {
    setTokens('a', 'r')
    setStoredHouseholdId('h1')
    logout()
    expect(getAccessToken()).toBe('')
    expect(getRefreshToken()).toBe('')
    expect(getStoredHouseholdId()).toBeNull()
  })

  it('loginWithEmail stores tokens and the first household id', async () => {
    fetchMock().mockResolvedValueOnce(
      jsonResponse(200, {
        access_token: 'a1',
        refresh_token: 'r1',
        user: { id: 'u1', email: 'a@b.c', name: 'A' },
        households: [{ id: 'h1', name: 'Home' }],
      }),
    )
    const data = await loginWithEmail('a@b.c', 'secret')
    expect(data.user.id).toBe('u1')
    expect(getAccessToken()).toBe('a1')
    expect(getRefreshToken()).toBe('r1')
    expect(getStoredHouseholdId()).toBe('h1')
    expect(getStoredHouseholdName()).toBe('Home')
  })

  it('loginWithEmail stores the email local part as the name when name is missing (Phase 4)', async () => {
    fetchMock().mockResolvedValueOnce(
      jsonResponse(200, {
        access_token: 'a1',
        refresh_token: 'r1',
        user: { id: 'u1', email: 'lam@example.com' },
        households: [{ id: 'h1', name: 'Home' }],
      }),
    )
    await loginWithEmail('lam@example.com', 'secret')
    // A stored name is never a full email address.
    expect(getStoredUserName()).toBe('lam')
  })

  it('registerWithEmail sends household_name and stores the returned household (Phase 5)', async () => {
    fetchMock().mockResolvedValueOnce(
      jsonResponse(200, {
        access_token: 'a1',
        refresh_token: 'r1',
        user: { id: 'u1', email: 'a@b.c', name: 'A' },
        households: [{ id: 'h1', name: '我家' }],
      }),
    )
    const data = await registerWithEmail('a@b.c', 'secret123', '我家')
    expect(data.households).toEqual([{ id: 'h1', name: '我家' }])
    const sent = JSON.parse(
      String(fetchMock().mock.calls[0][1]?.body),
    ) as Record<string, unknown>
    expect(sent.household_name).toBe('我家')
    expect(getStoredHouseholdId()).toBe('h1')
    expect(getStoredHouseholdName()).toBe('我家')
  })

  it('registerWithEmail without a household name sends null and stores no household (Phase 5)', async () => {
    fetchMock().mockResolvedValueOnce(
      jsonResponse(200, {
        access_token: 'a1',
        refresh_token: 'r1',
        user: { id: 'u1', email: 'a@b.c', name: 'a' },
        households: [],
      }),
    )
    const data = await registerWithEmail('a@b.c', 'secret123')
    expect(data.households).toEqual([])
    const sent = JSON.parse(
      String(fetchMock().mock.calls[0][1]?.body),
    ) as Record<string, unknown>
    expect(sent.household_name).toBeNull()
    expect(sent.name).toBeNull()
    expect(getStoredHouseholdId()).toBeNull()
    expect(getStoredHouseholdName()).toBeNull()
  })
})
