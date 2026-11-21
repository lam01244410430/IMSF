import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SpendingPage } from './Spending'

const HOUSEHOLD = {
  id: '11111111-1111-1111-1111-111111111111',
  name: '我家',
  default_currency: 'CNY',
  timezone: 'Asia/Shanghai',
  locale: 'zh-CN',
  created_at: null,
  role: 'owner',
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('SpendingPage currency separation', () => {
  let calls: string[]

  beforeEach(() => {
    calls = []
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) => {
        calls.push(url)
        if (url.startsWith('/api/v2/households')) return Promise.resolve(jsonResponse([HOUSEHOLD]))
        if (url.startsWith('/api/v2/spending/summary')) {
          const currency = new URL(url, 'http://localhost').searchParams.get('currency')
          return Promise.resolve(
            jsonResponse({
              currency,
              total: currency === 'VND' ? 500000 : 100,
              by_category: [{ category: 'food', total: currency === 'VND' ? 500000 : 100 }],
              by_month: [{ month: '2026-11', total: currency === 'VND' ? 500000 : 100 }],
            }),
          )
        }
        return Promise.resolve(jsonResponse(null, 404))
      }),
    )
    window.localStorage.clear()
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('shows one currency at a time and refetches per currency', async () => {
    const { container } = render(
      <MemoryRouter>
        <SpendingPage />
      </MemoryRouter>,
    )
    // Default = household currency CNY. The total appears in several
    // places (total card, category bar, month list), so assert on the
    // total card specifically.
    await waitFor(() =>
      expect(container.querySelector('.spending-total')?.textContent).toBe('¥100'),
    )
    expect(screen.getByText(/每种货币单独汇总，不混算、不换算/)).toBeDefined()

    fireEvent.change(screen.getByLabelText('货币'), { target: { value: 'VND' } })
    await waitFor(() =>
      expect(container.querySelector('.spending-total')?.textContent).toBe('₫500,000'),
    )

    // Every summary request carried exactly one currency; the VND
    // total never mixed with the CNY total.
    const summaryCalls = calls.filter((c) => c.includes('/spending/summary'))
    expect(summaryCalls.length).toBeGreaterThanOrEqual(2)
    for (const c of summaryCalls) {
      const params = new URL(c, 'http://localhost').searchParams
      expect(params.getAll('currency')).toHaveLength(1)
      expect(['CNY', 'VND']).toContain(params.get('currency'))
    }
    expect(summaryCalls.some((c) => c.includes('currency=VND'))).toBe(true)
  })
})
