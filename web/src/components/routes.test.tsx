import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AppRoutes } from '../App'
import { logout, resetAuthState, setTokens } from '../lib/auth'

function base64Url(obj: unknown): string {
  return btoa(JSON.stringify(obj))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '')
}

function fakeJwt(expSeconds: number): string {
  return `${base64Url({ alg: 'none' })}.${base64Url({ exp: expSeconds, sub: 'user-1' })}.sig`
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes />
    </MemoryRouter>,
  )
}

describe('/app redirect', () => {
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

  it('authenticated /app redirects to /app/dashboard (Dashboard Phase B, D1)', async () => {
    // Dashboard fetches on mount; stub every endpoint it calls.
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) => {
        const body = (data: unknown) =>
          new Response(JSON.stringify(data), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          })
        if (url.startsWith('/api/v2/households'))
          return Promise.resolve(
            body([
              {
                id: '11111111-1111-1111-1111-111111111111',
                name: '我家',
                default_currency: 'CNY',
                timezone: 'Asia/Shanghai',
                locale: 'zh-CN',
                created_at: null,
                role: 'owner',
              },
            ]),
          )
        if (url.startsWith('/api/v2/spending/summary'))
          return Promise.resolve(
            body({ currency: 'CNY', total: 0, by_category: [], by_month: [] }),
          )
        return Promise.resolve(body([]))
      }),
    )
    setTokens(fakeJwt(Math.floor(Date.now() / 1000) + 600), 'refresh-1')
    renderAt('/app')
    // Dashboard heading, not the upload page.
    expect(await screen.findByRole('heading', { name: '仪表盘' })).toBeDefined()
    // The heading renders before the fetch resolves — wait for the data.
    await waitFor(() =>
      expect(screen.getByText(/本月暂无支出/)).toBeDefined(),
    )
  })

  it('unauthenticated /app/maintenance → /login', () => {
    renderAt('/app/maintenance')
    expect(screen.getByRole('heading', { name: '登录' })).toBeDefined()
  })

  it('unauthenticated /app/receipts → /login', () => {
    renderAt('/app/receipts')
    expect(screen.getByRole('heading', { name: '登录' })).toBeDefined()
  })

  it('unauthenticated /knowledge → /login (endpoint needs auth)', () => {
    renderAt('/knowledge?q=%E9%B8%A1%E8%9B%8B')
    expect(screen.getByRole('heading', { name: '登录' })).toBeDefined()
  })

  it('unknown path → 404', () => {
    renderAt('/no-such-page')
    expect(screen.getByRole('heading', { name: '页面不存在' })).toBeDefined()
  })
})

function LocationProbe() {
  const location = useLocation()
  return <p data-testid="location">{location.pathname}</p>
}

function renderAtWithProbe(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes />
      <LocationProbe />
    </MemoryRouter>,
  )
}

describe('/recipes redirects (plan §10 Q9)', () => {
  beforeEach(() => {
    window.localStorage.clear()
    resetAuthState()
  })

  afterEach(() => {
    cleanup()
    logout()
  })

  it('/recipes redirects to /blog', async () => {
    renderAtWithProbe('/recipes')
    expect(await screen.findByRole('heading', { name: '菜谱' })).toBeDefined()
    expect(screen.getByTestId('location').textContent).toBe('/blog')
  })

  it('/app/recipes redirects to /blog without requiring login', async () => {
    renderAtWithProbe('/app/recipes')
    expect(await screen.findByRole('heading', { name: '菜谱' })).toBeDefined()
    expect(screen.getByTestId('location').textContent).toBe('/blog')
  })

  it('authenticated /app/recipes redirects to /blog too', async () => {
    setTokens(fakeJwt(Math.floor(Date.now() / 1000) + 600), 'refresh-1')
    renderAtWithProbe('/app/recipes')
    expect(await screen.findByRole('heading', { name: '菜谱' })).toBeDefined()
    expect(screen.getByTestId('location').textContent).toBe('/blog')
  })
})
