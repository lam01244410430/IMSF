/**
 * Admin Users tests — search / filters / pagination (contract §2 #3).
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AdminUsersPage } from './Users'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

const PAGE_1 = {
  items: [
    {
      id: 'u-1',
      name: 'Lam',
      email: 'lam@example.com',
      login_method: 'email',
      status: 'enabled',
      created_at: '2026-11-22T00:00:00Z',
    },
    {
      id: 'u-2',
      name: 'Bob',
      email: 'bob@example.com',
      login_method: 'wechat',
      status: 'disabled',
      created_at: '2026-11-21T00:00:00Z',
    },
  ],
  total: 21,
}

const PAGE_2 = {
  items: [
    {
      id: 'u-3',
      name: 'Carol',
      email: 'carol@example.com',
      login_method: 'email',
      status: 'enabled',
      created_at: '2026-11-20T00:00:00Z',
    },
  ],
  total: 21,
}

describe('AdminUsersPage', () => {
  let calls: string[]

  beforeEach(() => {
    window.localStorage.clear()
    calls = []
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) => {
        calls.push(url)
        if (url.startsWith('/api/v2/admin/users')) {
          const u = new URL(url, 'http://localhost')
          if (u.searchParams.get('offset') === '20')
            return Promise.resolve(jsonResponse(PAGE_2))
          return Promise.resolve(jsonResponse(PAGE_1))
        }
        return Promise.resolve(jsonResponse(null, 404))
      }),
    )
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  function renderPage() {
    return render(
      <MemoryRouter>
        <AdminUsersPage />
      </MemoryRouter>,
    )
  }

  it('lists users with login method, status and a detail link', async () => {
    renderPage()
    expect(await screen.findByText('lam@example.com')).toBeDefined()
    expect(screen.getByText('bob@example.com')).toBeDefined()
    // Status / method words also appear in the filter <option>s, so
    // scope the assertions to the table itself.
    const table = screen.getByRole('table')
    expect(within(table).getByText('已启用')).toBeDefined()
    expect(within(table).getByText('已停用')).toBeDefined()
    expect(within(table).getByText('WeChat')).toBeDefined()
    const link = screen.getByRole('link', { name: 'Lam' })
    expect(link.getAttribute('href')).toBe('/admin/users/u-1')
    // The list never exposes an openid.
    expect(document.body.textContent).not.toContain('openid')
  })

  it('search sends the exact q param and resets to page 1', async () => {
    renderPage()
    await screen.findByText('lam@example.com')
    fireEvent.change(screen.getByPlaceholderText('邮箱（精确）/ OpenID（精确）/ 姓名'), {
      target: { value: 'bob@example.com' },
    })
    fireEvent.click(screen.getByRole('button', { name: '搜索' }))
    await waitFor(() => {
      const url = new URL(calls[calls.length - 1], 'http://localhost')
      expect(url.searchParams.get('q')).toBe('bob@example.com')
      expect(url.searchParams.get('offset')).toBe('0')
    })
  })

  it('status filter sends status=disabled', async () => {
    renderPage()
    await screen.findByText('lam@example.com')
    fireEvent.change(screen.getByLabelText('状态'), {
      target: { value: 'disabled' },
    })
    await waitFor(() => {
      const url = new URL(calls[calls.length - 1], 'http://localhost')
      expect(url.searchParams.get('status')).toBe('disabled')
    })
  })

  it('next page requests offset=20 and shows page 2', async () => {
    renderPage()
    await screen.findByText('lam@example.com')
    fireEvent.click(screen.getByRole('button', { name: '下一页' }))
    expect(await screen.findByText('carol@example.com')).toBeDefined()
    expect(screen.queryByText('lam@example.com')).toBeNull()
    expect(screen.getByText('共 21 条')).toBeDefined()
  })

  it('empty result → honest empty state', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(jsonResponse({ items: [], total: 0 }))),
    )
    renderPage()
    expect(await screen.findByText('没有符合条件的用户')).toBeDefined()
  })
})
