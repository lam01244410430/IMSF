import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { AppShell } from './AppShell'
import {
  STORAGE_KEYS,
  resetAuthState,
  setStoredHouseholdId,
  setStoredHouseholdName,
  setStoredUserName,
  setTokens,
} from '../lib/auth'

function renderShell(initialEntries: string[] = ['/app/upload']) {
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <AppShell />
    </MemoryRouter>,
  )
}

/** The account button's visible name (desktop; hidden by CSS <768px). */
function topbarUserText(): string | null {
  return document.querySelector('.account-menu-name')?.textContent ?? null
}

/** Renders the current route pathname so navigation can be asserted. */
function LocationProbe() {
  const { pathname } = useLocation()
  return <div data-testid="location">{pathname}</div>
}

function renderShellWithProbe(initialEntries: string[] = ['/app/upload']) {
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <AppShell />
      <LocationProbe />
    </MemoryRouter>,
  )
}

function locationPath(): string | null {
  return screen.getByTestId('location').textContent
}

function accountButton(): HTMLElement {
  // The trigger's accessible name is the i18n account label
  // ('账户' / 'Tài khoản' / 'Account').
  return screen.getByRole('button', { name: /账户|Tài khoản|Account/ })
}

function openMenu() {
  fireEvent.click(accountButton())
  return screen.getByRole('menu')
}

