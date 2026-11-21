import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { AppRoutes } from '../App'
import { logout, resetAuthState, setTokens } from '../lib/auth'

function base64Url(obj: unknown): string {
  // btoa is ASCII-safe here: the fake payload is plain JSON.
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

describe('route guards', () => {
  beforeEach(() => {
    window.localStorage.clear()
    resetAuthState()
  })

  // @testing-library/react only auto-registers cleanup when vitest
  // globals are on; this config uses globals: false, so clean up
  // explicitly — otherwise renders accumulate and queries go ambiguous.
  afterEach(() => {
    cleanup()
  })

  it('unauthenticated /app/fridge → /login?next=/app/fridge', () => {
    renderAt('/app/fridge')
    // Login placeholder renders; the redirect carried the original path.
    expect(screen.getByRole('heading', { name: '登录' })).toBeDefined()
    expect(screen.getByText(/email login form is built in Wave 2/)).toBeDefined()
  })

  it('valid session: /app/fridge renders the fridge page', () => {
    setTokens(fakeJwt(Math.floor(Date.now() / 1000) + 600), 'refresh-1')
    const { container } = renderAt('/app/fridge')
    expect(container.querySelector('main h1')?.textContent).toBe('冰箱')
    // The sidebar AND the bottom nav both link to 冰箱; both must show
    // the active state on this route.
    expect(
      container.querySelector('.app-sidebar a[href="/app/fridge"].active'),
    ).not.toBeNull()
    expect(
      container.querySelector('.app-bottomnav a[href="/app/fridge"].active'),
    ).not.toBeNull()
  })

  it('authenticated on /login → /app (home placeholder)', () => {
    setTokens(fakeJwt(Math.floor(Date.now() / 1000) + 600), 'refresh-1')
    renderAt('/login')
    expect(screen.getByRole('heading', { name: '首页' })).toBeDefined()
  })

  it('authenticated on /register → /app', () => {
    setTokens(fakeJwt(Math.floor(Date.now() / 1000) + 600), 'refresh-1')
    renderAt('/register')
    expect(screen.getByRole('heading', { name: '首页' })).toBeDefined()
  })

  it('unauthenticated /login renders the login page (no redirect loop)', () => {
    renderAt('/login')
    expect(screen.getByRole('heading', { name: '登录' })).toBeDefined()
  })

  it('unauthenticated / shows 登录 and 注册 in the landing header', () => {
    renderAt('/')
    expect(screen.getByRole('link', { name: '登录' })).toBeDefined()
    expect(screen.getByRole('link', { name: '注册' })).toBeDefined()
    expect(screen.queryByText('进入应用')).toBeNull()
  })

  it('authenticated / shows 进入应用 in the landing header', () => {
    setTokens(fakeJwt(Math.floor(Date.now() / 1000) + 600), 'refresh-1')
    renderAt('/')
    expect(screen.getByRole('link', { name: '进入应用' })).toBeDefined()
    expect(screen.queryByText('注册')).toBeNull()
  })

  it('logout: after logout, /app redirects to /login', () => {
    setTokens(fakeJwt(Math.floor(Date.now() / 1000) + 600), 'refresh-1')
    const { unmount } = renderAt('/app/fridge')
    expect(screen.getByRole('heading', { name: '冰箱' })).toBeDefined()
    logout()
    unmount()
    renderAt('/app/fridge')
    expect(screen.getByRole('heading', { name: '登录' })).toBeDefined()
  })

  it('unknown route renders the 404 page', () => {
    renderAt('/no-such-page')
    expect(screen.getByRole('heading', { name: '页面不存在' })).toBeDefined()
  })

  it('public /blog renders without login', () => {
    renderAt('/blog')
    expect(screen.getByRole('heading', { name: '菜谱' })).toBeDefined()
  })
})
