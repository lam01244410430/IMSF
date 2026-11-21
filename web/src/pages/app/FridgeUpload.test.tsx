import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { FridgePage } from './Fridge'
import { UploadPage } from './Upload'

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

function fridgeItem(id: string, name: string, days_left: number | null) {
  return {
    id,
    household_id: HOUSEHOLD.id,
    receipt_id: null,
    receipt_line_id: null,
    raw_name: name,
    canonical_ingredient_id: null,
    quantity: 1,
    unit: '个',
    price: null,
    currency: 'CNY',
    storage_zone: 'fridge',
    added_date: '2026-11-20',
    auto_expiry_date: days_left === null ? null : '2026-11-22',
    status: 'fresh',
    consumed_at: null,
    created_at: null,
    updated_at: null,
    canonical_name: name,
    days_left,
  }
}

describe('FridgePage expiry chips', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) => {
        if (url.startsWith('/api/v2/households')) return Promise.resolve(jsonResponse([HOUSEHOLD]))
        if (url.startsWith('/api/v2/fridge')) {
          return Promise.resolve(
            jsonResponse([
              fridgeItem('i-expired', '牛奶', -2),
              fridgeItem('i-today', '鸡蛋', 0),
              fridgeItem('i-soon', '青菜', 2),
              fridgeItem('i-fresh', '大米', 10),
              fridgeItem('i-none', '盐', null),
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

  it('every chip carries icon + text, never colour alone', async () => {
    render(
      <MemoryRouter>
        <FridgePage />
      </MemoryRouter>,
    )
    // Expired, today, soon, fresh, no-expiry — all as text.
    expect(await screen.findByText('已过期 2 天')).toBeDefined()
    expect(screen.getByText('今天过期')).toBeDefined()
    expect(screen.getByText('还剩 2 天')).toBeDefined()
    expect(screen.getByText('还剩 10 天')).toBeDefined()
    expect(screen.getByText('无保质期')).toBeDefined()
    // Grouped by expiry: expired first.
    expect(screen.getByText('已过期（1）')).toBeDefined()
    expect(screen.getByText('快过期（3 天内）（2）')).toBeDefined()
    expect(screen.getByText('新鲜（1）')).toBeDefined()
    expect(screen.getByText('无保质期（1）')).toBeDefined()
    // Lazy Tracking 1-tap actions exist on every row.
    expect(screen.getAllByRole('button', { name: '已用完' })).toHaveLength(5)
    expect(screen.getAllByRole('button', { name: '再放三天' })).toHaveLength(5)
  })
})

describe('UploadPage scan-deferred state', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) => {
        if (url.startsWith('/api/v2/households')) return Promise.resolve(jsonResponse([HOUSEHOLD]))
        if (url.startsWith('/api/v2/receipts')) return Promise.resolve(jsonResponse([]))
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

  it('shows the honest notice and disables the capture actions', async () => {
    render(
      <MemoryRouter>
        <UploadPage />
      </MemoryRouter>,
    )
    expect(await screen.findByText(/小票自动识别功能暂未开启/)).toBeDefined()
    expect(screen.getByRole('button', { name: '拍照' })).toHaveProperty('disabled', true)
    expect(screen.getByRole('button', { name: '从相册选择' })).toHaveProperty('disabled', true)
    // No fake progress is shown.
    expect(screen.queryByText(/识别中/)).toBeNull()
    expect(screen.queryByText(/正在识别/)).toBeNull()
  })
})