describe('AppShell topbar display name (Phase 4)', () => {
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

  it('shows the stored display name', () => {
    setTokens('access-1', 'refresh-1')
    setStoredUserName('小明')
    renderShell()
    expect(topbarUserText()).toBe('小明')
  })

  it('missing name → email local part, never the full email', () => {
    setTokens('access-1', 'refresh-1')
    window.localStorage.setItem(STORAGE_KEYS.email, 'lam@example.com')
    renderShell()
    expect(topbarUserText()).toBe('lam')
  })

  it('logged in with nothing stored → plain 用户, no UUID', () => {
    setTokens('access-1', 'refresh-1')
    renderShell()
    expect(topbarUserText()).toBe('用户')
  })

  it('logged out with nothing stored → 未登录', () => {
    renderShell()
    expect(topbarUserText()).toBe('未登录')
  })

  it('sidebar footer shows the stored household name, never the id (Phase 4, F-06a)', () => {
    setTokens('access-1', 'refresh-1')
    setStoredHouseholdId('11111111-2222-3333-4444-555555555555')
    setStoredHouseholdName('我家')
    renderShell()
    expect(
      document.querySelector('.app-sidebar-footer')?.textContent,
    ).toBe('家庭 我家')
  })

  it('no household name stored → plain 家庭, no UUID (Phase 4, F-06a)', () => {
    setTokens('access-1', 'refresh-1')
    setStoredHouseholdId('11111111-2222-3333-4444-555555555555')
    renderShell()
    expect(
      document.querySelector('.app-sidebar-footer')?.textContent,
    ).toBe('家庭')
  })

  it('sidebar nav groups have distinct aria-labels (Phase 4, F-12)', () => {
    renderShell()
    const labels = Array.from(
      document.querySelectorAll('.app-sidebar-nav-group'),
    ).map((el) => el.getAttribute('aria-label'))
    expect(labels).toHaveLength(2)
    expect(new Set(labels).size).toBe(2)
    expect(labels).toContain('应用导航')
    expect(labels).toContain('记账导航')
  })

  it('never shows a UUID from the JWT', () => {
    // A real JWT whose sub is a UUID-like id; the topbar must not
    // render any part of it.
    const uuid = '11111111-2222-3333-4444-555555555555'
    const payload = btoa(JSON.stringify({ sub: uuid, exp: 9999999999 }))
      .replace(/\+/g, '-')
      .replace(/\//g, '_')
      .replace(/=+$/, '')
    setTokens(`header.${payload}.sig`, 'refresh-1')
    setStoredUserName('小明')
    renderShell()
    expect(topbarUserText()).toBe('小明')
    expect(topbarUserText()).not.toContain(uuid)
    expect(topbarUserText()).not.toContain('11111111')
  })
})

describe('AppShell sidebar (Dashboard Phase B, D1)', () => {
  beforeEach(() => {
    window.localStorage.clear()
    resetAuthState()
  })

  afterEach(() => {
    cleanup()
  })

  it('first nav item is 仪表盘 → /app/dashboard, no 首页 item, no duplicate 拍照 item', () => {
    setTokens('access-1', 'refresh-1')
    render(
      <MemoryRouter initialEntries={['/app/dashboard']}>
        <AppShell />
      </MemoryRouter>,
    )
    const sidebarLabels = Array.from(
      document.querySelectorAll('.sidebar-nav-item .nav-label'),
    ).map((el) => el.textContent)
    expect(sidebarLabels[0]).toBe('仪表盘')
    expect(sidebarLabels).not.toContain('首页')
    // /app/upload stays reachable via the sidebar 拍照 button + FAB.
    expect(
      document.querySelector('.app-sidebar-photo')?.textContent,
    ).toBe('拍照')
    expect(
      document.querySelector('.sidebar-nav-item[href="/app/dashboard"]'),
    ).not.toBeNull()
    expect(
      document.querySelector('.sidebar-nav-item[href="/app/upload"]'),
    ).toBeNull()
    // Bottom nav mirrors NAV_GROUP_1: 仪表盘 first on mobile too.
    const bottomLabels = Array.from(
      document.querySelectorAll('.app-bottomnav-item span'),
    ).map((el) => el.textContent)
    expect(bottomLabels[0]).toBe('仪表盘')
    expect(bottomLabels).not.toContain('首页')
  })
})

describe('AppShell account menu (header feature, Lam 2026-11-22)', () => {
  beforeEach(() => {
    window.localStorage.clear()
    resetAuthState()
  })

  afterEach(() => {
    cleanup()
  })

  it('button shows the account icon + stored name, starts closed', () => {
    setTokens('access-1', 'refresh-1')
    setStoredUserName('小明')
    renderShell()
    const button = accountButton()
    expect(button.getAttribute('aria-expanded')).toBe('false')
    expect(button.getAttribute('aria-haspopup')).toBe('menu')
    expect(screen.queryByRole('menu')).toBeNull()
    // The 'mine' account icon, not just text. (Vite inlines small
    // SVGs as data URIs in tests, so assert on the mine icon's
    // distinctive body path — the person silhouette — not a filename.)
    const use = button.querySelector('use')
    expect(use).not.toBeNull()
    expect(use?.getAttribute('href')).toContain('M4.5%2020.5a7.5')
    expect(button.textContent).toContain('小明')
  })

  it('click opens the menu with name + email, 我的 link and logout', () => {
    setTokens('access-1', 'refresh-1')
    setStoredUserName('小明')
    window.localStorage.setItem(STORAGE_KEYS.email, 'lam@example.com')
    renderShell()
    const panel = openMenu()
    expect(accountButton().getAttribute('aria-expanded')).toBe('true')
    expect(panel.textContent).toContain('小明')
    expect(panel.textContent).toContain('lam@example.com')
    expect(
      screen.getByRole('menuitem', { name: '我的' }),
    ).toHaveProperty('href')
    expect(
      screen.getByRole('menuitem', { name: '我的' }).getAttribute('href'),
    ).toBe('/app/mine')
    expect(screen.getByRole('menuitem', { name: '退出' })).toBeTruthy()
  })

  it('Escape closes the menu and returns focus to the trigger', () => {
    setTokens('access-1', 'refresh-1')
    setStoredUserName('小明')
    renderShell()
    openMenu()
    const items = screen.getAllByRole('menuitem')
    fireEvent.keyDown(items[0] as HTMLElement, { key: 'Escape' })
    expect(screen.queryByRole('menu')).toBeNull()
    expect(document.activeElement).toBe(accountButton())
  })

  it('pointerdown outside closes the menu', () => {
    setTokens('access-1', 'refresh-1')
    setStoredUserName('小明')
    renderShell()
    openMenu()
    fireEvent.pointerDown(document.body)
    expect(screen.queryByRole('menu')).toBeNull()
  })

  it('ArrowDown opens and focuses the first item, then moves and wraps', () => {
    setTokens('access-1', 'refresh-1')
    setStoredUserName('小明')
    renderShell()
    accountButton().focus()
    fireEvent.keyDown(accountButton(), { key: 'ArrowDown' })
    const items = screen.getAllByRole('menuitem')
    expect(items).toHaveLength(2)
    expect(document.activeElement).toBe(items[0])
    fireEvent.keyDown(items[0] as HTMLElement, { key: 'ArrowDown' })
    expect(document.activeElement).toBe(items[1])
    fireEvent.keyDown(items[1] as HTMLElement, { key: 'ArrowDown' })
    expect(document.activeElement).toBe(items[0])
  })

  it('ArrowUp moves up, Home jumps to first, End jumps to last', () => {
    setTokens('access-1', 'refresh-1')
    setStoredUserName('小明')
    renderShell()
    openMenu()
    const items = screen.getAllByRole('menuitem')
    fireEvent.keyDown(items[0] as HTMLElement, { key: 'End' })
    expect(document.activeElement).toBe(items[1])
    fireEvent.keyDown(items[1] as HTMLElement, { key: 'ArrowUp' })
    expect(document.activeElement).toBe(items[0])
    fireEvent.keyDown(items[0] as HTMLElement, { key: 'Home' })
    expect(document.activeElement).toBe(items[0])
  })

  it('logout clears the stored auth and navigates to /', () => {
    setTokens('access-1', 'refresh-1')
    setStoredUserName('小明')
    renderShellWithProbe(['/app/dashboard'])
    expect(locationPath()).toBe('/app/dashboard')
    openMenu()
    fireEvent.click(screen.getByRole('menuitem', { name: '退出' }))
    expect(window.localStorage.getItem(STORAGE_KEYS.access)).toBeNull()
    expect(window.localStorage.getItem(STORAGE_KEYS.refresh)).toBeNull()
    expect(window.localStorage.getItem(STORAGE_KEYS.userName)).toBeNull()
    expect(locationPath()).toBe('/')
  })

  it('我的 link navigates to /app/mine and closes the menu', () => {
    setTokens('access-1', 'refresh-1')
    setStoredUserName('小明')
    renderShellWithProbe(['/app/dashboard'])
    openMenu()
    fireEvent.click(screen.getByRole('menuitem', { name: '我的' }))
    expect(screen.queryByRole('menu')).toBeNull()
    expect(locationPath()).toBe('/app/mine')
  })

  it('logged out: button shows 未登录 + icon; menu offers only Log in / Register', () => {
    renderShell()
    const button = accountButton()
    expect(button.textContent).toContain('未登录')
    expect(button.querySelector('use')?.getAttribute('href')).toContain(
      'M4.5%2020.5a7.5',
    )
    openMenu()
    const items = screen.getAllByRole('menuitem')
    expect(items).toHaveLength(2)
    expect(
      screen.getByRole('menuitem', { name: '登录' }).getAttribute('href'),
    ).toBe('/login')
    expect(
      screen.getByRole('menuitem', { name: '注册' }).getAttribute('href'),
    ).toBe('/register')
    expect(screen.queryByRole('menuitem', { name: '退出' })).toBeNull()
  })
})
