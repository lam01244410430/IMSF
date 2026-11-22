import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MinePage } from './Mine'
import {
  STORAGE_KEYS,
  resetAuthState,
  setStoredUserName,
  setTokens,
} from '../../lib/auth'

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

describe('MinePage display name (Phase 4, F-06b)', () => {
  beforeEach(() => {
    window.localStorage.clear()
    resetAuthState()
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) => {
        if (url.startsWith('/api/v2/households'))
          return Promise.resolve(jsonResponse([HOUSEHOLD]))
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
        <MinePage />
      </MemoryRouter>,
    )
  }

  it('shows the stored display name, never the raw user id', async () => {
    const uuid = '11111111-2222-3333-4444-555555555555'
    const payload = btoa(JSON.stringify({ sub: uuid, exp: 9999999999 }))
      .replace(/\+/g, '-')
      .replace(/\//g, '_')
      .replace(/=+$/, '')
    setTokens(`header.${payload}.sig`, 'refresh-1')
    setStoredUserName('小明')
    renderPage()
    expect(await screen.findByText('小明')).toBeDefined()
    expect(document.body.textContent).not.toContain(uuid)
    expect(document.body.textContent).not.toContain('11111111')
  })

  it('admin link hidden when /admin/me is not an admin (404 stub)', async () => {
    setTokens('access-1', 'refresh-1')
    window.localStorage.setItem(STORAGE_KEYS.email, 'lam@example.com')
    renderPage()
    await screen.findByText('lam@example.com')
    expect(screen.queryByRole('link', { name: '管理后台' })).toBeNull()
  })

  it('missing name → email local part, never the full email or a UUID', async () => {
    setTokens('access-1', 'refresh-1')
    window.localStorage.setItem(STORAGE_KEYS.email, 'lam@example.com')
    renderPage()
    expect(await screen.findByText('lam')).toBeDefined()
    // The 用户 row shows the local part; the 邮箱 row still shows the
    // full address (that is its own field, not a leak).
    const values = Array.from(
      document.querySelectorAll('.mine-list dd'),
    ).map((el) => el.textContent)
    expect(values[0]).toBe('lam')
    expect(values[1]).toBe('lam@example.com')
  })
})

describe('MinePage admin link (Dashboard Phase C, contract §5)', () => {
  beforeEach(() => {
    window.localStorage.clear()
    resetAuthState()
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  function stubFetch(meStatus: number) {
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) => {
        if (url.startsWith('/api/v2/households'))
          return Promise.resolve(jsonResponse([HOUSEHOLD]))
        if (url.startsWith('/api/v2/admin/me'))
          return Promise.resolve(
            jsonResponse(
              {
                user_id: 'u-1',
                name: 'Lam',
                email: 'lam@example.com',
                login_method: 'email',
                capabilities: ['users:read'],
              },
              meStatus,
            ),
          )
        return Promise.resolve(jsonResponse(null, 404))
      }),
    )
  }

  function renderPage() {
    return render(
      <MemoryRouter>
        <MinePage />
      </MemoryRouter>,
    )
  }

  it('admin → "管理后台" link to /admin is shown', async () => {
    stubFetch(200)
    setTokens('access-1', 'refresh-1')
    window.localStorage.setItem(STORAGE_KEYS.email, 'lam@example.com')
    renderPage()
    const link = await screen.findByRole('link', { name: '管理后台' })
    expect(link.getAttribute('href')).toBe('/admin')
  })

  it('non-admin (403) → no "管理后台" link', async () => {
    stubFetch(403)
    setTokens('access-1', 'refresh-1')
    window.localStorage.setItem(STORAGE_KEYS.email, 'lam@example.com')
    renderPage()
    await screen.findByText('lam@example.com')
    expect(screen.queryByRole('link', { name: '管理后台' })).toBeNull()
  })
})
