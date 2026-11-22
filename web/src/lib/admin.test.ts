/**
 * Admin API client tests — Dashboard Phase C (contract §2).
 * Every one of the 13 endpoints is called with exactly the path,
 * query params and body the contract fixes, and no invented fields.
 * Response shapes are the contract shapes verbatim.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  createAdminRecipe,
  getAdminHealth,
  getAdminMe,
  getAdminStats,
  getAdminUser,
  listAdminAuditEvents,
  listAdminJobs,
  listAdminReceiptJobs,
  listAdminRecipes,
  listAdminUsers,
  listHouseholdRecords,
  patchAdminRecipe,
  patchAdminUserStatus,
} from './admin'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('admin API client (contract §2)', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    fetchMock = vi.fn((_url: string, _init?: RequestInit) =>
      Promise.resolve(jsonResponse({})),
    )
    vi.stubGlobal('fetch', fetchMock)
    window.localStorage.clear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  // Read the recorded calls off the mock itself: mockImplementationOnce
  // replaces the base implementation, so a hand-rolled `calls` array
  // in the base would miss those calls.
  function urlOf(index: number): URL {
    const url = fetchMock.mock.calls[index][0] as string
    return new URL(url, 'http://localhost')
  }

  function bodyOf(index: number): Record<string, unknown> {
    return JSON.parse(
      (fetchMock.mock.calls[index][1] as RequestInit).body as string,
    ) as Record<string, unknown>
  }

  it('GET /me hits the admin me endpoint', async () => {
    fetchMock.mockImplementationOnce(() =>
      Promise.resolve(
        jsonResponse({
          user_id: 'u-1',
          name: 'Lam',
          email: 'lam@example.com',
          login_method: 'email',
          capabilities: ['users:read', 'users:write', 'recipes:write', 'audit:read', 'system:read'],
        }),
      ),
    )
    const me = await getAdminMe()
    expect(me.login_method).toBe('email')
    expect(me.capabilities).toHaveLength(5)
    expect(urlOf(0).pathname).toBe('/api/v2/admin/me')
  })

  it('GET /stats hits the admin stats endpoint', async () => {
    fetchMock.mockImplementationOnce(() =>
      Promise.resolve(
        jsonResponse({
          counts: {
            users: 2,
            households: 1,
            receipts: 3,
            transactions: 4,
            inventory_items: 5,
            published_recipes: 6,
            draft_recipes: 1,
            hidden_recipes: 0,
          },
          exceptions: {
            failed_receipt_jobs: 1,
            overdue_cron: true,
            unavailable_dependencies: ['gpu'],
          },
        }),
      ),
    )
    const stats = await getAdminStats()
    expect(stats.counts.users).toBe(2)
    expect(stats.exceptions.overdue_cron).toBe(true)
    expect(urlOf(0).pathname).toBe('/api/v2/admin/stats')
  })

  it('GET /users sends q + login_method + status + pagination', async () => {
    await listAdminUsers({
      q: 'lam@example.com',
      login_method: 'email',
      status: 'disabled',
      limit: 20,
      offset: 40,
    })
    const url = urlOf(0)
    expect(url.pathname).toBe('/api/v2/admin/users')
    expect(url.searchParams.get('q')).toBe('lam@example.com')
    expect(url.searchParams.get('login_method')).toBe('email')
    expect(url.searchParams.get('status')).toBe('disabled')
    expect(url.searchParams.get('limit')).toBe('20')
    expect(url.searchParams.get('offset')).toBe('40')
  })

  it('GET /users/{id} returns the safe detail shape', async () => {
    fetchMock.mockImplementationOnce(() =>
      Promise.resolve(
        jsonResponse({
          id: 'u-1',
          name: 'Lam',
          email: 'lam@example.com',
          login_method: 'email',
          status: 'enabled',
          disabled_at: null,
          created_at: '2026-11-22T00:00:00Z',
          households: [{ household_id: 'h-1', name: '我家', role: 'owner' }],
          counts: { receipts: 1, transactions: 2, inventory_items: 3, equipments: 0 },
        }),
      ),
    )
    const user = await getAdminUser('u-1')
    expect(user.households[0].role).toBe('owner')
    expect(urlOf(0).pathname).toBe('/api/v2/admin/users/u-1')
    // The safe detail shape never carries secrets.
    expect('password_hash' in user).toBe(false)
    expect('refresh_token' in user).toBe(false)
  })

  it('GET /households/{id}/records requires type + reason', async () => {
    await listHouseholdRecords('h-1', {
      type: 'transactions',
      reason: 'abuse report',
      limit: 20,
      offset: 0,
    })
    const url = urlOf(0)
    expect(url.pathname).toBe('/api/v2/admin/households/h-1/records')
    expect(url.searchParams.get('type')).toBe('transactions')
    expect(url.searchParams.get('reason')).toBe('abuse report')
  })

  it('PATCH /users/{id}/status sends disabled + reason', async () => {
    fetchMock.mockImplementationOnce(() =>
      Promise.resolve(
        jsonResponse({
          id: 'u-2',
          name: 'Bob',
          email: 'bob@example.com',
          login_method: 'email',
          status: 'disabled',
          disabled_at: '2026-11-22T01:00:00Z',
        }),
      ),
    )
    await patchAdminUserStatus('u-2', { disabled: true, reason: 'spam' })
    expect(fetchMock.mock.calls[0][1]?.method).toBe('PATCH')
    expect(urlOf(0).pathname).toBe('/api/v2/admin/users/u-2/status')
    expect(bodyOf(0)).toEqual({ disabled: true, reason: 'spam' })
  })

  it('GET /health, /jobs and /receipt-jobs hit their endpoints', async () => {
    await getAdminHealth()
    await listAdminJobs(5)
    await listAdminReceiptJobs({ limit: 10, offset: 20 })
    expect(urlOf(0).pathname).toBe('/api/v2/admin/health')
    expect(urlOf(1).pathname).toBe('/api/v2/admin/jobs')
    expect(urlOf(1).searchParams.get('limit')).toBe('5')
    expect(urlOf(2).pathname).toBe('/api/v2/admin/receipt-jobs')
    expect(urlOf(2).searchParams.get('offset')).toBe('20')
  })

  it('GET /recipes sends the status filter; POST creates a draft', async () => {
    await listAdminRecipes({ status: 'hidden', limit: 20, offset: 0 })
    expect(urlOf(0).pathname).toBe('/api/v2/admin/recipes')
    expect(urlOf(0).searchParams.get('status')).toBe('hidden')
    await createAdminRecipe({ title: 'Phở bò' })
    expect(fetchMock.mock.calls[1][1]?.method).toBe('POST')
    expect(urlOf(1).pathname).toBe('/api/v2/admin/recipes')
    const body = bodyOf(1)
    expect(body.title).toBe('Phở bò')
    // The client never sends a status on create — the server always
    // creates drafts (contract §2 #11).
    expect('status' in body).toBe(false)
  })

  it('PATCH /recipes/{id} sends only the allowlisted fields', async () => {
    await patchAdminRecipe('r-1', { status: 'published' })
    expect(fetchMock.mock.calls[0][1]?.method).toBe('PATCH')
    expect(urlOf(0).pathname).toBe('/api/v2/admin/recipes/r-1')
    expect(bodyOf(0)).toEqual({ status: 'published' })
  })

  it('GET /audit-events sends action + target_id + date range', async () => {
    await listAdminAuditEvents({
      action: 'user_disabled',
      target_id: 'u-2',
      from: '2026-11-01',
      to: '2026-11-22',
      limit: 20,
      offset: 0,
    })
    const url = urlOf(0)
    expect(url.pathname).toBe('/api/v2/admin/audit-events')
    expect(url.searchParams.get('action')).toBe('user_disabled')
    expect(url.searchParams.get('target_id')).toBe('u-2')
    expect(url.searchParams.get('from')).toBe('2026-11-01')
    expect(url.searchParams.get('to')).toBe('2026-11-22')
  })

  it('a 403 from the API surfaces as an ApiError with status 403', async () => {
    fetchMock.mockImplementationOnce(() =>
      Promise.resolve(jsonResponse({ detail: 'Not admin' }, 403)),
    )
    await expect(getAdminMe()).rejects.toMatchObject({ status: 403 })
  })
})
