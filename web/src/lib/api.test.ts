/**
 * API client tests — currency separation is the rule under test: the
 * spending summary is fetched for exactly ONE currency at a time, and
 * the request carries that currency as a query param (the backend
 * requires it and never sums across currencies).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  getSpendingSummary,
  listTransactions,
  respondNotification,
} from './api'

const HOUSEHOLD = '11111111-1111-1111-1111-111111111111'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('spending currency separation', () => {
  let fetchMock: ReturnType<typeof vi.fn>
  let calls: string[]

  beforeEach(() => {
    calls = []
    fetchMock = vi.fn((url: string) => {
      calls.push(url)
      return Promise.resolve(
        jsonResponse({ currency: 'VND', total: 0, by_category: [], by_month: [] }),
      )
    })
    vi.stubGlobal('fetch', fetchMock)
    window.localStorage.clear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('getSpendingSummary sends exactly the selected currency, nothing else', async () => {
    const res = await getSpendingSummary(HOUSEHOLD, 'VND', {
      from: '2026-11-01T00:00:00+08:00',
      to: '2026-12-01T00:00:00+08:00',
    })
    expect(res.currency).toBe('VND')
    expect(calls).toHaveLength(1)
    const url = new URL(calls[0], 'http://localhost')
    expect(url.pathname).toBe('/api/v2/spending/summary')
    expect(url.searchParams.get('currency')).toBe('VND')
    expect(url.searchParams.get('household_id')).toBe(HOUSEHOLD)
  })

  it('switching currency issues a separate one-currency request', async () => {
    await getSpendingSummary(HOUSEHOLD, 'CNY')
    await getSpendingSummary(HOUSEHOLD, 'VND')
    expect(calls).toHaveLength(2)
    expect(new URL(calls[0], 'http://localhost').searchParams.get('currency')).toBe('CNY')
    expect(new URL(calls[1], 'http://localhost').searchParams.get('currency')).toBe('VND')
    // No request ever carries two currencies.
    for (const c of calls) {
      expect(new URL(c, 'http://localhost').searchParams.getAll('currency')).toHaveLength(1)
    }
  })

  it('listTransactions passes the currency filter through', async () => {
    fetchMock.mockImplementation((url: string) => {
      calls.push(url)
      return Promise.resolve(jsonResponse([]))
    })
    await listTransactions(HOUSEHOLD, { currency: 'EUR' })
    const url = new URL(calls[0], 'http://localhost')
    expect(url.searchParams.get('currency')).toBe('EUR')
  })

  it('respondNotification posts used_up / extended with days=3', async () => {
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      calls.push(url)
      expect(init?.method).toBe('POST')
      return Promise.resolve(
        jsonResponse({ id: 'n1', status: 'responded', response: 'extended' }),
      )
    })
    await respondNotification('n1', 'extended', 3)
    expect(calls[0]).toBe('/api/v2/notifications/n1/respond')
    const body = JSON.parse(fetchMock.mock.calls[0][1].body as string) as {
      response: string
      days: number
    }
    expect(body).toEqual({ response: 'extended', days: 3 })
  })
})
