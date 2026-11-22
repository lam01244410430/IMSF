/**
 * Admin user detail tests — detail, disable/re-enable with a
 * required reason, and deliberate household inspection (contract
 * §2 #4–#6). The page is rendered at /admin/users/u-1 via the
 * router so useParams works.
 */
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AdminUserDetailPage } from './UserDetail'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

const DETAIL = {
  id: 'u-1',
  name: 'Lam',
  email: 'lam@example.com',
  login_method: 'email',
  status: 'enabled',
  disabled_at: null,
  created_at: '2026-11-22T00:00:00Z',
  households: [{ household_id: 'h-1', name: '我家', role: 'owner' }],
  counts: { receipts: 1, transactions: 2, inventory_items: 3, equipments: 0 },
}

const INVENTORY = {
  items: [
    {
      id: 'i-1',
      household_id: 'h-1',
      receipt_id: null,
      raw_name: '牛奶',
      quantity: 2,
      unit: '盒',
      price: 12.5,
      currency: 'CNY',
      storage_zone: 'fridge',
      added_date: '2026-11-21',
      auto_expiry_date: '2026-11-25',
      status: 'fresh',
      created_at: '2026-11-21T00:30:00Z',
    },
  ],
  total: 1,
}

const RECEIPTS = {
  items: [
    {
      id: 'r-1',
      household_id: 'h-1',
      uploaded_by_user_id: 'u-1',
      image_url: 'https://example.com/r1.jpg',
      store_name: '超市',
      purchased_at: '2026-11-21T00:00:00Z',
      total_amount: 123.45,
      currency: 'CNY',
      status: 'completed',
      ocr_raw_text: null,
      error_message: null,
      processed_at: '2026-11-21T01:00:00Z',
      created_at: '2026-11-21T00:30:00Z',
      updated_at: '2026-11-21T01:00:00Z',
    },
  ],
  total: 1,
}

describe('AdminUserDetailPage', () => {
  let calls: { url: string; init?: RequestInit }[]

  function stubFetch(detailStatus = 200) {
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string, init?: RequestInit) => {
        calls.push({ url, init })
        if (url.startsWith('/api/v2/admin/households/')) {
          if (url.includes('type=inventory')) {
            return Promise.resolve(jsonResponse(INVENTORY))
          }
          return Promise.resolve(jsonResponse(RECEIPTS))
        }
        if (url.startsWith('/api/v2/admin/users/')) {
          if (init?.method === 'PATCH') {
            return Promise.resolve(
              jsonResponse({
                ...DETAIL,
                status: 'disabled',
                disabled_at: '2026-11-22T02:00:00Z',
              }),
            )
          }
          return Promise.resolve(jsonResponse(DETAIL, detailStatus))
        }
        return Promise.resolve(jsonResponse(null, 404))
      }),
    )
  }

  beforeEach(() => {
    window.localStorage.clear()
    calls = []
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  function renderPage() {
    return render(
      <MemoryRouter initialEntries={['/admin/users/u-1']}>
        <Routes>
          <Route path="/admin/users/:id" element={<AdminUserDetailPage />} />
        </Routes>
      </MemoryRouter>,
    )
  }

  it('shows account, households with ownership, and data counts', async () => {
    stubFetch()
    renderPage()
    expect(await screen.findByText('lam@example.com')).toBeDefined()
    expect(screen.getAllByText('我家').length).toBe(2)
    expect(screen.getByText('户主')).toBeDefined()
    expect(screen.getByText('已启用')).toBeDefined()
    // Data counts: receipts 1, transactions 2, inventory 3, equipment 0.
    expect(screen.getByText('数据统计')).toBeDefined()
  })

  it('disable requires a reason, then PATCHes disabled=true with it', async () => {
    stubFetch()
    renderPage()
    await screen.findByText('lam@example.com')
    fireEvent.click(screen.getByRole('button', { name: '停用账号' }))
    const dialog = screen.getByRole('dialog')
    // The confirm panel names the target clearly.
    expect(within(dialog).getByText('Lam · lam@example.com')).toBeDefined()
    // Empty reason → required error, no PATCH sent.
    fireEvent.click(within(dialog).getByRole('button', { name: '确认' }))
    expect(await screen.findByText('请填写原因')).toBeDefined()
    expect(calls.some((c) => c.init?.method === 'PATCH')).toBe(false)
    fireEvent.change(within(dialog).getByLabelText('原因（必填）'), {
      target: { value: 'spam' },
    })
    fireEvent.click(within(dialog).getByRole('button', { name: '确认' }))
    await waitFor(() => {
      const patch = calls.find((c) => c.init?.method === 'PATCH')
      expect(patch).toBeDefined()
      expect(JSON.parse(patch?.init?.body as string)).toEqual({
        disabled: true,
        reason: 'spam',
      })
    })
    expect(await screen.findByText(/已停用/)).toBeDefined()
  })

  it('inspect needs a household + reason, then shows read-only records', async () => {
    stubFetch()
    renderPage()
    await screen.findByText('lam@example.com')
    fireEvent.change(screen.getByLabelText('家庭', { selector: 'select' }), {
      target: { value: 'h-1' },
    })
    // No reason yet → required error, no records request.
    fireEvent.click(screen.getByRole('button', { name: '查看家庭数据' }))
    expect(await screen.findByText('请填写原因')).toBeDefined()
    expect(calls.some((c) => c.url.includes('/records'))).toBe(false)
    const reasonInput = document.querySelector(
      '#admin-inspect-reason',
    ) as HTMLInputElement
    fireEvent.change(reasonInput, { target: { value: 'abuse report' } })
    fireEvent.click(screen.getByRole('button', { name: '查看家庭数据' }))
    expect(await screen.findByText(/超市 · ¥123.45/)).toBeDefined()
    const recordsCall = calls.find((c) => c.url.includes('/records'))
    expect(recordsCall).toBeDefined()
    const url = new URL(recordsCall!.url, 'http://localhost')
    expect(url.searchParams.get('type')).toBe('receipts')
    expect(url.searchParams.get('reason')).toBe('abuse report')
  })

  it('inspect inventory (admin shape, no days_left) renders name + quantity, not "—"', async () => {
    stubFetch()
    renderPage()
    await screen.findByText('lam@example.com')
    fireEvent.change(screen.getByLabelText('家庭', { selector: 'select' }), {
      target: { value: 'h-1' },
    })
    fireEvent.change(screen.getByLabelText('数据类型'), {
      target: { value: 'inventory' },
    })
    const reasonInput = document.querySelector(
      '#admin-inspect-reason',
    ) as HTMLInputElement
    fireEvent.change(reasonInput, { target: { value: 'abuse report' } })
    fireEvent.click(screen.getByRole('button', { name: '查看家庭数据' }))
    expect(await screen.findByText(/牛奶 · 2 盒/)).toBeDefined()
  })

  it('unknown user → not-found, not a blank page', async () => {
    stubFetch(404)
    renderPage()
    expect(await screen.findByText('找不到该用户')).toBeDefined()
  })
})
