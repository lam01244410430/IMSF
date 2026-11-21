import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
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
  })

  it('authenticated /app redirects to /app/upload', () => {
    setTokens(fakeJwt(Math.floor(Date.now() / 1000) + 600), 'refresh-1')
    renderAt('/app')
    // Upload page heading + honest scan notice.
    expect(screen.getByRole('heading', { name: '拍照' })).toBeDefined()
    expect(screen.getByText(/小票自动识别功能暂未开启/)).toBeDefined()
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
