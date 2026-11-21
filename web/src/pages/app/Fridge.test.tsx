import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { FridgePage } from './Fridge'

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

function fridgeItem(
  id: string,
  rawName: string,
  canonicalName: string | null,
  daysLeft: number | null,
) {
  return {
    id,
    household_id: HOUSEHOLD.id,
    receipt_id: null,
    receipt_line_id: null,
    raw_name: rawName,
    canonical_ingredient_id: null,
    quantity: 2,
    unit: '个',
    price: null,
    currency: 'CNY',
    storage_zone: 'fridge',
    added_date: '2026-11-20',
    auto_expiry_date: '2026-11-22',
    status: 'fresh',
    consumed_at: null,
    created_at: null,
    updated_at: null,
    canonical_name: canonicalName,
    days_left: daysLeft,
  }
}

describe('FridgePage knowledge link (Phase 4, F-09)', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) => {
        if (url.startsWith('/api/v2/households'))
          return Promise.resolve(jsonResponse([HOUSEHOLD]))
        if (url.startsWith('/api/v2/fridge')) {
          return Promise.resolve(
            jsonResponse([
              // Canonical name present -> the link uses it.
              fridgeItem('i-egg', '土鸡蛋', '鸡蛋', 1),
              // No canonical name -> the link falls back to the
              // display name.
              fridgeItem('i-milk', '牛奶', null, 5),
            ]),
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

  it('each row links to /knowledge?q=<canonical name or display name>', async () => {
    render(
      <MemoryRouter>
        <FridgePage />
      </MemoryRouter>,
    )
    // The row shows the canonical name (鸡蛋), not the raw name.
    await screen.findByText('鸡蛋')
    const links = screen.getAllByRole('link', { name: '查保质期' })
    expect(links).toHaveLength(2)
    expect(links[0].getAttribute('href')).toBe(
      '/knowledge?q=%E9%B8%A1%E8%9B%8B',
    )
    expect(links[1].getAttribute('href')).toBe(
      '/knowledge?q=%E7%89%9B%E5%A5%B6',
    )
  })
})
