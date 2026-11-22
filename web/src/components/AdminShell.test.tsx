/**
 * Admin guard + shell tests — Dashboard Phase C (contract §5).
 * 401 → /login; 403 → a plain "no access" page that reveals nothing
 * about the admins; 200 → the admin shell with its banner, 5-page
 * sidebar and "Return to family app" link. Rendered through the
 * real AppRoutes so the routing itself is under test.
 */
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AppRoutes } from '../App'
import { logout, resetAuthState } from '../lib/auth'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

const ME = {
  user_id: 'u-1',
  name: 'Lam',
  email: 'lam@example.com',
  login_method: 'email',
  capabilities: ['users:read', 'users:write', 'recipes:write', 'audit:read', 'system:read'],
}

const STATS = {
  counts: {
    users: 2,
    households: 1,
    receipts: 0,
    transactions: 0,
    inventory_items: 0,
    published_recipes: 0,
    draft_recipes: 0,
    hidden_recipes: 0,
  },
  exceptions: { failed_receipt_jobs: 0, overdue_cron: false, unavailable_dependencies: [] },
}

describe('admin guard + shell', () => {
  beforeEach(() => {
    window.localStorage.clear()
    resetAuthState()
  })

  afterEach(() => {
    cleanup()
    logout()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  function stubFetch(meStatus: number, opts: { throwNetwork?: boolean } = {}) {
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) => {
        if (opts.throwNetwork) return Promise.reject(new Error('network down'))
        if (url.startsWith('/api/v2/admin/me'))
          return Promise.resolve(jsonResponse(ME, meStatus))
        if (url.startsWith('/api/v2/admin/stats'))
          return Promise.resolve(jsonResponse(STATS))
        if (url.startsWith('/api/v2/admin/users'))
          return Promise.resolve(jsonResponse({ items: [], total: 0 }))
        return Promise.resolve(jsonResponse(null, 404))
      }),
    )
  }

  function renderAt(path: string) {
    return render(
      <MemoryRouter initialEntries={[path]}>
        <AppRoutes />
      </MemoryRouter>,
    )
  }

  it('401 from /admin/me → /login', async () => {
    stubFetch(401)
    renderAt('/admin')
    // The login page's submit button (the heading shares the same
    // "登录" text, so the button role disambiguates).
    expect(await screen.findByRole('button', { name: '登录' })).toBeDefined()
    expect(screen.getByLabelText('邮箱')).toBeDefined()
  })

  it('403 from /admin/me → plain no-access page, no admin details', async () => {
    stubFetch(403)
    renderAt('/admin')
    expect(await screen.findByText('无权访问此页面。')).toBeDefined()
    expect(screen.getByText('如果你认为这是个错误，请联系系统管理员。')).toBeDefined()
    // The no-access page never names an admin or an allowlist.
    expect(document.body.textContent).not.toContain('IMSF_ADMIN_USER_IDS')
    expect(document.body.textContent).not.toContain('lam@example.com')
    // It still offers the way back to the family app.
    expect(screen.getByRole('link', { name: '返回家庭应用' })).toBeDefined()
  })

  it('admin → shell with persistent banner, 5 nav items, return link', async () => {
    stubFetch(200)
    renderAt('/admin')
    expect(await screen.findByText('暂无需要处理的问题')).toBeDefined()
    expect(screen.getByText('Admin / 管理后台')).toBeDefined()
    const nav = screen.getByRole('link', { name: '总览' })
    expect(nav.getAttribute('href')).toBe('/admin')
    expect(screen.getByRole('link', { name: '用户' }).getAttribute('href')).toBe(
      '/admin/users',
    )
    expect(screen.getByRole('link', { name: '菜谱' }).getAttribute('href')).toBe(
      '/admin/recipes',
    )
    expect(screen.getByRole('link', { name: '系统' }).getAttribute('href')).toBe(
      '/admin/system',
    )
    expect(screen.getByRole('link', { name: '操作记录' }).getAttribute('href')).toBe(
      '/admin/audit',
    )
    const back = screen.getByRole('link', { name: '返回家庭应用' })
    expect(back.getAttribute('href')).toBe('/app/dashboard')
  })

  it('admin → /admin/users renders the users page inside the shell', async () => {
    stubFetch(200)
    renderAt('/admin/users')
    expect(await screen.findByText('没有符合条件的用户')).toBeDefined()
    expect(screen.getByText('Admin / 管理后台')).toBeDefined()
  })

  it('network failure → load error with retry, not a redirect', async () => {
    stubFetch(200, { throwNetwork: true })
    renderAt('/admin')
    expect(await screen.findByText('加载失败，请检查网络后重试。')).toBeDefined()
    expect(screen.getByRole('button', { name: '重试' })).toBeDefined()
  })

  it('retry after failure re-calls /admin/me', async () => {
    let calls = 0
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) => {
        calls += 1
        if (calls === 1) return Promise.reject(new Error('network down'))
        if (url.startsWith('/api/v2/admin/me'))
          return Promise.resolve(jsonResponse(ME))
        if (url.startsWith('/api/v2/admin/stats'))
          return Promise.resolve(jsonResponse(STATS))
        return Promise.resolve(jsonResponse(null, 404))
      }),
    )
    renderAt('/admin')
    await screen.findByText('加载失败，请检查网络后重试。')
    fireEvent.click(screen.getByRole('button', { name: '重试' }))
    await waitFor(() =>
      expect(screen.queryByText('暂无需要处理的问题')).toBeDefined(),
    )
  })
})
