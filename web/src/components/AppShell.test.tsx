import { cleanup, render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
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

function renderShell() {
  return render(
    <MemoryRouter initialEntries={['/app/upload']}>
      <AppShell />
    </MemoryRouter>,
  )
}

function topbarUserText(): string | null {
  return document.querySelector('.app-topbar-user')?.textContent ?? null
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
